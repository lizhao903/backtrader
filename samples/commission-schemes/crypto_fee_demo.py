#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
# Demo: CryptoCommissionInfo tiered maker/taker + BNB-style discount.
#
# Prints the taker fee (default conservative path) and maker fee
# (getcommission_by_exectype with Order.Limit) for a 10 BTC @ 60_000 USDT
# trade under three commission configurations:
#
#   1. base         -- default Binance-style schedule, no volume, no discount
#   2. high_volume  -- 30d rolling volume = 10_000_000 USDT
#   3. bnb_discount -- base schedule + 25 %% BNB discount (multiplier = 0.75)
#
# No cerebro, pure arithmetic demonstration.
###############################################################################
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from backtrader.commissions import CryptoCommissionInfo
from backtrader.order import Order


def main():
    size = 10.0              # 10 BTC
    price = 60_000.0         # 60_000 USDT / BTC
    notional = size * price

    schemes = [
        ('base',         CryptoCommissionInfo()),
        ('high_volume',  CryptoCommissionInfo(rolling_volume=10_000_000)),
        ('bnb_discount', CryptoCommissionInfo(discount=0.75)),
    ]

    print('Trade: size={:g} BTC  price={:.2f} USDT  notional={:.2f} USDT'
          .format(size, price, notional))
    print('-' * 78)
    header = '{:<14s} {:>10s} {:>10s} {:>14s} {:>14s}'.format(
        'scheme', 'maker_rate', 'taker_rate', 'maker_fee', 'taker_fee')
    print(header)
    print('-' * 78)

    for name, comm in schemes:
        maker_fee = comm.getcommission_by_exectype(size, price, Order.Limit)
        taker_fee = comm.getcommission_by_exectype(size, price, Order.Market)
        # default path (_getcommission) picks taker -- show it matches
        default_fee = comm._getcommission(size, price, pseudoexec=True)
        assert abs(default_fee - taker_fee) < 1e-9

        print('{:<14s} {:>10.6f} {:>10.6f} {:>14.4f} {:>14.4f}'.format(
            name,
            comm.maker_rate(),
            comm.taker_rate(),
            maker_fee,
            taker_fee,
        ))


if __name__ == '__main__':
    main()
