# Phase 11C.1D-D-I — Blind Runner Historical Store Input Glue (PR103)

> Minimal glue that wires the PR101/PR102 Historical Data Store
> output (`records.jsonl` + `historical_data_manifest.json` +
> `universe_manifest.json`) into the PR100 Blind Walk-forward Runner
> CLI. Paper-only / report-only / sandbox-only. **NOT** a new blind
> testing system, **NOT** a new strategy, **NOT** the 30D / 60D / 90D
> / 2Y runner. Phase 12 remains **FORBIDDEN**.

## Purpose

Before PR103, `scripts/run_blind_walk_forward.py` always built an
**empty** `HistoricalMarketStore`, so the runner had nothing to
replay. PR101 (Historical Data Ingestion / Backfill) and PR102
(Binance Public Kline File Adapter Fix) produce a real Historical
Data Store on disk, but there was no CLI path to feed it into the
runner — `--historical-store-dir` did not exist and the cloud run
failed with `unrecognized arguments: --historical-store-dir`.

PR103 adds exactly that input wiring and nothing else:

- read `records.jsonl` and restore the PR95 record types
  (`HistoricalKlineRecord` / `HistoricalMarketRecord` /
  `SymbolStatusRecord`),
- load them into a `HistoricalMarketStore`,
- build the PR96 `ReplayFeedProvider` over that store,
- let the PR100 `BlindWalkForwardRunner` consume the provider,
- pin the **real** `data_manifest_hash` / `universe_manifest_hash`
  (read straight from the PR101 manifests) onto the
  `BlindRunManifest`.

PR103 does **not** rewrite the Blind Runner, does **not** implement a
strategy, does **not** add a decision callback, and does **not**
relax any PR94 / PR96 gate.

## CLI surface

New flags on `scripts/run_blind_walk_forward.py`:

| Flag | Meaning |
| --- | --- |
| `--historical-store-dir DIR` | Read `DIR/records.jsonl`, `DIR/historical_data_manifest.json`, `DIR/universe_manifest.json`. |
| `--records-path PATH` | Explicit override for `records.jsonl`. |
| `--historical-data-manifest-path PATH` | Explicit override for `historical_data_manifest.json`. |
| `--universe-manifest-path PATH` | Explicit override for `universe_manifest.json`. |

When none of these flags is supplied the runner keeps its prior v0
behaviour (empty substrate).

## Data → store → provider → runner

1. **`records.jsonl` → records.** Each line is
   `json.dumps(record.to_dict(), sort_keys=True)` as written by PR101.
   `_record_from_dict` dispatches on the explicit
   `is_historical_kline_record` / `is_symbol_status_record` /
   `is_historical_market_record` marker (falling back to
   `record_type`) and rebuilds the dataclass, re-running every PR95
   construction-time invariant (e.g. kline `available_at >=
   close_time`). No field is fabricated.
2. **records → store.** `build_historical_store_from_records` adds the
   restored rows to a fresh `HistoricalMarketStore`. The store keeps
   the PR94 `TimeWallGuard` and closed-candle visibility guard fully
   in force.
3. **store → provider.** `main()` builds the PR96
   `ReplayFeedProvider` over the loaded store and the
   `SimulationClock`. Every `available_at <= simulated_time` check and
   every closed-candle gate is enforced by PR94/PR96 exactly as
   before — PR103 bypasses neither.
4. **provider → runner.** The PR100 `BlindWalkForwardRunner` consumes
   the provider batch-by-batch, unchanged.

## Manifest hashes (real, never fabricated)

`BlindWalkForwardRunnerConfig` gains two optional fields,
`data_manifest_hash` and `universe_manifest_hash`. When provided they
must be canonical `sha256:`-prefixed strings and `prepare_manifest`
pins them directly onto the `BlindRunManifest`; when `None` the
runner falls back to hashing the inline artefact exactly as in PR100.
The CLI reads the real hashes out of the PR101 manifests and passes
them through, so the `BlindRunManifest` carries the **actual**
`data_manifest_hash` / `universe_manifest_hash` of the ingested data.

## Evidence sufficiency / WARN rules

| Condition | Result |
| --- | --- |
| `records.jsonl` missing | `status = INSUFFICIENT_EVIDENCE`, exit code `3`, run NOT started, no fabricated data |
| `records.jsonl` empty | `status = INSUFFICIENT_EVIDENCE`, exit code `3`, run NOT started |
| `historical_data_manifest.json` missing | WARN; `data_manifest_hash` left to hash-of-inline-artefact (never fabricated) |
| `universe_manifest.json` missing | WARN; kline-only short smoke is NOT blocked; `universe_manifest_hash` left to hash-of-inline-artefact |

A `historical_store_input.json` sidecar is written next to the report
artefacts recording `ingested_record_count`, `record_counts_by_type`,
`source_files`, the pinned hashes, and the warnings.

## Hard safety boundary (unchanged)

PR103 inherits the PR93 / PR100 boundary verbatim and changes none of
it:

```
mode = historical_blind_sim_live
sandbox_only = True            simulated_only = True
no_live_order = True           live_trading = False
exchange_live_orders = False   binance_private_api_enabled = False
signed_endpoint_reachable = False
private_websocket_reachable = False
account_endpoint_reachable = False
order_endpoint_reachable = False
real_exchange_order_path = False
real_capital = False
telegram_outbound_enabled = False
telegram_live_command_authority = False
ai_trade_authority = False     trade_authority = False
auto_tuning_inside_blind_window = False
auto_tuning_allowed = False     phase_12_forbidden = True
```

The CLI imports only `app.sim` + the Python standard library: never
`app.risk` / `app.execution` / `app.exchanges` / `app.telegram` /
`app.config` / `app.ai`, and no network / Binance private API /
DeepSeek / LLM transport. The Risk Engine remains the single
trade-decision gate.

## What PR103 does NOT do

- Does **not** rewrite the Blind Runner.
- Does **not** implement a new strategy or a decision callback.
- Does **not** implement the 30D / 60D / 90D / 2Y runner.
- Does **not** touch `app/risk/`, `app/execution/`, `app/exchanges/`,
  `app/telegram/`, `app/config/`, strategy logic, AI decision logic,
  the Binance private API, or the live-order path.
- Does **not** authorise live trading, auto-tuning, real Telegram
  outbound, the Binance private API, or Phase 12.

> Note on real multi-day data: the PR96 `ReplayFeedProvider` records
> every not-yet-available store record as a `FUTURE_AVAILABLE_AT`
> audit violation at each tick, and the PR100 runner routes any batch
> violation into a `FUTURE_RECORD_ACCESS` invalidation. A run over a
> store whose data spans well past the blind window may therefore
> score `INVALIDATED_LOOKAHEAD_OR_DRIFT`. That is the existing
> PR96/PR100 substrate behaviour (correctly withholding future data),
> not a PR103 regression; PR103 wires the data in without bypassing
> either gate.

## Tests

`tests/unit/test_blind_walk_forward_runner.py` adds the PR103
acceptance tests: CLI accepts `--historical-store-dir`; `records.jsonl`
loads and restores into a `HistoricalMarketStore`; the runner consumes
the real records through the `ReplayFeedProvider`; missing / empty
`records.jsonl` returns `INSUFFICIENT_EVIDENCE` (never fake data); the
real `data_manifest_hash` / `universe_manifest_hash` appear in the
`BlindRunManifest`; missing universe manifest does not block kline-only
smoke; no-lookahead violations remain zero for a valid as-of fixture;
every safety flag is pinned; no forbidden fields / imports / network
paths; deterministic output.

```
python -m pytest tests/unit/test_blind_walk_forward_runner.py -q
```

## Status

**Phase 11C.1D-D-I / PR103 — IN_REVIEW** (after this implementation
PR; not `ACCEPTED` until maintainer review). Phase 12 remains
**FORBIDDEN**.
