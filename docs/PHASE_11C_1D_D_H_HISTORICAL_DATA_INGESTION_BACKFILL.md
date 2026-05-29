# Phase 11C.1D-D-H — Historical Data Ingestion / Backfill v0 (PR101)

> **Status: IN_REVIEW** (after this implementation PR; **NOT**
> `ACCEPTED` until maintainer review).
> **Type: paper / report / evidence-only infrastructure.**
> mode = `historical_blind_sim_live`. Paper-only, sandbox-only.
> **Phase 12 remains FORBIDDEN.**

This document describes the **eighth** anti-future-lookahead
infrastructure block of the strict blind walk-forward stack defined by
Phase 11C.1D-D (PR93, the *Strict Blind Walk-forward Sim-Live
Constitution*). PR101 ships the historical-data ingestion / backfill
foundation that turns local files into the PR95 record types and
produces the data / universe manifests + coverage / gap audit that the
later strict forward-only blind walk-forward runs will consume.

PR101 is **strictly a data-coverage layer.** A successful PR101 run
proves only **which historical data we have and how complete it is**.
It does **NOT** prove that any strategy is profitable, that any
direction/entry/exit is correct, or that any window is "ready to
trade".

---

## 1. Purpose

- Convert **local file** rows (klines / funding / open interest /
  24h ticker / exchangeInfo / symbol status) into the PR95 record
  types (`HistoricalKlineRecord`, `HistoricalMarketRecord`,
  `SymbolStatusRecord`).
- Compute the four-timestamp record-time model (`event_time` /
  `available_at` / `ingested_at` / `source`) and enforce
  timezone-aware UTC.
- Build a deterministic **data manifest** (record counts, per-symbol
  coverage, data-gap summary, `data_manifest_hash`) and a
  **universe manifest** (as-of universe, no survivorship bias,
  `universe_manifest_hash`).
- Emit a coverage report and a data-gap report.
- Provide a `records.jsonl` dump that a `HistoricalMarketStore` can
  load under its strict `available_at <= simulated_time` gate.

This phase **does not require network access**. It is a file-based
ingestion framework / parser / manifest / coverage report / fixture
harness. Real data download or long-running cloud backfill is a
**later operator run**, not part of PR101.

## 2. Relation to PR93 (Constitution)

PR101 obeys the Strict Blind Walk-forward Sim-Live Constitution:

- **§5 (four timestamps).** Every record distinguishes `event_time`
  / `available_at` / `ingested_at` / `source`. `ingested_at` is
  **NEVER** substituted for `available_at`.
- **§6 (closed-candle visibility).** A kline's `available_at` is
  derived from `close_time + lag`; the PR95 record type rejects any
  `available_at < close_time`.
- **§9 (no survivorship bias).** The universe manifest retains every
  `SymbolStatusRecord` — including delisted symbols — and
  reconstructs the as-of universe from the listing/delisting timeline,
  never from the current symbol list.

## 3. Relation to PR95 (Historical Market Store)

PR101 is the **feeder** for PR95. It reuses, verbatim and
unmodified:

- `HistoricalMarketRecord`, `HistoricalKlineRecord`,
  `SymbolStatusRecord`,
- `HistoricalMarketRecordType`, `DataQualityFlag`,
  `DataCompletenessState`, `SymbolStatus`,
- `HistoricalMarketStore` (via `HistoricalDataIngestion.build_store()`),
- `TimeWallGuard` / `CandleVisibilityGuard` (transitively, through the
  store and record types).

PR101 does not change any PR95 behaviour.

## 4. Relation to PR100 (Blind Runner)

PR100's `BlindRunManifest` pins `data_manifest_hash` and
`universe_manifest_hash`. PR101 is what *produces* those hashes from a
concrete historical dataset. A future operator run will:

1. ingest a window with PR101,
2. feed the resulting store + manifests into the PR100 runner,
3. run a strict forward-only blind walk-forward.

PR101 itself does **NOT** run the blind walk-forward, does **NOT**
implement the 30D / 60D / 90D / 2Y runner, and does **NOT** authorise
any of those steps.

## 5. Supported v0 datasets

| Dataset | Source type | Produces |
| --- | --- | --- |
| 1m / 5m klines | `BINANCE_PUBLIC_KLINE_FILE` / `MANUAL_FIXTURE_FILE` | `HistoricalKlineRecord` |
| Funding rate | `BINANCE_PUBLIC_FUNDING_FILE` | `HistoricalMarketRecord` (`FUNDING_RATE`) |
| Open interest | `BINANCE_PUBLIC_OPEN_INTEREST_FILE` | `HistoricalMarketRecord` (`OPEN_INTEREST`) |
| 24h ticker | `BINANCE_PUBLIC_TICKER_FILE` | `HistoricalMarketRecord` (`TICKER_24H`) |
| exchangeInfo / symbol status | `EXCHANGE_INFO_FILE` / `SYMBOL_STATUS_FILE` | `SymbolStatusRecord` |
| Manual fixture | `MANUAL_FIXTURE_FILE` | any of the above (synthetic) |

Every member of `HistoricalDataSourceType` is a **public / file**
source. The taxonomy NEVER includes a private / signed / account /
order / position / leverage / margin endpoint, a private websocket, or
a listenKey.

### Expected on-disk layout (default discovery)

```
<input_root>/
  klines/<SYMBOL>/<interval>.jsonl        # or klines/<SYMBOL>_<interval>.jsonl
  funding/<SYMBOL>.jsonl
  open_interest/<SYMBOL>.jsonl
  ticker_24h/<SYMBOL>.jsonl
  symbol_status.jsonl                     # or exchange_info.jsonl
```

Each `.jsonl` file holds one JSON value per line; a `.json` file holds
a single top-level JSON array. Kline rows may be dict objects or
Binance public-kline arrays
(`[open_time_ms, o, h, l, c, v, close_time_ms, ...]`).

## 6. event_time / available_at / ingested_at rules

- **`event_time`** — when the underlying market event occurred
  (kline `open_time`, funding settlement time, OI/ticker timestamp,
  symbol `listed_at`).
- **`available_at`** — the earliest time a sim-live consumer could
  legitimately have observed the record:
  - klines: `close_time + default_availability_lag_seconds`
    (Constitution §6),
  - funding / OI / ticker: `event_time + lag`,
  - symbol status: `listed_at + lag`,
  - or an **explicit** `available_at` field if the row carries one.
- **`ingested_at`** — when the record entered the store. It is
  carried through verbatim and is **NEVER** used as a substitute for
  `available_at`.

Timezone-aware UTC is mandatory. Naive datetimes, ISO strings without
an explicit offset, malformed strings, and missing required time
fields are **rejected** (`IngestionTimeFieldError`). The
"explicitly documented metadata exception" for `available_at >=
event_time` is the pre-listing-announcement case on
`SymbolStatusRecord`, where `event_time` may differ from `listed_at`
while still satisfying `available_at >= event_time`.

## 7. Data manifest schema

`HistoricalDataManifest` fields:

- `manifest_id` — `hdm_<first-16-hex-of-hash>` (deterministic),
- `generated_at_utc` — wall-clock metadata (excluded from the hash),
- `input_root`, `start_time`, `end_time`,
- `symbols`, `intervals`, `source_type`,
- `record_counts_by_type`,
- `coverage_by_symbol`,
- `data_gap_summary`,
- `late_arrival_count`, `revised_record_count`,
- `data_manifest_hash` — `sha256:<hex>` over the manifest *content*
  (excludes `generated_at_utc`, `manifest_id`, and the hash itself, so
  identical inputs always carry an identical hash),
- `source_files`, `warnings`,
- hard-pinned `phase_12_forbidden=True`, `auto_tuning_allowed=False`,
  `trade_authority=False`.

## 8. Universe manifest schema

`UniverseManifest` fields:

- `manifest_id` — `uvm_<first-16-hex-of-hash>`,
- `generated_at_utc`, `start_time`, `end_time`,
- `symbols`, `symbol_status_records`,
- `listed_count`, `delisted_count`, `status_unknown_count`,
- `universe_manifest_hash` — `sha256:<hex>`,
- `survivorship_bias_guard=True`,
- `warnings`.

`asof_universe_symbols(simulated_time)` reconstructs the tradable /
monitorable universe from the per-symbol status timeline.

## 9. As-of universe and survivorship-bias prevention

A symbol is in the as-of universe at simulated time `T` iff its latest
*visible* (`available_at <= T`) `SymbolStatusRecord` is tradable /
monitorable, `listed_at <= T`, and (`delisted_at is None` OR
`delisted_at > T`). A delisted symbol is **never** erased from the
manifest; it is simply excluded from the universe at simulated times on
/ after its `delisted_at`. The current symbol list is **never** used to
reconstruct the past.

## 10. Data quality / coverage audit

For each symbol / interval the audit computes expected vs. actual kline
counts over the window, lists missing open-times as gaps, and assigns a
completeness bucket:

- `COMPLETE` — actual / expected ≥ 0.999,
- `PARTIAL` — ≥ 0.90,
- `DEGRADED` — > 0,
- `INSUFFICIENT` — no data.

It also records per-type record counts, symbol-status gaps, and
funding / OI / ticker missing warnings. The thresholds are **module
constants** — they are not runtime knobs, are not loaded from config or
an LLM, are not exposed via CLI, and are not auto-tuned.

## 11. Late-arrival / revision policy

- `late_arrival=True` and an `available_at` later than the
  event/close time are preserved; the record stays invisible until its
  `available_at` (enforced by the store's `TimeWallGuard`).
- `revised_from_record_id` and `revision_time` are carried verbatim and
  the `REVISED_RECORD` data-quality flag is preserved.

## 12. Missing-data behaviour

If `input_root` does not exist or carries no data, the engine returns
`INSUFFICIENT_EVIDENCE` and **NEVER fabricates real market data**. The
result records a warning to that effect.

## 13. Fixture-mode behaviour

A deterministic synthetic dataset is produced **ONLY** when
`fixture_mode` is explicitly enabled (`--fixture-mode`). Every fixture
run emits the warning
`SYNTHETIC_FIXTURE_NOT_REAL_MARKET_DATA: ... this is NOT real market
data and proves nothing about strategy effectiveness`, and fixture
records carry a `MANUAL_FIXTURE_FILE:synthetic` source. Fixture output
is for smoke / wiring tests only.

## 14. Result status taxonomy

`DataIngestionStatus`:

- `EVIDENCE_GENERATED` — records ingested, coverage complete,
- `PARTIAL_EVIDENCE` — records ingested but coverage has gaps,
- `INSUFFICIENT_EVIDENCE` — no records (e.g. missing input),
- `FAILED_SCHEMA_VALIDATION` — schema errors dominate,
- `INVALIDATED_TIME_FIELDS` — one or more rows carry invalid /
  naive / future-relative time fields.

None of these statuses is a strategy-effectiveness conclusion.

## 15. Hard safety boundary

- mode = `historical_blind_sim_live`
- sandbox_only = True, simulated_only = True, no_live_order = True
- live_trading = False
- exchange_live_orders = False
- binance_private_api_enabled = False
- signed_endpoint_reachable = False
- private_websocket_reachable = False
- account / order / position / leverage / margin endpoint = False
- real_exchange_order_path = False
- real_capital = False
- telegram_outbound_enabled = False
- telegram_live_command_authority = False
- ai_trade_authority = False
- trade_authority = False
- auto_tuning_allowed = False
- phase_12_forbidden = True

### Forbidden

- No private API. No signed endpoint / private websocket / listenKey.
- No real account / order / position / leverage / margin endpoint.
- No real exchange order. No real capital.
- No real Telegram outbound. No Telegram command authority.
- No DeepSeek / LLM call. No network call path.
- No auto-tuning. No runtime-config / threshold / symbol-limit /
  candidate-pool / regime-weight / strategy-parameter patch.
- No `api_key` / `api_secret` / `listenKey` / `signed_endpoint` /
  `private_websocket` / `real_order_id` / `exchange_order_id` /
  `enable_live` / `live_ready` / `trading_approved` in any output.
- No coverage report presented as a strategy-effectiveness conclusion.
- No 30D / 60D / 90D / 2Y runner.
- **Phase 12 = FORBIDDEN.**

PR101 does not modify `app/risk/**`, `app/execution/**`,
`app/exchanges/**`, `app/telegram/**`, or `app/config/**`, and does not
change their live behaviour.

## 16. What successful PR101 authorises

Successful PR101 acceptance authorises **only** a *Historical Data
Coverage Checkpoint / short-window no-lookahead trial preparation*. It
does **NOT** authorise live trading, auto-tuning, real Telegram
outbound, real exchange orders, the Binance private API, the
30D / 60D / 90D / 2Y runner, or Phase 12. The Risk Engine remains the
single trade-decision gate.

## 17. Files

- `app/sim/historical_data_manifest.py` — `HistoricalDataSourceType`,
  `DataIngestionStatus`, `HistoricalDataManifest`, `UniverseManifest`,
  hash + safety helpers.
- `app/sim/historical_data_ingestion.py` —
  `HistoricalDataIngestionConfig`, `HistoricalDataIngestionResult`,
  the row parsers, the coverage / gap audit, and the
  `HistoricalDataIngestion` engine.
- `app/sim/__init__.py` — re-exports the new public surface.
- `scripts/run_historical_data_ingestion.py` — operator entry point.
- `tests/unit/test_historical_data_ingestion.py` — 30 PASSING tests.

## 18. Test command

```
python -m pytest tests/unit/test_historical_data_ingestion.py -q
```
