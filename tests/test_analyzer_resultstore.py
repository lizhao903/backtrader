#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2023 Daniel Rodriguez
#
# pytest-style tests for backtrader.analyzers.ResultStore.
#
# These tests exercise ResultStore in isolation (no Cerebro) by driving
# its lifecycle manually against a fake strategy that exposes the bits
# ResultStore touches (``analyzers`` ItemCollection + a fake broker).
# That keeps the tests fast, deterministic, and free of the full
# backtrader runtime.
###############################################################################
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import sqlite3
import sys
import types

import pytest

# Make repository root importable when running pytest from any directory
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backtrader.analyzers.resultstore import ResultStore, _flatten  # noqa: E402
from backtrader.metabase import ItemCollection  # noqa: E402


class _FakeBroker(object):
    def __init__(self, startingcash=100000.0, endingvalue=110000.0):
        self.startingcash = startingcash
        self._ending = endingvalue

    def getvalue(self):
        return self._ending


class _FakeStrategy(object):
    '''Minimal stand-in for bt.Strategy that exposes everything ResultStore
    reads from ``self.strategy`` during ``start()`` / ``stop()``.'''

    def __init__(self):
        self.broker = _FakeBroker()
        self.analyzers = ItemCollection()


class _FakeTrade(object):
    '''Stand-in for bt.Trade with only the fields ResultStore.notify_trade
    reads.'''

    # mirror the Trade class status constants
    Created, Open, Closed = 0, 1, 2

    def __init__(self, ref, size=10, price=100.0, pnl=50.0, pnlcomm=45.0,
                 commission=5.0, data_name='yhoo',
                 open_iso='2024-01-02T00:00:00',
                 close_iso='2024-01-10T00:00:00'):
        self.ref = ref
        self.status = self.Closed
        self.size = size
        self.price = price
        self.pnl = pnl
        self.pnlcomm = pnlcomm
        self.commission = commission
        self._data_name = data_name
        self._open_iso = open_iso
        self._close_iso = close_iso

    def getdataname(self):
        return self._data_name

    def open_datetime(self):
        import datetime as _dt
        return _dt.datetime.fromisoformat(self._open_iso)

    def close_datetime(self):
        import datetime as _dt
        return _dt.datetime.fromisoformat(self._close_iso)


class _FakeAnalyzer(object):
    '''Sibling analyzer stub. ResultStore only needs ``get_analysis()``
    and the class name to key metrics.'''

    def __init__(self, analysis):
        self._analysis = analysis

    def get_analysis(self):
        return self._analysis


def _make_store(tmp_path, **params):
    '''Build a ResultStore wired to a fake strategy without going through
    the MetaAnalyzer machinery.'''
    db_path = str(tmp_path / 'results.sqlite')
    store = ResultStore.__new__(ResultStore)

    # Minimal params container matching backtrader's self.p.<name> access.
    # ResultStore only reads params, never mutates them.
    defaults = {
        'db_path': db_path,
        'run_label': None,
        'include_trades': True,
        'include_equity_curve': False,
    }
    defaults.update(params)
    store.p = types.SimpleNamespace(**defaults)

    strategy = _FakeStrategy()
    store.strategy = strategy
    # ResultStore participates in the sibling enumeration; register it
    # so the "skip self" branch is exercised too.
    strategy.analyzers.append(store, 'resultstore')

    store.create_analysis()
    return store, strategy, db_path


# ---------------------------------------------------------------------------
# 1. schema
# ---------------------------------------------------------------------------

def test_schema_created(tmp_path):
    store, _, db_path = _make_store(tmp_path)
    store.start()

    assert os.path.exists(db_path)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' ORDER BY name"
        ).fetchall()
    finally:
        conn.close()

    names = {r[0] for r in rows}
    assert {'backtest_run', 'backtest_metric', 'backtest_trade'}.issubset(names)


# ---------------------------------------------------------------------------
# 2. flattening of nested analyzer output
# ---------------------------------------------------------------------------

def test_metric_flatten_nested(tmp_path):
    store, strategy, db_path = _make_store(tmp_path)

    nested = {
        'sharpe': {'ratio': 1.5, 'meta': {'bars': 250}},
        'drawdown': {'max': 0.12, 'len': 7},
        'flag_ok': True,
        'note': 'run-1',
    }
    strategy.analyzers.append(_FakeAnalyzer(nested), 'sharpe')

    store.start()
    store.stop()

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT analyzer, key, value_num, value_text "
            "FROM backtest_metric WHERE run_id = ? "
            "ORDER BY key",
            (store.run_id,),
        ).fetchall()
    finally:
        conn.close()

    index = {(a, k): (n, t) for (a, k, n, t) in rows}

    # Nested numeric dot-paths
    assert ('_FakeAnalyzer', 'sharpe.ratio') in index
    assert index[('_FakeAnalyzer', 'sharpe.ratio')][0] == pytest.approx(1.5)
    assert ('_FakeAnalyzer', 'sharpe.meta.bars') in index
    assert index[('_FakeAnalyzer', 'sharpe.meta.bars')][0] == pytest.approx(250)
    assert ('_FakeAnalyzer', 'drawdown.max') in index
    assert index[('_FakeAnalyzer', 'drawdown.max')][0] == pytest.approx(0.12)

    # Bool goes to value_num (True -> 1.0)
    assert ('_FakeAnalyzer', 'flag_ok') in index
    assert index[('_FakeAnalyzer', 'flag_ok')][0] == pytest.approx(1.0)

    # String goes to value_text (JSON-encoded)
    assert ('_FakeAnalyzer', 'note') in index
    assert index[('_FakeAnalyzer', 'note')][1] == '"run-1"'


# ---------------------------------------------------------------------------
# 3. trades are recorded
# ---------------------------------------------------------------------------

def test_trade_recorded(tmp_path):
    store, _, db_path = _make_store(tmp_path)
    store.start()

    trade = _FakeTrade(ref=42, size=10, price=123.45,
                       pnl=50.0, pnlcomm=45.0, commission=5.0,
                       data_name='yhoo')
    store.notify_trade(trade)

    # Trades still in Open state should not be recorded.
    open_trade = _FakeTrade(ref=43)
    open_trade.status = open_trade.Open
    store.notify_trade(open_trade)

    store.stop()

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT trade_ref, data_name, size, price, pnl, pnlcomm, "
            "commission, open_dt, close_dt "
            "FROM backtest_trade WHERE run_id = ?",
            (store.run_id,),
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    ref, data_name, size, price, pnl, pnlcomm, comm, odt, cdt = rows[0]
    assert ref == 42
    assert data_name == 'yhoo'
    assert size == pytest.approx(10)
    assert price == pytest.approx(123.45)
    assert pnl == pytest.approx(50.0)
    assert pnlcomm == pytest.approx(45.0)
    assert comm == pytest.approx(5.0)
    assert odt == '2024-01-02T00:00:00'
    assert cdt == '2024-01-10T00:00:00'

    # get_analysis summary
    summary = store.get_analysis()
    assert summary['trade_count'] == 1
    assert summary['run_id'] == store.run_id


# ---------------------------------------------------------------------------
# 4. idempotent re-run: same run_id, stop() called twice should not duplicate
# ---------------------------------------------------------------------------

def test_idempotent_rerun(tmp_path):
    store, strategy, db_path = _make_store(tmp_path)
    strategy.analyzers.append(
        _FakeAnalyzer({'sharpe': {'ratio': 1.25}}), 'sharpe')

    store.start()
    store.notify_trade(_FakeTrade(ref=1))
    store.notify_trade(_FakeTrade(ref=2))
    store.stop()

    def _counts():
        conn = sqlite3.connect(db_path)
        try:
            r = conn.execute(
                "SELECT COUNT(*) FROM backtest_run WHERE run_id=?",
                (store.run_id,)).fetchone()[0]
            m = conn.execute(
                "SELECT COUNT(*) FROM backtest_metric WHERE run_id=?",
                (store.run_id,)).fetchone()[0]
            t = conn.execute(
                "SELECT COUNT(*) FROM backtest_trade WHERE run_id=?",
                (store.run_id,)).fetchone()[0]
            return r, m, t
        finally:
            conn.close()

    first = _counts()
    assert first[0] == 1      # one run row
    assert first[1] >= 1      # at least one metric row
    assert first[2] == 2      # two trades

    # Call stop() again with the same run_id -- counts must not grow.
    store.stop()
    second = _counts()
    assert second == first


# ---------------------------------------------------------------------------
# bonus: _flatten unit-level tests for the helper
# ---------------------------------------------------------------------------

def test_flatten_skips_none_and_handles_collections():
    out = []
    _flatten('', {'a': None, 'b': [1, 2], 'c': {'d': 3}}, out)
    keys = {k for (k, _, _) in out}
    assert 'a' not in keys          # None skipped
    assert 'b' in keys              # list JSON-encoded
    assert 'c.d' in keys            # nested dict flattened
    by_key = {k: (n, t) for (k, n, t) in out}
    assert by_key['c.d'][0] == pytest.approx(3.0)
    assert by_key['b'][1] == '[1, 2]'
