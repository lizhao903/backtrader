"""Tests for :class:`backtrader.commissions.CryptoCommissionInfo`.

Covers tiered maker/taker selection by rolling 30d volume, BNB-style discount
multiplier, maker/taker differentiation by ``Order.exectype`` and notional
scaling.
"""

import math

import pytest

from backtrader.commissions import CryptoCommissionInfo
from backtrader.order import Order


def _approx(value):
    return pytest.approx(value, rel=1e-12, abs=1e-12)


def test_default_tier_0_volume():
    """rolling_volume=0 -> first tier (0.001 maker/taker)."""
    comm = CryptoCommissionInfo()
    size, price = 1.0, 60_000.0
    # taker path (default _getcommission)
    fee = comm._getcommission(size, price, pseudoexec=True)
    assert fee == _approx(size * price * 0.001)
    assert comm.maker_rate() == _approx(0.001)
    assert comm.taker_rate() == _approx(0.001)


def test_upgrade_tier_by_volume():
    """rolling_volume=2_000_000 -> 2nd tier (maker 0.0009, taker 0.001)."""
    comm = CryptoCommissionInfo(rolling_volume=2_000_000)
    assert comm.maker_rate() == _approx(0.0009)
    assert comm.taker_rate() == _approx(0.001)

    # Also verify the top tier kicks in at 5M
    comm_top = CryptoCommissionInfo(rolling_volume=10_000_000)
    assert comm_top.maker_rate() == _approx(0.0008)
    assert comm_top.taker_rate() == _approx(0.001)


def test_maker_vs_taker_differentiation():
    """Different maker/taker rates must route by Order.exectype."""
    schedule = [
        {'min_volume': 0, 'maker': 0.0002, 'taker': 0.0010},
    ]
    comm = CryptoCommissionInfo(tier_schedule=schedule)

    size, price = 2.0, 30_000.0
    notional = abs(size) * price  # 60_000

    fee_maker = comm.getcommission_by_exectype(size, price, Order.Limit)
    fee_taker_market = comm.getcommission_by_exectype(size, price, Order.Market)
    fee_taker_stop = comm.getcommission_by_exectype(size, price, Order.Stop)
    fee_taker_stoplimit = comm.getcommission_by_exectype(
        size, price, Order.StopLimit)

    assert fee_maker == _approx(notional * 0.0002)
    assert fee_taker_market == _approx(notional * 0.0010)
    assert fee_taker_stop == _approx(notional * 0.0010)
    assert fee_taker_stoplimit == _approx(notional * 0.0010)
    assert fee_maker < fee_taker_market
    # plain _getcommission defaults to taker (conservative)
    assert comm._getcommission(size, price, pseudoexec=True) == _approx(
        fee_taker_market)


def test_discount_applied():
    """discount=0.75 must scale every fee by exactly 75%."""
    base = CryptoCommissionInfo()
    disc = CryptoCommissionInfo(discount=0.75)

    size, price = 1.0, 60_000.0
    fee_base = base._getcommission(size, price, pseudoexec=True)
    fee_disc = disc._getcommission(size, price, pseudoexec=True)

    assert fee_disc == _approx(fee_base * 0.75)
    assert disc.maker_rate() == _approx(0.001 * 0.75)
    assert disc.taker_rate() == _approx(0.001 * 0.75)

    # Combined: mid tier + discount
    combo = CryptoCommissionInfo(rolling_volume=2_000_000, discount=0.75)
    fee_combo_maker = combo.getcommission_by_exectype(
        size, price, Order.Limit)
    assert fee_combo_maker == _approx(size * price * 0.0009 * 0.75)


def test_notional_scales():
    """Fee must scale linearly with |size| (notional)."""
    comm = CryptoCommissionInfo()
    price = 60_000.0
    fee_1 = comm._getcommission(1.0, price, pseudoexec=True)
    fee_2 = comm._getcommission(2.0, price, pseudoexec=True)
    fee_neg3 = comm._getcommission(-3.0, price, pseudoexec=True)

    assert fee_2 == _approx(2.0 * fee_1)
    assert fee_neg3 == _approx(3.0 * fee_1)
    assert not math.isclose(fee_1, 0.0)
