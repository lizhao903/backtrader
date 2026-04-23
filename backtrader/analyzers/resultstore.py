#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2023 Daniel Rodriguez
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import json
import os
import sqlite3
import uuid

from backtrader import Analyzer


__all__ = ['ResultStore']


_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS backtest_run (
        run_id TEXT PRIMARY KEY,
        label TEXT,
        start_ts TEXT NOT NULL,
        end_ts TEXT,
        cerebro_broker_starting_cash REAL,
        cerebro_broker_ending_value REAL,
        strategy_name TEXT,
        meta_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS backtest_metric (
        run_id TEXT NOT NULL,
        analyzer TEXT NOT NULL,
        key TEXT NOT NULL,
        value_num REAL,
        value_text TEXT,
        PRIMARY KEY (run_id, analyzer, key),
        FOREIGN KEY (run_id) REFERENCES backtest_run(run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS backtest_trade (
        run_id TEXT NOT NULL,
        trade_ref INTEGER NOT NULL,
        data_name TEXT,
        size REAL,
        price REAL,
        pnl REAL,
        pnlcomm REAL,
        commission REAL,
        open_dt TEXT,
        close_dt TEXT,
        PRIMARY KEY (run_id, trade_ref),
        FOREIGN KEY (run_id) REFERENCES backtest_run(run_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_metric_analyzer ON backtest_metric(analyzer)",
    "CREATE INDEX IF NOT EXISTS idx_trade_data ON backtest_trade(data_name)",
)


def _utcnow_iso():
    # py3.12+ prefers timezone-aware now(UTC); fall back for older interpreters
    try:
        now = datetime.datetime.now(datetime.timezone.utc).replace(
            microsecond=0, tzinfo=None)
    except Exception:
        now = datetime.datetime.utcnow().replace(microsecond=0)
    return now.isoformat() + 'Z'


def _flatten(prefix, value, out):
    '''Flatten nested dicts into dotted paths.

    - numeric/bool -> value_num column
    - everything else -> JSON stringified into value_text column
    - None values are skipped
    '''
    if value is None:
        return

    # dict-like: recurse
    if hasattr(value, 'items') and callable(value.items):
        # empty dict: still emit a marker so we don't swallow the info
        if not list(value.items()):
            out.append((prefix, None, '{}'))
            return
        for k, v in value.items():
            key = '{0}.{1}'.format(prefix, k) if prefix else str(k)
            _flatten(key, v, out)
        return

    # bool first: bool is a subclass of int in python
    if isinstance(value, bool):
        out.append((prefix, float(value), None))
        return

    if isinstance(value, (int, float)):
        try:
            num = float(value)
        except (TypeError, ValueError):
            num = None
        out.append((prefix, num, None))
        return

    # list / tuple / str / datetime / anything else -> json
    try:
        text = json.dumps(value, default=str)
    except (TypeError, ValueError):
        text = json.dumps(str(value))
    out.append((prefix, None, text))


class ResultStore(Analyzer):
    '''Persist backtest results (metrics + trades) to a SQLite file.

    Enumerates sibling analyzers in ``stop()`` and stores their
    ``get_analysis()`` outputs keyed by analyzer class name. Also records
    every completed trade into a normalized trades table.

    Use together with other analyzers - ``ResultStore`` does NOT compute
    metrics, it only aggregates what siblings produce.

    Params:

      - ``db_path`` (default: ``'backtest_results.sqlite'``): SQLite file path.
        Parent directory is created if missing.

      - ``run_label`` (default: ``None``): optional human-readable label; if
        ``None`` the start timestamp is used as the label.

      - ``include_trades`` (default: ``True``): write one row per closed trade
        into ``backtest_trade``.

      - ``include_equity_curve`` (default: ``False``): reserved for future use
        (daily/bar-level equity snapshots).

    Schema (three tables, all ``IF NOT EXISTS``):

      - ``backtest_run``       -- one row per run, keyed by ``run_id`` (uuid4)
      - ``backtest_metric``    -- flattened analyzer outputs, one row per key
      - ``backtest_trade``     -- one row per closed trade

    Nested dicts from ``get_analysis()`` are dot-path flattened. Numeric
    values go into ``value_num``; other values are JSON-stringified into
    ``value_text``. Writes use ``INSERT OR REPLACE`` so a same-``run_id``
    re-run is idempotent (no duplicate rows).
    '''

    params = (
        ('db_path', 'backtest_results.sqlite'),
        ('run_label', None),
        ('include_trades', True),
        ('include_equity_curve', False),
    )

    def create_analysis(self):
        super(ResultStore, self).create_analysis()
        self._closed_trades = []
        self.run_id = None
        self._start_ts = None
        self._starting_cash = None

    # --- lifecycle --------------------------------------------------------

    def start(self):
        super(ResultStore, self).start()
        self.run_id = str(uuid.uuid4())
        self._start_ts = _utcnow_iso()
        self._closed_trades = []

        # Record starting cash if broker is available
        try:
            self._starting_cash = float(self.strategy.broker.startingcash)
        except (AttributeError, TypeError, ValueError):
            self._starting_cash = None

        self._ensure_db_dir()
        conn = self._connect()
        try:
            for stmt in _SCHEMA_STATEMENTS:
                conn.execute(stmt)
            conn.commit()
        finally:
            conn.close()

    def notify_trade(self, trade):
        if not self.p.include_trades:
            return
        if trade.status != trade.Closed:
            return
        try:
            open_dt = trade.open_datetime().isoformat()
        except Exception:
            open_dt = None
        try:
            close_dt = trade.close_datetime().isoformat()
        except Exception:
            close_dt = None
        data_name = None
        try:
            data_name = trade.getdataname()
        except Exception:
            data_name = None
        self._closed_trades.append({
            'trade_ref': int(trade.ref),
            'data_name': data_name,
            'size': float(getattr(trade, 'size', 0) or 0),
            'price': float(getattr(trade, 'price', 0) or 0),
            'pnl': float(getattr(trade, 'pnl', 0) or 0),
            'pnlcomm': float(getattr(trade, 'pnlcomm', 0) or 0),
            'commission': float(getattr(trade, 'commission', 0) or 0),
            'open_dt': open_dt,
            'close_dt': close_dt,
        })

    def stop(self):
        super(ResultStore, self).stop()

        end_ts = _utcnow_iso()
        ending_value = None
        try:
            ending_value = float(self.strategy.broker.getvalue())
        except (AttributeError, TypeError, ValueError):
            ending_value = None

        strategy_name = type(self.strategy).__name__

        metric_rows = self._collect_metrics()
        trade_rows = list(self._closed_trades) if self.p.include_trades else []

        conn = self._connect()
        try:
            # ensure schema even if start() was not triggered externally
            for stmt in _SCHEMA_STATEMENTS:
                conn.execute(stmt)

            label = self.p.run_label or self._start_ts
            conn.execute(
                """
                INSERT OR REPLACE INTO backtest_run
                    (run_id, label, start_ts, end_ts,
                     cerebro_broker_starting_cash, cerebro_broker_ending_value,
                     strategy_name, meta_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.run_id,
                    label,
                    self._start_ts or end_ts,
                    end_ts,
                    self._starting_cash,
                    ending_value,
                    strategy_name,
                    json.dumps({
                        'analyzers': [name for name, _ in
                                      self._iter_sibling_analyzers()],
                    }, default=str),
                ),
            )

            # Clear any previous rows for this run (makes full re-run
            # idempotent even if metric/trade sets shrink).
            conn.execute(
                "DELETE FROM backtest_metric WHERE run_id = ?",
                (self.run_id,),
            )
            conn.execute(
                "DELETE FROM backtest_trade WHERE run_id = ?",
                (self.run_id,),
            )

            if metric_rows:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO backtest_metric
                        (run_id, analyzer, key, value_num, value_text)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (self.run_id, analyzer_name, key, value_num, value_text)
                        for (analyzer_name, key, value_num, value_text)
                        in metric_rows
                    ],
                )

            if trade_rows:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO backtest_trade
                        (run_id, trade_ref, data_name, size, price,
                         pnl, pnlcomm, commission, open_dt, close_dt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            self.run_id, t['trade_ref'], t['data_name'],
                            t['size'], t['price'],
                            t['pnl'], t['pnlcomm'], t['commission'],
                            t['open_dt'], t['close_dt'],
                        )
                        for t in trade_rows
                    ],
                )

            conn.commit()
        finally:
            conn.close()

        self.rets['run_id'] = self.run_id
        self.rets['db_path'] = self.p.db_path
        self.rets['metric_count'] = len(metric_rows)
        self.rets['trade_count'] = len(trade_rows)

    # --- helpers ----------------------------------------------------------

    def get_analysis(self):
        return self.rets

    def _ensure_db_dir(self):
        db_path = self.p.db_path
        if db_path in (None, '', ':memory:'):
            return
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)

    def _connect(self):
        # isolation_level=None is not used; we want explicit commit
        return sqlite3.connect(self.p.db_path)

    def _iter_sibling_analyzers(self):
        '''Yield (name, analyzer) pairs for every non-self analyzer hanging
        off the owning strategy.'''
        analyzers = getattr(self.strategy, 'analyzers', None)
        if analyzers is None:
            return
        for aname, analyzer in analyzers.getitems():
            if analyzer is self:
                continue
            yield aname, analyzer

    def _collect_metrics(self):
        rows = []
        for aname, analyzer in self._iter_sibling_analyzers():
            try:
                analysis = analyzer.get_analysis()
            except Exception as exc:  # analyzer exploded; record failure
                rows.append((type(analyzer).__name__, '_error', None,
                             json.dumps(str(exc))))
                continue
            analyzer_cls = type(analyzer).__name__
            flat = []
            _flatten('', analysis, flat)
            for key, value_num, value_text in flat:
                # empty key can happen if get_analysis returns a scalar
                rows.append((analyzer_cls, key or '_value',
                             value_num, value_text))
        return rows
