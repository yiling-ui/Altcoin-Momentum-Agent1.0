# PR #65 — Phase 11C.1C-C-B-B-B-D-A.1 Historical 60D Mover Reference Store Builder v0

> **Status: DATA-PREPARATION PR.** Paper / report / evidence only.
> **NOT** live trading. **NOT** AI Learning. **NOT** automatic
> parameter optimisation. **NOT** reinforcement learning. **NOT**
> a strategy implementation. **NOT** a trading module. **NOT** a
> Historical 30D+ / 60D *complete strategy* blind replay /
> walk-forward validation gate. **NOT** the small-money
> live-trading pre-validation gate. **NOT** Phase 12.

## What this PR is

This PR ships **Phase 11C.1C-C-B-B-B-D-A.1**, a small data
preparation sub-task under the Phase 11C.1C-C-B-B-B-D-A
*Historical 60D Mover Coverage Backfill Audit v0* parent slice
(PR #64). It provides a minimal, public-data-only **Historical
60D Mover Reference Store Builder** that produces the
`data/historical_market_store/` artefacts the D-A audit's
`load_historical_market_store(...)` consumes today.

It exists because the D-A audit currently reports
`mover_capture_audit_status=INSUFFICIENT_HISTORY` /
`history_days_observed=0` and
`HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED=0` on the operator-VPS
WS smoke window — the audit ran successfully, but had no local
historical reference data to evaluate against. This PR fills
exactly that gap.

## What this PR is NOT

  - **NOT** a complete strategy blind replay.
  - **NOT** a PnL backtest.
  - **NOT** a trading module.
  - **NOT** AI Learning, automatic parameter optimisation, or
    reinforcement learning.
  - **NOT** the small-money live-trading pre-validation gate.
  - **NOT** Phase 12.
  - **NOT** an authorisation to flip any safety flag.
  - **NOT** the Phase 11C.1C-C-B-B-B-D-A *closeout*. After this
    PR merges, the operator must still produce real 60D
    backfill audit evidence; a separate docs-only closeout PR
    will then flip the slice to `ACCEPTED`.

## Phase ledger effect

  - **Phase 11C.1C-C-B-B-B-D-A.1** is added as a child task
    under Phase 11C.1C-C-B-B-B-D-A.
  - Phase 11C.1C-C-B-B-B-D-A *implementation* has been **merged
    (PR #64)** and the operator-VPS WS paper smoke + Phase 8.5
    export evidence has been validated, but Phase
    11C.1C-C-B-B-B-D-A itself is **NOT yet `ACCEPTED`**. Its
    current state is `NOT_ACCEPTED /
    HISTORICAL_REFERENCE_DATA_REQUIRED / CLOSEOUT_PENDING`:
    real 60D Historical Market Store reference rows have not
    yet been generated, so D-A cannot be flipped to
    `ACCEPTED`. PR #65 only adds the Historical 60D Mover
    Reference Store Builder v0; PR #65 does **NOT** complete
    the real 60D backfill; PR #65 does **NOT** flip D-A to
    `ACCEPTED`. Real 60D data generation against Binance
    public futures endpoints + operator evidence are required
    after PR #65 merges before a separate docs-only closeout
    PR can mark D-A `ACCEPTED`.
  - **No** previously-`ACCEPTED` phase is modified. Phase 12
    remains **FORBIDDEN**.

## Safety boundary (carried verbatim into the builder + every
manifest + every JSONL row)

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - No Binance API key. No Binance API secret. No signed
    endpoint. No `account` / `order` / `position` / `leverage` /
    `margin` endpoint. No private WebSocket. No `listenKey`.
  - No DeepSeek trade decision. No real Telegram outbound.
  - The reference set is **post-hoc audit reference only**. It
    MUST NEVER drive live radar score, candidate promotion,
    the Risk Engine, the Execution FSM, `symbol_limit`,
    candidate-pool capacity, anomaly thresholds, Regime
    weights, or any other runtime knob. The Risk Engine
    remains the single trade-decision gate.
  - Phase 12 remains **FORBIDDEN**.

The builder enforces these invariants directly:

  - Refuses to start if any of `BINANCE_API_KEY`,
    `BINANCE_API_SECRET`, `BINANCE_KEY`, `BINANCE_SECRET`,
    `BINANCE_TOKEN`, or `BINANCE_PASSPHRASE` is set in the
    environment.
  - Refuses every credential-shaped constructor kwarg
    (`api_key`, `api_secret`, `token`, `passphrase`, ...).
  - Refuses every signed-request query parameter
    (`signature`, `timestamp`, `recvWindow`, `apiKey`).
  - Reuses
    `app.exchanges.binance_public.assert_public_endpoint_allowed`
    so any URL outside the Phase 11C public allowlist
    (`/fapi/v1/exchangeInfo`, `/fapi/v1/ticker/24hr`,
    `/fapi/v1/klines`) is refused with `SafeModeViolation`.
  - Calls
    `app.adaptive.historical_mover_coverage_backfill.validate_no_lookahead_fields`
    on every row before writing it; any forbidden lookahead
    field (`completed_tail_label`, `future_return`,
    `final_max_gain`, ...) raises
    `HistoricalMoverLookaheadGuardError` and aborts the run.

## What this PR ships

### Builder script

`scripts/build_historical_mover_reference_store.py`

Public-only, no-API-key, optionally network-free builder. Pure
helpers:

  - `assert_no_credentials_in_env(env)` — refuses to start when
    any forbidden credential env var is present.
  - `BinanceFuturesPublicSource` — thin public-only data source
    that reuses the Phase 11C allowlist guard and rejects every
    credential-shaped kwarg.
  - `filter_eligible_usdt_perpetual_universe(exchange_info)` —
    `quoteAsset == "USDT"` AND `contractType == "PERPETUAL"` AND
    `status == "TRADING"`.
  - `select_symbols_by_volume(...)` — optional 24 h-quote-volume
    ranking when `--symbol-limit` is provided.
  - `klines_to_daily_top_movers(...)` — pure transformation from
    raw 1 h klines into per-day top-mover rows ranked by
    `window_gain_pct`.
  - `write_exchange_info_snapshot(...)`,
    `write_top_movers_jsonl(...)`, `write_manifest(...)` —
    deterministic disk writers, no-op under `--dry-run`.
  - `build_no_network_source(...)` — deterministic in-process
    `BinanceFuturesPublicSource` for the `--no-network` smoke
    path.
  - `run_build(...)` — single-entry orchestrator used by both
    the CLI and the test suite.
  - `main(argv)` — CLI entry point with the brief-mandated
    flags.

### CLI

```
python -m scripts.build_historical_mover_reference_store \
    --days 60 --top-n 20

python -m scripts.build_historical_mover_reference_store \
    --days 2 --symbol-limit 3 --top-n 5 --dry-run

python -m scripts.build_historical_mover_reference_store \
    --days 2 --symbol-limit 3 --top-n 5 --no-network
```

Flags:

| Flag | Purpose |
| ---- | ------- |
| `--days` | Trailing-window length, default 60. |
| `--timeframe` | Kline timeframe, default `1h` (allowlisted). |
| `--top-n` | Top-N movers per day, default 20. |
| `--symbol-limit` | Optional cap, ranks by 24 h volume. |
| `--output-dir` | Output root. Defaults to `data/historical_market_store`. |
| `--rest-base-url` | Public Binance futures REST base URL. |
| `--audit-window-end-utc-ms` | Reproducible end timestamp. |
| `--request-sleep-seconds` | Polite sleep between REST calls. |
| `--dry-run` | Compute everything but never touch disk. |
| `--no-network` | Use deterministic in-process data source. |
| `--no-network-test-mode` | Alias for `--no-network` (matches brief). |
| `--quiet` | Suppress per-symbol log output. |

### On-disk layout

`data/historical_market_store/`

```
exchange_info/
    binance_futures_exchange_info_<ts>.json   (human-readable)
    binance_futures_exchange_info_<ts>.jsonl  (loader-readable)
top_movers/
    historical_<days>d_top_movers_<ts>.jsonl
manifests/
    historical_<days>d_mover_reference_manifest_<ts>.json
```

The layout is deliberately the one
`app.adaptive.historical_mover_coverage_backfill.load_historical_market_store(root)`
already expects. **No D-A loader change is required.**

### JSONL row schema (top-mover row)

Every row carries both the brief-mandated columns and the
loader-required columns:

  - **Brief columns:** `symbol`, `mover_window_start_utc`,
    `mover_window_end_utc`, `reference_timestamp_utc`,
    `top_mover_rank`, `window_gain_pct`, `max_24h_gain_pct`,
    `open_price`, `close_price`, `high_price`, `low_price`,
    `quote_volume`, `eligible_usdt_perpetual`,
    `source = binance_public_futures_klines_1h`,
    `lookahead_policy = post_hoc_reference_only`,
    `generated_at_utc`.
  - **Loader columns:** `snapshot_date`,
    `reference_timestamp_utc_ms`, `mover_window_start_utc_ms`,
    `mover_window_end_utc_ms`, `max_window_gain`,
    `max_24h_gain`, `quote_volume_usdt`, `quote_asset`,
    `contract_type`.
  - **Schema versions:** `schema_version` (builder),
    `audit_schema_version` (audit).

Every row is validated against
`LOOKAHEAD_FORBIDDEN_FIELDS` before being written.

### Manifest schema

```
{
  "schema_version": "...v0",
  "audit_schema_version": "...v1",
  "builder_version": "...v0",
  "generated_at_utc": "...",
  "audit_window_end_utc": "...",
  "days_requested": 60,
  "timeframe": "1h",
  "top_n": 20,
  "eligible_symbol_count": ...,
  "symbols_processed": [...],
  "symbols_failed": [...],
  "top_mover_record_count": ...,
  "history_days_observed": ...,
  "source": "binance_public_futures_klines_1h",
  "rest_base_url": "...",
  "public_endpoint_allowlist": [...],
  "allowed_public_hosts": [...],
  "forbidden_private_endpoints": [...],
  "forbidden_query_parameters": [...],
  "public_endpoint_only": true,
  "private_api_used": false,
  "api_key_loaded": false,
  "signed_endpoint_used": false,
  "binance_private_api_enabled": false,
  "telegram_outbound_enabled": false,
  "live_trading_enabled": false,
  "exchange_live_order_enabled": false,
  "right_tail_enabled": false,
  "llm_enabled": false,
  "trading_mode": "paper",
  "lookahead_policy": "post_hoc_reference_only",
  "lookahead_guard": "reference_set_is_post_hoc_audit_only",
  "lookahead_forbidden_fields": [...],
  "no_network_test_mode": ...,
  "dry_run": ...,
  "output_files": {"exchange_info": "...", "top_movers": "..."},
  "public_calls": [{"path": "...", "status": "ok"}, ...],
  "boundary": {
    "is_strategy_blind_replay": false,
    "is_pnl_backtest": false,
    "is_trading_module": false,
    "is_ai_learning": false,
    "is_parameter_optimisation": false,
    "is_reinforcement_learning": false,
    "is_phase_12": false,
    "is_post_hoc_audit_reference_only": true,
    "phase_12_remains_forbidden": true
  }
}
```

### D-A loader integration (no loader change)

The PR includes a round-trip test
(`test_top_movers_can_be_loaded_by_historical_coverage_backfill`)
that runs the builder, calls
`load_historical_market_store(<root>)`, and feeds the result
into `build_historical_60d_mover_reference_set(...)`. The
existing loader consumes the new JSONL exactly as designed.

A second round-trip test
(`test_missing_event_history_remains_valid_miss_reason`) feeds
the resulting reference set through
`HistoricalMoverCoverageBackfillRuntime` against an empty
`EventRepository` and confirms every record is classified as
`MISSING_EVENT_HISTORY` — i.e. the audit's miss-reason
taxonomy is unchanged.

### `.gitignore`

`data/historical_market_store/` is added to `.gitignore`. The
store is regenerated locally and must not be committed.

## New / updated tests

`tests/unit/test_phase11c_1c_c_b_b_b_d_a_historical_mover_reference_store.py`
covers the brief-mandated cases and a few extras:

  - `test_exchange_info_filters_usdt_perpetual_universe`
  - `test_select_symbols_by_volume_ranks_eligible_universe_only`
  - `test_select_symbols_with_no_limit_returns_alphabetical_universe`
  - `test_top_mover_reference_store_schema`
  - `test_window_gain_calculation_is_post_hoc_only`
  - `test_reference_builder_does_not_load_api_keys`
  - `test_reference_builder_does_not_use_signed_endpoints`
  - `test_reference_set_is_post_hoc_only`
  - `test_lookahead_guard_rejects_completed_tail_label_in_builder_output`
  - `test_manifest_records_public_only_invariants`
  - `test_top_movers_can_be_loaded_by_historical_coverage_backfill`
  - `test_missing_event_history_remains_valid_miss_reason`
  - `test_no_live_trading_flags_unchanged`
  - `test_phase_12_remains_forbidden`
  - `test_cli_dry_run_smoke`
  - `test_cli_refuses_with_credentials_in_env`

## Test results

  - `tests/unit/test_phase11c_1c_c_b_b_b_d_a_historical_mover_reference_store.py`:
    16 / 16 PASS.
  - `tests/unit/test_phase11c_1c_c_b_b_b_d_a_historical_mover_coverage_backfill.py`:
    22 / 22 PASS (no regression).
  - `tests/unit/ -k phase11c_`: full filtered set PASS.
  - `tests/`: **2422 / 2422 PASS** (vs. 2406 baseline pre-PR; +16
    new tests, no regressions).

## Dry-run + no-network smoke

```
python -m scripts.build_historical_mover_reference_store \
    --days 2 --symbol-limit 3 --top-n 5 --dry-run --no-network \
    --request-sleep-seconds 0 --quiet
```

Result (excerpt):

```
"public_endpoint_only": true,
"private_api_used": false,
"api_key_loaded": false,
"signed_endpoint_used": false,
"lookahead_policy": "post_hoc_reference_only",
"lookahead_guard": "reference_set_is_post_hoc_audit_only",
"phase_12_remains_forbidden": true,
"trading_mode": "paper",
"days_requested": 2,
"top_n": 5,
"symbols_processed": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
"top_mover_record_count": 6,
"dry_run": true,
"no_network_test_mode": true
```

A non-dry-run `--no-network` run was also exercised locally and
produced loader-compatible files under
`data/historical_market_store/`. The artefacts are not
committed (see `.gitignore`).

## Real 60D data generation is required after merge

This PR ships the **builder**. The D-A slice still needs the
operator to run the builder against the real Binance public
futures endpoints (no `--no-network` flag) on the operator-VPS
to produce a real 60D Historical Market Store, then re-run the
public-market paper runner with
`--historical-mover-store-dir data/historical_market_store`,
collect the operator-VPS evidence (`HISTORICAL_MOVER_COVERAGE_*`
event counts, daily report excerpt, Phase 8.5 export bundle
manifest count, audit `backfill_status`), and submit a
docs-only closeout PR. Only that closeout PR may flip Phase
11C.1C-C-B-B-B-D-A to `ACCEPTED`. **This PR does not.**

## Remaining risk

  - Builder runs against the real Binance public REST surface
    will count against the Phase 11C.1A rate-limit governor
    budget if executed on the same host as the live paper
    runner. The builder defaults to a 50 ms request sleep and
    paginates klines in batches of ≤ 1000 rows, but operators
    should still avoid running the builder concurrently with a
    long live paper run on the same host.
  - The deterministic `--no-network` data set is intentionally
    simple. It exercises every column the builder writes but is
    not a substitute for real 60D market data — only the
    operator-driven real-network run can produce real
    historical reference rows.

## Ready for human review?

Yes. All boundaries hold; `data/historical_market_store/` is
.gitignored; full pytest is green; safety flags are unchanged;
Phase 12 remains `FORBIDDEN`; the audit's miss-reason taxonomy
and event-emission contract are untouched.
