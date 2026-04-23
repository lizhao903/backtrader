#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Unit tests for backtrader.brokers.wallets.keystore.LocalKeystoreWallet
# and the ledger stub.
#
###############################################################################
"""Tests for the local-keystore wallet + Ledger stub (see issue #23)."""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import json

import pytest

from backtrader.brokers.wallets import (
    WalletError,
    WalletNotConfigured,
)
from backtrader.brokers.wallets.keystore import LocalKeystoreWallet
from backtrader.brokers.wallets.ledger import LedgerWallet


# A deterministic 32-byte hex private key used only for tests. The matching
# address is derived by ``eth_account`` at runtime so we don't hardcode it.
_TEST_EVM_HEX = (
    "4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318"
)
_TEST_PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure ``BT_KEYSTORE_PASSWORD`` is not inherited from the host env."""
    monkeypatch.delenv("BT_KEYSTORE_PASSWORD", raising=False)
    yield


def _write_valid_keystore(tmp_path, password=_TEST_PASSWORD, privkey_hex=_TEST_EVM_HEX):
    """Use eth_account to write a real Web3 Secret Storage file.

    We use the ``pbkdf2`` KDF with a tiny iteration count because the test
    only cares about round-tripping encrypt/decrypt, not cryptographic
    strength -- scrypt with defaults takes multiple seconds per test.
    """
    eth_account = pytest.importorskip("eth_account")
    from eth_account import Account

    # iterations kept tiny to keep the test fast.
    encrypted = Account.encrypt(
        "0x" + privkey_hex, password, kdf="pbkdf2", iterations=2)
    path = tmp_path / "keystore.json"
    path.write_text(json.dumps(encrypted))
    expected_address = Account.from_key("0x" + privkey_hex).address
    return path, expected_address


# ---------------------------------------------------------------------------
# Construction / sanity checks
# ---------------------------------------------------------------------------

def test_missing_file_raises(tmp_path):
    missing = tmp_path / "nope.json"
    with pytest.raises((FileNotFoundError, WalletError)):
        LocalKeystoreWallet(missing)


def test_bad_json_raises(tmp_path):
    # File exists but content is not a keystore.
    bad = tmp_path / "bad.json"
    bad.write_text("not json at all {")
    with pytest.raises(WalletError):
        LocalKeystoreWallet(bad)

    # Valid JSON but missing required keys.
    incomplete = tmp_path / "incomplete.json"
    incomplete.write_text(json.dumps({"hello": "world"}))
    with pytest.raises(WalletError):
        LocalKeystoreWallet(incomplete)


def test_not_regular_file(tmp_path):
    # A directory should be rejected.
    with pytest.raises(WalletError):
        LocalKeystoreWallet(tmp_path)


# ---------------------------------------------------------------------------
# Unlock / signing behaviour (need eth_account)
# ---------------------------------------------------------------------------

def test_no_password_raises_not_configured(tmp_path):
    path, _expected = _write_valid_keystore(tmp_path)
    # Env var not set -> WalletNotConfigured on first address() call.
    w = LocalKeystoreWallet(path)
    with pytest.raises(WalletNotConfigured):
        w.address("ethereum")


def test_unlock_and_address(tmp_path, monkeypatch):
    path, expected_address = _write_valid_keystore(tmp_path)
    monkeypatch.setenv("BT_KEYSTORE_PASSWORD", _TEST_PASSWORD)
    w = LocalKeystoreWallet(path)
    assert w.address("ethereum").lower() == expected_address.lower()
    # Supports all EVM chains in the whitelist.
    for chain in ("ethereum", "arbitrum", "base", "bsc", "polygon"):
        assert w.supports(chain) is True
    # Chains outside the EVM whitelist are rejected.
    assert w.supports("solana") is False
    with pytest.raises(WalletError):
        w.address("solana")


def test_sign_sol_raises_not_implemented(tmp_path):
    path, _ = _write_valid_keystore(tmp_path)
    w = LocalKeystoreWallet(path)
    with pytest.raises(NotImplementedError):
        w.sign_sol_tx({"dummy": "tx"})


def test_repr_no_leak(tmp_path, monkeypatch):
    path, expected_address = _write_valid_keystore(tmp_path)
    password = _TEST_PASSWORD
    monkeypatch.setenv("BT_KEYSTORE_PASSWORD", password)
    w = LocalKeystoreWallet(path)

    # Before unlock: repr/str must not contain password or any part of the
    # encrypted keystore JSON (ciphertext / salt / mac / iv).
    r_locked = repr(w)
    s_locked = str(w)
    assert password not in r_locked
    assert password not in s_locked
    assert _TEST_EVM_HEX not in r_locked
    assert _TEST_EVM_HEX not in s_locked
    assert "(locked)" in r_locked

    encrypted = json.loads(path.read_text())
    crypto = encrypted.get("crypto") or encrypted.get("Crypto") or {}
    ciphertext = crypto.get("ciphertext", "")
    if ciphertext:
        assert ciphertext not in r_locked
        assert ciphertext not in s_locked

    # Trigger unlock, then re-check.
    _ = w.address("ethereum")
    r_unlocked = repr(w)
    assert password not in r_unlocked
    assert _TEST_EVM_HEX not in r_unlocked
    if ciphertext:
        assert ciphertext not in r_unlocked
    assert "(unlocked)" in r_unlocked


# ---------------------------------------------------------------------------
# Ledger stub
# ---------------------------------------------------------------------------

def test_ledger_stub_raises():
    with pytest.raises(NotImplementedError):
        LedgerWallet()
    with pytest.raises(NotImplementedError):
        LedgerWallet("some", kw="arg")
