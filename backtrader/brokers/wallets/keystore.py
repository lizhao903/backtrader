#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# LocalKeystoreWallet: EVM wallet backed by a Web3 Secret Storage JSON file.
#
# Decryption is lazy (on first ``address`` / ``sign_evm_tx`` call) and the
# password is read from the ``BT_KEYSTORE_PASSWORD`` env var so it never
# becomes a constructor argument that might leak into logs or tracebacks.
#
###############################################################################
"""Local-keystore-backed wallet implementation.

This module reads an encrypted Web3 Secret Storage JSON (the format produced
by ``geth account new`` and ``eth_account.Account.encrypt``) and decrypts it
on demand using the password found in ``BT_KEYSTORE_PASSWORD``. The decrypted
``eth_account.Account`` object is cached in memory for the lifetime of the
wallet instance; the password itself is never stored on the instance.

Solana signing is intentionally unsupported here -- use ``EnvVarWallet`` or a
future ``SolanaKeystoreWallet`` for Solana keys.
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import json
import os
from pathlib import Path
from typing import Any, Union

from . import SigningError, WalletBase, WalletError, WalletNotConfigured


# Optional dep -- imported lazily so that importing this module does not fail
# when eth_account is missing. Construction / unlock raise a clear error if
# the library is actually needed.
try:
    from eth_account import Account as _EthAccount  # type: ignore
    _HAS_ETH_ACCOUNT = True
except Exception:  # pragma: no cover - import guard
    _EthAccount = None
    _HAS_ETH_ACCOUNT = False


class LocalKeystoreWallet(WalletBase):
    """EVM keystore-backed wallet using eth_account's Web3 Secret Storage format.

    Reads an encrypted keystore JSON file (SCrypt or PBKDF2) and caches the
    decrypted private key in memory only. Password comes from env var
    ``BT_KEYSTORE_PASSWORD`` -- never passed via constructor argument to avoid
    accidental leak into logs.

    Solana keystore is NOT supported by this implementation -- Solana wallets
    should continue to use ``EnvVarWallet`` or a future ``SolanaKeystoreWallet``.
    """

    CHAINS = frozenset({"ethereum", "arbitrum", "base", "bsc", "polygon"})
    PASSWORD_ENV_VAR = "BT_KEYSTORE_PASSWORD"

    def __init__(self, keystore_path):
        # type: (Union[str, Path]) -> None
        path = Path(keystore_path)
        if not path.exists():
            raise FileNotFoundError(
                "keystore file does not exist: %s" % path)
        if not path.is_file():
            raise WalletError(
                "keystore path is not a regular file: %s" % path)

        # Basic sanity check: the file must be JSON with ``address`` / ``crypto``
        # top-level keys (the Web3 Secret Storage shape). We do NOT decrypt
        # yet -- decryption is deferred to the first ``_unlock`` call.
        try:
            with path.open("r") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise WalletError(
                "failed to read keystore JSON at %s: %s" % (path, exc))

        if not isinstance(data, dict):
            raise WalletError(
                "keystore JSON at %s is not an object" % path)
        # eth_account tolerates both ``crypto`` and ``Crypto`` (case variants);
        # we accept either for the sanity check.
        has_crypto = "crypto" in data or "Crypto" in data
        if "address" not in data or not has_crypto:
            raise WalletError(
                "keystore JSON at %s is missing required 'address' or "
                "'crypto' fields" % path)

        self._keystore_path = path
        self._keystore_dict = data
        self._account = None  # populated lazily by _unlock()

    # -- internal ---------------------------------------------------------

    def _unlock(self):
        # type: () -> None
        """Decrypt the keystore and cache the ``Account`` object."""
        if self._account is not None:
            return
        if not _HAS_ETH_ACCOUNT:
            raise NotImplementedError(
                "install eth_account to use LocalKeystoreWallet "
                "(pip install eth-account)")

        password = os.environ.get(self.PASSWORD_ENV_VAR)
        if not password:
            raise WalletNotConfigured(
                "%s not set" % self.PASSWORD_ENV_VAR)

        try:
            privkey = _EthAccount.decrypt(self._keystore_dict, password)
        except Exception as exc:
            raise SigningError(
                "failed to decrypt keystore at %s: %s"
                % (self._keystore_path, exc))

        try:
            self._account = _EthAccount.from_key(privkey)
        finally:
            # Best-effort erase of the raw private key from local scope.
            del privkey

    # -- WalletBase API ---------------------------------------------------

    def address(self, chain):
        # type: (str) -> str
        if chain not in self.CHAINS:
            raise WalletError("unsupported chain %r" % chain)
        self._unlock()
        return str(self._account.address)

    def sign_evm_tx(self, tx):
        # type: (dict) -> bytes
        self._unlock()
        try:
            signed = self._account.sign_transaction(tx)
        except Exception as exc:
            raise SigningError("EVM signing failed: %s" % exc)
        return bytes(signed.rawTransaction)

    def sign_sol_tx(self, tx):
        # type: (Any) -> bytes
        raise NotImplementedError(
            "LocalKeystoreWallet does not support Solana; use EnvVarWallet "
            "or a dedicated SolanaKeystoreWallet")

    # -- safety -----------------------------------------------------------

    def __repr__(self):
        state = "unlocked" if self._account is not None else "locked"
        return "<LocalKeystoreWallet path=%s (%s)>" % (
            self._keystore_path, state)

    __str__ = __repr__
