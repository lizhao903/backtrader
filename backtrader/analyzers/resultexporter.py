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
"""Export a run from a ResultStore SQLite DB into the ``result_v1`` JSON
contract consumed by downstream services (e.g. the crypto-trading-mgmt
FastAPI backend).

This module is a utility — not an Analyzer. It reads the three tables
produced by :class:`backtrader.analyzers.resultstore.ResultStore`
(``backtest_run``, ``backtest_metric``, ``backtest_trade``) and emits a
plain dict / JSON document that conforms to
``backtrader/contrib/schema/result_v1.json``.

The exporter keeps ``value_num`` and ``value_text`` as parallel columns
on each metric row; it deliberately does not collapse them so that the
consumer can decide which representation to use.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import json
import os
import sqlite3


__all__ = [
    'SCHEMA_VERSION',
    'SCHEMA_PATH',
    'export_run_to_dict',
    'export_run_to_json',
]


SCHEMA_VERSION = 'v1'

# Absolute path to the JSON Schema file that describes this contract.
SCHEMA_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        '..',
        'contrib',
        'schema',
        'result_v1.json',
    )
)


_RUN_COLUMNS = (
    'run_id',
    'label',
    'start_ts',
    'end_ts',
    'cerebro_broker_starting_cash',
    'cerebro_broker_ending_value',
    'strategy_name',
    'meta_json',
)

_METRIC_COLUMNS = ('analyzer', 'key', 'value_num', 'value_text')

_TRADE_COLUMNS = (
    'trade_ref',
    'data_name',
    'size',
    'price',
    'pnl',
    'pnlcomm',
    'commission',
    'open_dt',
    'close_dt',
)


def _row_to_dict(columns, row):
    return {col: row[idx] for idx, col in enumerate(columns)}


def _decode_meta_json(raw):
    '''``meta_json`` is stored as a string in SQLite. Expose it as a parsed
    object when possible so the consumer doesn't have to double-decode.'''
    if raw is None:
        return None
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def export_run_to_dict(db_path, run_id):
    '''Read a single run from the SQLite DB produced by ResultStore and
    return a dict that conforms to ``result_v1.json``.

    Parameters
    ----------
    db_path : str
        Path to the SQLite file written by ``ResultStore``.
    run_id : str
        UUID of the run to export.

    Returns
    -------
    dict
        A dict with keys ``schema_version``, ``run``, ``metrics`` and
        ``trades`` that validates against ``result_v1.json``.

    Raises
    ------
    LookupError
        If ``run_id`` does not exist in ``backtest_run``.
    '''
    if not os.path.exists(db_path):
        raise FileNotFoundError('SQLite DB not found: {0}'.format(db_path))

    conn = sqlite3.connect(db_path)
    try:
        run_row = conn.execute(
            'SELECT {cols} FROM backtest_run WHERE run_id = ?'.format(
                cols=', '.join(_RUN_COLUMNS)
            ),
            (run_id,),
        ).fetchone()
        if run_row is None:
            raise LookupError(
                'run_id {0!r} not found in {1}'.format(run_id, db_path)
            )
        run = _row_to_dict(_RUN_COLUMNS, run_row)
        run['meta_json'] = _decode_meta_json(run['meta_json'])

        metric_rows = conn.execute(
            'SELECT {cols} FROM backtest_metric WHERE run_id = ? '
            'ORDER BY analyzer, key'.format(cols=', '.join(_METRIC_COLUMNS)),
            (run_id,),
        ).fetchall()
        metrics = [_row_to_dict(_METRIC_COLUMNS, r) for r in metric_rows]

        trade_rows = conn.execute(
            'SELECT {cols} FROM backtest_trade WHERE run_id = ? '
            'ORDER BY trade_ref'.format(cols=', '.join(_TRADE_COLUMNS)),
            (run_id,),
        ).fetchall()
        trades = [_row_to_dict(_TRADE_COLUMNS, r) for r in trade_rows]
    finally:
        conn.close()

    return {
        'schema_version': SCHEMA_VERSION,
        'run': run,
        'metrics': metrics,
        'trades': trades,
    }


def export_run_to_json(db_path, run_id, out_path=None):
    '''Export a run and write the JSON to ``out_path`` (when given) or
    return the JSON string.

    Parameters
    ----------
    db_path : str
        Path to the SQLite file written by ``ResultStore``.
    run_id : str
        UUID of the run to export.
    out_path : str or None, optional
        If provided, the JSON document is written to this path and the
        same path is returned. Parent directories are created if missing.

    Returns
    -------
    str
        The JSON string (when ``out_path`` is ``None``) or the output
        path (when ``out_path`` is supplied).
    '''
    document = export_run_to_dict(db_path, run_id)
    text = json.dumps(document, ensure_ascii=False, indent=2, default=str)

    if out_path is None:
        return text

    parent = os.path.dirname(os.path.abspath(out_path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)

    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write(text)
        if not text.endswith('\n'):
            fh.write('\n')
    return out_path
