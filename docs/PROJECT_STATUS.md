# AMA-RT Project Status

This document is the at-a-glance status board for AMA-RT V1.4. It is
intentionally short. The full phase-gate ledger lives in
`docs/PHASE_GATE.md`; per-phase deep dives live in their own
`PHASE_*` documents.

| Date (UTC) | Phase    | Tag                                        | State   | Evidence                                                |
| ---------- | -------- | ------------------------------------------ | ------- | ------------------------------------------------------- |
| 2026-05-21 | Phase 11C.1A | Binance Public REST Rate Limit Governor & 418 Protection | in-development | `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md` §11C.1A     |
| 2026-05-21 | Phase 11C | Real Binance Public Market Data Read-Only Paper | paused (rate-limit fix in progress) | `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md`             |
| 2026-05-19 | Phase 11B-HF | Cloud Paper - High-Frequency observation     | accepted (GO) | 30/30 dry-run PASS, 648/648 24h@2min observations PASS |
| 2026-05-19 | Phase 11B | Cloud Paper Acceptance                       | accepted (GO) | `docs/PHASE_11B_PAPER_ACCEPTANCE_REPORT.md`            |
| ...        | Phase 10D | Telegram Outbound + Export Commands          | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 10C | LLM Guarded Interpreter (receive-only)       | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 10B | Reflection + Replay engines (read-only)      | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 10A | Replay engine substrate                      | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 9   | Execution FSM + Reconciliation               | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 8.5 | Learning-Ready Data Contract                 | merged        | `docs/PHASE_8_5_TELEGRAM_EXPORT_CONTRACT.md`           |
| ...        | Phase 8   | Capital Flow Engine                          | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 7   | Risk Engine + No-Trade Gate                  | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 6   | Pre-Anomaly + Anomaly + Confirmation + Manipulation | merged | `docs/CHANGELOG.md`                                  |
| ...        | Phase 5   | Regime + Universe + Liquidity                | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 4   | Market Data Buffer                           | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 3   | Exchange Gateway (read-only abstract)        | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 2   | Event Sourcing + Database Set                | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 1   | Safety Foundation                            | merged        | `docs/CHANGELOG.md`                                    |

## Live safety flags (Phase 1 lock)

```
trading_mode                    = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
```

The Phase 1 safety lock in `app/config/settings.py::_apply_phase1_safety_lock`
hard-coerces the first five flags. The Phase 11C
`MarketDataConfig` and `SafetyConfig` schemas refuse to load any
deployment that flips a `forbid_*` flag.

## Why the Phase 11C real-data acceptance is paused

The first 24h test against the real Binance public REST endpoints
(`fapi.binance.com`) exposed two failure modes the original Phase 11C
runner did not protect against:

  1. HTTP 429 (Too Many Requests). Binance returned this once the
     per-IP weight budget was exceeded. The runner kept polling and
     escalated to:
  2. HTTP 418 (I'm a teapot). Binance uses 418 to signal a real IP
     ban.

Phase 11C's safety lock held throughout (`mode=paper`,
`live_trading=False`, no API key, no signed endpoint, no real order),
but the gateway was unusable for real-data acceptance until the
rate-limit problem is fixed.

**Phase 11C.1A** (PR-A in this branch) ships the fix in three layers:

  - a new `BinancePublicRestGovernor`
    (`app/exchanges/binance_rate_limit.py`) that wraps every public
    REST call, tracks the rolling weight budget, sleeps the
    `Retry-After` window on 429, latches into protection mode on
    418, and opens a P1 incident;
  - lower defaults (`symbol_limit=5`, `rest_poll_interval_seconds=60`,
    `weight_budget_per_minute=300`, soft 0.50 / hard 0.75);
  - a layered REST runner that does `exchangeInfo` / `ticker/24hr`
    only at bootstrap and refuses per-symbol detail REST calls
    unless a candidate ranking selects them (PR-B work).

PR-B (WebSocket-first all-market radar) and PR-C (cluster exposure
control + multi-candidate priority ranking) are tracked separately
and have NOT landed in this branch.

## What Phase 11C is

Phase 11C is real **Binance public market data** read-only paper.
It connects to public REST endpoints (`/fapi/v1/exchangeInfo`,
`/fapi/v1/ticker/24hr`, `/fapi/v1/klines`, `/fapi/v1/aggTrades`,
`/fapi/v1/depth`, `/fapi/v1/fundingRate`, `/fapi/v1/openInterest`,
`/fapi/v1/premiumIndex`, `/fapi/v1/ticker/bookTicker`), feeds the
data through the existing `MarketDataBuffer` and Risk Engine, and
emits the full Phase 11C event chain into `events.db`.

## What Phase 11C is NOT

- NOT live trading
- NOT connected to the Binance trading API
- NOT consuming any Binance API key / API secret
- NOT calling any signed endpoint
- NOT calling any account / position / leverage / margin endpoint
- NOT connected to DeepSeek
- NOT connected to a real Telegram bot
- NOT connected to 币安广场
- NOT a path into Phase 12

## Open phase

**Phase 11C.1A - Binance Public REST Rate Limit Governor & 418
Protection.** Acceptance criteria + test matrix in
`docs/PHASE_11C_PUBLIC_MARKET_READONLY.md` §11C.1A. Acceptance
gate: every test in `tests/unit/test_phase11c1a_rate_limit_governor.py`
passes; the four ExchangeClientBase write surfaces still refuse;
the Phase 1 safety lock is unchanged; the Phase 11C real-data
acceptance run is held until PR-A merges.
