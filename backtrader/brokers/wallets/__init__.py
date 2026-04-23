#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Wallet abstraction layer for live trading.
#
# This package defines the ``WalletBase`` abstract interface that broker
# implementations rely on for key management and transaction signing across
# multiple chains (EVM + Solana). Concrete wallet backends (env var, local
# keystore, hardware wallets) live in sibling modules and are imported
# explicitly by the caller to keep import-time side effects minimal.
#
###############################################################################
"""Wallet abstraction layer for live trading brokers.

See ADR 0001 (live-trading). Concrete implementations are loaded on demand,
e.g. ``from backtrader.brokers.wallets.envvar import EnvVarWallet``.
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import abc
from typing import Any


class WalletError(Exception):
    """Base class for all wallet-related errors."""


class WalletNotConfigured(WalletError):
    """Raised when required wallet configuration (e.g. env vars) is missing."""


class SigningError(WalletError):
    """Raised when a transaction cannot be signed."""


class WalletBase(abc.ABC):
    """Abstract base class for all wallet implementations.

    Subclasses must declare ``CHAINS`` (a ``frozenset`` of chain identifiers
    they support) and implement ``address`` / ``sign_evm_tx`` / ``sign_sol_tx``.
    """

    # Subclasses override with the set of chains they support.
    CHAINS: frozenset = frozenset()

    @abc.abstractmethod
    def address(self, chain):
        # type: (str) -> str
        """Return the public address for ``chain``."""
        raise NotImplementedError

    @abc.abstractmethod
    def sign_evm_tx(self, tx):
        # type: (dict) -> bytes
        """Sign an EVM transaction dict and return raw signed bytes."""
        raise NotImplementedError

    @abc.abstractmethod
    def sign_sol_tx(self, tx):
        # type: (Any) -> bytes
        """Sign a Solana transaction (VersionedTransaction in the future)."""
        raise NotImplementedError

    def supports(self, chain):
        # type: (str) -> bool
        """Return True iff this wallet supports ``chain``.

        Default implementation consults the ``CHAINS`` class attribute;
        subclasses may override for more dynamic behavior.
        """
        return chain in self.CHAINS


__all__ = [
    "WalletBase",
    "WalletError",
    "WalletNotConfigured",
    "SigningError",
]
