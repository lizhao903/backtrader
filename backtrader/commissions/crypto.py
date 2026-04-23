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

from ..comminfo import CommInfoBase


# Binance-style default tier schedule (maker/taker fractions).  Tiers must be
# ordered ascending by ``min_volume``.  The highest tier whose ``min_volume``
# is <= current rolling volume is selected.
DEFAULT_TIER_SCHEDULE = [
    {'min_volume': 0,         'maker': 0.0010, 'taker': 0.0010},
    {'min_volume': 1_000_000, 'maker': 0.0009, 'taker': 0.0010},
    {'min_volume': 5_000_000, 'maker': 0.0008, 'taker': 0.0010},
]


class CryptoCommissionInfo(CommInfoBase):
    """Maker/taker fee model for crypto spot exchanges with optional
    tier schedule based on 30d volume and optional BNB-style discount.

    Parameters
    ----------
    tier_schedule : list of dict
        Ordered ascending by ``min_volume``.  Each dict has keys:
        ``{'min_volume': float, 'maker': float, 'taker': float}``.
        When ``None`` a Binance-style 3 tier default is used.
    rolling_volume : float
        Current 30d trailing volume (quote currency).  Selects the tier.
    discount : float
        Multiplier applied to fees (e.g. BNB 25% off -> ``discount=0.75``).

    Notes
    -----
    ``_getcommission`` alone cannot tell maker from taker because backtrader
    does not plumb ``exectype`` into the commission callback.  The plain
    ``_getcommission`` therefore returns the (conservative) taker fee.  To
    obtain the true maker/taker rate, the broker layer should call
    :py:meth:`getcommission_by_exectype` which inspects ``Order.exectype``:
    a plain ``Limit`` is treated as maker; everything else (market, stop,
    stop-limit, ...) is taker.
    """

    params = (
        ('tier_schedule', None),
        ('rolling_volume', 0.0),
        ('discount', 1.0),
        ('stocklike', True),          # crypto spot treated stock-like
        ('commtype', CommInfoBase.COMM_PERC),
        ('percabs', True),            # rates given as fractions (0.001=0.1%)
    )

    def _tier_schedule(self):
        sched = self.p.tier_schedule
        if sched is None:
            return DEFAULT_TIER_SCHEDULE
        return sched

    def _pick_tier(self):
        """Return the highest tier whose ``min_volume`` <= rolling_volume.

        Assumes the schedule is ordered ascending by ``min_volume``.  Falls
        back to the first tier if ``rolling_volume`` is below all thresholds.
        """
        rv = self.p.rolling_volume
        selected = None
        for tier in self._tier_schedule():
            if rv >= tier['min_volume']:
                selected = tier
            else:
                break
        if selected is None:
            selected = self._tier_schedule()[0]
        return selected

    def _maker_rate(self):
        return self._pick_tier()['maker'] * self.p.discount

    def _taker_rate(self):
        return self._pick_tier()['taker'] * self.p.discount

    # Public helpers
    def maker_rate(self):
        return self._maker_rate()

    def taker_rate(self):
        return self._taker_rate()

    def _getcommission(self, size, price, pseudoexec):
        """Conservative default: taker fee (market/crossable limit)."""
        return abs(size) * price * self._taker_rate()

    def getcommission_by_exectype(self, size, price, exectype):
        """Return commission using ``Order.exectype`` to pick maker/taker.

        ``Order.Limit`` is treated as maker (non-immediate limit / post-only).
        Everything else (Market, Stop, StopLimit, trailing, ...) is taker.
        """
        from ..order import Order
        if exectype == Order.Limit:
            rate = self._maker_rate()
        else:
            rate = self._taker_rate()
        return abs(size) * price * rate
