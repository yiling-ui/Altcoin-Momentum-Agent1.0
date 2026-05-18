# Phase 3 Contract (Issue #3)

This document is the **single source of truth** for the read-only Exchange
Gateway introduced by Phase 3. It is version-controlled so the contract
travels with the code, not with the PR description on GitHub.

If anything in `app/exchanges/` ever disagrees with this file, this file
wins and the code must be fixed. The test suite asserts the same
invariants programmatically; see references below.

---

## 1. Reliability tier table (Spec §13.3)

The default reliability tier for each read-only surface is locked as:

| Surface                | Default tier | Source                                  |
| ---------------------- | ------------ | --------------------------------------- |
| `get_recent_trades`    | **A**        | WS aggTrade / trade stream              |
| `get_orderbook`        | **A**        | WS depth-diff maintained book           |
| `get_funding_rate`     | **B**        | REST                                    |
| `get_open_interest`    | **B**        | REST                                    |
| `get_symbols`          | **B**        | REST exchangeInfo                       |
| `get_account_snapshot` | **B**        | mock-only / skeleton-only in Phase 3+4  |

Both tier-A surfaces are explicitly **`get_orderbook` AND
`get_recent_trades`**. There is no other interpretation.

A REST-fallback orderbook taken when the WS link is degraded must be
tagged tier B explicitly on the response model (`OrderBook(...,
reliability=DataReliability.B)`); the *default* mapping above describes
the canonical, healthy-link tier - not the worst case.

**Locked by:**
- `app/exchanges/base.ExchangeClientBase.reliability_tiers` (the dict
  the runtime returns)
- `app/exchanges/models.OrderBook.reliability` default = `DataReliability.A`
- `app/exchanges/mock.MockExchangeClient.get_orderbook` (synthetic
  book stamped tier A)
- `tests/unit/test_exchange_base.py::test_reliability_tiers_contract`
  (full-table dict equality)
- `tests/unit/test_exchange_base.py::test_get_orderbook_is_tier_a`
- `tests/unit/test_exchange_base.py::test_get_recent_trades_is_tier_a`
- `tests/unit/test_exchange_base.py::test_get_funding_rate_is_tier_b`
- `tests/unit/test_exchange_base.py::test_get_open_interest_is_tier_b`
- `tests/unit/test_exchange_base.py::test_get_symbols_is_tier_b`
- `tests/unit/test_exchange_base.py::test_get_account_snapshot_is_tier_b`
- `tests/unit/test_phase3_contract_doc.py` (asserts this file states
  the table verbatim)

---

## 2. Phase 4 invariants (Issue #4 - Market Data Buffer)

The Phase 4 PR **must** obey all five rules below. Any drift is a hard
review failure and must block merge.

1. **Mock / fixture data is the default.** Phase 4 implements the
   Market Data Buffer driven by `MockExchangeClient` and / or static
   fixture files. Real-network adapters are not required to land in
   Phase 4.
2. **Any real public read-only adapter is opt-in only.** If Phase 4
   chooses to land a real public WS / REST adapter at all, it MUST
   ship behind an explicit, off-by-default toggle. It MUST NOT
   auto-connect to the real exchange under any default code path,
   test path, CI path, or boot path.
3. **No API key. No credentials.** The Phase 4 adapter MUST refuse
   credentials at construction time, exactly as `BinanceClient` does
   today. No `os.environ` lookup of a key. No `.env` ingestion of a
   key. No "if the key is set we'll use it" branch.
4. **No write surface. Ever.** The Phase 4 adapter MUST NOT add a
   `create_order`, `cancel_order`, `set_leverage`, or
   `set_margin_mode` method override. The base-class
   `SafeModeViolation` refusal must continue to fire.
5. **Tests must not depend on real network.** Phase 4 unit tests run
   without internet access. Any new test that talks to a real
   exchange must be quarantined behind an explicit opt-in marker that
   is **off in CI** and is not enabled by `pytest` with no flags.

The earliest a real authenticated adapter (account-data WS,
order-event stream, signed REST) may exist in this repository is
**Phase 9 (Reconciliation)**, behind the Risk Engine, behind the
Phase 1 safety lock, behind a deliberate Go / No-Go review.

**Locked by:**
- `app/exchanges/binance.py` - every `NotImplementedError` message
  for the five public-data surfaces restates these constraints
  verbatim.
- `tests/unit/test_binance_client.py
  ::test_binance_real_market_data_methods_message_is_explicit_about_phase4_constraints`
  (asserts every message contains the constraint phrases)
- `tests/unit/test_phase3_no_network.py` (asserts no exchange SDK,
  no outbound HTTP / WS library is imported)

---

## 3. `get_account_snapshot` is mock-only / skeleton-only in Phase 3 and Phase 4

A real account snapshot needs an authenticated REST call and an API
key. Both are forbidden until the limited-live phase. Therefore:

- **Phase 3:** `BinanceClient.get_account_snapshot` raises
  `NotImplementedError`. The only working implementation is
  `MockExchangeClient.get_account_snapshot`.
- **Phase 4:** SAME. `BinanceClient.get_account_snapshot` continues to
  raise `NotImplementedError`. Phase 4 is allowed to wire
  `MockExchangeClient.get_account_snapshot` into the Capital Flow
  Engine plumbing (Issue #8 will replace this with the real source
  later), but it MUST NOT add an authenticated REST call to
  `BinanceClient`.

The earliest a real authenticated account snapshot may land is
**Issue #9 (Reconciliation)**, behind the Risk Engine.

**Locked by:**
- `app/exchanges/binance.BinanceClient.get_account_snapshot` raises
  `NotImplementedError` whose message names "API key",
  "authenticated", "MockExchangeClient", and "limited-live".
- `tests/unit/test_binance_client.py
  ::test_binance_get_account_snapshot_message_is_explicit_about_no_api_key`
  (asserts the message contains those four tokens)

---

## 4. Phase 3 hard refusals (unchanged from Issue #3 acceptance)

The four write surfaces on `ExchangeClientBase` are **concrete on the
base class** and **always raise `SafeModeViolation`**. Subclasses
inherit the refusal:

- `create_order`
- `cancel_order`
- `set_leverage`
- `set_margin_mode`

The Phase 1 safety lock (`trading_mode=paper`, `live_trading_enabled=False`,
`right_tail_enabled=False`, `llm_enabled=False`,
`exchange_live_order_enabled=False`) is unchanged. The Phase 3 boot
self-check `_assert_phase3_read_only(client)` in `app/main.py`
additionally probes every banned write surface at boot and refuses to
start unless each one raises `SafeModeViolation`.

---

## Change control

This file is the contract. To change it:

1. Open a PR that updates **both** this file and the matching code /
   tests in the same commit.
2. Update the spec reference (`docs/AMA_RT_V1_4_Production_Spec_Kiro.md`)
   if the change crosses a §13 / §14 / §31 boundary.
3. Re-run the Go / No-Go checklist (Spec §41) before any tier or
   safety-lock relaxation lands on `main`.

Last updated: Phase 3 review fixes, Issue #3 (PR #14).
