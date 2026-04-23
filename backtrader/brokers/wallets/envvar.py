#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# EnvVarWallet: reads private keys from environment variables.
#
# This wallet is intended for development, CI and small-scale live sessions.
# For production setups prefer ``LocalKeystoreWallet`` (Seg 3) or a hardware
# wallet backend. Private keys are never logged and never exposed via
# ``str`` / ``repr``.
#
###############################################################################
"""Environment-variable-backed wallet implementation.

Env var conventions:
  * ``BT_EVM_PRIVKEY`` -- hex-encoded EVM private key (optional ``0x``
    prefix). One key is shared across all EVM chains.
  * ``BT_SOL_PRIVKEY`` -- hex-encoded (or base58) Solana secret key.

Address derivation and signing depend on optional third-party libraries
(``eth_account`` for EVM, ``solders`` for Solana). If those libraries are
not installed the wallet still constructs, but ``address`` returns a
deterministic placeholder and signing raises ``NotImplementedError`` with
an install hint.

For real deployments, use ``LocalKeystoreWallet`` (Seg 3) instead.
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
from typing import Any, Tuple

from . import SigningError, WalletBase, WalletNotConfigured


# Optional deps -- imported lazily so the scaffold is usable without them.
try:
    from eth_account import Account as _EthAccount  # type: ignore
    _HAS_ETH_ACCOUNT = True
except Exception:  # pragma: no cover - import guard
    _EthAccount = None
    _HAS_ETH_ACCOUNT = False

try:
    from solders.keypair import Keypair as _SolKeypair  # type: ignore
    _HAS_SOLDERS = True
except Exception:  # pragma: no cover - import guard
    _SolKeypair = None
    _HAS_SOLDERS = False


_EVM_ENV = "BT_EVM_PRIVKEY"
_SOL_ENV = "BT_SOL_PRIVKEY"

_EVM_CHAINS = frozenset({"ethereum", "arbitrum", "base", "bsc", "polygon"})
_SOL_CHAINS = frozenset({"solana"})


class EnvVarWallet(WalletBase):
    """Wallet backed by environment variables.

    Parameters
    ----------
    require : tuple of str, optional
        Chain identifiers for which configuration is mandatory. If the
        corresponding env var is missing for any required chain,
        ``WalletNotConfigured`` is raised from ``__init__``.
    """

    CHAINS = _EVM_CHAINS | _SOL_CHAINS

    def __init__(self, require=()):
        # type: (Tuple[str, ...]) -> None
        # Store nothing sensitive on ``self``: keys are re-read from env on
        # demand so they can be rotated without reconstructing the wallet,
        # and so ``repr`` / ``str`` cannot accidentally leak them.
        self._require = tuple(require)
        for chain in self._require:
            if not self._has_key_for(chain):
                raise WalletNotConfigured(
                    "missing env var for chain %r" % chain)

    # -- internal helpers -------------------------------------------------

    @staticmethod
    def _env_for(chain):
        # type: (str) -> str
        if chain in _EVM_CHAINS:
            return _EVM_ENV
        if chain in _SOL_CHAINS:
            return _SOL_ENV
        raise WalletNotConfigured("unsupported chain %r" % chain)

    def _has_key_for(self, chain):
        # type: (str) -> bool
        try:
            env = self._env_for(chain)
        except WalletNotConfigured:
            return False
        return bool(os.environ.get(env))

    def _get_key(self, chain):
        # type: (str) -> str
        env = self._env_for(chain)
        val = os.environ.get(env)
        if not val:
            raise WalletNotConfigured(
                "env var %s is not set for chain %r" % (env, chain))
        return val

    @staticmethod
    def _normalize_hex(s):
        # type: (str) -> str
        s = s.strip()
        if s.startswith("0x") or s.startswith("0X"):
            s = s[2:]
        return s

    # -- WalletBase API ---------------------------------------------------

    def address(self, chain):
        # type: (str) -> str
        if not self.supports(chain):
            raise WalletNotConfigured("unsupported chain %r" % chain)
        key = self._get_key(chain)  # raises if missing

        if chain in _EVM_CHAINS:
            if _HAS_ETH_ACCOUNT:
                try:
                    acct = _EthAccount.from_key("0x" + self._normalize_hex(key))
                    return str(acct.address)
                except Exception as exc:  # pragma: no cover - lib error path
                    raise SigningError(
                        "failed to derive EVM address: %s" % exc)
            # Placeholder when eth_account not installed. Real addresses
            # require Seg 3's LocalKeystoreWallet.
            return "0x" + "0" * 40

        if chain in _SOL_CHAINS:
            if _HAS_SOLDERS:
                try:
                    raw = self._normalize_hex(key)
                    # Accept hex-encoded secret; solders also accepts base58
                    # via ``Keypair.from_base58_string``. Try hex first.
                    try:
                        kp = _SolKeypair.from_seed(bytes.fromhex(raw)[:32])
                    except Exception:
                        kp = _SolKeypair.from_base58_string(key)
                    return str(kp.pubkey())
                except Exception as exc:  # pragma: no cover
                    raise SigningError(
                        "failed to derive Solana address: %s" % exc)
            return "1" * 32  # placeholder (non-empty, clearly fake)

        raise WalletNotConfigured("unsupported chain %r" % chain)

    def sign_evm_tx(self, tx):
        # type: (dict) -> bytes
        key = self._get_key("ethereum")
        if not _HAS_ETH_ACCOUNT:
            raise NotImplementedError(
                "install eth_account for EVM signing (pip install eth-account)")
        try:
            signed = _EthAccount.sign_transaction(
                tx, "0x" + self._normalize_hex(key))
            return bytes(signed.rawTransaction)
        except Exception as exc:
            raise SigningError("EVM signing failed: %s" % exc)

    def sign_sol_tx(self, tx):
        # type: (Any) -> bytes
        key = self._get_key("solana")
        if not _HAS_SOLDERS:
            raise NotImplementedError(
                "install solders for Solana signing (pip install solders)")
        try:
            raw = self._normalize_hex(key)
            try:
                kp = _SolKeypair.from_seed(bytes.fromhex(raw)[:32])
            except Exception:
                kp = _SolKeypair.from_base58_string(key)
            # tx is expected to expose ``sign`` / serialize via solders API.
            if hasattr(tx, "sign"):
                tx.sign([kp])
            if hasattr(tx, "serialize"):
                return bytes(tx.serialize())
            return bytes(tx)
        except NotImplementedError:
            raise
        except Exception as exc:
            raise SigningError("Solana signing failed: %s" % exc)

    # -- safety -----------------------------------------------------------

    def __repr__(self):
        # Never include any env var values in repr / str.
        return "<EnvVarWallet require=%r>" % (self._require,)

    __str__ = __repr__
