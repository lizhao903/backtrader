#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# LedgerWallet: stub for future hardware Ledger integration.
#
# The real implementation will use either ``ledgerblue`` or ``ledgereth`` and
# shell out through the Ledger transport layer. Until that lands in a
# follow-up issue, constructing this class raises ``NotImplementedError`` so
# that callers fail fast rather than silently getting a non-functional wallet.
#
###############################################################################
"""Stub Ledger hardware-wallet implementation.

This class exists so that downstream code can ``import`` a ``LedgerWallet``
symbol today, but any attempt to actually construct one raises
``NotImplementedError`` pointing at the follow-up issue.
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from . import WalletBase


class LedgerWallet(WalletBase):
    """Stub for hardware Ledger wallet integration.

    Will use ``ledgerblue`` or ``ledgereth`` in a future issue. TODO: Issue TBD.
    """

    CHAINS = frozenset({"ethereum", "arbitrum", "base", "bsc", "polygon"})

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "LedgerWallet is not implemented yet. "
            "Scheduled for a follow-up issue."
        )

    # Abstract methods -- must exist for subclass concreteness, even if
    # unreachable because ``__init__`` always raises.
    def address(self, chain):
        raise NotImplementedError

    def sign_evm_tx(self, tx):
        raise NotImplementedError

    def sign_sol_tx(self, tx):
        raise NotImplementedError
