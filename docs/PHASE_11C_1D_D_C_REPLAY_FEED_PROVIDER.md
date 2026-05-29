# Phase 11C.1D-D-C — ReplayFeedProvider v0 (PR96)

> *Strict forward-only historical sim-live replay feed provider*
> *严格前向 Sim-Live 历史回放喂数器 v0*
>
> **Status:** IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).
> **Type:** **Implementation PR** (paper / report / evidence-only
> infrastructure).
> **Parent:** Phase 11C.1D-D *Strict Blind Walk-forward Sim-Live
> Constitution* (PR93, merged), Phase 11C.1D-D-A *SimulationClock
> + Time-Wall Guard* (PR94, merged), and Phase 11C.1D-D-B
> *Historical Market Store v0* (PR95, merged).
> **Trade authority:** **none.**
> **Phase 12:** **FORBIDDEN.**

---

## 0. Pre-amble — what this PR is and is NOT

This PR ships the **third** anti-future-lookahead infrastructure
block of the strict blind walk-forward stack defined by Phase
11C.1D-D (PR93). It is a small, deterministic, pure-Python
in-memory feed provider. It introduces **no** runtime hot-path
wiring, **no** new event types, **no** schema migration, **no**
I/O, **no** network, **no** real data fetch, and **no** authority
over the Risk Engine, the Execution FSM, or the Capital Flow
Engine. PR96 builds strictly on top of the PR94 + PR95 substrate
and re-uses every PR94 / PR95 primitive verbatim (`SimulationClock`,
`HistoricalRecordTime`, `TimeWallGuard`, `CandleVisibilityGuard`,
`NoLookaheadViolation`, `assert_no_forbidden_fields`,
`HistoricalMarketStore`, `HistoricalMarketRecord`,
`HistoricalKlineRecord`, `SymbolStatusRecord`,
`HistoricalMarketRecordType`, `SymbolStatus`, `DataQualityFlag`,
`DataCompletenessState`).

This PR IS:

  - a `ReplayFeedProviderConfig` (frozen, validated): replay window
    (`start_time` / `end_time`), `step_interval`,
    `include_record_types` filter (default = full Constitution §10
    v0 minimum set), optional `symbols` filter,
    `include_asof_universe`, `allow_reemit`, `strict_time_wall`,
    `strict_candle_visibility`,
  - a `ReplayFeedCursor` (forward-only): `start_time`, `end_time`,
    `step_interval`, `current_time`, `emitted_record_ids`,
    `replay_complete`. Cursor cannot move backward, cannot fall
    below `start_time`, cannot exceed `end_time`,
  - a `ReplayFeedDiagnostics` (mutable counters):
    `total_records_considered`, `emitted_record_count`,
    `future_records_rejected_count`, `missing_available_at_count`,
    `unclosed_candle_violation_count`,
    `duplicate_record_skipped_count`, `data_gap_flags`, and the
    preserved `NoLookaheadViolation` audit list,
  - a `ReplayFeedBatch` (frozen, JSON-serialisable): `batch_id`,
    `simulated_time`, `records` (deterministic catch-all union),
    `klines_1m`, `klines_5m`, `funding_rates`, `open_interest`,
    `ticker_24h`, `symbol_status`, `asof_universe`, `diagnostics`
    snapshot, `violations` (per-batch slice), `replay_complete`,
    and hard-pinned `phase_12_forbidden=True`,
    `auto_tuning_allowed=False`, `trade_authority=False`,
  - a `ReplayFeedProvider` (deterministic, forward-only):
    `next_batch()`, `advance_and_get_batch(delta)`,
    `batch_at(simulated_time)`, `get_asof_universe()`,
    `get_diagnostics()`, `reset()` (test-only, requires
    non-monotonic clock), `safety_payload()`, `to_dict()`,
  - the matching unit-test module
    `tests/unit/test_replay_feed_provider.py` (26 PASSING tests
    covering all 21 brief-mandated scenarios plus 5 defensive
    extras).

This PR is **NOT**:

  - a `MockExchange` + Pessimistic Fill Model (PR97's
    responsibility),
  - a Simulated Capital Flow + Trade Ledger (PR98's responsibility),
  - a Telegram Sandbox Outbox (PR99's responsibility),
  - a Blind Walk-forward Runner (PR100's responsibility),
  - a fetcher of real market network data,
  - an authorisation to enter Phase 12,
  - an authorisation to enable live orders,
  - an authorisation to connect to Binance private API,
  - an authorisation to grant AI trade authority,
  - an authorisation to grant Telegram command authority,
  - an authorisation to auto-tune any rule, threshold, or parameter.

PR96 acceptance authorises the next allowed paper-only step
(**PR97 — MockExchange + Pessimistic Fill Model v0**). It does NOT
authorise PR98 → PR100, live trading, auto-tuning, the DeepSeek
hot path, Telegram live outbound, or Phase 12.

---

## 1. Purpose

Strict blind walk-forward (PR93 §1) is **not** an ordinary backtest.
At simulated time `T`, the system MAY only access records whose
`available_at <= T`. The substrate that produced this guarantee
already exists:

  - PR94 supplied the time substrate (`SimulationClock` +
    `TimeWallGuard` + `CandleVisibilityGuard` +
    `NoLookaheadViolation`),
  - PR95 supplied the data substrate (`HistoricalMarketStore` +
    typed records).

PR96 supplies the **feed substrate**: the deterministic
forward-only iterator that consumes the PR95 store under the
PR94 clock and emits per-tick `ReplayFeedBatch` snapshots that
obey every Constitution §5 / §6 / §9 / §10 / §E rule.

The objective is **truthful, deterministic, reproducible feed
discipline**, not a fast pipeline. Pretty equity curves built on
even one form of feed-side leakage are not evidence; they are
falsifications. PR96 makes the leakage path syntactically
impossible for the modules that consume it (PR97 → PR100), and
turns every attempted future read into an auditable
`NoLookaheadViolation` accumulated on
`ReplayFeedDiagnostics.violations`.

---

## 2. Relation to PR93 constitution

PR93 (the *Strict Blind Walk-forward Sim-Live Constitution*) is
docs-only. PR96 is the **third implementation slice** authorised
by PR93 §19's engineering route (after PR94 and PR95 were
merged). PR96 implements the feed layer required by:

  - **§5 Time-Wall Constitution.** Every emitted record obeys
    `available_at <= simulated_time`. `ingested_at` is NEVER a
    substitute for `available_at`. Rejection is auditable via
    `NoLookaheadViolation` accumulated on
    `ReplayFeedDiagnostics.violations`.
  - **§6 Candle visibility rule.** A 1m / 5m / longer-period
    candle's final OHLCV is fully visible only after that candle
    has closed. PR95 already enforces this at construction time
    (`HistoricalKlineRecord.available_at >= close_time`). PR96
    adds belt-and-suspenders runtime cross-checks via
    `CandleVisibilityGuard.is_candle_closed` for every emitted
    kline. If `strict_candle_visibility=True` (default) and a
    kline somehow lands on an unclosed candle relative to
    `simulated_time`, PR96 mints an
    `UNCLOSED_CANDLE_FIELD_ACCESS` violation and refuses to emit
    the batch.
  - **§9 As-of market universe.** `ReplayFeedBatch.asof_universe`
    is delegated to
    `HistoricalMarketStore.query_asof_universe(simulated_time)`,
    which obeys: `listed_at <= T` AND
    (`delisted_at is None` OR `delisted_at > T`) AND
    `available_at <= T` AND `status` is in
    `SymbolStatus.TRADABLE_OR_MONITORABLE`. The provider NEVER
    consults the *current* symbol list; an empty store at any
    `T` returns an empty universe.
  - **§10 Historical data scope (v0 minimum).** 1m / 5m kline,
    funding rate, open interest, 24h ticker, exchangeInfo,
    listing / delisting timeline. PR96's
    `include_record_types` defaults to that v0 minimum and
    refuses any value outside `HistoricalMarketRecordType.ALLOWED`.
  - **§E Data revision / late arrival policy.** Inherited
    end-to-end from PR95: a revised record is just another
    record; the original is NEVER overwritten or removed. PR96
    surfaces both records on equal footing once both are visible
    to `simulated_time`.
  - **§F Run invalidation rules.** Future-record access, missing
    `available_at`, unclosed-candle field access, and
    `ingested_at` substitution all route through the PR94
    `NoLookaheadViolation` taxonomy. PR96 accumulates them on
    `ReplayFeedDiagnostics.violations` and counts them via the
    closed `future_records_rejected_count` /
    `missing_available_at_count` /
    `unclosed_candle_violation_count` /
    `duplicate_record_skipped_count` set.

PR93 §19 explicitly authorises ONLY this PR (PR96) to begin its
own gate after PR95. PR96 does NOT touch §11 (MockExchange +
Pessimistic Fill Model), §12 (Latency / Outage / Data Degradation
injection), §13 (Simulated Capital Flow), §14 (Telegram sandbox),
§15 (AI role), §16 (Required outputs), §17 (Acceptance criteria).
Those are the responsibility of PR97 → PR100, each behind its own
gate.

---

## 3. Relation to PR94 SimulationClock + Time-Wall Guard

PR94 supplied the time substrate. PR96 reuses every PR94 primitive
verbatim:

  - `SimulationClock` — the strict forward-only simulated UTC
    clock. PR96 does NOT introduce a competing clock. Every
    `ReplayFeedProvider` is constructed with one
    `SimulationClock`; every `next_batch` /
    `advance_and_get_batch` / `batch_at` call advances that
    clock via `set_time` (no wall-clock substitute).
  - `HistoricalRecordTime` — used internally by PR95 records
    when the store calls `TimeWallGuard.validate_no_lookahead`.
    PR96 never constructs them directly.
  - `TimeWallGuard` — the `available_at <= simulated_time`
    enforcement layer. PR96 uses
    `store.time_wall_guard` by default (or accepts an injected
    guard for testability). Every record query routes through
    the store, which routes through the time wall, which mints
    a `NoLookaheadViolation` for every rejection. PR96 consumes
    those violations via `store.violations[pre:after]` slice and
    classifies them via `ReplayFeedDiagnostics.record_violation`.
  - `CandleVisibilityGuard` — the closed-candle visibility rule.
    PR96 cross-checks
    `CandleVisibilityGuard.is_candle_closed(open_time, interval,
    simulated_time)` for every emitted kline when
    `strict_candle_visibility=True` (default). Belt-and-
    suspenders.
  - `NoLookaheadViolation` (closed reason / severity taxonomy).
    PR96 mints `UNCLOSED_CANDLE_FIELD_ACCESS` violations via
    `TimeWallGuard.make_unclosed_candle_field_access_violation`
    and consumes the four other reasons produced by the store.
    PR96 does NOT introduce new reasons; the taxonomy is closed.
  - `assert_no_forbidden_fields` — every PR96 dataclass'
    `to_dict()` runs through this recursive guard before
    returning. Any payload that smuggles a trade-action /
    runtime-config-patch / "live ready" / "trading approved"
    field at any nesting depth is rejected at construction time.

Hard rule: PR96 NEVER calls `datetime.now()` /
`datetime.utcnow()` / `time.time()` / `time.monotonic()` /
`pandas.Timestamp.now()` to compute decision time. Every visible
moment is the caller-supplied `simulated_time` or the
`SimulationClock`.

---

## 4. Relation to PR95 Historical Market Store

PR95 supplied the data substrate. PR96 reuses every PR95 primitive
verbatim:

  - `HistoricalMarketStore` — PR96 is constructed with one store
    and consumes it via `query_records(record_type,
    simulated_time=T)` and `query_asof_universe(simulated_time)`.
    PR96 NEVER bypasses the store's TimeWallGuard /
    CandleVisibilityGuard cross-checks; PR96 NEVER mutates
    private fields of the store. The shared
    `store.violations` audit list is consumed slice-wise across
    batches.
  - `HistoricalMarketRecord` — emitted as-is in
    `ReplayFeedBatch.records` / `funding_rates` /
    `open_interest` / `ticker_24h`.
  - `HistoricalKlineRecord` — emitted as-is in
    `ReplayFeedBatch.klines_1m` / `klines_5m`. The
    construction-time invariant `available_at >= close_time`
    means a kline can only enter the store if its candle is
    closed by the time it is visible — and the runtime
    `is_candle_closed` cross-check confirms this on every
    batch.
  - `SymbolStatusRecord` — emitted as-is in
    `ReplayFeedBatch.symbol_status` and consulted in
    `ReplayFeedBatch.asof_universe`.
  - `HistoricalMarketRecordType` (closed taxonomy) — used to
    drive `ReplayFeedProviderConfig.include_record_types`. The
    config refuses any value outside
    `HistoricalMarketRecordType.ALLOWED`.
  - `SymbolStatus` (closed taxonomy) — already enforced by the
    store; PR96 inherits the rule that `DELISTED` is excluded
    from the as-of universe.
  - `DataQualityFlag` (closed taxonomy) — `data_quality_flags`
    on emitted records is propagated into
    `ReplayFeedDiagnostics.data_gap_flags` (deduped, closed-
    taxonomy enforced).
  - `DataCompletenessState` (closed taxonomy) — descriptive
    pass-through.

---

## 5. Provider contract

`ReplayFeedProvider` is constructed with three required arguments:

  - `store: HistoricalMarketStore`,
  - `clock: SimulationClock`,
  - `config: ReplayFeedProviderConfig`,

and two optional arguments (`time_wall_guard`,
`candle_visibility_guard`) that default to the store's own
guards. At construction, the provider verifies:

  - `clock.start_time_utc <= config.start_time`,
  - `clock.end_time_utc is None` OR
    `clock.end_time_utc >= config.end_time`,
  - if the clock is forward-only (`monotonic_forward_only=True`,
    the default), `clock.now() <= config.start_time`,
  - the clock is then snapped to `config.start_time` via
    `clock.set_time(config.start_time)`.

Public API (each call advances both the clock and the cursor):

| method | behaviour |
| --- | --- |
| `next_batch()` | Advance clock by `config.step_interval`, return the resulting `ReplayFeedBatch`. Raises `StopIteration` when the cursor has already reached `config.end_time`. |
| `advance_and_get_batch(delta)` | Advance clock by `delta` (a `timedelta`, a number of seconds, or an interval string such as `"1m"`), return the batch. Raises `StopIteration` if the cursor is already complete and `delta > 0`. |
| `batch_at(simulated_time)` | Advance clock to `simulated_time` (which MUST be `>= cursor.current_time` and within `[config.start_time, config.end_time]`), return the batch. |
| `get_asof_universe(simulated_time=None)` | Query the as-of universe at `simulated_time` (or `cursor.current_time` if `None`). Forward-only: rejects `simulated_time < cursor.current_time`. |
| `get_diagnostics()` | Return a deep-copy snapshot of the cumulative `ReplayFeedDiagnostics`. |
| `reset()` | Reset cursor / diagnostics / clock to `config.start_time`. **Test-only**: requires `monotonic_forward_only=False` on the clock. |
| `safety_payload()` | Return the project-wide safety boundary dict (re-pinned). |
| `to_dict()` | Return a JSON-serialisable view of `(config, cursor, diagnostics, batch_count)`. |

Public properties: `store`, `clock`, `config`, `cursor`,
`diagnostics`, `time_wall_guard`, `candle_visibility_guard`,
`replay_complete`, plus the defensive tripwires `sandbox_only`,
`live_trading`, `exchange_live_orders`,
`binance_private_api_enabled`, `telegram_outbound_enabled`,
`ai_trade_authority`, `trade_authority`, `auto_tuning_allowed`,
`phase_12_forbidden`.

`ReplayFeedProvider` is **not** a `Mapping` and does **not**
support backward iteration. Two providers fed identical store /
clock / config produce identical batch sequences (verified by
`test_deterministic_output_from_same_store_clock_config`).

---

## 6. Batch schema

`ReplayFeedBatch` is a frozen dataclass with the following fields:

| field | type | role |
| --- | --- | --- |
| `batch_id` | `str` | non-empty, deterministic (`"replay_batch_{counter:06d}"`) |
| `simulated_time` | `datetime` | UTC-aware; the time at which the batch is visible |
| `records` | `Tuple[Any, ...]` | deterministic catch-all union of all per-type lists, sorted by `(event_time, available_at, symbol, record_id)` |
| `klines_1m` | `Tuple[HistoricalKlineRecord, ...]` | 1m klines emitted in this batch |
| `klines_5m` | `Tuple[HistoricalKlineRecord, ...]` | 5m klines emitted in this batch |
| `funding_rates` | `Tuple[HistoricalMarketRecord, ...]` | funding-rate records emitted in this batch |
| `open_interest` | `Tuple[HistoricalMarketRecord, ...]` | OI records emitted in this batch |
| `ticker_24h` | `Tuple[HistoricalMarketRecord, ...]` | 24h-ticker records emitted in this batch |
| `symbol_status` | `Tuple[SymbolStatusRecord, ...]` | `SYMBOL_STATUS` records emitted in this batch |
| `asof_universe` | `Tuple[SymbolStatusRecord, ...]` | as-of universe **snapshot** at `simulated_time` (NEVER deduped; always re-emitted) |
| `diagnostics` | `Optional[ReplayFeedDiagnostics]` | deep-copy snapshot of cumulative provider diagnostics |
| `violations` | `Tuple[NoLookaheadViolation, ...]` | the slice of `store.violations` produced **during this batch's queries** (subset of `diagnostics.violations`) |
| `replay_complete` | `bool` | `True` iff the cursor has reached `config.end_time` |
| `phase_12_forbidden` | `bool` (hard-pinned `True`) | refuses to construct with any other value |
| `auto_tuning_allowed` | `bool` (hard-pinned `False`) | refuses to construct with any other value |
| `trade_authority` | `bool` (hard-pinned `False`) | refuses to construct with any other value |

`ReplayFeedBatch.to_dict()` is JSON-serialisable, runs through
`assert_no_forbidden_fields`, and re-pins the project-wide
safety boundary (mode=paper, sandbox_only=True, live_trading=False,
…, phase_12_forbidden=True).

---

## 7. Diagnostics schema

`ReplayFeedDiagnostics` is a mutable dataclass:

| field | type | role |
| --- | --- | --- |
| `total_records_considered` | `int` | every record looked at by the provider, including duplicates and filtered-out symbols |
| `emitted_record_count` | `int` | total records included in batches across the provider's lifetime |
| `future_records_rejected_count` | `int` | count of `FUTURE_AVAILABLE_AT` violations |
| `missing_available_at_count` | `int` | count of `MISSING_AVAILABLE_AT` violations |
| `unclosed_candle_violation_count` | `int` | count of `UNCLOSED_CANDLE_FIELD_ACCESS` violations |
| `duplicate_record_skipped_count` | `int` | count of records skipped because their `record_id` was already emitted (with `allow_reemit=False`) |
| `data_gap_flags` | `List[str]` | unique `DataQualityFlag.*` strings seen on emitted records |
| `violations` | `List[NoLookaheadViolation]` | the cumulative audit list, preserved across batches |

`ReplayFeedDiagnostics.record_violation(v)` appends `v` and bumps
the matching reason counter:

  - `FUTURE_AVAILABLE_AT` → `future_records_rejected_count`,
  - `MISSING_AVAILABLE_AT` → `missing_available_at_count`,
  - `UNCLOSED_CANDLE_FIELD_ACCESS` →
    `unclosed_candle_violation_count`,
  - `INGESTED_AT_USED_AS_AVAILABILITY` and
    `OUTCOME_LABEL_DURING_BLIND_WINDOW` are stored in
    `violations` but do not have a dedicated v0 counter;
    downstream PRs (PR100) will fold them into the run
    invalidation matrix.

`ReplayFeedDiagnostics.snapshot()` returns a deep copy that the
`ReplayFeedBatch.diagnostics` field uses; downstream consumers can
treat the snapshot as immutable.

`ReplayFeedDiagnostics.to_dict()` is JSON-serialisable.

---

## 8. The `available_at <= simulated_time` rule

Single rule: at simulated time `T`, a record is visible iff
`available_at <= T`. The provider implements this by routing
every record query through `HistoricalMarketStore.query_records`,
which routes through `TimeWallGuard.validate_no_lookahead`.
Records rejected by the time wall are NEVER silently dropped:
every rejection produces a `NoLookaheadViolation` audit object
appended to `store.violations`. PR96 reads the slice
`store.violations[pre:after]` produced by THIS batch's queries
and:

  - calls `ReplayFeedDiagnostics.record_violation(v)` for each
    violation (which bumps the reason counter and appends to
    `diagnostics.violations`),
  - exposes the same slice as `ReplayFeedBatch.violations`
    (per-batch audit subset).

`ingested_at` is NEVER substituted for `available_at`. The
`NoLookaheadViolationReason.INGESTED_AT_USED_AS_AVAILABILITY`
audit object can be minted by callers via
`TimeWallGuard.make_ingested_at_used_as_availability_violation`
and recorded on `diagnostics` like any other violation.

`MISSING_AVAILABLE_AT` arises when the time wall encounters a
Mapping-shape record without an `available_at` field. The PR95
store dataclasses always carry `available_at` by construction,
so `missing_available_at_count` is normally 0; the counter is
present so downstream consumers (and the PR100 runner) can
invalidate a run if a misconfigured caller ever bypasses the
dataclass.

---

## 9. Closed-candle visibility rule

Constitution §6: a 1m / 5m / longer-period candle's final OHLCV
(`high` / `low` / `close` / `volume`) is fully visible only after
that candle has closed.

The provider enforces this in two complementary places:

  1. **By construction (PR95).** `HistoricalKlineRecord` rejects
     any `available_at < close_time`. By construction, no kline
     in the store can advertise final OHLCV before its candle has
     closed.
  2. **At query time (PR96).** When
     `config.strict_candle_visibility=True` (the default), every
     emitted kline is cross-checked via
     `CandleVisibilityGuard.is_candle_closed(open_time, interval,
     simulated_time)`. The candle is closed when
     `simulated_time >= candle_close_time` (the close instant
     itself counts as closed). If a kline somehow survives the
     time wall but lands on an unclosed candle relative to
     `simulated_time`, PR96 mints an
     `UNCLOSED_CANDLE_FIELD_ACCESS` violation via
     `TimeWallGuard.make_unclosed_candle_field_access_violation`
     and refuses to emit the batch.

The two checks are intentionally redundant. Construction-time
enforcement protects against bad-shape inputs; query-time
enforcement protects against subtle bugs where `available_at`
was somehow set earlier than `close_time` through a Mapping-shape
backdoor that bypassed the dataclass.

---

## 10. As-of universe feed rule

Constitution §9: as-of universe queries MUST NOT use the *current*
symbol list to reconstruct the past.

`ReplayFeedBatch.asof_universe` is delegated to
`HistoricalMarketStore.query_asof_universe(simulated_time)`,
which returns the set of `SymbolStatusRecord` rows for which
**all** of the following hold:

  - `available_at <= simulated_time` (time wall),
  - `listed_at <= simulated_time` (the symbol had actually
    listed by `simulated_time`),
  - `delisted_at is None` OR `delisted_at > simulated_time`,
  - `status` is in `SymbolStatus.TRADABLE_OR_MONITORABLE`
    (`TRADING`, `BREAK`, `HALT`, `SETTLING`, `PRE_TRADING`).
    `DELISTED` is **explicitly excluded** even if the time wall
    and listing checks pass.

Multi-snapshot dedup: if a symbol has more than one visible
`SymbolStatusRecord` at `simulated_time`, the latest by
`(event_time, available_at, record_id)` is the one consulted.
The result is deterministically sorted by
`(symbol, listed_at, record_id)` (PR95 contract).

`ReplayFeedBatch.asof_universe` is a **snapshot** and is NEVER
deduped against `cursor.emitted_record_ids`. It is re-emitted in
every batch at the appropriate `simulated_time`.

`include_asof_universe=False` skips the universe query (the field
is `()` in that case); the rule is unchanged when the universe is
queried.

---

## 11. No-lookahead violation handling

Closed taxonomy (PR94):

| reason | PR96 counter | when |
| --- | --- | --- |
| `FUTURE_AVAILABLE_AT` | `future_records_rejected_count` | record's `available_at > simulated_time` |
| `MISSING_AVAILABLE_AT` | `missing_available_at_count` | Mapping-shape record without `available_at` (cannot prove visibility) |
| `INGESTED_AT_USED_AS_AVAILABILITY` | preserved in `violations` only | caller-minted via `TimeWallGuard` helper |
| `UNCLOSED_CANDLE_FIELD_ACCESS` | `unclosed_candle_violation_count` | kline whose candle is not yet closed |
| `OUTCOME_LABEL_DURING_BLIND_WINDOW` | preserved in `violations` only | caller-minted via `TimeWallGuard` helper |

Closed severity taxonomy (PR94): `P0`, `P1`. PR96 does NOT
introduce new reasons or severities.

Violations are NEVER silently dropped. Every rejected record
produces an auditable `NoLookaheadViolation` that:

  - is appended to `ReplayFeedDiagnostics.violations` (cumulative),
  - is appended to `ReplayFeedBatch.violations` (per-batch slice),
  - is JSON-serialisable via `to_dict()`,
  - re-pins `phase_12_forbidden=True`,
    `auto_tuning_allowed=False`, `trade_authority=False`.

---

## 12. Determinism

Two providers fed identical (store, clock, config) produce
**byte-identical** batch sequences:

  - records are sorted by
    `(event_time, available_at, symbol, record_id)`,
  - klines are sorted by
    `(open_time, available_at, record_id)` (PR95 contract; PR96
    inherits via the same key),
  - the as-of universe is sorted by
    `(symbol, listed_at, record_id)`,
  - `batch_id` is a deterministic `"replay_batch_{counter:06d}"`
    string,
  - `cursor.emitted_record_ids` is updated only with
    non-empty `record_id` values, in the order records were
    emitted (the set semantics make order irrelevant).

`test_deterministic_output_from_same_store_clock_config` asserts
this end-to-end: 5 successive `next_batch().to_dict()` calls
from two providers built from the same fixture produce identical
JSON.

---

## 13. This does NOT implement `MockExchange` + Pessimistic Fill Model

PR96 has no concept of orders, fills, latency, slippage,
pessimistic fill, or order lifecycle. It has no
`place_order` / `submit_order` / `cancel_order` / `set_leverage` /
`set_stop` / `set_target` method. It has no order books. It has
no position state. The MockExchange + Pessimistic Fill Model
(Constitution §11) is PR97's responsibility.

The unit suite explicitly asserts that no public method on
`ReplayFeedProvider`, `ReplayFeedBatch`, `ReplayFeedCursor`,
`ReplayFeedDiagnostics`, or `ReplayFeedProviderConfig` exposes any
of the trade verbs `buy`, `sell`, `place_order`, `submit_order`,
`long`, `short`, `open_position`, `close_position`,
`set_leverage`, `set_stop`, `set_target`, `apply_change`,
`deploy`, `enable_live`.

---

## 14. This does NOT implement Blind Walk-forward Runner

PR96 has no concept of a run, a window, a freeze, a manifest hash,
a Blind Run Manifest, a Trade Ledger, an Equity Timeseries, a
Discovery Quality Ledger, a Failure Ledger, a Telegram Sandbox
Transcript, or an AI Operator Briefing (Constitution §16). It
has no training / freeze / blind / score / experience-update loop
(Constitution §8). It has no run-status taxonomy. It has no
`INVALIDATED_LOOKAHEAD_OR_DRIFT` concept. The Blind Walk-forward
Runner is PR100's responsibility.

PR96 supplies the **feed substrate** that the runner will
consume. That is the entire scope.

---

## 15. This does NOT authorise live trading

Hard safety boundary (Phase 11C.1D-D-C / PR96):

| flag | value |
| --- | --- |
| `mode` | `paper` |
| `sandbox_only` | `True` |
| `live_trading` | `False` |
| `exchange_live_orders` | `False` |
| `binance_private_api_enabled` | `False` |
| `signed_endpoint_reachable` | `False` |
| `private_websocket_reachable` | `False` |
| `account_endpoint_reachable` | `False` |
| `order_endpoint_reachable` | `False` |
| `position_endpoint_reachable` | `False` |
| `leverage_endpoint_reachable` | `False` |
| `margin_endpoint_reachable` | `False` |
| `real_exchange_order_path` | `False` |
| `real_capital` | `False` |
| `telegram_outbound_enabled` | `False` |
| `telegram_live_command_authority` | `False` |
| `ai_trade_authority` | `False` |
| `trade_authority` | `False` |
| `auto_tuning_allowed` | `False` |
| `phase_12_forbidden` | **`True`** |

Every record / batch / cursor / diagnostics / config / provider
`to_dict()` re-pins this boundary at the serialisation edge via
the recursive `assert_no_forbidden_fields` guard. The Risk
Engine remains the single trade-decision gate.

---

## 16. This does NOT authorise auto-tuning

PR96 NEVER writes runtime config. PR96 exposes no
`apply_change`, `deploy_change`, `runtime_config_patch`,
`symbol_limit_patch`, `threshold_patch`, `candidate_pool_patch`,
`regime_weight_patch`, or `strategy_parameter_patch` field. The
recursive `assert_no_forbidden_fields` guard refuses any payload
that smuggles those names at any nesting depth.
`auto_tuning_allowed=False` is re-pinned on every serialisation
boundary.

A `data_gap_flags` entry on `ReplayFeedDiagnostics`, or any
combination of `DataQualityFlag.*` markers carried on emitted
records, is descriptive audit metadata only. It MUST NEVER
trigger a runtime knob change. It MUST NEVER trigger a real
trade.

---

## 17. This does NOT authorise Phase 12

Phase 12 remains **FORBIDDEN**. The literal string `"Phase 12"`
does not appear as a destination in
`REPLAY_FEED_PROVIDER_PHASE_NAME`. Every `to_dict()` boundary
re-pins `phase_12_forbidden=True`. Tests assert that the flag is
true on the provider, every PR96 dataclass, every emitted batch,
and every violation produced by store reads.

---

## 18. Successful PR96 only allows PR97 MockExchange + Pessimistic Fill Model v0

Next-allowed-phase decision rule:

  - PR96 acceptance only authorises **PR97 — MockExchange +
    Pessimistic Fill Model v0** to begin its own gate.
  - PR96 acceptance does **NOT** authorise PR98 (Simulated
    Capital Flow + Trade Ledger), PR99 (Telegram Sandbox
    Outbox), PR100 (Blind Walk-forward Runner), live trading,
    auto-tuning, the DeepSeek hot path, Telegram live outbound,
    or Phase 12. **Phase 12 remains FORBIDDEN.**

---

## 19. File map

| file | role |
| --- | --- |
| `app/sim/replay_feed_provider.py` | the core implementation |
| `app/sim/__init__.py` | re-exports the new public surface alongside the PR94 + PR95 substrate |
| `tests/unit/test_replay_feed_provider.py` | 26 PASSING tests covering all 21 brief-mandated scenarios plus 5 defensive extras (config validation sweep, replay_complete + StopIteration, symbol filter, reset-requires-non-monotonic-clock, data-quality-flags propagation) |
| `docs/PHASE_11C_1D_D_C_REPLAY_FEED_PROVIDER.md` | this file |
| `docs/PROJECT_STATUS.md` | current-phase block updated |
| `docs/PHASE_GATE.md` | new *Open phase: Phase 11C.1D-D-C* section appended; Phase 12 row unchanged |
| `docs/CHANGELOG.md` | this PR's entry |

Files **explicitly NOT touched** by this PR:

  - `app/risk/**`, `app/execution/**`, `app/exchanges/**`,
    `app/telegram/**`, `app/config/**`,
  - `app/sim/simulation_clock.py`, `app/sim/time_wall_guard.py`,
    `app/sim/historical_market_store.py` (PR94 + PR95 contracts
    are reused verbatim; not modified),
  - `app/safety/**`, `app/ai/**`, `app/replay/**`,
    `app/reflection/**`, `app/paper_shadow/**`,
    `app/sandbox/**`, `app/state_machine/**`,
    `app/scanner/**`, `app/regime/**`, `app/market_data/**`,
    `app/market_data_public/**`, `app/universe/**`,
    `app/liquidity/**`, `app/manipulation/**`,
    `app/monitoring/**`, `app/database/**`, `app/exports/**`,
    `app/incidents/**`, `app/learning/**`, `app/llm/**`,
    `app/paper_run/**`, `app/reconciliation/**`,
    `app/confirmation/**`, `app/capital/**`, `app/core/**`,
    `app/main.py`,
  - `scripts/**`, `configs/**`, `data/**`, `requirements.txt`,
    `pyproject.toml`, `.env*`.

---

## 20. Test command

```
python -m pytest tests/unit/test_replay_feed_provider.py -q
```

Result: **26 PASSING** tests covering all 21 brief-mandated
scenarios plus 5 defensive extras.

Full suite:

```
python -m pytest tests/unit -q
```

Result: **3479 PASSING** tests, 0 failures (was 3453 before this
phase; +26 from this phase).

---

## 21. Acceptance status

**Status:** IN_REVIEW (after this implementation PR; not
`ACCEPTED` until maintainer review).

`ACCEPTED` requires a separate docs-closeout PR after maintainer
review.

Phase 12 remains **FORBIDDEN**.
