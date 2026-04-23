#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2023 Daniel Rodriguez
#
# pytest-style tests for backtrader.analyzers.resultexporter.
#
# These tests write a small SQLite DB by driving ResultStore manually
# (same fake-strategy approach used in test_analyzer_resultstore.py),
# then verify the JSON exporter emits a document that (a) has the
# required top-level keys and (b) validates against the published
# JSON schema when ``jsonschema`` is installed.
###############################################################################
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import json
import os
import sys
import types

import pytest


# Make repository root importable when running pytest from any directory
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backtrader.analyzers.resultstore import ResultStore  # noqa: E402
from backtrader.analyzers.resultexporter import (  # noqa: E402
    SCHEMA_PATH,
    SCHEMA_VERSION,
    export_run_to_dict,
    export_run_to_json,
)
from backtrader.metabase import ItemCollection  # noqa: E402


# ---------------------------------------------------------------------------
# Test fixtures (mirrors test_analyzer_resultstore.py deliberately so the
# two test files stay in lock-step).
# ---------------------------------------------------------------------------


class _FakeBroker(object):
    def __init__(self, startingcash=100000.0, endingvalue=110000.0):
        self.startingcash = startingcash
        self._ending = endingvalue

    def getvalue(self):
        return self._ending


class _FakeStrategy(object):
    def __init__(self):
        self.broker = _FakeBroker()
        self.analyzers = ItemCollection()


class _FakeTrade(object):
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
    def __init__(self, analysis):
        self._analysis = analysis

    def get_analysis(self):
        return self._analysis


def _make_store(tmp_path, **params):
    db_path = str(tmp_path / 'results.sqlite')
    store = ResultStore.__new__(ResultStore)

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
    strategy.analyzers.append(store, 'resultstore')

    store.create_analysis()
    return store, strategy, db_path


def _write_sample_run(tmp_path, run_label='sample-run'):
    '''Drive a ResultStore lifecycle with one sibling analyzer and two
    trades. Returns ``(db_path, run_id)``.'''
    store, strategy, db_path = _make_store(tmp_path, run_label=run_label)

    analysis = {
        'sharpe': {'ratio': 1.25, 'meta': {'bars': 250}},
        'drawdown': {'max': 0.12, 'len': 7},
        'note': 'hello',
    }
    strategy.analyzers.append(_FakeAnalyzer(analysis), 'sharpe')

    store.start()
    store.notify_trade(_FakeTrade(ref=1))
    store.notify_trade(_FakeTrade(ref=2, size=5, price=99.5))
    store.stop()

    return db_path, store.run_id


def _write_empty_run(tmp_path, run_label='empty-run'):
    '''ResultStore run with no sibling analyzers and no trades.'''
    store, _, db_path = _make_store(tmp_path, run_label=run_label)
    store.start()
    store.stop()
    return db_path, store.run_id


# ---------------------------------------------------------------------------
# 1. top-level keys
# ---------------------------------------------------------------------------

def test_roundtrip_dict_has_required_keys(tmp_path):
    db_path, run_id = _write_sample_run(tmp_path)

    doc = export_run_to_dict(db_path, run_id)

    assert set(doc.keys()) == {'schema_version', 'run', 'metrics', 'trades'}
    assert doc['schema_version'] == SCHEMA_VERSION
    assert doc['run']['run_id'] == run_id
    assert doc['run']['label'] == 'sample-run'
    # sibling analyzer produced at least 4 flattened keys
    assert len(doc['metrics']) >= 4
    metric_keys = {(m['analyzer'], m['key']) for m in doc['metrics']}
    assert ('_FakeAnalyzer', 'sharpe.ratio') in metric_keys
    # two trades were recorded
    assert len(doc['trades']) == 2
    refs = sorted(t['trade_ref'] for t in doc['trades'])
    assert refs == [1, 2]

    # export_run_to_json should round-trip when no out_path is given
    text = export_run_to_json(db_path, run_id)
    reparsed = json.loads(text)
    assert reparsed['run']['run_id'] == run_id

    # writing to disk returns the path
    out_path = str(tmp_path / 'out.json')
    returned = export_run_to_json(db_path, run_id, out_path)
    assert returned == out_path
    assert os.path.exists(out_path)
    with open(out_path, 'r', encoding='utf-8') as fh:
        on_disk = json.load(fh)
    assert on_disk['run']['run_id'] == run_id


# ---------------------------------------------------------------------------
# 2. schema validation (optional — skipped gracefully when jsonschema absent)
# ---------------------------------------------------------------------------

def test_schema_validates(tmp_path):
    jsonschema = pytest.importorskip('jsonschema')

    assert os.path.exists(SCHEMA_PATH), (
        'result_v1.json schema missing at {0}'.format(SCHEMA_PATH))
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as fh:
        schema = json.load(fh)

    db_path, run_id = _write_sample_run(tmp_path)
    doc = export_run_to_dict(db_path, run_id)

    # jsonschema.validate raises on failure; pass-through is green
    jsonschema.validate(instance=doc, schema=schema)


# ---------------------------------------------------------------------------
# 3. empty run still valid
# ---------------------------------------------------------------------------

def test_empty_run_still_valid(tmp_path):
    db_path, run_id = _write_empty_run(tmp_path)

    doc = export_run_to_dict(db_path, run_id)
    assert doc['schema_version'] == SCHEMA_VERSION
    assert doc['run']['run_id'] == run_id
    assert doc['metrics'] == []
    assert doc['trades'] == []

    jsonschema = pytest.importorskip('jsonschema')
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as fh:
        schema = json.load(fh)
    jsonschema.validate(instance=doc, schema=schema)


# ---------------------------------------------------------------------------
# 4. missing run_id raises LookupError (bonus guard)
# ---------------------------------------------------------------------------

def test_unknown_run_id_raises(tmp_path):
    db_path, _ = _write_sample_run(tmp_path)
    with pytest.raises(LookupError):
        export_run_to_dict(db_path, 'does-not-exist')
