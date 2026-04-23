#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2023 Daniel Rodriguez
#
# pytest-style tests for backtrader.analyzers.htmlreport.
#
# These tests drive a minimal ResultStore lifecycle (same fake-strategy
# approach used in test_result_exporter.py), then render an HTML report
# and verify:
#   - the file is self-contained and contains the expected content
#   - rendering still works when plotly is unavailable (degraded mode)
#   - empty runs render without crashing
#   - unknown run ids raise LookupError (bubbled up from the exporter)
###############################################################################
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import sys
import types

import pytest


# Make repository root importable when running pytest from any directory
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# Skip the whole module if Jinja2 is missing — render_report requires it.
pytest.importorskip('jinja2')

from backtrader.analyzers.resultstore import ResultStore  # noqa: E402
from backtrader.analyzers.htmlreport import render_report  # noqa: E402
from backtrader.metabase import ItemCollection  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures (mirror test_result_exporter.py deliberately).
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
    store, strategy, db_path = _make_store(tmp_path, run_label=run_label)

    analysis = {
        'sharpe': {'ratio': 1.25, 'meta': {'bars': 250}},
        'drawdown': {'max': {'drawdown': 0.12, 'len': 7}, 'moneydown': 1234.5},
        'note': 'hello',
    }
    strategy.analyzers.append(_FakeAnalyzer(analysis), 'sharpe')

    store.start()
    store.notify_trade(_FakeTrade(ref=1))
    store.notify_trade(_FakeTrade(ref=2, size=5, price=99.5, pnl=-20.0,
                                  pnlcomm=-25.0))
    store.stop()

    return db_path, store.run_id


def _write_empty_run(tmp_path, run_label='empty-run'):
    store, _, db_path = _make_store(tmp_path, run_label=run_label)
    store.start()
    store.stop()
    return db_path, store.run_id


# ---------------------------------------------------------------------------
# 1. Renders a self-contained offline HTML report.
# ---------------------------------------------------------------------------

def test_renders_offline_html(tmp_path):
    db_path, run_id = _write_sample_run(tmp_path)
    out_path = str(tmp_path / 'report.html')

    returned = render_report(db_path, run_id, out_path)

    assert returned == os.path.abspath(out_path)
    assert os.path.exists(out_path)

    size = os.path.getsize(out_path)
    assert size > 1024, (
        'expected report to be > 1 KB, got {0} bytes'.format(size))

    with open(out_path, 'r', encoding='utf-8') as fh:
        body = fh.read()

    assert '<html>' in body.lower()
    # the actual run_id should be present in the body (not the literal
    # template placeholder)
    assert run_id in body
    assert '{{ run.run_id }}' not in body
    # expected major sections
    assert 'Backtest Report' in body
    assert 'Metrics' in body
    assert 'Trades' in body
    # self-contained: should NOT load plotly via an external <script src=>.
    # (plotly's inlined bundle embeds the literal string "cdn.plot.ly" as
    # data somewhere, so we check for the script-src pattern instead.)
    import re
    assert not re.search(r'<script[^>]+src=["\'][^"\']*cdn\.plot', body), (
        'report should not reference plotly via an external CDN src'
    )


def test_renders_offline_html_has_plotly_inlined(tmp_path):
    pytest.importorskip('plotly')
    db_path, run_id = _write_sample_run(tmp_path)
    out_path = str(tmp_path / 'report.html')

    render_report(db_path, run_id, out_path)
    with open(out_path, 'r', encoding='utf-8') as fh:
        body = fh.read()
    # plotly.js inlined into the page (script tag + function bootstrap)
    assert 'Plotly' in body


# ---------------------------------------------------------------------------
# 2. Works when plotly is unavailable (graceful degradation).
# ---------------------------------------------------------------------------

def test_works_without_plotly(tmp_path, monkeypatch):
    # Block plotly imports at the module level so htmlreport's lazy
    # `import plotly...` fails even if the package is installed in the env.
    import importlib

    real_import = __builtins__['__import__'] if isinstance(
        __builtins__, dict) else __builtins__.__import__

    def _blocked_import(name, *args, **kwargs):
        if name == 'plotly' or name.startswith('plotly.'):
            raise ImportError('plotly disabled for this test')
        return real_import(name, *args, **kwargs)

    # Evict any cached plotly modules so the guarded import runs fresh
    for mod_name in list(sys.modules):
        if mod_name == 'plotly' or mod_name.startswith('plotly.'):
            sys.modules.pop(mod_name, None)

    if isinstance(__builtins__, dict):
        monkeypatch.setitem(__builtins__, '__import__', _blocked_import)
    else:
        monkeypatch.setattr(__builtins__, '__import__', _blocked_import)

    # Re-import htmlreport to make sure no stale plotly references sneak in
    import backtrader.analyzers.htmlreport as hr
    importlib.reload(hr)

    db_path, run_id = _write_sample_run(tmp_path)
    out_path = str(tmp_path / 'report.html')

    returned = hr.render_report(db_path, run_id, out_path)
    assert os.path.exists(returned)

    with open(returned, 'r', encoding='utf-8') as fh:
        body = fh.read()

    # Charts section exists but plotly bootstrap JS is not there
    assert 'Charts' in body
    assert 'Plotly.newPlot' not in body
    # The degradation note surfaces in the rendered HTML
    assert 'plotly is not installed' in body
    # Tables still rendered
    assert 'Metrics' in body
    assert 'Trades' in body


# ---------------------------------------------------------------------------
# 3. Empty run renders without crashing.
# ---------------------------------------------------------------------------

def test_empty_run_renders(tmp_path):
    db_path, run_id = _write_empty_run(tmp_path)
    out_path = str(tmp_path / 'empty.html')

    returned = render_report(db_path, run_id, out_path)
    assert os.path.exists(returned)

    with open(returned, 'r', encoding='utf-8') as fh:
        body = fh.read()

    assert run_id in body
    assert 'Trades (0)' in body


# ---------------------------------------------------------------------------
# 4. Unknown run id raises LookupError (bubbled from exporter).
# ---------------------------------------------------------------------------

def test_invalid_run_id_raises(tmp_path):
    db_path, _ = _write_sample_run(tmp_path)
    out_path = str(tmp_path / 'nope.html')
    with pytest.raises(LookupError):
        render_report(db_path, 'does-not-exist', out_path)
