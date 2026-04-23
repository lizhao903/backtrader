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
"""HTML report renderer for a ResultStore SQLite run.

``render_report(db_path, run_id, out_path)`` reads a single backtest run
via :func:`backtrader.analyzers.resultexporter.export_run_to_dict` and
writes a self-contained HTML file. Charts are generated with plotly and
inlined into the document (``include_plotlyjs='inline'`` on the first
figure only) so the report is fully offline and does not hit any CDN.

Both ``jinja2`` and ``plotly`` are optional runtime dependencies. If
``jinja2`` is missing ``render_report`` raises ``ImportError`` (the
report cannot be produced without a template engine); if ``plotly`` is
missing the report degrades gracefully to pure HTML tables with a note
in the Charts section.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os

from .resultexporter import export_run_to_dict


__all__ = ['render_report']


DEFAULT_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')
DEFAULT_TEMPLATE_NAME = 'report.html.j2'


def _group_metrics_by_analyzer(metrics):
    '''Group a flat metrics list into ``{analyzer: [rows...]}`` preserving
    insertion order. Rows inside each analyzer stay sorted by key.'''
    grouped = {}
    for row in metrics:
        analyzer = row.get('analyzer') or '(unknown)'
        grouped.setdefault(analyzer, []).append(row)
    for rows in grouped.values():
        rows.sort(key=lambda r: (r.get('key') or ''))
    return grouped


def _build_equity_series(run, trades):
    '''Construct a cumulative PnL curve from closed trades.

    Each trade contributes ``pnlcomm`` (falling back to ``pnl``) to the
    running total, anchored at the run's starting cash.'''
    start_cash = run.get('cerebro_broker_starting_cash') or 0.0
    xs = []
    ys = []
    total = 0.0
    for t in trades:
        pnl = t.get('pnlcomm')
        if pnl is None:
            pnl = t.get('pnl')
        if pnl is None:
            continue
        total += float(pnl)
        close_dt = t.get('close_dt') or t.get('open_dt')
        xs.append(close_dt if close_dt is not None else t.get('trade_ref'))
        ys.append(start_cash + total)
    return xs, ys


def _build_trade_pnl_series(trades):
    refs = []
    pnls = []
    for t in trades:
        pnl = t.get('pnlcomm')
        if pnl is None:
            pnl = t.get('pnl')
        if pnl is None:
            continue
        refs.append(t.get('trade_ref'))
        pnls.append(float(pnl))
    return refs, pnls


def _find_drawdown_series(metrics):
    '''Pick out drawdown-related metrics for a small summary chart.

    The ``DrawDown`` analyzer flattens into keys like ``drawdown``,
    ``moneydown``, ``max.drawdown``, ``max.moneydown``, ``len``,
    ``max.len``. We extract the numeric values and surface them as a
    tiny bar chart — not a time series, since ResultStore does not
    persist the equity curve (yet).
    '''
    labels = []
    values = []
    for m in metrics:
        analyzer = (m.get('analyzer') or '').lower()
        if 'drawdown' not in analyzer:
            continue
        if m.get('value_num') is None:
            continue
        labels.append(m.get('key') or '')
        values.append(float(m['value_num']))
    return labels, values


def _render_charts(run, metrics, trades):
    '''Return a list of HTML chart fragments (strings) ready to embed.

    If plotly is unavailable, returns a single placeholder note so the
    template still renders a Charts section.'''
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
    except Exception:
        return [
            '<p><em>plotly is not installed; charts omitted. '
            'Install with <code>pip install plotly</code> for interactive '
            'charts.</em></p>'
        ]

    charts = []

    # 1. Cumulative PnL
    eq_x, eq_y = _build_equity_series(run, trades)
    if eq_x:
        fig = go.Figure(data=[go.Scatter(x=eq_x, y=eq_y, mode='lines+markers',
                                         name='Equity')])
        fig.update_layout(title='Cumulative PnL', xaxis_title='Trade close',
                          yaxis_title='Equity', height=360)
        charts.append(fig)

    # 2. Per-trade PnL bar chart
    refs, pnls = _build_trade_pnl_series(trades)
    if refs:
        colors = ['#2ca02c' if v >= 0 else '#d62728' for v in pnls]
        fig = go.Figure(data=[go.Bar(x=refs, y=pnls, marker_color=colors,
                                     name='Trade PnL')])
        fig.update_layout(title='Trade PnL', xaxis_title='Trade ref',
                          yaxis_title='PnL (comm)', height=320)
        charts.append(fig)

    # 3. Drawdown summary (if analyzer data present)
    dd_labels, dd_values = _find_drawdown_series(metrics)
    if dd_labels:
        fig = go.Figure(data=[go.Bar(x=dd_labels, y=dd_values,
                                     marker_color='#8c564b',
                                     name='Drawdown')])
        fig.update_layout(title='Drawdown metrics', height=320,
                          xaxis_tickangle=-30)
        charts.append(fig)

    if not charts:
        return ['<p><em>No chartable data for this run.</em></p>']

    html_fragments = []
    for idx, fig in enumerate(charts):
        include = 'inline' if idx == 0 else False
        html_fragments.append(pio.to_html(
            fig, include_plotlyjs=include, full_html=False))
    return html_fragments


def render_report(db_path, run_id, out_path, template_dir=None):
    '''Render a self-contained HTML report for a given backtest run.

    Reads SQLite via :func:`export_run_to_dict`, then renders via a
    Jinja2 template. Charts are embedded as plotly ``<script>`` blocks
    in the HTML (plotly.js is inlined on the first figure so the file
    is fully offline).

    Parameters
    ----------
    db_path : str
        Path to the SQLite file written by ``ResultStore``.
    run_id : str
        UUID of the run to export.
    out_path : str
        Destination path for the HTML file. Parent directories are
        created if missing.
    template_dir : str or None, optional
        Directory containing ``report.html.j2``. Defaults to
        ``backtrader/analyzers/templates``.

    Returns
    -------
    str
        The absolute path to the written HTML file.
    '''
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError as exc:  # pragma: no cover - import-time guard
        raise ImportError(
            'jinja2 is required for render_report(); install with '
            '`pip install jinja2`'
        ) from exc

    document = export_run_to_dict(db_path, run_id)
    run = document['run']
    metrics = document['metrics']
    trades = document['trades']

    metrics_by_analyzer = _group_metrics_by_analyzer(metrics)
    charts = _render_charts(run, metrics, trades)

    equity_x, equity_y = _build_equity_series(run, trades)
    trade_refs, trade_pnls = _build_trade_pnl_series(trades)

    tpl_dir = template_dir or DEFAULT_TEMPLATE_DIR
    env = Environment(
        loader=FileSystemLoader(tpl_dir),
        autoescape=select_autoescape(['html', 'htm', 'xml']),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(DEFAULT_TEMPLATE_NAME)

    html = template.render(
        run=run,
        metrics=metrics,
        metrics_by_analyzer=metrics_by_analyzer,
        trades=trades,
        charts=charts,
        equity_series={'x': equity_x, 'y': equity_y},
        trade_pnl_series={'refs': trade_refs, 'pnls': trade_pnls},
    )

    out_abs = os.path.abspath(out_path)
    parent = os.path.dirname(out_abs)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(out_abs, 'w', encoding='utf-8') as fh:
        fh.write(html)
    return out_abs
