# Phase 11C.1D-D-B — Historical Market Store v0 (PR95)

> *Strict forward-only historical sim-live market data store*
> *严格前向 Sim-Live 历史市场数据存储 v0*
>
> **Status:** IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).
> **Type:** **Implementation PR** (paper / report / evidence-only
> infrastructure).
> **Parent:** Phase 11C.1D-D *Strict Blind Walk-forward Sim-Live
> Constitution* (PR93, merged) and Phase 11C.1D-D-A *SimulationClock
> + Time-Wall Guard* (PR94, merged).
> **Trade authority:** **none.**
> **Phase 12:** **FORBIDDEN.**

---

## 0. Pre-amble — what this PR is and is NOT

This PR ships the **second** anti-future-lookahead infrastructure
block of the strict blind walk-forward stack defined by Phase
11C.1D-D (PR93). It is a small, deterministic, pure-Python in-memory
market data store. It introduces **no** runtime hot-path wiring,
**no** new event types, **no** schema migration, **no** I/O, **no**
network, **no** real data fetch, and **no** authority over the Risk
Engine or the Execution FSM. PR95 builds strictly on top of the PR94
substrate and re-uses every PR94 primitive verbatim
(`SimulationClock`, `HistoricalRecordTime`, `TimeWallGuard`,
`CandleVisibilityGuard`, `NoLookaheadViolation`,
`assert_no_forbidden_fields`).

This PR IS:

  - a closed `HistoricalMarketRecordType` taxonomy (1m / 5m kline,
    funding rate, open interest, 24h ticker, exchangeInfo, symbol /
    listing / delisting status),
  - a closed `DataQualityFlag` taxonomy (`DATA_GAP`, `LATE_ARRIVAL`,
    `REVISED_RECORD`, `INCOMPLETE_KLINE`, `SYMBOL_STATUS_UNKNOWN`,
    `FUNDING_MISSING`, `OI_MISSING`, `TICKER_MISSING`),
  - a closed `SymbolStatus` taxonomy (`TRADING`, `BREAK`, `HALT`,
    `DELISTED`, `SETTLING`, `PRE_TRADING`, `UNKNOWN`) with a
    `TRADABLE_OR_MONITORABLE` subset that the as-of universe query
    consults,
  - a closed `DataCompletenessState` taxonomy (`OK`, `DEGRADED`,
    `INCOMPLETE`, `UNKNOWN`),
  - a `HistoricalMarketRecord` (generic non-kline record),
  - a `HistoricalKlineRecord` (1m / 5m kline; final OHLCV invisible
    before candle close),
  - a `SymbolStatusRecord` (symbol metadata for the as-of universe,
    no survivorship bias),
  - a `HistoricalMarketStore` (in-memory store with
    `available_at <= simulated_time` enforcement, closed-candle
    visibility, deterministic ordering, JSON-serialisable outputs,
    accumulated `NoLookaheadViolation` audit list),
  - the matching unit-test module
    `tests/unit/test_historical_market_store.py`.

This PR is **NOT**:

  - a `ReplayFeedProvider` (PR96's responsibility),
  - a `MockExchange` + Pessimistic Fill Model (PR97's responsibility),
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

PR95 acceptance authorises the next allowed paper-only step
(**PR96 — ReplayFeedProvider**). It does NOT authorise the rest of
the engineering route; each of PR97 → PR100 must pass its own gate.

---

## 1. Purpose

Strict blind walk-forward (PR93 §1) is **not** an ordinary backtest.
At simulated time `T`, the system MAY only access records whose
`available_at <= T`. Any module that touches simulation-sensitive
state must consume a single, deterministic, audit-rich substrate so
that the §5 / §6 / §9 anti-leakage rules become machine-enforceable.

PR94 supplied the time substrate (clock + time wall + closed-candle
visibility). PR95 supplies the **data substrate**: a typed historical
market record schema with the four-timestamp record-time model and
the rules the time wall needs to do its job, plus an in-memory store
that consults that time wall on every read.

The objective is **truthful, deterministic, reproducible historical
data discipline**, not pretty equity curves. Pretty curves produced
by even one form of leakage are not evidence; they are
falsifications. PR95 makes the leakage path syntactically impossible
for the modules that consume it, and turns every attempted future
read into an auditable `NoLookaheadViolation`.

---

## 2. Relation to PR93 constitution

PR93 (the *Strict Blind Walk-forward Sim-Live Constitution*) is
docs-only. PR95 is the **second implementation slice** authorised by
PR93 §19's engineering route (after PR94 was merged). PR95 implements
the data substrate required by:

  - **§5 Time-Wall Constitution.** Every historical record MUST
    distinguish four timestamps (`event_time`, `available_at`,
    `ingested_at`, `source`). At simulated time `T`, the store MAY
    only read records whose `available_at <= T`. `ingested_at` is
    NEVER a substitute for `available_at`.
  - **§6 Candle visibility rule.** A 1m / 5m / longer-period candle's
    final OHLCV is fully visible only after that candle has closed.
    The store enforces this by requiring `available_at >= close_time`
    on every kline at construction time AND cross-checking with
    `CandleVisibilityGuard.is_candle_closed` on every kline query.
  - **§9 As-of market universe.** No survivorship bias. A symbol is
    in the universe at `T` iff its latest visible
    `SymbolStatusRecord` has `listed_at <= T` AND
    (`delisted_at is None` OR `delisted_at > T`) AND
    `available_at <= T` AND `status` is in
    `SymbolStatus.TRADABLE_OR_MONITORABLE`. The store NEVER consults
    the *current* symbol list; an empty store at any `T` returns an
    empty universe.
  - **§10 Historical data scope (v0 minimum).** 1m / 5m kline,
    funding rate, open interest, 24h ticker, exchangeInfo, listing /
    delisting timeline. Tick / orderbook is deferred. PR95 ships
    record types for exactly that v0 minimum, and **only** that.
  - **§E Data revision / late arrival policy.** A record not
    available at `T` MAY NOT be used inside `T` even after correction.
    Revisions are first-class records with `revision_time`,
    `revised_from_record_id`, and `late_arrival` fields, and become
    visible only after their own `available_at`. The original record
    remains in the audit trail; the revision NEVER overwrites it.
  - **§F Run invalidation rules.** Future-record access, missing
    `available_at`, and substituting `ingested_at` for `available_at`
    are all `NO_LOOKAHEAD_VIOLATION` audit events. PR95 routes every
    such event through the PR94 `NoLookaheadViolation` taxonomy and
    accumulates them on the store for downstream invalidation
    checks.

PR93 §19 explicitly authorises ONLY PR95 to begin this gate. PR95
does NOT touch §11 (MockExchange + Pessimistic Fill Model), §12
(Latency / Outage / Data Degradation injection), §13 (Simulated
Capital Flow), §14 (Telegram sandbox), §15 (AI role), §16 (Required
outputs), §17 (Acceptance criteria). Those are the responsibility of
PR96 → PR100, each behind its own gate.

---

## 3. Relation to PR94 SimulationClock + Time-Wall Guard

PR94 supplied the time substrate. PR95 reuses every PR94 primitive
verbatim:

  - `SimulationClock` — the strict forward-only simulated UTC clock.
    PR95 does NOT introduce a competing clock. Every PR95 query takes
    a `simulated_time` argument and runs it through
    `ensure_utc_aware()` so naive datetimes are rejected and non-UTC
    offsets are normalised to UTC.
  - `HistoricalRecordTime` — the four-timestamp record-time helper.
    Every PR95 record exposes a `to_record_time()` method that
    constructs a `HistoricalRecordTime` from its own
    `event_time` / `available_at` / `ingested_at` / `source` /
    `record_id` / `symbol` / `interval`. The store passes this to
    `TimeWallGuard.validate_no_lookahead` on every read.
  - `TimeWallGuard` — the `available_at <= simulated_time`
    enforcement layer. The store's
    `query_records` / `query_latest` / `query_klines` /
    `query_symbol_status` / `query_asof_universe` methods all delegate
    visibility to `TimeWallGuard.validate_no_lookahead`. Records
    rejected by the guard are NEVER silently dropped; the resulting
    `NoLookaheadViolation` is appended to `store.violations` for
    audit.
  - `CandleVisibilityGuard` — the closed-candle visibility rule. The
    store's `query_klines` cross-checks
    `CandleVisibilityGuard.is_candle_closed(open_time, interval,
    simulated_time)` even after the time wall has passed. If a kline
    survives the time wall but somehow lands on an unclosed candle
    relative to `simulated_time`, the store mints an
    `UNCLOSED_CANDLE_FIELD_ACCESS` violation via
    `TimeWallGuard.make_unclosed_candle_field_access_violation` and
    refuses to return the record.
  - `NoLookaheadViolation` (closed reason / severity taxonomy:
    `FUTURE_AVAILABLE_AT`, `MISSING_AVAILABLE_AT`,
    `INGESTED_AT_USED_AS_AVAILABILITY`,
    `UNCLOSED_CANDLE_FIELD_ACCESS`,
    `OUTCOME_LABEL_DURING_BLIND_WINDOW`; severities `P0`, `P1`) —
    PR95 produces these via the PR94 helper API. PR95 does NOT
    introduce new reasons; the taxonomy is closed.
  - `assert_no_forbidden_fields` — every PR95 record's `to_dict()`
    runs through this recursive guard before returning. Any payload
    that smuggles a trade-action / runtime-config-patch / "live
    ready" / "trading approved" field at any nesting depth is
    rejected at construction time.

Hard rule: PR95 NEVER calls `datetime.now()` /
`datetime.utcnow()` / `time.time()` / `time.monotonic()` /
`pandas.Timestamp.now()` to compute decision time. Every visible
moment is the caller-supplied `simulated_time`. The store has no
internal clock of its own.

---

## 4. Historical record schema

PR95 ships three concrete record types. All three are
`@dataclass(frozen=True)`, all three carry the four-timestamp
record-time model, all three are JSON-serialisable, and all three
have a `to_record_time()` method that the store uses to drive the
time wall.

### 4.1 `HistoricalMarketRecord` (generic, non-kline)

| field | type | required | notes |
| --- | --- | --- | --- |
| `record_id` | `str` | ✓ | non-empty |
| `record_type` | `str` | ✓ | one of `HistoricalMarketRecordType.ALLOWED` |
| `symbol` | `Optional[str]` | — | `EXCHANGE_INFO` may have no per-symbol scope |
| `event_time` | `datetime` | ✓ | UTC-aware |
| `available_at` | `datetime` | ✓ | UTC-aware; `>= event_time` |
| `ingested_at` | `Optional[datetime]` | — | UTC-aware if set; **NEVER** used as availability |
| `source` | `Optional[str]` | — | provider / endpoint |
| `interval` | `Optional[str]` | — | when set, must be in PR94's closed interval taxonomy |
| `payload` | `Mapping[str, Any]` | — | JSON-serialisable; runs `assert_no_forbidden_fields` at construction |
| `data_quality_flags` | `Tuple[str, ...]` | — | subset of `DataQualityFlag.ALLOWED` |
| `evidence_refs` | `Tuple[str, ...]` | — | string references only |
| `revision_time` | `Optional[datetime]` | — | UTC-aware if set |
| `revised_from_record_id` | `Optional[str]` | — | non-empty if set |
| `late_arrival` | `bool` | — | default `False` |

### 4.2 `HistoricalKlineRecord` (1m / 5m kline)

| field | type | required | notes |
| --- | --- | --- | --- |
| `symbol` | `str` | ✓ | non-empty |
| `interval` | `str` | ✓ | v0: `"1m"` or `"5m"` only |
| `open_time` | `datetime` | ✓ | UTC-aware |
| `open` / `high` / `low` / `close` / `volume` | `float` | ✓ | OHLC sanity enforced; `volume >= 0` |
| `available_at` | `datetime` | ✓ | UTC-aware; **MUST be `>= close_time`** (Constitution §6) |
| `close_time` | `Optional[datetime]` | — | defaults to `open_time + interval`; explicit value must agree |
| `event_time` | `Optional[datetime]` | — | defaults to `open_time`; must lie within `[open_time, close_time]` |
| `ingested_at` | `Optional[datetime]` | — | UTC-aware if set |
| `source` | `Optional[str]` | — | provider / endpoint |
| `record_id` | `Optional[str]` | — | defaulted from `(symbol, interval, open_time)` |
| `data_quality_flags` | `Tuple[str, ...]` | — | subset of `DataQualityFlag.ALLOWED` |
| `evidence_refs` | `Tuple[str, ...]` | — | string references only |
| `revision_time` / `revised_from_record_id` / `late_arrival` | — | — | revision policy as for the generic record |

`record_type` is computed: `"1m"` → `KLINE_1M`, `"5m"` → `KLINE_5M`.

### 4.3 `SymbolStatusRecord` (as-of universe)

| field | type | required | notes |
| --- | --- | --- | --- |
| `symbol` | `str` | ✓ | non-empty |
| `market_type` | `str` | ✓ | non-empty (e.g. `"PERP"`, `"SPOT"`) |
| `listed_at` | `datetime` | ✓ | UTC-aware |
| `status` | `str` | ✓ | one of `SymbolStatus.ALLOWED` |
| `available_at` | `datetime` | ✓ | UTC-aware; `>= event_time` |
| `delisted_at` | `Optional[datetime]` | — | UTC-aware if set; required when `status == DELISTED` |
| `min_notional` / `tick_size` / `step_size` | `Optional[float]` | — | non-negative if set |
| `contract_type` | `Optional[str]` | — | provider-specific |
| `data_completeness_state` | `str` | — | one of `DataCompletenessState.ALLOWED`; default `OK` |
| `source` / `ingested_at` / `record_id` | — | — | as for the generic record |
| `event_time` | `Optional[datetime]` | — | defaults to `listed_at`; the **only** field that may legitimately allow `available_at < listed_at` (pre-listing announcement) by being set explicitly to the announcement time |
| `data_quality_flags` / `evidence_refs` / `revision_time` / `revised_from_record_id` / `late_arrival` | — | — | as for the generic record |

`record_type` is computed: always `SYMBOL_STATUS`.

---

## 5. `event_time` vs `available_at` vs `ingested_at`

Constitution §5 is verbatim:

  - `event_time` — when the underlying market event actually
    occurred. For a kline this is a point inside `[open_time,
    close_time]`; for a funding rate, the funding observation time;
    for a listing, the moment trading became live.
  - `available_at` — the earliest time at which a sim-live consumer
    could legitimately have observed the record. For a kline this is
    `>= close_time` (final OHLCV invisible before close + provider
    publication latency). For a funding rate / OI / ticker, this is
    the publish time. For a listing, this is when the exchange
    publicised the listing.
  - `ingested_at` — when the record entered the historical store.
    `ingested_at` is BOOK-KEEPING, not visibility. **`ingested_at` is
    NEVER a valid substitute for `available_at`.** A record whose
    `ingested_at <= T` but whose `available_at > T` is still future
    data and MUST be rejected by the time wall.
  - `source` — which provider / endpoint produced the record.
    Required for audit; does NOT participate in visibility logic.

The store enforces this discipline by:

  1. requiring `available_at` on every record at construction time
     (the dataclasses cannot be built without it),
  2. enforcing `available_at >= event_time` at construction time
     (with the `SymbolStatusRecord` pre-listing-announcement
     exception, which still requires `available_at >= event_time`
     once `event_time` is explicitly set to the announcement time),
  3. routing every read through `TimeWallGuard.validate_no_lookahead`
     which ONLY consults `available_at` (never `ingested_at`),
  4. exposing `TimeWallGuard.make_ingested_at_used_as_availability_violation`
     so any caller that incorrectly substitutes the two can mint an
     audit object even before reaching the store.

---

## 6. The `available_at <= simulated_time` rule

Single rule: at simulated time `T`, a record is visible iff
`available_at <= T`. The store implements this as follows:

  - `query_records(record_type, *, symbol, start_time, end_time,
    simulated_time)` — filters by `record_type`, optional `symbol`,
    and `event_time` bounds, then runs every candidate through
    `TimeWallGuard.validate_no_lookahead`. Visible records are
    returned sorted by `(event_time, available_at, symbol,
    record_id)`. Rejected records produce `NoLookaheadViolation`
    audit objects appended to `store.violations`.
  - `query_latest(record_type, symbol, simulated_time)` — returns the
    record with the largest `event_time` (ties broken by
    `available_at` then `record_id`) that is visible at
    `simulated_time`.
  - `query_klines(symbol, interval, *, start_time, end_time,
    simulated_time)` — filters by `symbol` / `interval` /
    `open_time` bounds, runs the time wall, then runs the closed-
    candle visibility check (§7) before returning.
  - `query_symbol_status(symbol, simulated_time)` — returns the
    latest visible `SymbolStatusRecord` for `symbol`, or `None` if
    no such record is visible.
  - `query_asof_universe(simulated_time)` — see §8.

Records are NEVER silently dropped. Every rejected record produces a
`NoLookaheadViolation` with the appropriate closed reason
(`FUTURE_AVAILABLE_AT` for future data, `MISSING_AVAILABLE_AT` if a
caller hand-rolls a Mapping-shape record without `available_at`,
`UNCLOSED_CANDLE_FIELD_ACCESS` for unclosed-candle final-field
access, `INGESTED_AT_USED_AS_AVAILABILITY` for the substitution
audit). Callers can read the accumulated audit list via
`store.violations` and reset it via `store.clear_violations()`.

---

## 7. Kline closed-candle visibility rule

Constitution §6: a 1m / 5m / longer-period candle's final OHLCV
(`high` / `low` / `close` / `volume`) is fully visible only after
that candle has closed. Without tick / trade data, intra-bar paths
are ambiguous and cannot be inferred (a downstream pessimistic fill
model in PR97 will pick `AMBIGUOUS_INTRABAR_PATH` for those cases;
PR95 simply refuses to leak unclosed-candle final fields).

The store enforces this in two places:

  1. **At record construction.** `HistoricalKlineRecord` rejects any
     `available_at < close_time`. By construction, no kline in the
     store can advertise final OHLCV before its candle has closed.
  2. **At query time.** `query_klines` cross-checks
     `CandleVisibilityGuard.is_candle_closed(open_time, interval,
     simulated_time)` even after the time wall has passed. The candle
     is closed when `simulated_time >= close_time` (the close instant
     itself counts as closed). If somehow a kline survives the time
     wall but the candle is not yet closed, the store mints an
     `UNCLOSED_CANDLE_FIELD_ACCESS` violation and refuses to return
     the record.

The two checks are intentionally redundant. Construction-time
enforcement protects against bad-shape inputs; query-time enforcement
protects against subtle bugs where `available_at` was somehow set
earlier than `close_time` through a mapping-shape backdoor that
bypassed the dataclass.

---

## 8. As-of universe rule

Constitution §9: as-of universe queries MUST NOT use the *current*
symbol list to reconstruct the past.

`HistoricalMarketStore.query_asof_universe(simulated_time)` returns
the set of `SymbolStatusRecord` rows for which **all** of the
following hold:

  - `available_at <= simulated_time` (time wall),
  - `listed_at <= simulated_time` (the symbol had actually listed by
    `simulated_time`),
  - `delisted_at is None` OR `delisted_at > simulated_time` (the
    symbol had NOT been delisted by `simulated_time`; a `delisted_at`
    that equals `simulated_time` excludes the symbol from the
    universe at that exact instant — see §9 below),
  - `status` is in `SymbolStatus.TRADABLE_OR_MONITORABLE`
    (`TRADING`, `BREAK`, `HALT`, `SETTLING`, `PRE_TRADING`).
    `DELISTED` is **explicitly excluded** even if the time wall and
    listing checks pass, because a delisted symbol is not tradable
    or monitorable.

Multi-snapshot dedup: if a symbol has more than one visible
`SymbolStatusRecord` at `simulated_time`, the latest by
`(event_time, available_at, record_id)` is the one consulted. The
result is sorted by `(symbol, listed_at, record_id)` for
determinism.

---

## 9. Survivorship bias prevention

Two complementary defences:

  - **No baked-in current symbol list.** The store's only knowledge
    of which symbols exist is the set of `SymbolStatusRecord` rows
    that have been added to it. An empty store at any `T` returns an
    empty universe. There is no "default" universe. There is no
    config-supplied universe.
  - **Strict listing / delisting timeline gating.** Each
    `SymbolStatusRecord` carries `listed_at` and (optional)
    `delisted_at`. A record claiming a symbol existed before its
    `listed_at` is rejected at the universe boundary; a record whose
    `delisted_at <= simulated_time` is excluded at the universe
    boundary. The store does NOT use the current state of the symbol
    to reconstruct any past state — every past state is reconstructed
    from a record whose own `available_at` is `<= simulated_time`.

Tested by `test_asof_universe_does_not_use_current_symbol_list`: an
empty store at any `simulated_time` returns `[]`; adding a single
symbol with `listed_at = T0 + 1h` and querying at `T0` returns `[]`
even though the record is "currently in the store at the program-
runtime level".

---

## 10. Data quality flags

Closed taxonomy `DataQualityFlag.ALLOWED`:

| flag | meaning |
| --- | --- |
| `DATA_GAP` | a known gap between adjacent records of the same record_type / symbol |
| `LATE_ARRIVAL` | the record arrived after its expected publication latency |
| `REVISED_RECORD` | the record is a corrected version of an earlier record (carries `revised_from_record_id`) |
| `INCOMPLETE_KLINE` | a kline whose underlying tick stream had gaps |
| `SYMBOL_STATUS_UNKNOWN` | a symbol metadata record whose status could not be confirmed at the source |
| `FUNDING_MISSING` | a funding-rate cycle for which no record was published |
| `OI_MISSING` | an open-interest snapshot interval for which no record was published |
| `TICKER_MISSING` | a 24h-ticker snapshot interval for which no record was published |

Adding a new flag is a docs / brief / new-PR concern, not a runtime
knob. The dataclasses reject any flag string that is not in this
closed set.

Flags are preserved end-to-end: they are stored on the record, are
returned by every query, and appear verbatim in `to_dict()`.

---

## 11. Late-arrival / data revision policy

Constitution §E: a record not available at `T` MAY NOT be used
inside `T` even after correction. Revisions are logged with their
own `revision_time` / `available_at`; corrected-data replay requires
a new data-manifest hash and becomes a new run, never overwriting
old evidence.

PR95 implements §E as follows:

  - A revised record is just another record. It carries
    `revision_time`, `revised_from_record_id`, `late_arrival`, and
    typically `data_quality_flags = (REVISED_RECORD, LATE_ARRIVAL)`.
  - The revised record's own `available_at` decides its earliest
    visibility. A revision that arrives at `T0 + 10m` becomes visible
    at `T0 + 10m`; querying at `T0 + 2m` returns the original
    only.
  - The original record is **NOT** removed when a revision is added.
    Both records remain in the store. At sufficiently late
    `simulated_time` both are visible to `query_records`, and
    `query_latest` will pick the revision (deterministic tie-break:
    larger `event_time`, then larger `available_at`, then larger
    `record_id`).
  - The store NEVER overwrites old evidence. There is no `update`
    method; there is no `delete` method.

Tested by
`test_late_arrival_and_revised_record_visible_only_after_own_available_at`.

---

## 12. This does NOT implement `ReplayFeedProvider`

PR95 ships a typed in-memory **store**. It does NOT replay records
into a feed pipeline. There is no:

  - `next()` / `tick()` / `step()` / `peek()` provider iterator,
  - feed pipeline that decides which record to surface at a given
    simulated tick,
  - subscription API for downstream consumers,
  - integration with the MarketDataBuffer.

The store is consulted via `query_*` methods that take an explicit
`simulated_time`. Wiring those methods into a forward-only feed
provider (and the surrounding ordering / interleaving discipline) is
PR96's responsibility.

---

## 13. This does NOT implement `MockExchange`

PR95 has no concept of orders, fills, latency, slippage,
pessimistic fill, or order lifecycle. It has no
`place_order` / `submit_order` / `cancel_order` / `set_leverage` /
`set_stop` / `set_target` method. It has no order books. It has no
position state. The MockExchange + Pessimistic Fill Model (Constitution
§11) is PR97's responsibility.

The unit suite explicitly asserts that no public method on the store
or any record type exposes a trade verb (`buy`, `sell`,
`place_order`, `submit_order`, `long`, `short`, `open_position`,
`close_position`, `set_leverage`, `set_stop`, `set_target`,
`apply_change`, `deploy`, `enable_live`).

---

## 14. This does NOT implement Blind Walk-forward Runner

PR95 has no concept of a run, a window, a freeze, a manifest hash,
a Blind Run Manifest, a Trade Ledger, an Equity Timeseries, a
Discovery Quality Ledger, a Failure Ledger, a Telegram Sandbox
Transcript, or an AI Operator Briefing (Constitution §16). It has no
training / freeze / blind / score / experience-update loop
(Constitution §8). It has no run-status taxonomy. It has no
`INVALIDATED_LOOKAHEAD_OR_DRIFT` concept. The Blind Walk-forward
Runner is PR100's responsibility.

PR95 supplies the **data substrate** that the runner will consume.
That is the entire scope.

---

## 15. This does NOT authorise live trading

Hard safety boundary (Phase 11C.1D-D-B / PR95):

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

Every record's `to_dict()` re-pins this boundary at the serialisation
edge via the recursive `assert_no_forbidden_fields` guard. Every
violation's `to_dict()` does the same. Every `store.to_dict()` and
`store.safety_payload()` does the same. The Risk Engine remains the
single trade-decision gate.

---

## 16. This does NOT authorise auto-tuning

PR95 NEVER writes runtime config. PR95 exposes no `apply_change`,
`deploy_change`, `runtime_config_patch`, `symbol_limit_patch`,
`threshold_patch`, `candidate_pool_patch`, `regime_weight_patch`, or
`strategy_parameter_patch` field. The recursive
`assert_no_forbidden_fields` guard refuses any payload that smuggles
those names at any nesting depth. `auto_tuning_allowed=False` is
re-pinned on every serialisation boundary.

A `data_completeness_state=DEGRADED` flag on a `SymbolStatusRecord`,
or any combination of `DataQualityFlag.*` markers, is descriptive
audit metadata only. It MUST NEVER trigger a runtime knob change. It
MUST NEVER trigger a real trade. Downstream modules that consume
those flags inherit the same safety contract.

---

## 17. This does NOT authorise Phase 12

Phase 12 remains **FORBIDDEN**. The literal string `"Phase 12"` does
not appear as a destination in
`HISTORICAL_MARKET_STORE_PHASE_NAME`. Every `to_dict()` boundary
re-pins `phase_12_forbidden=True`. Tests assert that the flag is
true on the store, every record type, and every violation produced
by store reads.

---

## 18. Successful PR95 only allows PR96 ReplayFeedProvider

Next-allowed-phase decision rule:

  - PR95 acceptance only authorises **PR96 — ReplayFeedProvider** to
    begin its own gate.
  - PR95 acceptance does **NOT** authorise PR97 (MockExchange +
    Pessimistic Fill Model), PR98 (Simulated Capital Flow + Trade
    Ledger), PR99 (Telegram Sandbox Outbox), PR100 (Blind
    Walk-forward Runner), live trading, auto-tuning, the DeepSeek hot
    path, Telegram live outbound, or Phase 12. **Phase 12 remains
    FORBIDDEN.**

---

## 19. File map

| file | role |
| --- | --- |
| `app/sim/historical_market_store.py` | the core implementation |
| `app/sim/__init__.py` | re-exports the new public surface alongside the PR94 substrate |
| `tests/unit/test_historical_market_store.py` | 26 PASSING tests covering all 21 brief-mandated scenarios plus 5 defensive extras (closed-taxonomy sweep, kline construction-time invariants, symbol-status invariants, latest-symbol-status, deterministic violation IDs) |
| `docs/PHASE_11C_1D_D_B_HISTORICAL_MARKET_STORE.md` | this file |
| `docs/PROJECT_STATUS.md` | current-phase block updated |
| `docs/PHASE_GATE.md` | new *Open phase: Phase 11C.1D-D-B* section appended; Phase 12 row unchanged |
| `docs/CHANGELOG.md` | this PR's entry |

Files **explicitly NOT touched** by this PR:

  - `app/risk/**`, `app/execution/**`, `app/exchanges/**`,
    `app/telegram/**`, `app/config/**`,
  - `app/safety/**`, `app/ai/**`, `app/replay/**`,
    `app/reflection/**`, `app/paper_shadow/**`, `app/sandbox/**`,
    `app/state_machine/**`, `app/scanner/**`, `app/regime/**`,
    `app/market_data/**`, `app/market_data_public/**`,
    `app/universe/**`, `app/liquidity/**`, `app/manipulation/**`,
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
python -m pytest tests/unit/test_historical_market_store.py -q
```

Optional full suite:

```
python -m pytest tests/unit -q
```

PR95 status when both commands return PASSING with **0** regressions
relative to the post-PR94 baseline (3427 PASSING): **IN_REVIEW**.
Promotion to **ACCEPTED** requires a separate docs-closeout PR after
maintainer review.
