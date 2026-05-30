"""AMA-RT Live API Integration Pack v0 (PR111).

This package is the FIRST place in the project allowed to hold real
Binance / Telegram / DeepSeek API *credentials* and to talk to those
real private / authenticated APIs. It exists to build the foundation
for the live-capital road map (LIVE_SHADOW -> LIVE_LIMITED -> ...).

PR111 boundary (hard rules)
---------------------------

PR111 connects real external APIs but **does NOT place, cancel, or
modify any real order**, and does **NOT** change leverage / margin
mode. Concretely:

  - Binance ``PUBLIC_MARKET`` + ``PRIVATE_READ`` layers may talk to the
    real exchange (ping / exchangeInfo / mark price / account / balance
    / positions / income history).
  - The Binance ``PRIVATE_TRADE`` layer is an interface **only**. Every
    trade method is blocked by default and either returns
    ``TRADE_API_BLOCKED_BY_PR111`` or raises
    :class:`app.core.errors.LiveTradeNotEnabled`. No HTTP order request
    is ever built or sent in PR111.
  - Telegram outbound is gated by config and disabled by default; a
    test message is sent only when the operator explicitly enables
    outbound AND asks for the test.
  - DeepSeek output is MARKET_INTELLIGENCE_ONLY. It can never carry
    trade-authority fields (direction / size / leverage / stop /
    target / execution). ``ai_trade_authority`` is pinned ``False``.
  - No API key / secret / token is ever hard-coded, logged, exported,
    embedded in a Telegram message, or placed in an exception text.
    Only masked forms (``abc***xyz``) ever surface.
  - The default live runtime mode is :class:`LiveRuntimeMode.LIVE_SHADOW`
    which keeps the order path blocked even if a trade-capable API key
    is configured.

Relationship to PR110
---------------------

PR111 is designed to dock onto the PR110 "Live Path Isolation" /
``LIVE_SHADOW`` / ``LIVE_LIMITED`` runtime modes and the PR110
Capital Event Contract. While PR110 is in review, this package ships a
self-contained :class:`LiveRuntimeMode` and a self-contained
:class:`app.live.capital_events.CapitalEvent` contract that are
intentionally shaped to be unified with PR110's once both land. Search
this package for ``HANDOFF`` to find the unification points.
"""

from __future__ import annotations

LIVE_API_PACK_VERSION = "v0"
LIVE_API_PACK_PR = "PR111"

__all__ = ["LIVE_API_PACK_VERSION", "LIVE_API_PACK_PR"]
