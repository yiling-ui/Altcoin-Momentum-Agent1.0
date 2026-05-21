"""AMA-RT Altcoin Momentum Agent - Right Tail Edition.

Phase 11C: Real Binance Public Market Data Read-Only Paper
(Issue #11C).

This package is paper-mode by default and contains NO live trading
code. Every Phase 1-11B contract remains in force. Phase 11C ADDS
the FIRST real-exchange surface in the project: a public-market,
read-only Binance USDT-M perpetual futures gateway driven through
the existing :class:`MarketDataBuffer`, the :class:`RiskEngine`,
and the Phase 8.5 learning-ready contract.

Phase 11C is constrained:

  - The five Phase 1 safety flags remain locked. ``llm_enabled``
    stays ``False`` at boot. Phase 11C does not flip any of them.
  - ``binance_private_api_enabled`` stays ``False``. The
    :class:`app.exchanges.binance_public.BinancePublicClient`
    constructor refuses ``api_key`` / ``api_secret``.
  - ``telegram_outbound_enabled`` stays ``False``. The Phase 11C
    runner uses :class:`FakeTelegramClient` from
    :mod:`app.telegram.outbound`.
  - The four ExchangeClientBase write surfaces (``create_order``
    / ``cancel_order`` / ``set_leverage`` / ``set_margin_mode``)
    continue to raise :class:`SafeModeViolation` on the public
    client.
  - The endpoint allowlist
    (:data:`app.exchanges.binance_public.PUBLIC_MARKET_ENDPOINT_ALLOWLIST`)
    enumerates every URL the public client may issue. Any signed
    or private endpoint is refused with
    :class:`SafeModeViolation`.
  - No third-party HTTP / WebSocket / exchange / LLM / Telegram
    bot library is imported anywhere in the Phase 11C source set.
    The default REST transport uses :mod:`urllib.request` from
    the Python standard library.
  - No ``api_key`` / ``api_secret`` / ``bot_token`` parameter or
    concrete env-var literal lives anywhere under
    :mod:`app.exchanges.binance_public` or
    :mod:`app.market_data_public`. Env inspection is delegated to
    the Phase 11B :class:`EnvGuard`.

Phase 1 - 10D contracts that remain in force are unchanged.

Phase 11C does NOT implement:

  - Real WebSocket transport (the ``websocket_enabled`` flag is
    accepted as a future-capability hook; Phase 11C ships the
    REST poller only).
  - Real account / position / equity persistence (the public
    client refuses every authenticated endpoint).
  - LLM-driven trade decisions / direction / leverage /
    target_price.
  - Real network access in the test suite (every test injects a
    deterministic ``transport`` callable).
  - Phase 12. Passing Phase 11C does NOT authorise Phase 12.
"""

__version__ = "1.4.0a11c"
__phase__ = "Phase 11C - Real Binance Public Market Data Read-Only Paper"
