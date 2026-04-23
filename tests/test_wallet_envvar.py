#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Unit tests for backtrader.brokers.wallets.envvar.EnvVarWallet.
#
###############################################################################
"""Tests for the env-var-backed wallet scaffold (see issue #23)."""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import pytest

from backtrader.brokers.wallets import (
    WalletBase,
    WalletNotConfigured,
)
from backtrader.brokers.wallets.envvar import EnvVarWallet


# A deterministic 32-byte hex key used only for testing.
_TEST_EVM_HEX = (
    "4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318"
)
# 32-byte test hex for solana seed.
_TEST_SOL_HEX = (
    "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure env is clean for every test -- isolates from host env."""
    monkeypatch.delenv("BT_EVM_PRIVKEY", raising=False)
    monkeypatch.delenv("BT_SOL_PRIVKEY", raising=False)
    yield


def test_no_env_raises_not_configured():
    # Empty env + require ethereum => WalletNotConfigured at construction.
    with pytest.raises(WalletNotConfigured):
        EnvVarWallet(require=("ethereum",))


def test_supports_chain(monkeypatch):
    monkeypatch.setenv("BT_EVM_PRIVKEY", _TEST_EVM_HEX)
    w = EnvVarWallet()  # no require -> does not raise
    assert isinstance(w, WalletBase)
    # In whitelist:
    for chain in ("ethereum", "arbitrum", "base", "bsc", "polygon", "solana"):
        assert w.supports(chain) is True
    # Outside whitelist:
    for chain in ("dogecoin", "", "bitcoin", "tron"):
        assert w.supports(chain) is False


def test_evm_address_format(monkeypatch):
    pytest.importorskip(
        "eth_account",
        reason="eth_account not installed; address derivation needs it",
    )
    monkeypatch.setenv("BT_EVM_PRIVKEY", _TEST_EVM_HEX)
    w = EnvVarWallet(require=("ethereum",))
    addr = w.address("ethereum")
    assert isinstance(addr, str)
    assert addr.startswith("0x")
    assert len(addr) == 42


def test_sol_address_format(monkeypatch):
    pytest.importorskip(
        "solders",
        reason="solders not installed; pubkey derivation needs it",
    )
    monkeypatch.setenv("BT_SOL_PRIVKEY", _TEST_SOL_HEX)
    w = EnvVarWallet(require=("solana",))
    addr = w.address("solana")
    assert isinstance(addr, str)
    # Solana base58 pubkeys are typically 32-44 chars.
    assert 32 <= len(addr) <= 44


def test_str_no_leak(monkeypatch):
    secret = _TEST_EVM_HEX
    sol_secret = _TEST_SOL_HEX
    monkeypatch.setenv("BT_EVM_PRIVKEY", secret)
    monkeypatch.setenv("BT_SOL_PRIVKEY", sol_secret)
    w = EnvVarWallet(require=("ethereum",))
    assert secret not in str(w)
    assert secret not in repr(w)
    assert sol_secret not in str(w)
    assert sol_secret not in repr(w)
    # Also make sure the env var name isn't the vehicle for leaking the value.
    assert "0x" + secret not in repr(w)
