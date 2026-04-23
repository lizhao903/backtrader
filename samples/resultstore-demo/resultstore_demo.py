#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2023 Daniel Rodriguez
#
# ResultStore demo
# ----------------
# Run a trivial SMA crossover against a local CSV, mount Sharpe / DrawDown /
# TradeAnalyzer / ResultStore, and show the SQLite rows the ResultStore wrote.
#
# Usage:
#     python resultstore_demo.py
#     python resultstore_demo.py --db /tmp/bt.sqlite --data ../../datas/orcl-1995-2014.txt
###############################################################################
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import os
import sqlite3
import sys

import backtrader as bt
import backtrader.indicators as btind


HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA = os.path.abspath(
    os.path.join(HERE, '..', '..', 'datas', 'yhoo-1996-2015.txt'))
DEFAULT_DB = os.path.join(HERE, 'resultstore_demo.sqlite')


class SmaCross(bt.Strategy):
    params = (('fast', 10), ('slow', 30))

    def __init__(self):
        sma_fast = btind.SMA(self.data.close, period=self.p.fast)
        sma_slow = btind.SMA(self.data.close, period=self.p.slow)
        self.cross = btind.CrossOver(sma_fast, sma_slow)

    def next(self):
        if not self.position:
            if self.cross > 0:
                self.buy()
        elif self.cross < 0:
            self.close()


def build_cerebro(datafile, db_path):
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(100000.0)

    data = bt.feeds.BacktraderCSVData(dataname=datafile)
    cerebro.adddata(data)

    cerebro.addstrategy(SmaCross)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    # ResultStore goes last so siblings are all registered when it
    # enumerates them in stop().
    cerebro.addanalyzer(bt.analyzers.ResultStore,
                        _name='resultstore',
                        db_path=db_path,
                        run_label='sma-cross-demo')
    return cerebro


def dump_db(db_path):
    print('\n=== SQLite contents at {0} ==='.format(db_path))
    conn = sqlite3.connect(db_path)
    try:
        for table in ('backtest_run', 'backtest_metric', 'backtest_trade'):
            count = conn.execute(
                'SELECT COUNT(*) FROM {0}'.format(table)).fetchone()[0]
            print('  {0:<18} {1} rows'.format(table, count))

        print('\n-- backtest_run --')
        for row in conn.execute(
                'SELECT run_id, label, strategy_name, '
                'cerebro_broker_starting_cash, cerebro_broker_ending_value '
                'FROM backtest_run'):
            print('  ', row)

        print('\n-- backtest_metric (first 10) --')
        for row in conn.execute(
                'SELECT analyzer, key, value_num, value_text '
                'FROM backtest_metric LIMIT 10'):
            print('  ', row)
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='ResultStore analyzer demo')
    parser.add_argument('--data', default=DEFAULT_DATA,
                        help='CSV datafile (BacktraderCSVData format)')
    parser.add_argument('--db', default=DEFAULT_DB, help='SQLite db path')
    args = parser.parse_args(argv)

    if not os.path.exists(args.data):
        print('Data file not found: {0}'.format(args.data), file=sys.stderr)
        print('Pass --data to point at an existing CSV in backtrader/datas/.',
              file=sys.stderr)
        return 2

    # Fresh DB for demo clarity
    if os.path.exists(args.db):
        os.remove(args.db)

    cerebro = build_cerebro(args.data, args.db)
    print('Starting portfolio value: {0:.2f}'.format(cerebro.broker.getvalue()))
    strats = cerebro.run()
    print('Ending portfolio value:   {0:.2f}'.format(cerebro.broker.getvalue()))

    rs = strats[0].analyzers.resultstore
    print('\nResultStore summary:', rs.get_analysis())

    dump_db(args.db)

    # Emit the FastAPI-interop JSON document alongside the SQLite file.
    from backtrader.analyzers.resultexporter import export_run_to_json
    run_id = rs.get_analysis()['run_id']
    json_path = args.db.replace('.sqlite', '.json')
    export_run_to_json(args.db, run_id, json_path)
    print('JSON export: {0}'.format(json_path))
    return 0


if __name__ == '__main__':
    sys.exit(main())
