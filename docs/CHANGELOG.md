# Changelog

All notable changes to AMA-RT will be recorded in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows the project phase plan in `docs/AMA_RT_V1_4_Production_Spec_Kiro.md` §43.

## [Unreleased]

### Phase 7 - Issue #7 review fix: conservative throughput discount

Issue #7 review pointed out that the original PR deferred the
Phase 5 ``can_exit_position`` upper-bound discount to Issue #8 / #9.
That is wrong - Spec §27.2 + §19.2 require the Risk Engine to apply
the conservative discount itself. This commit moves the discount on
to the Phase 7 No-Trade Gate, where Issue #7 actually wants it.

#### Added

- ``RiskEngine.throughput_safety_factor`` (default ``0.5``) and a
  matching ``throughput_safety_factor: float | None`` field on
  :class:`RiskRequest`. Allowed range is ``(0.0, 1.0]``; the engine
  raises ``ValueError`` outside that range. Per-request overrides
  are honoured.
- ``RiskRequest.max_exit_seconds`` (optional) - ceiling for the
  discounted re-check. When ``None`` the engine derives it from the
  supplied :class:`LiquidityDecision` / :class:`ExitPlan`.
- ``NoTradeGateInput.throughput_safety_factor`` and
  ``NoTradeGateInput.max_exit_seconds`` so the gate can be driven
  directly by tests / replay.
- :attr:`RiskRejectReason.LIQUIDITY_THROUGHPUT_INSUFFICIENT` typed
  reject reason: fires when
  ``estimated_exit_seconds / throughput_safety_factor`` exceeds the
  resolved ``max_exit_seconds`` ceiling on a new opening.
- ``RISK_APPROVED`` / ``RISK_REJECTED`` audit payload now carries
  ``throughput_safety_factor`` and ``max_exit_seconds`` so
  Reflection (Issue #10) can reproduce the decision.
- README "Phase 7 conservative throughput discount" subsection that
  explains the Issue #7 hard rule, the resolution policy
  (``RiskRequest.throughput_safety_factor`` -> engine default), and
  the reuse rule for any future Phase 5
  ``LiquidityConfig.throughput_safety_factor``.

#### Changed

- ``app/risk/no_trade_gate.py`` - the Phase 5 ``can_exit_position``
  output is now treated as an upper bound. The gate runs the raw
  feasibility check first (``NO_EXIT_CHANNEL`` /
  ``LIQUIDITY_REJECTED`` / ``DATA_DEGRADED`` still fire as before)
  and then runs the discounted re-check on every new opening with a
  feasible plan. Step ordering is deterministic so reflective tools
  see the most severe / earliest reason at index 0.
- ``app/risk/engine.py`` - ``RiskEngine.__init__`` accepts the new
  keyword. Audit payload extended.
- README + CHANGELOG explicit: "Risk Engine treats liquidity
  throughput as an upper bound and applies a conservative safety
  factor before allowing ATTACK / RIGHT_TAIL_AMPLIFY."

#### Reuse policy

If a future Phase 5 PR ever adds ``throughput_safety_factor`` to
``LiquidityConfig``, the Phase 7 engine MUST consume that field
directly instead of defining its own. As of this commit no such
field exists on ``LiquidityConfig`` and the
``app/liquidity/`` package is unchanged.

#### Tests

**+9 new tests on top of the 714 from the Phase 7 PR = 723 total,
all passing.**

| Test | Pins |
| --- | --- |
| ``test_throughput_safety_factor_default_is_one_half`` | Default factor is 0.5. |
| ``test_throughput_safety_factor_invalid_rejected`` | (0.0, 1.0] enforced; constructor raises ``ValueError`` outside that range. |
| ``test_raw_feasible_plan_rejected_when_discounted_exceeds_ceiling`` | Issue #7 review fix: 40s raw + factor 0.5 -> 80s discounted -> REJECT with ``liquidity_throughput_insufficient``. |
| ``test_raw_feasible_plan_passes_when_discounted_under_ceiling`` | 10s raw + factor 0.5 -> 20s discounted -> APPROVE. |
| ``test_data_degraded_blocks_even_when_raw_plan_is_feasible`` | Issue #7 review fix: feasible plan + degraded data -> still rejected with ``data_degraded``. |
| ``test_no_trade_gate_throughput_discount_directly`` | Direct ``evaluate_no_trade_gate(...)`` regression so the discount is independently pinned at the gate level. |
| ``test_per_request_safety_factor_override_honoured`` | Per-request ``throughput_safety_factor=1.0`` (no discount) approves the same input that 0.5 would refuse. |
| ``test_engine_level_safety_factor_override_honoured`` | ``RiskEngine(throughput_safety_factor=0.9)`` approves a 40s/60s plan. |
| ``test_audit_payload_includes_throughput_safety_factor`` | The factor is on the persisted ``RISK_APPROVED`` audit row. |

#### Live trading risk

**None.** This commit only adds defensive plumbing: a new
multiplicative discount, a new typed reject reason, two new
optional ``RiskRequest`` fields, and audit-payload entries. No new
mode flag, no loosened safety lock, no new dependency, no new
write surface, no new network surface, no LLM. The Phase 1 safety
lock, the Phase 3 read-only invariant, the Phase 4 / 5 / 6
boundaries remain unchanged.

### Phase 7 - State Machine Risk Engine

#### Added

- **`app/state_machine/` package** (Spec §26, Issue #7).
  - `TradeStateMachine` per-symbol Trade State Machine implementing
    the Spec §26.1 ladder (`NO_TRADE -> OBSERVE -> SCOUT -> CONFIRM
    -> ATTACK -> RIGHT_TAIL_AMPLIFY -> LOCK_PROFIT ->
    DISTRIBUTION_ALERT -> FORCED_EXIT`).
  - Whitelisted transition table forbidding level skipping
    (Issue #7 hard rule 1). OBSERVE cannot directly become
    RIGHT_TAIL_AMPLIFY; SCOUT cannot directly become ATTACK; every
    illegal attempt raises :class:`IllegalStateTransition`.
  - `promote(TradeStateContext)` / `downgrade(reason)` /
    `record_breakout_failure()` / `record_distribution_bar()` /
    `lock_profit()` / `distribution_alert()` / `forced_exit()` /
    `tick(clock_ms)` / `reset()` operations. Each successful
    transition writes one ``STATE_TRANSITION`` event with the
    `from / to / trigger / reasons` payload.
  - Phase 7 hard rules enforced: CONFIRM-failures downgrade to
    SCOUT after the configured threshold; DISTRIBUTION_ALERT
    cannot promote; FORCED_EXIT is sticky (only `reset()` clears
    it); a losing position cannot enter RIGHT_TAIL_AMPLIFY;
    right-tail amplification must come from floating profit.
  - Spec §26.4 timeouts implemented in `tick(clock_ms)`: OBSERVE
    -> NO_TRADE after 30 min, SCOUT -> NO_TRADE after 12 min,
    ATTACK -> LOCK_PROFIT on `cvd_weakening=True`,
    RIGHT_TAIL_AMPLIFY -> LOCK_PROFIT on
    `right_tail_core_failed=True`, DISTRIBUTION_ALERT -> FORCED_EXIT
    after 3 confirming bars.
  - :class:`TimeoutConfig` exposes the timeout policy as a frozen
    dataclass so YAML overrides remain a future, additive change.

- **`app/risk/no_trade_gate.py`** (Spec §27.2, Issue #7).
  - `evaluate_no_trade_gate(NoTradeGateInput) -> NoTradeGateDecision`
    composes every Spec §27.2 condition into a typed
    :class:`RiskRejectReason` list. Walks in stable order so the
    "first" reason in the list is the most severe / earliest.
  - Reads Phase 5 `RegimeSnapshot.risk_permission`,
    `UniverseDecision.eligible`, `LiquidityDecision.passed`, and
    `ExitPlan.feasible`.
  - Reads Phase 6 `ManipulationLevel` and
    `TradeConfirmationLevel`.
  - Reads exchange-link state, market-data degraded view,
    stop-confirmation, position-known flag, and the two circuit
    breaker states.
  - Honours the `is_new_open` flag so Phase 9 can call the gate
    on a protective-exit / reduce-only path without M3 / regime /
    data-degraded firing.

- **`app/risk/account_tier.py`** (Spec §27.4, Issue #7).
  - `classify_account_tier(current_equity, initial_capital) ->
    AccountLifeTier` pure function (A..F by equity ratio).
  - `ACCOUNT_TIER_POLICY` table + `policy_for(tier)` helper. Each
    `AccountTierPolicy` exposes `allow_new_open`, `allow_attack`,
    `allow_right_tail_amplify`, `allow_live_trading`, `halt_only`,
    `paper_only`, `notes`. Tiers D / E / F progressively restrict
    the ladder; tier F is halt-only.

- **`app/risk/circuit_breaker.py`** (Spec §27.2, Issue #7).
  - `ConsecutiveLossCircuitBreaker` opens after N consecutive
    losses (default 5). `record_loss()` / `record_win()` /
    `reset()`. A winning trade does NOT auto-close an opened
    breaker - Phase 7 requires an explicit `reset()`.
  - `DailyLossCircuitBreaker` opens once cumulative gross daily
    loss exceeds `max_daily_loss_pct * initial_capital` (default
    5%). Rolls over on UTC date change. Same explicit-`reset()`
    contract.

- **`app/risk/engine.py` Phase 7 extension** (Spec §27, Issue #7).
  - `RiskRequest` gained ten optional Phase 7 fields:
    `is_new_open` (default `True` for backwards compat),
    `regime_snapshot`, `universe_decision`, `liquidity_decision`,
    `exit_plan`, `is_data_degraded`, `exchange_connection_state`,
    `current_equity`, `initial_capital`, `account_tier_override`.
  - `RiskEngine.evaluate(...)` now composes the Phase 1 hard
    flags + Phase 6 hard rules + the Phase 7 No-Trade Gate +
    Account Life Tier policy + Circuit Breaker state into one
    decision.
  - `RiskEngine.record_loss(loss_amount=)` /
    `record_win(profit_amount=)` /
    `configure_initial_capital(initial_capital=)` are the public
    hooks Issue #8 (Capital Flow Engine) will use to record
    realised PnL onto the breakers without re-instantiating the
    engine.
  - The audit payload extends Phase 6 with `account_tier`,
    `is_new_open`, `regime`, `risk_permission`,
    `exchange_connection_state`, `daily_loss_breaker_state`,
    `consecutive_loss_breaker_state`, `no_trade_gate_reasons`,
    `no_trade_gate_notes`. Reasons are still rendered as
    byte-compatible strings so Phase 1 / Phase 6 Replay code
    keeps working unchanged.

- **`app/core/enums.py`** new vocabulary:
  - `CircuitBreakerState` (`closed`, `open_daily_loss`,
    `open_consecutive_loss`, `cool_down`).
  - `TradeStateTrigger` (`signal`, `promote`, `downgrade`,
    `timeout`, `lock_profit`, `distribution_alert`,
    `forced_exit`, `kill_switch`, `reset`).
  - `RiskRejectReason` typed enum with **23** values covering
    Phase 1 + Phase 6 + Phase 7 reasons. Values match the Phase 1
    / Phase 6 string reasons byte-for-byte so existing tests and
    audit rows stay byte-compatible.

- **Phase 7 boot self-check in `python -m app.main`**.
  - Drives a `TradeStateMachine` `NO_TRADE -> OBSERVE`
    transition for the first mock symbol. One additional
    ``STATE_TRANSITION`` event is written via the state-machine
    module (the Phase 6 boot drill already wrote one
    `IDLE -> IDLE` marker; Phase 7 raises the total to two).
  - Calls `RiskEngine.evaluate(...)` with
    `is_new_open=False`, the Phase 5 regime snapshot, the Phase
    6 manipulation + confirmation levels, and the exchange link
    state. The bootstrap stays a clean approval because every
    `is_new_open=True`-only gate is bypassed.
  - Banner extended with four Phase 7 fields:
    `state_transitions=`, `trade_state=`, `daily_loss_breaker=`,
    `consecutive_loss_breaker=`.

- **Documentation**.
  - `README.md` rewritten: status table updated (Phase 6 ->
    merged, Phase 7 -> this branch); new "Phase 7 deliverable"
    section with the State Machine ladder + transition rules,
    No-Trade Gate composition, Account Life Tier table, Circuit
    Breaker contract, protective-exit caveat, and seven semantic
    locks.
  - `docs/CHANGELOG.md`: this entry. Phase 6 entries are
    preserved below.
  - `app/__init__.py` bumped to `Phase 7 - State Machine Risk
    Engine` / `1.4.0a7`.

#### Phase 7 hard rules enforced

| Rule | Enforcement |
|---|---|
| 1. No trade-state level skipping | `ALLOWED_TRANSITIONS` whitelist + `IllegalStateTransition`. |
| 2. SCOUT cannot become ATTACK directly | SCOUT -> CONFIRM is the only legal step in `ALLOWED_TRANSITIONS`. |
| 3. CONFIRM failures must downgrade | `record_breakout_failure()` after 2 consecutive failures returns SCOUT. |
| 4. DISTRIBUTION_ALERT cannot promote | `promote(...)` refuses with `cannot_promote_from_distribution_alert`. |
| 5. FORCED_EXIT is sticky | `ALLOWED_TRANSITIONS[FORCED_EXIT] = frozenset()`; only `reset()` clears it. |
| 6. Losing position cannot amplify | Refused at promotion; refused at engine via `right_tail_from_principal_forbidden`. |
| 7. SYSTEMIC_RISK -> BLOCK_ALL | `RiskRejectReason.REGIME_BLOCK_ALL` fires for every new opening. |
| 8. ALT_RISK_OFF -> ALLOW_SCOUT no attack | `RiskRejectReason.REGIME_SCOUT_ONLY_FOR_ATTACK` fires for `attack_intent=True`. |
| 9. M3 blocks new open | `RiskRejectReason.MANIPULATION_M3` fires when `is_new_open=True`; protective exits pass with `is_new_open=False`. |
| 10. M2 + attack_intent blocks | `RiskRejectReason.MANIPULATION_M2_ATTACK`. |
| 11. T0/T1 + attack_intent blocks | `RiskRejectReason.TRADE_CONFIRMATION_TOO_LOW_FOR_ATTACK`. |
| 12. 5 consecutive losses pause new open | `ConsecutiveLossCircuitBreaker` opens; engine emits `CONSECUTIVE_LOSS_BREAKER_OPEN`. |
| 13. Daily loss threshold pauses new open | `DailyLossCircuitBreaker` opens; engine emits `DAILY_LOSS_BREAKER_OPEN`. |
| 14. State transitions persisted | One `STATE_TRANSITION` event per accepted transition. |
| 15. Reject events carry typed reasons | Every reason is a `RiskRejectReason` value; rendered as its string in the audit row. |

#### Tests

123 new Phase 7 unit tests on top of the 591 retained from
Phase 1-6 = 714 total, all passing.

| File | Tests | What it covers |
| --- | --- | --- |
| `tests/unit/test_state_machine.py` | 27 | Issue #7 acceptance criteria 1+2 (no level skipping, no SCOUT->ATTACK), promotion guards, downgrade ladder, CONFIRM-failure threshold, DISTRIBUTION_ALERT cannot promote, three-bar -> FORCED_EXIT, FORCED_EXIT is sticky / only reset() clears it, Spec §26.4 timeouts (OBSERVE / SCOUT / ATTACK / RIGHT_TAIL_AMPLIFY), `STATE_TRANSITION` events persisted, refusal counter, custom `TimeoutConfig` honoured. |
| `tests/unit/test_account_tier.py` | 12 | Tier A..F classifier boundary tests, F when initial_capital invalid, per-tier `AccountTierPolicy` flags, policy table covers every tier. |
| `tests/unit/test_circuit_breaker.py` | 9 | Issue #7 acceptance criteria 12+13: 5 consecutive losses open the breaker; daily-loss threshold opens the breaker; winning does not auto-close an opened breaker; explicit reset returns to closed; gross daily loss is measured (not net); zero-amount and zero-initial-capital edge cases. |
| `tests/unit/test_no_trade_gate.py` | 23 | Every Spec §27.2 condition individually + composed. Acceptance criteria 4 (M2 + attack), 5 (T0/T1 + attack), 8 (liquidity not exitable), 9 (DATA_DEGRADED), plus the ALLOW_SCOUT-no-attack semantic lock and the M3 protective-exit caveat. |
| `tests/unit/test_risk_engine_phase7.py` | 18 | Liquidity reject, no-exit-channel reject, SYSTEMIC_RISK overrides T4 / M0, ALLOW_ATTACK alone does not authorise live trade, T3 alone does not authorise, M3 protective-exit caveat, DATA_DEGRADED rejects new open / passes protective exit, breakers + tier policies, audit payload exposes Phase 7 fields, Phase 1 + Phase 6 + Phase 7 reasons accumulate, `legacy_request_still_approved`. |
| `tests/unit/test_phase7_boundary.py` | 16 | Phase 1 + Phase 3 invariants unchanged, TradeState / AccountLifeTier / CircuitBreakerState / TradeStateTrigger / `RiskRejectReason` vocabularies pinned, public exports complete (`app.risk.__all__`, `app.state_machine.__all__`), Risk Engine + State Machine expose no write surface, do not subclass ExchangeClientBase, `RiskRequest` Phase 7 fields present, `is_new_open` defaults True. |
| `tests/unit/test_phase7_no_network.py` | 9 | No exchange SDK / LLM import under `app/state_machine/` or `app/risk/`, no `api_key` substring, no `os.environ` / `getenv` (AST scan), no write surface, no Issue #8 / #9 / #10 module imports, no MarketDataBuffer / Mock / Binance constructor call, no stand-alone BTC/ETH module added, no other-DB direct sqlite3.connect. |
| `tests/unit/test_main_entrypoint.py` | extended | Phase 7 banner fields (`Phase 7 - State Machine Risk Engine`, `state_transitions=`, `trade_state=`, `daily_loss_breaker=`, `consecutive_loss_breaker=`). |

#### Issue #7 acceptance criteria

| # | Criterion | Test |
| --- | --- | --- |
| 1 | OBSERVE 不能直接 RIGHT_TAIL_AMPLIFY | `test_observe_cannot_directly_become_right_tail_amplify` |
| 2 | SCOUT 不能直接 ATTACK | `test_scout_cannot_directly_become_attack` |
| 3 | M3 必须禁止新开仓 | `test_m3_blocks_new_open` (gate), `test_m3_does_not_block_protective_exit_when_is_new_open_false` (engine) |
| 4 | M2 + attack_intent 必须禁止 ATTACK / RIGHT_TAIL_AMPLIFY | `test_m2_with_attack_intent_blocks` |
| 5 | T0/T1 + attack_intent 必须拒绝进攻 | `test_t0_with_attack_intent_blocks` / `test_t1_with_attack_intent_blocks` |
| 6 | T3/T4 不得单独批准交易 | `test_t3_alone_does_not_authorise_live_trade` |
| 7 | ALLOW_ATTACK 不得单独批准交易 | `test_allow_attack_alone_does_not_authorise_live_trade` |
| 8 | Liquidity 不可退出时必须拒绝进攻 | `test_liquidity_rejected_blocks_attack` / `test_no_exit_channel_blocks_attack` |
| 9 | DATA_DEGRADED 时必须拒绝或降级 | `test_data_degraded_rejects_new_open` / `test_data_degraded_does_not_block_protective_exit` |
| 10 | stop_unconfirmed 必须拒绝新开仓 | `test_stop_unconfirmed_blocks` (gate) + Phase 1 test still applies |
| 11 | unknown_position 必须拒绝新开仓 | `test_unknown_position_blocks` / `test_unknown_position_rejected_for_new_open` |
| 12 | 连续亏损 5 次必须暂停新开仓 | `test_consecutive_loss_breaker_opens_at_threshold` + `test_consecutive_loss_breaker_blocks_new_open` |
| 13 | 单日亏损触发必须暂停新开仓 | `test_daily_loss_breaker_opens_at_threshold` + `test_daily_loss_breaker_blocks_new_open` |
| 14 | 状态转移事件可回放 | `test_state_transition_event_persisted` / `test_full_ladder_writes_all_transition_events` |
| 15 | 风控拒绝事件包含 reason_tags | `test_audit_payload_includes_phase7_fields` (typed `RiskRejectReason` -> string) |
| 16 | pytest 全部通过 | 714 passed |
| 17 | 不存在 live trading 风险 | Defence-in-depth (see "Live trading risk" below) |
| 18 | 不存在真实交易所下单风险 | Same as 17 |

#### Live trading risk

**None.** Phase 7 is additive on top of the Phase 1 - 6 safety
substrate. No exchange SDK, no HTTP client, no LLM client, no
write surface. The Phase 1 safety lock, the Phase 3 read-only
invariant, the Phase 4 / 5 / 6 boundaries are all unchanged. The
boot banner still shows
`mode=paper live_trading=False right_tail=False llm=False
exchange_live_orders=False`.

#### Real exchange order risk

**None.** No `create_order` / `cancel_order` / `set_leverage` /
`set_margin_mode` call site is added. The four
`SafeModeViolation` refusals on `ExchangeClientBase` continue to
apply.

#### Next-phase recommendation

After this merges, **Issue #8 (Phase 8 - Capital Flow / Profit
Harvest / Rebase)** is the next phase. Issue #8 will:

- Replace the in-memory counters in
  `RiskEngine.consecutive_loss_breaker` / `daily_loss_breaker`
  with `capital.db.capital_snapshots` lookups.
- Drive `RiskEngine.configure_initial_capital(...)` from the
  capital event stream, so Account Tier classification is
  always anchored to the latest `lifetime_equity`.
- Add the `CAPITAL_REBASE` flow: pause new openings, recompute
  `risk_budget`, recompute `account_life_tier`, then resume.
- Land the `withdrawn_profit` invariant so a user-initiated
  withdrawal is NOT misread as a draw-down.

The Phase 7 boundary (no exchange SDK, no real network, no API
key, no write surface, no LLM, no stand-alone BTC/ETH module,
trade-state level whitelist) plus the cumulative defence-in-depth
layers will continue to gate against accidental live trading
until the Go/No-Go checklist (§41) is executed end to end.

### Phase 6 - Scanner Confirmation Manipulation

#### Added

- **`app/scanner/` package** (Spec §17 / §18, Issue #6).
  - `PreAnomalyScanner.evaluate(PreAnomalyInput)` /
    `evaluate_snapshot(snapshot, ...)` returns a
    :class:`PreAnomalyDecision` with `pre_anomaly_score` and
    `reason_tags`. Six Spec §17.2 signals: volume base-expansion,
    spread compression, buy-pressure rising, OI soft-rise,
    funding-not-overheated, minor uptrend.
  - `AnomalyScanner.evaluate(AnomalyInput)` returns
    :class:`AnomalyDecision` with `anomaly_score` (Spec §18.2
    weighted sum) and `reason_tags`. Eight Spec §18.1 signals:
    `OI_SPIKE`, `CVD_SPIKE`, `VOLUME_SPIKE`, `ATR_EXPANSION`,
    `FUNDING_EXTREME`, `LIQUIDATION_SPIKE`, `SWEEP`,
    `MULTI_TIMEFRAME_BREAKOUT`. The Spec §18.2 weights live in
    `AnomalyConfig` and sum to 1.0; sweep + multi-tf-breakout add
    bonuses on top so a clean structural breakout is not missed
    when the underlying spikes are not yet extreme.
  - Emits one ``PRE_ANOMALY_DETECTED`` and one ``ANOMALY_DETECTED``
    event per evaluation. Both event types were already declared
    in the Phase 1 :class:`EventType` vocabulary; Phase 6
    populates them.

- **`app/confirmation/` package - Real Trade Confirmation**
  (Spec §20, Issue #6).
  - `RealTradeConfirmation.evaluate(ConfirmationInput)` /
    `evaluate_snapshot(snapshot, ...)` returns a
    :class:`ConfirmationDecision` mapping fired-signal count to a
    :class:`TradeConfirmationLevel` (T0..T4):
    - 0 signals  -> T0
    - 1 signal   -> T1
    - 2 signals  -> T2
    - 3 signals  -> T3
    - 4+ signals -> T4
  - Five Spec §20.4 signals: CVD-price agreement, breakout hold
    over N bars, large-trade follow-through, trade-efficiency
    above mean, volume-up-price-move.
  - Emits one ``TRADE_CONFIRMED`` event per evaluation.

- **`app/manipulation/` package - Manipulation Detector**
  (Spec §21, Issue #6).
  - `ManipulationDetector.evaluate(ManipulationInput)` /
    `evaluate_snapshot(snapshot, ...)` returns a
    :class:`ManipulationDecision` mapping fired-signal count to a
    :class:`ManipulationLevel` (M0..M3):
    - 0 signals  -> M0
    - 1 signal   -> M1
    - 2 signals  -> M2
    - 3+ signals -> M3
  - Eight Spec §21.2 signals: CVD up + price flat (CVD-price
    divergence), volume up + price no move, OI up + price flat,
    funding hot + price weak, upper-wick growth, buy-pressure-
    no-push, book-wall flicker (caller-supplied count), narrative-
    after-pump.
  - Emits one ``MANIPULATION_DETECTED`` event per evaluation.

- **Risk Engine Phase 6 hooks** (Issue #6 hard rules).
  - `RiskRequest` gained three optional fields:
    - `manipulation_level: ManipulationLevel | None`
    - `trade_confirmation_level: TradeConfirmationLevel | None`
    - `attack_intent: bool` (default `False`)
  - New `RiskRequest.effective_attack_intent` property:
    `right_tail_amplify=True` always implies attack intent.
  - Three new Phase 6 rejection rules in `RiskEngine.evaluate`:
    - `manipulation_m3` -> reject every new opening
      (Spec §21.3 "M3 禁止交易").
    - `manipulation_m2_attack` -> reject ATTACK /
      RIGHT_TAIL_AMPLIFY only (Spec §21.3 "M2 禁止进攻").
    - `trade_confirmation_too_low_for_attack` -> reject ATTACK
      candidates when the level is T0 / T1 (Issue #6 "T0/T1 不
      允许进攻"). Smaller scout / observe actions remain
      allowed; the gate is size-class, not blanket.
  - The ``RISK_REJECTED`` / ``RISK_APPROVED`` audit payload now
    carries `attack_intent`, `manipulation_level`,
    `trade_confirmation_level` so Replay (Issue #10) can
    reconstruct every Phase 6 decision from `events.db` alone.
  - Phase 1 hard rejections (`live_trading_disabled`,
    `right_tail_disabled`, `stop_unconfirmed`, `unknown_position`,
    `trading_mode_inconsistent`) are unchanged. The Phase 6 rules
    are additive.

- **Reason-tag enums in `app/core/enums.py`:**
  - `PreAnomalyReasonTag` (9 values: 6 Spec §17.2 signals +
    `DATA_DEGRADED` / `REGIME_BLOCKED` / `INSUFFICIENT_HISTORY`).
  - `AnomalyReasonTag` (11 values: 8 Spec §18.1 signals +
    `DATA_DEGRADED` / `REGIME_BLOCKED` / `INSUFFICIENT_HISTORY`).
  - `ConfirmationReasonTag` (8 values: 5 Spec §20.4 signals +
    `DATA_DEGRADED` / `REGIME_BLOCKED` / `INSUFFICIENT_HISTORY`).
  - `ManipulationReasonTag` (11 values: 8 Spec §21.2 signals +
    `DATA_DEGRADED` / `REGIME_BLOCKED` / `INSUFFICIENT_HISTORY`).

- **Event-emission throttle**, mirroring the Phase 5 PR #16
  review-fix shape:
  - Each of `PreAnomalyConfig`, `AnomalyConfig`,
    `ConfirmationConfig`, `ManipulationConfig` exposes
    `event_emit_enabled: bool` (default `True`).
  - Every classifier accepts a per-call `emit_event: bool | None`
    on its `evaluate` and `evaluate_snapshot` entry points.
  - Resolution rule: `True` -> always emit, `False` -> always
    skip, `None` -> follow the config flag.
  - Each classifier exposes two counters:
    `<event>_events_emitted` and `<event>_events_skipped`. Issue
    #7's full Top-200 scanner can flip the config flag off and
    confirm via the counter that the event is being skipped.

- **Boot drill in `python -m app.main`:**
  - After the Phase 5 Liquidity loop, runs all four classifiers
    once per mock symbol (3 symbols -> 12 new events: 3
    ``PRE_ANOMALY_DETECTED``, 3 ``ANOMALY_DETECTED``, 3
    ``TRADE_CONFIRMED``, 3 ``MANIPULATION_DETECTED``).
  - Tracks the worst-observed manipulation + confirmation level
    and feeds them into the bootstrap Risk Engine self-check
    with `attack_intent=False` so the bootstrap stays approved.
    The resulting ``RISK_APPROVED`` audit row exercises the new
    payload fields end-to-end.
  - Banner extended with four new fields:
    `pre_anomaly_events`, `anomaly_events`,
    `trade_confirmed_events`, `manipulation_events`.

#### Phase 6 hard rules (per Issue #6)

1. **M2 forbids ATTACK / RIGHT_TAIL_AMPLIFY.** Risk Engine emits
   `manipulation_m2_attack` when `attack_intent=True`.
2. **M3 forbids any new opening.** Risk Engine emits
   `manipulation_m3` regardless of `attack_intent`.
3. **T0 / T1 forbid ATTACK candidates.** Risk Engine emits
   `trade_confirmation_too_low_for_attack` when
   `attack_intent=True`.
4. **All four classifier outputs are persisted as events.** One
   event per evaluation, full payload + reason-tag list, so
   Reflection (Issue #10) and Replay can reconstruct the
   decision from `events.db` alone.
5. **Every reject path carries `reason_tags`.** Tuples of typed
   enum values, never free-form strings.

#### Phase 6 boundary (declared explicitly so the next PR cannot drift)

1. Pre-Anomaly / Anomaly / Real-Trade Confirmation / Manipulation
   ONLY. **No Strategy Engine, no State Machine, no LLM, no
   Capital Flow, no Execution FSM, no Reconciliation.** Those
   land with Issue #7 / #8 / #9 / #10.
2. **No write surface added.** The four `SafeModeViolation`
   refusals on `ExchangeClientBase` are unchanged.
3. **No LLM.** No `app/scanner/`, `app/confirmation/`,
   `app/manipulation/` source file imports `openai`, `anthropic`,
   `deepseek`, or any other LLM client. Issue #6 forbids using an
   LLM to decide direction or to bypass the Risk Engine.
4. **No real Binance WebSocket and no real REST.** The boot path
   continues to drive the deterministic `MockExchangeClient`.
   `BinanceClient.get_*` continues to raise `NotImplementedError`.
5. **No API key.** No source file under the three new packages
   reads `os.environ` for a credential, accepts an `api_key`
   keyword argument, or persists a key.
6. **No auto-connect.** The classifiers do not own a
   `MarketDataBuffer`, do not own an `ExchangeClientBase`, and
   never instantiate one for themselves.
7. **Phase 1 / 3 / 4 / 5 invariants intact.** The Phase 1 safety
   lock, the Phase 3 read-only invariant, the Phase 4 Market Data
   Buffer boundary, and the Phase 5 Regime / Universe / Liquidity
   contract are unchanged.

#### Tests

`tests/unit/test_pre_anomaly_scanner.py`,
`tests/unit/test_anomaly_scanner.py`,
`tests/unit/test_real_trade_confirmation.py`,
`tests/unit/test_manipulation_detector.py`,
`tests/unit/test_risk_engine_phase6.py`,
`tests/unit/test_phase6_no_network.py`,
`tests/unit/test_phase6_boundary.py`, plus the existing
`tests/unit/test_main_entrypoint.py` extended with the Phase 6
banner + 4 new event-type assertions.

**+117 new Phase 6 tests on top of the 457 retained from Phase
1-5 = 574 total, all passing.**

Issue #6 acceptance criteria covered:

1. **mock 数据能触发 T3** -
   `test_mock_input_triggers_t3` (3 fired signals).
2. **mock 派发数据能触发 M2/M3** -
   `test_distribution_mock_data_triggers_m2`,
   `test_distribution_mock_data_triggers_m3`,
   `test_full_distribution_with_wick_and_flicker_triggers_m3`.
3. **M3 时 Risk Engine 必须拒绝** -
   `test_m3_rejects_observation_request`,
   `test_m3_rejects_attack_request`,
   `test_m3_rejection_writes_audit_event`.
4. **Volume Up + Price No Move 有测试** -
   `test_volume_up_price_no_move_signal_fires`,
   `test_volume_up_price_no_move_does_not_fire_when_price_actually_moves`.
5. **OI Up + Price Flat 有测试** -
   `test_oi_up_price_flat_signal_fires`,
   `test_oi_up_price_flat_does_not_fire_when_price_moves`.
6. **pytest 通过** - 574 passed.

#### Live trading risk

**None.** Phase 6 adds:

- Four pure stateless classifiers (`PreAnomalyScanner`,
  `AnomalyScanner`, `RealTradeConfirmation`,
  `ManipulationDetector`).
- Four reason-tag enums + four event-payload shapes.
- Three new optional fields on `RiskRequest` and three additive
  rejection rules in `RiskEngine.evaluate` that follow the same
  pattern Phase 1 introduced.
- One boot-drill loop that exercises every classifier against
  the deterministic `MockExchangeClient`.
- 117 new unit tests.

What Phase 6 does NOT add:

- No exchange SDK in `requirements.txt` / `pyproject.toml`.
- No outbound HTTP / WebSocket client of any kind in `app/`.
- No LLM client of any kind.
- No `create_order` / `cancel_order` / `set_leverage` /
  `set_margin_mode` call site.
- No new mode flags, no loosened safety lock, no relaxed
  read-only invariant.

The `python -m app.main` boot banner continues to log all five
safety flags every run:

```
mode=paper live_trading=False right_tail=False
llm=False exchange_live_orders=False
```

Sample Phase 6 boot output:

```
[AMA-RT] Phase 6 - Scanner Confirmation Manipulation v1.4.0a6 \
  mode=paper live_trading=False right_tail=False \
  llm=False exchange_live_orders=False \
  databases=5 events_count=31 capital_events=1 \
  exchange=mock/connected exchange_symbols=3 exchange_connected_events=1 \
  market_data=3/0 market_snapshots=3 data_unreliable=1 \
  regime=ALT_RISK_OFF/ALLOW_SCOUT regime_events=1 \
  universe=0/3 universe_events=3 liquidity_events=6 \
  pre_anomaly_events=3 anomaly_events=3 trade_confirmed_events=3 \
  manipulation_events=3 \
  risk_decision=True/paper_only_skeleton_approval health=ok
```

### Phase 5 - Review fixes (PR #16 review feedback)

The four follow-up clarifications requested on PR #16 are documentation
+ observability only. No mode flag is loosened, no safety lock is
relaxed, no new dependency, no new write surface, no new network
surface. The Phase 1 safety lock and the Phase 3 read-only invariant
are unchanged.

#### Added

- **`UniverseConfig.event_emit_enabled`** (default `True`) -
  construct-time throttle for `UNIVERSE_FILTERED` events. Phase 5's
  boot drill, replay, and reflection paths still observe every
  decision; Issue #6's full Top-200 scanner can flip this to `False`
  to avoid bloating events.db at scan rate. The per-call
  `emit_event=True` override on
  `UniverseFilter.evaluate` / `evaluate_snapshot` / `evaluate_many`
  still lets monitoring write an on-demand audit-trail entry.
  Mirrors Phase 4's
  `MarketDataBufferConfig.market_snapshot_event_emit_enabled`.
- **`LiquidityConfig.event_emit_enabled`** (default `True`) - the
  same construct-time throttle for `LIQUIDITY_CHECKED` events. Two
  events per symbol per tick (one `check="evaluate"` + one
  `check="can_exit_position"`) at Top-200 scan rate would mean
  ~400 events/tick; Issue #6 / #7 high-frequency consumers will flip
  this to `False`.
- **`UniverseFilter.universe_filtered_events_skipped`** property -
  counts decisions that were NOT persisted because either the
  per-call override or the config flag suppressed them. Confirms
  the throttle is doing what it claims.
- **`LiquidityFilter.liquidity_checked_events_skipped`** property -
  the same counter for the Liquidity Filter. Both `evaluate` and
  `can_exit_position` increment it.
- **`emit_event` resolution policy** (mirrors the Phase 4 review
  fix on `MarketDataBuffer.snapshot()`):

  ```text
  emit_event=True   -> always emit (per-call override)
  emit_event=False  -> always skip (per-call override)
  emit_event=None   -> follow config.event_emit_enabled (default)
  ```

  applied on `UniverseFilter.evaluate`,
  `UniverseFilter.evaluate_snapshot`,
  `UniverseFilter.evaluate_many`,
  `LiquidityFilter.evaluate`,
  `LiquidityFilter.evaluate_with_buffer`,
  `LiquidityFilter.can_exit_position`, and the module-level
  `app.liquidity.filter.can_exit_position` free function.

- **`RiskPermission` docstring rewritten** to make the
  regime-cycle-gate vs. trade-approval distinction explicit
  (review items 1 + 2). Key clarifications now part of the
  source:
  1. `ALLOW_ATTACK` is a market-cycle permission, NOT a trade
     approval. A real opening still requires Universe.eligible,
     Liquidity.passed, can_exit_position.feasible, Issue #6 scanners
     (Pre-Anomaly / Anomaly / Real-Trade Confirmation /
     Manipulation), and the Issue #7 Risk Engine's final word.
     The eight-step conjunctive ladder is enumerated in the
     docstring.
  2. `ALLOW_SCOUT` (the `ALT_RISK_OFF` fallback and the unknown-
     inputs default) permits only OBSERVE or a tiny SCOUT
     candidate. Issue #7 MUST further restrict: NO ATTACK, NO
     RIGHT_TAIL_AMPLIFY, SCOUT size capped at the per-trade scout
     budget. The `right_tail_enabled` flag is locked False through
     the limited-live phase regardless.
  3. `OBSERVE_ONLY` blocks new openings; existing positions
     remain managed.
  4. `BLOCK_ALL` is SYSTEMIC_RISK; no new opening of any kind.

- **`REGIME_TO_RISK_PERMISSION` map docstring** in
  `app/regime/models.py` echoes the same warning so anyone reading
  the source-of-truth dict sees the regime-gate vs.
  trade-approval distinction without having to chase the enum.

- **`RegimeSnapshot.risk_permission` docstring warning** -
  pointed at `RiskPermission` for the full ladder. The first
  reader of a `RegimeSnapshot` value will not silently treat
  `ALLOW_ATTACK` as authorisation.

- **`LiquidityFilter.can_exit_position` docstring rewritten** to
  cover the throughput-discount contract (review item 3):
  - The `volume_5m / 300s` fallback is documented as an UPPER
    BOUND, not a conservative estimate. Three reasons are listed
    (calm-tape extrapolation, no-crowding assumption, no ATR / OI
    discount).
  - Issue #7's Risk Engine MUST apply a conservative discount on
    top. Three recommended directions are documented (ATR-scaled
    divisor, fraction-of-average cap, post-discount feasibility
    re-check). Phase 5 ships the gate; sizing decisions are
    Issue #7's job.
  - Degraded-data contract pinned: callers in Phase 7+ MUST pass
    `MarketDataBuffer.is_degraded(symbol)` through, never invert
    `feasible=False`, never feed a stale book with
    `is_data_degraded=False`. The buffer's degraded view is the
    single source of truth.
- **`_VOLUME_WINDOW_5M_SECONDS` module constant** in
  `app/liquidity/filter.py` got its own warning comment block
  describing the same upper-bound assumption set so a future
  reader of the constant does not need to chase the docstring.
- **Free-function `can_exit_position`** docstring restates the
  same throughput-and-degraded contract with a pointer back to
  the method form.

#### Tests

`tests/unit/test_phase5_review_fixes.py` (NEW) covers:
- The two new config flags exist with correct defaults.
- The `*_events_skipped` counters are exposed and start at zero.
- `event_emit_enabled=False` + `emit_event=None` -> emits 0,
  skipped += 1 (Universe and Liquidity).
- `event_emit_enabled=False` + `emit_event=True` -> still emits
  (per-call override beats config).
- `event_emit_enabled=True` + `emit_event=False` -> still skips
  (per-call override beats config).
- `can_exit_position` (both method and free function) honours
  the same `bool | None` resolution rules.
- `RiskPermission` docstring contains the
  "regime-cycle permission" + "NOT a trade approval" wording so
  the regime-gate vs. trade-approval distinction cannot drift.
- `REGIME_TO_RISK_PERMISSION` map docstring contains the same
  warning so a future map mutation cannot silently weaken the
  contract.
- `LiquidityFilter.can_exit_position` docstring contains the
  upper-bound + Issue #7-discount + degraded-data wording.

#### Live trading risk

**None.** This commit only:

- Adds two construct-time throttle flags that default to today's
  behaviour (emit every event).
- Adds two skipped-event counters for monitoring.
- Rewrites three docstrings (`RiskPermission`,
  `REGIME_TO_RISK_PERMISSION`, `RegimeSnapshot.risk_permission`,
  `LiquidityFilter.can_exit_position`) and one constant comment
  (`_VOLUME_WINDOW_5M_SECONDS`).
- Adds one test file pinning the new flags + the docstring
  boundary phrases.

The Phase 1 safety lock, the Phase 3 read-only invariant, the
Phase 4 Market Data Buffer boundary, and the original Phase 5
classifier behaviour are all unchanged.

### Phase 5 - Regime Universe Liquidity

#### Added

- **`app/regime/` package** introducing the Regime Engine (Spec §15).
  - `RegimeConfig`, `RegimeInput`, `RegimeSnapshot` (Pydantic v2 frozen
    value objects).
  - `REGIME_TO_RISK_PERMISSION` static map (Spec §15.3) wired into
    Phase 7's future Risk Engine, the Universe Filter, and the
    Liquidity Filter.
  - `RegimeEngine.evaluate(request=...)` for tests and
    `RegimeEngine.evaluate(buffer=..., btc_symbol=...)` /
    `evaluate_from_buffer()` for the boot path. The classifier walks
    in this order:

      1. **SYSTEMIC_RISK overrides** - explicit flag, BTC return <=
         configured drop threshold, BTC ATR >= configured extreme.
         All three force `MarketRegime.SYSTEMIC_RISK` /
         `RiskPermission.BLOCK_ALL`.
      2. **Data degraded fallback** - any input flagged
         `data_degraded=True` falls back to `MarketRegime.ALT_RISK_OFF`
         / `RiskPermission.ALLOW_SCOUT`.
      3. **Trend / volatility / liquidity classifier** - five regimes:
         `MEME_RISK_ON`, `SECTOR_ROTATION`, `BTC_ABSORPTION`,
         `ALT_RISK_OFF`, `SYSTEMIC_RISK`.
  - One ``REGIME_UPDATED`` event per evaluation, with the full Spec
    §15.1 payload (`market_regime`, `btc_trend`, `btc_volatility`,
    `alt_liquidity`, `risk_permission`, `reason_tags`).

- **`app/universe/` package** introducing the Universe Filter
  (Spec §16).
  - `UniverseConfig`, `UniverseInput`, `UniverseDecision` value
    objects.
  - `UniverseFilter.evaluate(...)` walks **nine** reject conditions in
    a stable order and returns the full reason list:
    `REGIME_BLOCKED`, `DATA_DEGRADED`, `ABNORMAL_DATA_FLAG`,
    `DATA_RELIABILITY_TOO_LOW`, `CONTRACT_NOT_TRADING`,
    `SPREAD_TOO_WIDE`, `DEPTH_INSUFFICIENT`, `TRADE_DISCONTINUOUS`,
    `VOLUME_BELOW_MINIMUM`.
  - `evaluate_snapshot(snapshot, symbol_meta=, regime=, ...)`
    convenience helper consumes the Phase 4 `MarketSnapshot` directly.
  - One ``UNIVERSE_FILTERED`` event per symbol with the eligibility
    decision, full reject-reason list, and the input metrics. The
    event is persisted regardless of the eligible / rejected outcome
    so Replay (Issue #10) can rebuild the decision from events.db.

- **`app/liquidity/` package** introducing the Liquidity Filter
  (Spec §19).
  - `LiquidityConfig`, `LiquidityInput`, `LiquidityDecision`,
    `ExitPlan`, `Side` value objects.
  - **`app/liquidity/slippage.py`** - pure helpers: `estimate_book_walk`,
    `estimated_slippage_pct`, `walk_book_for_quote_notional`. Each
    walks the *opposite* side of the order book against a planned qty
    or a planned quote-notional and returns a `BookWalkResult` with
    cleared qty, weighted-average fill price, worst price, slippage
    pct, and an `exhausted` flag. No state, no events, no IO.
  - `LiquidityFilter.evaluate(...)` produces a `LiquidityDecision`
    with `spread_score`, `depth_score`, `estimated_slippage_pct`,
    `estimated_exit_seconds`, `exit_plan`, and the full reject-reason
    list. Reasons: `REGIME_BLOCKED`, `DATA_DEGRADED`, `BOOK_MISSING`,
    `SPREAD_TOO_WIDE`, `DEPTH_INSUFFICIENT`, `SLIPPAGE_TOO_HIGH`,
    `NO_EXIT_CHANNEL`, `EXIT_TOO_SLOW`. Spec §19.1.
  - **`LiquidityFilter.can_exit_position(symbol, qty,
    max_slippage_pct, max_seconds, ...)`** (Spec §19.2 - mandatory
    function). Returns an `ExitPlan` describing whether the position
    can be flattened within `max_seconds` at `<= max_slippage_pct`
    given the current book and rolling 5-minute throughput.
    `feasible=False` is the binary the Risk Engine (Issue #7) will
    consult through the No-Trade Gate.
  - Module-level **`can_exit_position(...)` free function** so
    Issue #7's No-Trade Gate can call it without keeping a filter
    instance around.
  - One ``LIQUIDITY_CHECKED`` event per call, tagged
    `check="evaluate"` or `check="can_exit_position"`, with the full
    metric set on the payload.

- **Core vocabulary additions** in `app/core/enums.py`:
  - `BtcTrend` (UP / SIDEWAYS / DOWN / UNKNOWN).
  - `BtcVolatility` (LOW / NORMAL / HIGH / EXTREME / UNKNOWN).
  - `AltLiquidity` (EXPANDING / STABLE / CONTRACTING / DRY / UNKNOWN).
  - `RiskPermission` (ALLOW_ATTACK / ALLOW_SCOUT / OBSERVE_ONLY /
    BLOCK_ALL). Spec §15.3 maps every regime to one of these values.
  - `UniverseRejectReason` - 9 hardcoded reasons.
  - `LiquidityRejectReason` - 8 hardcoded reasons.
  - `MarketRegime` was already declared in Phase 1; the
    `REGIME_UPDATED` / `UNIVERSE_FILTERED` / `LIQUIDITY_CHECKED`
    event types were already declared in Phase 1 too. Phase 5
    populates them.

#### Phase 5 boot self-check in `python -m app.main`

Phase 5 extends the boot drill to drive every new module against the
same deterministic in-process mock + buffer:

  - One ``REGIME_UPDATED`` event written. The default mock seed
    classifies as `ALT_RISK_OFF / ALLOW_SCOUT` (BTC trend cannot be
    derived from the seed - we have no historical bars - so the
    engine falls back to the conservative risk-off label, exactly as
    Issue #5 mandates).
  - One ``UNIVERSE_FILTERED`` event per symbol. The deterministic
    mock book is intentionally shallow, so the boot drill exercises
    the rejection path end-to-end (depth_insufficient,
    trade_discontinuous, regime_blocked when applicable).
  - Two ``LIQUIDITY_CHECKED`` events per symbol: one from
    `LiquidityFilter.evaluate` (`check="evaluate"`) and one from
    `LiquidityFilter.can_exit_position` (`check="can_exit_position"`).
  - A `regime_gate` health probe is registered. It reports
    `DEGRADED` only when `risk_permission` is `BLOCK_ALL`.
  - Banner extended with seven Phase 5 fields:
    `regime=<market_regime>/<risk_permission>`, `regime_events`,
    `universe=<eligible>/<total>`, `universe_events`,
    `liquidity_events`.

  Sample boot output (default mock seed; same shape every run):

  ```
  [AMA-RT] Phase 5 - Regime Universe Liquidity v1.4.0a5 mode=paper \
    live_trading=False right_tail=False llm=False exchange_live_orders=False \
    databases=5 events_count=19 capital_events=1 \
    exchange=mock/connected exchange_symbols=3 exchange_connected_events=1 \
    market_data=3/0 market_snapshots=3 data_unreliable=1 \
    regime=ALT_RISK_OFF/ALLOW_SCOUT regime_events=1 \
    universe=0/3 universe_events=3 liquidity_events=6 \
    risk_decision=True/paper_only_skeleton_approval health=ok
  ```

#### Phase 5 hard rules enforced

1. **SYSTEMIC_RISK -> BLOCK_ALL** is the only action attached to
   `RiskPermission.BLOCK_ALL`, which sits in
   `UniverseConfig.blocking_risk_permissions` and
   `LiquidityConfig.blocking_risk_permissions` by default. Any new
   opening through either filter is hard-rejected with
   `REGIME_BLOCKED`.
2. **Insufficient liquidity -> reject** with reasons. The Liquidity
   Filter inspects spread, depth, slippage, and exit time;
   any single threshold violation produces a typed reject reason.
3. **No exit channel -> reject the attack candidate.** The
   `can_exit_position` book walk returns `exhausted=True` when the
   book runs out before `qty` is filled; that maps to
   `NO_EXIT_CHANNEL` and `feasible=False` on the `ExitPlan`.
4. **Data degraded -> reject (or downgrade for the regime).** The
   buffer's `is_degraded(symbol)` flows into both filters as
   `is_data_degraded=True`, producing `DATA_DEGRADED` reject reasons.
   The Regime Engine treats the same flag as a fall-back to
   `ALT_RISK_OFF / ALLOW_SCOUT`.
5. **Every reject carries `reject_reasons`.** Both filters return
   `tuple[RejectReason, ...]` plus a free-form `notes` tuple.
6. **Every reject is persisted as one event.** The
   ``UNIVERSE_FILTERED`` and ``LIQUIDITY_CHECKED`` events carry the
   full metric snapshot AND the reason list, so Replay (Issue #10)
   can rebuild the decision from events.db alone.

#### Phase 5 boundary (declared explicitly to avoid drift)

This PR observes the boundary set by Issue #5:

1. **Regime / Universe / Liquidity ONLY.** No anomaly scanner, no
   real-trade confirmation, no manipulation detector, no strategy,
   no state machine. Those land in Issue #6 / #7.
2. The three engines read from the Phase 4 `MarketDataBuffer` and
   the Phase 3 `ExchangeClientBase` only. **They do NOT call any
   write surface; they do NOT add any write surface.** The four
   `SafeModeViolation` refusals on `ExchangeClientBase` are
   unchanged.
3. **No real Binance WebSocket and no real REST.** The boot path
   continues to drive the deterministic `MockExchangeClient`.
   `BinanceClient.get_*` continues to raise `NotImplementedError`
   for every read method.
4. **No API key.** None of `app/regime/`, `app/universe/`,
   `app/liquidity/` parameterises a credential, reads `os.environ`
   for one, or has an `api_key` keyword argument anywhere.
5. **No write surface.** Same refusal as Phase 3 / Phase 4.
6. **No auto-connect.** The three engines do not own a
   :class:`MarketDataBuffer`, do not own an
   :class:`ExchangeClientBase`, and never instantiate one for
   themselves. Tests pass stub buffers / explicit inputs.
7. **Tests do not depend on real network**
   (`test_phase3_no_network.py`, `test_phase4_no_network.py`, and
   the new `test_phase5_no_network.py`).
8. `BinanceClient.get_account_snapshot` continues to refuse outright
   in Phase 3, Phase 4, **and** Phase 5. No change.

#### Not in Phase 5 (deferred)

- Issue #6 - Pre-anomaly / Anomaly / Real-Trade Confirmation /
  Manipulation Detector.
- Issue #7 - Full Risk Engine + State Machine (will read
  `RegimeSnapshot.risk_permission`, `UniverseDecision.eligible`, and
  `LiquidityFilter.can_exit_position` at the No-Trade Gate).
- Issue #8 - Capital Flow Engine.
- Issue #9 - Real Execution FSM + Reconciliation.
- Issue #10 - LLM, Telegram outbound, Replay diff reports,
  Reflection.

#### Live trading risk

**None.** Phase 5 ships only three pure classifiers (`RegimeEngine`,
`UniverseFilter`, `LiquidityFilter`), pure helpers
(`estimate_book_walk`, `walk_book_for_quote_notional`), three new
event-emission paths through the existing `EventRepository`, and a
boot-time self-check that drives them through one decision per
symbol against the deterministic `MockExchangeClient`. No exchange
SDK is added. No outbound HTTP / WebSocket library is imported. No
API key is read. No write surface is added. The Phase 1 safety
lock, the Phase 3 read-only invariant, and the Phase 4 Market Data
Buffer boundary are unchanged. Seven layers of defence (config
lock, Phase 1 boot assertion, Phase 3 read-only assertion, Risk
Engine refusal, base-class write-surface refusal, Phase 4 no-network
/ no-API-key tests, Phase 5 no-network / no-write-surface / no-API-key
tests) are all unit-tested.

### Phase 4 - Review fixes (PR #15 review feedback)

#### Added

- **`MarketDataBufferConfig.market_snapshot_event_emit_enabled`**
  (default `True`) - construct-time throttle for `MARKET_SNAPSHOT`
  events. Phase 4 keeps the existing per-call
  ``snapshot(symbol, emit_event=...)`` override; this config flag
  lets a Phase 5+ high-frequency consumer (anomaly scanner, regime
  engine) flip the default once instead of having to remember
  ``emit_event=False`` at every call site. The MarketSnapshot return
  value is unchanged - only the events.db append is suppressed -
  so downstream code stays event-shape-stable.
- **`MarketDataBuffer.market_snapshot_events_skipped`** property +
  **`BufferStats.market_snapshot_events_skipped`** field. Confirms
  that the throttle is actually doing what it claims to do.
- **`MarketDataBuffer.late_trades_dropped_total`** property +
  **`BufferStats.late_trades_dropped_total`** field. Aggregates
  `CandleBuilder.dropped_late_trades` across every tracked symbol
  so an out-of-order tape (mis-ordered REST replay, inverted aggTrade
  delivery, producer clock skew) is observable from a single counter.
  Issue #5 / #6 monitoring will alert on this.
- **`refresh_from_exchange` docstring rewritten** to declare the
  Phase 4 boundary verbatim: mock-only / fixture-driven by default,
  no auto-connect to a real public adapter, opt-in only with no API
  key and no write surface, tests must not depend on real network.
  The contract is pinned by
  `tests/unit/test_market_data_buffer_review_fixes.py
  ::test_refresh_from_exchange_docstring_declares_phase4_boundary`.
- **8 new unit tests**
  (`tests/unit/test_market_data_buffer_review_fixes.py`):
  - `test_default_emits_market_snapshot_event`
  - `test_explicit_emit_false_skips_event`
  - `test_config_flag_disables_emit_by_default`
  - `test_config_flag_off_but_explicit_true_still_emits`
  - `test_late_trades_dropped_counter_starts_at_zero`
  - `test_late_trades_dropped_counter_increments_on_out_of_order_tape`
  - `test_late_trades_dropped_counter_isolates_per_symbol_aggregate`
  - `test_refresh_from_exchange_docstring_declares_phase4_boundary`

#### Changed

- `MarketDataBuffer.snapshot()` parameter `emit_event` is now
  `bool | None` (default `None`); `None` resolves to the new config
  flag. `True` / `False` overrides remain available per call. This is
  source-compatible: every existing call site that passed
  `emit_event=True` / `emit_event=False` keeps its old behaviour
  exactly.

#### Tests

**+8 review-fix tests on top of 311 = 319 total. Full suite: 319
passed in 2.21s.**

#### Live trading risk

None. The review fixes only add observability counters, a
construct-time throttle for an existing event emission, and tighten
the docstring of an existing helper. No new mode flag, no loosened
safety lock, no new dependency, no new write surface, no new
network surface.

### Phase 4 - Market Data Buffer

#### Added
- **`app/market_data/` package** introducing the in-process Market
  Data Buffer that every later phase will read from. The package
  never imports an exchange SDK, never opens an outbound socket,
  never reads a credential, never adds a write surface. This is
  asserted by `tests/unit/test_phase4_no_network.py` (and by the
  pre-existing repo-wide `test_phase3_no_network.py`).

- **`app/market_data/models.py`** - frozen Pydantic v2 value objects:
  - `Bar`, `BarInterval` (`M1` / `M5`).
  - `LiquidationEvent`, `LiquidationSide` (data shape only - Phase 4
    does NOT subscribe to a real liquidation feed).
  - `MarketDataBufferConfig`, `MarketDataStalenessConfig` -
    rolling-window widths (1m / 5m / 15m), bar-history sizes, ATR
    windows, per-surface staleness thresholds.
  - `MarketDataDegradedReason` enum: `never_initialised`,
    `exchange_disconnected`, `exchange_degraded`, `trades_stale`,
    `orderbook_stale`, `oi_stale`, `funding_stale`,
    `rest_ws_conflict`, `explicit_mark`. Vocabulary locked by
    `tests/unit/test_market_data_models.py::test_degraded_reason_vocabulary`.
  - `BufferStats` - per-tick observability shape exposed by
    `MarketDataBuffer.stats()`.
  - The Spec §11.1 `MarketSnapshot` model lives in
    `app/core/models.py` (Phase 1) - this PR populates it, it does
    NOT redefine it.

- **`app/market_data/candles.py`** - streaming OHLCV builder with
  buy / sell taker volume split. Late trades (arrived after their
  bucket has already closed) are *dropped*, not back-filled (Spec
  §14.2: silent rewrites are forbidden); the
  `dropped_late_trades` counter exposes the count for monitoring.
  Multi-minute gaps between trades are filled with **flat synthetic
  bars** so ATR sees no missing slots.

- **`app/market_data/cvd.py`** - pure CVD calculator
  (`signed_volume`, `compute_cvd`). Honours Binance's
  `is_buyer_maker=True` convention as "the aggressor was a seller";
  falls back to `RecentTrade.side` when the flag is unset (mock
  fixtures).

- **`app/market_data/atr.py`** - SMA-of-True-Range over closed
  bars. Returns `None` for fewer than two closed bars. Wilder-style
  EMA smoothing is deliberately deferred to Issue #6 / #7 - SMA is
  enough for Phase 4's data-quality role and trivially deterministic
  under replay.

- **`app/market_data/oi.py`** + **`app/market_data/funding.py`** -
  `OpenInterestSnapshotState` and `FundingSnapshotState` keep the
  latest plus previous snapshot per symbol. Out-of-order updates are
  rejected. Cross-symbol updates raise `ValueError`. `delta()` and
  `percent_change()` handle the zero-baseline case explicitly.

- **`app/market_data/liquidation.py`** - bounded
  `LiquidationFeedState` deque per symbol; FIFO eviction with a
  configurable capacity. Phase 4 ships only the data structure and a
  `LiquidationEvent` shape - there is no `get_liquidations` method
  on the gateway, no real-time feed, no auto-subscribe.

- **`app/market_data/buffer.py` - `MarketDataBuffer`**:
  - Lazy per-symbol state via `track(symbol)` or auto-creation on
    first ingest.
  - Rolling trade windows for **1m / 5m / 15m**, anchored to the
    *latest observed timestamp across all surfaces* so the buffer
    is fully deterministic under replay (Spec §14, Issue #4
    "necessary support" list).
  - 1m and 5m candle builders fed by every ingested trade.
  - Latest order book per symbol with reliability tier carried.
  - Latest / previous funding rate and open interest.
  - Bounded liquidation history.
  - **`is_degraded(symbol)` and `degraded_reasons(symbol)`** for the
    future No-Trade Gate (Issue #7) and Reconciliation loop
    (Issue #9). Spec §14.2 + §31: untrustworthy data must NOT feed
    new openings.
  - **`snapshot(symbol)`** returns a Spec §11.1 `MarketSnapshot`
    populated with `last_price`, `bid`, `ask`, `spread_pct`,
    `volume_1m`, `volume_5m`, `cvd_1m`, `cvd_5m`, `atr_1m`,
    `atr_5m`, `oi`, `funding_rate`, `orderbook_depth_usdt`. Emits a
    `MARKET_SNAPSHOT` event when an `EventRepository` is wired in.
  - **`cvd_15m(symbol)`** for the 15-minute window required by
    Issue #4.
  - **REST vs WS conflict detection** (Spec §14.2): when an
    incoming order book has a different `DataReliability` tier than
    the existing one, the buffer emits a single
    `DATA_UNRELIABLE` event tagged
    `MarketDataDegradedReason.REST_WS_CONFLICT` with the previous
    and incoming tiers in the payload, AND keeps the strong-tier
    book on a tier downgrade. A tier upgrade (e.g. REST -> WS) is
    accepted but still counted; the audit trail captures both.
  - **`on_websocket_disconnect(reason=...)`** - marks every tracked
    symbol as `EXCHANGE_DISCONNECTED` and writes one batched
    `DATA_UNRELIABLE` event with `scope=all_symbols`,
    `trigger=websocket_disconnect`, and the full symbol list.
    Issue #4 acceptance criterion 4.
  - **`on_websocket_reconnect(reason=...)`** - clears the explicit
    disconnect / degraded reasons (stale-window reasons are
    recomputed and may legitimately stay set until fresh data
    arrives).
  - **Exchange-link health propagation**: when wired to an
    `ExchangeClientBase`, the gateway's
    `ExchangeConnectionState.{DISCONNECTED, DEGRADED, UNINITIALISED}`
    automatically maps to the corresponding degraded reason on every
    symbol view.
  - **`mark_degraded` / `clear_explicit_degraded`** for manual
    test-driven and Reconciliation-driven transitions.
  - **`refresh_from_exchange(symbol)`** - convenience helper that
    pulls trades, book, funding and OI from the attached client and
    feeds them through the ingest path. **Phase 4 only ever wires a
    `MockExchangeClient`** here; if a `BinanceClient` skeleton ever
    gets wired in, the call surfaces the underlying
    `NotImplementedError` instead of pretending it has data
    (asserted by
    `test_refresh_from_exchange_propagates_notimplementederror_from_binance`).
    The helper batches its emits so a fresh refresh produces at most
    one `DATA_UNRELIABLE` event per symbol regardless of how many
    surfaces it touched.

- **Boot path additions** in `python -m app.main`:
  - `_build_phase4_boot_seed()` constructs a deterministic
    in-process tape anchored at `now_ms()` so the buffer's
    staleness gate sees a fresh window. **No fixture file is read,
    no network call is made, no credential is consumed.**
  - `MarketDataBuffer` is instantiated, every symbol the mock
    exposes is `track`-ed, `refresh_from_exchange`-ed, and
    `snapshot`-ed.
  - One WS disconnect + reconnect probe is driven through the
    buffer so the audit trail at boot includes one batched
    `DATA_UNRELIABLE` event with `trigger=websocket_disconnect`
    and one recovery.
  - A `market_data_buffer` health probe is registered that goes
    `DEGRADED` if any symbol is degraded.
  - Banner extended with three Phase 4 fields:
    - `market_data=<tracked>/<degraded>`
    - `market_snapshots=<count>`
    - `data_unreliable=<count>`

  Sample boot output:

  ```
  [AMA-RT] Phase 4 - Market Data Buffer v1.4.0a4 mode=paper \
    live_trading=False right_tail=False llm=False exchange_live_orders=False \
    databases=5 events_count=9 capital_events=1 \
    exchange=mock/connected exchange_symbols=3 exchange_connected_events=1 \
    market_data=3/0 market_snapshots=3 data_unreliable=1 \
    risk_decision=True/paper_only_skeleton_approval health=ok
  ```

- **76 new unit tests**:
  - `tests/unit/test_market_data_models.py` (8) - `Bar` /
    `LiquidationEvent` shape, `BarInterval` widths,
    `MarketDataBufferConfig` defaults, frozen-ness, degraded-reason
    vocabulary.
  - `tests/unit/test_market_data_candles.py` (12) - bucket
    alignment, first-trade live bar, in-place updates, bar
    closing, multi-minute gap filling with flat bars, late-trade
    drop, buy/sell volume split (both `is_buyer_maker` and `side`
    fallback), `force_close` padding, history bound, cross-symbol
    rejection.
  - `tests/unit/test_market_data_cvd.py` (7) - `signed_volume`
    sign, `compute_cvd` empty / pure-buy / pure-sell / mixed,
    Issue #4 acceptance criterion 1.
  - `tests/unit/test_market_data_atr.py` (8) - True Range with /
    without prev close, `compute_atr` `None` cases, simple-average
    correctness, prev-close from history when window is smaller
    than history, unclosed-bar exclusion, Issue #4 acceptance
    criterion 2.
  - `tests/unit/test_market_data_oi_funding_liquidation.py` (12) -
    initial state, advance-on-update, out-of-order rejection,
    cross-symbol rejection, zero-baseline percent change,
    capacity eviction, recent-since-ts filter.
  - `tests/unit/test_market_data_buffer.py` (25) - lazy track,
    never-initialised symbol, rolling-window math, MarketSnapshot
    Spec §11.1 fields, CVD helpers match `compute_cvd`,
    Issue #4 acceptance criterion 3 (no data -> degraded; partial
    data -> stale; fresh data -> clean), live recomputation of
    staleness, Issue #4 acceptance criterion 4 (WS disconnect ->
    DATA_UNRELIABLE), reconnect clears explicit reasons,
    `mark_degraded` / `clear_explicit_degraded` semantics, REST vs
    WS conflict in both directions plus same-tier-newer-wins,
    exchange health propagation (DISCONNECTED, DEGRADED), per-symbol
    liquidation deque, stats consistency, `refresh_from_exchange`
    requires a client, `BinanceClient` skeleton surfaces
    `NotImplementedError`, disconnected-client short-circuit,
    constructor refuses an `api_key` parameter, `BinanceClient`
    still refuses credentials at construction.
  - `tests/unit/test_phase4_no_network.py` (4) - `app/market_data/`
    imports no network library, mentions no `api_key` /
    `api_secret`, never creates `market.db`, and
    `BinanceClient.get_account_snapshot` continues to raise
    `NotImplementedError` with messages that mention "skeleton",
    "phase 4" and "api key".
  - `tests/unit/test_main_entrypoint.py` extended (1 test, now
    Phase 4-aware) - banner contains `Phase 4 - Market Data
    Buffer`, `market_data=...`, `market_snapshots=...`,
    `data_unreliable=...`, and the events DB contains at least one
    `MARKET_SNAPSHOT` event plus one batched
    `DATA_UNRELIABLE` event with `trigger=websocket_disconnect`.

#### Changed
- `app/__init__.py` - `__phase__` is now `Phase 4 - Market Data
  Buffer`; `__version__` is `1.4.0a4`.
- `app/main.py` - new `_build_phase4_boot_seed()` helper, boot path
  drives the buffer through one full ingest + snapshot + WS
  disconnect / reconnect cycle. The Phase 1
  `_assert_phase1_safety()` and Phase 3 `_assert_phase3_read_only()`
  guards are unchanged. `STATE_TRANSITION` reason updated to
  `phase4_boot`. Exchange shutdown reason updated to
  `phase4_shutdown`.

#### Phase 4 boundary (declared explicitly to avoid drift)

This PR observes the boundary set by Issue #4 and the user-facing
review of PR #14:

1. **Market Data Buffer ONLY.** No Regime / Universe / Liquidity
   engine, no Scanner, no Confirmation, no Manipulation Detector.
2. The buffer is fed by `MockExchangeClient` / fixture data **by
   default**. The boot path uses the deterministic mock; tests use
   deterministic fixtures.
3. **No real Binance WebSocket and no real REST.** `BinanceClient`
   continues to raise `NotImplementedError` for every read method.
4. **No API key.** `BinanceClient.__init__` still refuses any
   credential. `MarketDataBuffer.__init__` exposes no `api_key`
   parameter (asserted by a test that passes the kwarg and expects
   a `TypeError`).
5. **No write surface.** The four `SafeModeViolation` refusals on
   `ExchangeClientBase` (`create_order`, `cancel_order`,
   `set_leverage`, `set_margin_mode`) are unchanged.
6. **No auto-connect.** `MarketDataBuffer` opens no socket; it only
   receives data via `ingest_*` calls or via
   `refresh_from_exchange` against a deterministic
   `MockExchangeClient`.
7. **Tests do not depend on real network.** Both
   `test_phase3_no_network.py` and the new
   `test_phase4_no_network.py` enforce this.
8. **`BinanceClient.get_account_snapshot` remains mock-only /
   skeleton-only in both Phase 3 and Phase 4.** Real account
   snapshots require an authenticated REST call and an API key,
   forbidden until the limited-live phase. Locked by
   `test_binance_client_get_account_snapshot_remains_skeleton` in
   `test_phase4_no_network.py`.

#### Not in Phase 4 (deferred)
- Issue #5 - Regime / Universe / Liquidity engines.
- Issue #6 - Pre-anomaly / Anomaly / Confirmation / Manipulation
  scanners.
- Issue #7 - full Risk Engine (will read `is_degraded` from this
  buffer to drive the No-Trade Gate).
- Issue #8 - Capital Flow Engine.
- Issue #9 - real Execution FSM + Reconciliation; first place a
  real `create_order` is *allowed* to exist, behind the Risk
  Engine.
- Issue #10 - LLM, Telegram outbound, Replay diff reports,
  Reflection.

#### Live trading risk
**None.** Phase 4 ships only an in-process buffer and a
deterministic boot drill. No exchange SDK is added. No outbound
HTTP / WebSocket library is imported. No API key is read. No
write surface is added. The Phase 1 safety lock and Phase 3
read-only invariant are unchanged. Six layers of defence (config
lock, Phase 1 boot assertion, Phase 3 read-only assertion, Risk
Engine refusal, base-class write-surface refusal, Phase 4
no-network / no-api-key tests) are all unit-tested.

### Phase 3 - Review fixes (Issue #3 review feedback)

#### Changed

- **Reliability tier alignment** (review item 1). The default
  `OrderBook.reliability` was tier B; this was inconsistent with
  the rest of the PR description and with the actual Phase 4+ source
  (a WS-maintained depth-diff book is tier A). Updated:
  - `app/exchanges/base.ExchangeClientBase.reliability_tiers` now
    returns `get_orderbook -> A` (was B). The full table is now
    locked: `get_recent_trades=A`, `get_orderbook=A`,
    `get_funding_rate=B`, `get_open_interest=B`, `get_symbols=B`,
    `get_account_snapshot=B`.
  - `app/exchanges/models.OrderBook.reliability` default raised from
    `DataReliability.B` to `DataReliability.A`. Adapters that fall
    back to a REST snapshot when the WS link is degraded must tag
    that response tier B explicitly.
  - `MockExchangeClient.get_orderbook` now stamps its synthetic book
    as tier A (it is the in-memory analogue of a WS-maintained book).
    A tier-B `OrderBook` supplied via `MockExchangeSeed.orderbooks`
    is preserved as-is - the mock does not silently upgrade it.
  - 4 new tests pin the new contract:
    `test_reliability_tiers_contract` (full-table assertion),
    `test_reliability_tiers_lists_all_six_read_methods`,
    `test_orderbook_default_reliability_is_a_at_model_level`,
    `test_orderbook_can_be_tagged_tier_b_for_rest_fallback`,
    `test_mock_synthetic_orderbook_is_tier_a`,
    `test_mock_can_serve_a_tier_b_seed_orderbook`.
- **Phase 4 constraint hardened** (review item 2). The Phase 4
  recommendation in the PR description and the
  `BinanceClient.get_*` `NotImplementedError` messages are reworded:
  Phase 4 (Market Data Buffer) must drive the buffer from
  `MockExchangeClient` / fixture data **by default**; any real public
  read-only WS / REST adapter must be opt-in (off by default),
  require no API key, expose no write surface, and not auto-connect
  to the real exchange. `WebSocketManager`'s docstring is reworded
  for the same reason - it no longer claims Phase 4 will adopt any
  particular network library. New test
  `test_binance_real_market_data_methods_message_is_explicit_about_phase4_constraints`
  asserts every public-data `NotImplementedError` message contains
  the four constraint phrases ("opt-in", "off by default", "no API
  key", "no write surface", "auto-connect").
- **`get_account_snapshot` mock-only / skeleton-only** (review item
  3). The `BinanceClient.get_account_snapshot` `NotImplementedError`
  message is rewritten to say explicitly: real account snapshots
  require authentication and an API key, both of which are forbidden
  until the limited-live phase; the only working implementation is
  `MockExchangeClient.get_account_snapshot`. New test
  `test_binance_get_account_snapshot_message_is_explicit_about_no_api_key`
  asserts the message contains "api key", "authenticated",
  "mockexchangeclient", and "limited-live".
- **README** updated with an explicit "Reliability tier contract"
  table and a "Phase 4 constraints" section that declares the four
  Phase 4 invariants up-front so the next PR cannot drift.

#### Tests
**+7 review-fix tests on top of 97 Phase 3 tests = 104 Phase 3 tests
total. Full suite: 211 passed in 1.87s** (107 retained from
Phase 1 / 2 + 104 Phase 3).

#### Live trading risk
None. The review fixes only adjust default reliability tiers,
strengthen `NotImplementedError` messages, and tighten Phase 4
constraint documentation. No new mode flag, no loosened safety lock,
no new dependency, no new write surface.

### Phase 3 - Exchange Gateway Read-Only

#### Added
- **`app/exchanges/` package** introducing the read-only Exchange Gateway
  abstraction. The package never imports an exchange SDK and never opens
  an outbound socket; this is asserted by
  `tests/unit/test_phase3_no_network.py`.
- **`ExchangeClientBase` abstract class** (`app/exchanges/base.py`):
  - 6 abstract read-only methods: `get_symbols`, `get_orderbook`,
    `get_recent_trades`, `get_funding_rate`, `get_open_interest`,
    `get_account_snapshot`.
  - 4 **concrete** write surfaces (`create_order`, `cancel_order`,
    `set_leverage`, `set_margin_mode`) that **always** raise
    `SafeModeViolation`. Subclasses inherit the refusal.
  - `ExchangeHealth` value-object with state transitions
    (`UNINITIALISED -> CONNECTED -> DEGRADED / RECONNECTING /
    DISCONNECTED`), counters and an `is_data_trustworthy()` predicate.
  - `WebSocketManager` skeleton (`connect / disconnect / subscribe /
    unsubscribe`) that emits `DATA_UNRELIABLE` with the pending
    subscription set on every drop. **No real socket is opened in
    Phase 3.**
  - Health transitions emit `EXCHANGE_CONNECTED` /
    `EXCHANGE_DISCONNECTED` / `EXCHANGE_DEGRADED` events through
    `EventRepository`.
  - `_require_trustworthy(surface=...)` helper raises
    `ExchangeConnectionError` whenever the link is not `CONNECTED`
    (Spec §14.2 + §31).
  - `READ_ONLY_METHODS` and `WRITE_SURFACE_METHODS` module-level
    tuples used by the entrypoint and the test suite to assert the
    Phase 3 contract.
  - `assert_read_only()` boot-time guard.
  - `reliability_tiers` static map documenting the default
    `DataReliability` tier each surface returns (Spec §13.3).
- **`BinanceClient` skeleton** (`app/exchanges/binance.py`):
  - All 6 read methods raise `NotImplementedError` pointing at the
    later phase that owns the real adapter (Phase 4 / 8 / 9).
  - All 4 write methods inherit `SafeModeViolation` from the base
    class (asserted by tests; the skeleton must NOT override them).
  - Constructor refuses any `api_key` / `api_secret` (Spec §37 anti-leak).
- **`MockExchangeClient`** (`app/exchanges/mock.py`):
  - Deterministic in-memory implementation used by the entrypoint and
    the test suite. **No network**.
  - Optional `MockExchangeSeed` for fully predictable test fixtures.
  - `simulate_disconnect` / `simulate_reconnect` /
    `simulate_degraded` test hooks drive the No-Trade Gate paths.
  - Tier-A surfaces refuse when not `CONNECTED`; tier-B REST surfaces
    (`get_symbols`, `get_account_snapshot`) remain usable when
    `DEGRADED` per Spec §13.3.
- **Read-only data models** (`app/exchanges/models.py`): Pydantic v2
  frozen models `ExchangeSymbol`, `OrderBook` (+ `OrderBookLevel`,
  with bid/ask sort validation), `RecentTrade`, `FundingRate`,
  `OpenInterest`, `AccountSnapshot`. Each carries an explicit
  `reliability: DataReliability` field with the default tier per
  surface.
- **New core vocabulary**:
  - `app/core/enums.ExchangeConnectionState` enum (`UNINITIALISED /
    CONNECTED / DEGRADED / RECONNECTING / DISCONNECTED`) with an
    `is_trustworthy` property.
  - `app/core/enums.DataReliability.is_at_least()` helper for
    consistent tier comparisons (Spec §13.3).
  - `app/core/events.EventType.{EXCHANGE_CONNECTED,
    EXCHANGE_DISCONNECTED, EXCHANGE_DEGRADED}`. `DATA_UNRELIABLE` was
    already declared in Phase 1.
  - `app/core/errors.SafeModeViolation` (subclass of
    `SafetyViolation`).
  - `app/core/errors.ExchangeError` and
    `app/core/errors.ExchangeConnectionError`.
- **Phase 3 boot self-check** in `python -m app.main`:
  - Instantiates `MockExchangeClient(event_repo=repo, autostart=True)`,
    runs `assert_read_only()`, **probes every banned write surface**
    and refuses to start unless each one raises `SafeModeViolation`.
  - Calls `get_symbols()` to prove the read path works.
  - Registers an `exchange_link` health probe.
  - Emits `EXCHANGE_CONNECTED` on start and
    `EXCHANGE_DISCONNECTED` + `DATA_UNRELIABLE` on shutdown so
    replay-based tests can confirm the lifecycle closed.
  - Status banner now reports
    `exchange=<name>/<state> exchange_symbols=N exchange_connected_events=1`.
- **97 new unit tests**:
  - `tests/unit/test_exchange_models.py` (15) - `DataReliability`
    ordering (A>B>C>D), `is_at_least` helper,
    `ExchangeConnectionState.is_trustworthy`, `OrderBook` sort
    validation, frozen models, default reliability tiers per model.
  - `tests/unit/test_exchange_base.py` (20) - cannot instantiate the
    ABC directly; `READ_ONLY_METHODS == __abstractmethods__`; write
    surfaces are concrete on the base class; `SafeModeViolation`
    IS-A `SafetyViolation`; `ExchangeError` IS-A `AMARTError` and is
    NOT a `SafetyViolation`; `assert_read_only` refuses when
    `_live_orders_enabled=True`; `WebSocketManager` connect /
    disconnect lifecycle and the `DATA_UNRELIABLE` event payload;
    `ExchangeHealth` counters; `start` / `stop` / `_mark_degraded`
    emit the matching events through `EventRepository`;
    `_require_trustworthy` refuses when uninitialised / disconnected;
    `reliability_tiers` contract; no network library imports.
  - `tests/unit/test_binance_client.py` (20) - `name='binance'`;
    refuses any `api_key` / `api_secret`; every read method raises
    `NotImplementedError`; every write surface refuses with
    `SafeModeViolation`; every read method is overridden on
    `BinanceClient` itself; write surfaces NOT overridden (inherit
    base refusal); module imports no network library.
  - `tests/unit/test_mock_exchange_client.py` (28) - `autostart`
    emits `EXCHANGE_CONNECTED`; default seed has BTCUSDT, ETHUSDT,
    PEPEUSDT; orderbook / trades / funding / OI / account read
    paths; `MockExchangeSeed` determinism; `simulate_disconnect`
    emits `EXCHANGE_DISCONNECTED` + `DATA_UNRELIABLE`; tier-A
    surfaces refused when `DEGRADED`; tier-B surfaces (symbols,
    account_snapshot) ALLOWED when `DEGRADED`; both refused when
    `DISCONNECTED`; `simulate_reconnect` restores trust + new
    `EXCHANGE_CONNECTED`; write surfaces refuse; mock does NOT
    override write surfaces; lifecycle smoke; no network library
    imports.
  - `tests/unit/test_phase3_no_network.py` (3) - `requirements.txt`
    and `pyproject.toml` contain no exchange SDK / HTTP client; no
    file under `app/` issues an `import` for any forbidden token.
  - Existing `tests/unit/test_main_entrypoint.py` extended to assert
    the Phase 3 banner fields and the new `EXCHANGE_CONNECTED` /
    `EXCHANGE_DISCONNECTED` / `DATA_UNRELIABLE` events.

#### Changed
- `app/__init__.py` - `__phase__` is now `Phase 3 - Exchange Gateway
  Read-Only`; `__version__` is `1.4.0a3`.
- `app/main.py` - new `_assert_phase3_read_only(client)` guard that
  probes every entry in `WRITE_SURFACE_METHODS` and raises
  `SafeModeViolation` if any of them stops refusing. The existing
  `_assert_phase1_safety()` check is unchanged. Banner extended with
  `exchange=<name>/<state>`, `exchange_symbols=N`,
  `exchange_connected_events=1`. `STATE_TRANSITION` reason updated to
  `phase3_boot`. The exchange is stopped cleanly on shutdown
  (`reason="phase3_shutdown"`), which emits `DATA_UNRELIABLE` +
  `EXCHANGE_DISCONNECTED`.

#### Not in Phase 3 (deferred)
- Issue #4 - real Market Data Buffer; `BinanceClient` read methods
  remain `NotImplementedError` until then.
- Issue #5 - Regime / Universe / Liquidity engines.
- Issue #6 - Pre-anomaly / Anomaly / Confirmation / Manipulation
  scanners.
- Issue #7 - full Risk Engine.
- Issue #8 - Capital Flow Engine.
- Issue #9 - real Execution FSM + Reconciliation; first place a real
  `create_order` is *allowed* to exist, behind the Risk Engine.
- Issue #10 - LLM, Telegram outbound, Replay diff reports, Reflection.

#### Live trading risk
**None.** Phase 3 ships only an abstract read-only gateway plus a
deterministic in-memory mock. The four write surfaces always raise
`SafeModeViolation`; the Phase 1 safety lock is unchanged; no exchange
SDK / HTTP / WebSocket library is installed; no real API key is
accepted by `BinanceClient`. Five layers of defence (config lock, boot
assertion, Phase 3 read-only assertion, Risk Engine refusal, base-class
write-surface refusal) are all unit-tested.

### Phase 2 - Event Sourcing and Database

#### Added
- **Five SQLite databases** (Spec §33.1) opened in WAL mode and migrated
  by an idempotent runner: `events.db`, `trades.db`, `positions.db`,
  `capital.db`, `incidents.db`.
- **New schema files** under `app/database/schemas/`:
  - `trades.sql` - fills (write-once); writers land in Issue #9.
  - `positions.sql` - position lifecycle; writers land in Issues #7/#9.
  - `capital.sql` - `capital_snapshots` (Issue #8) and
    `capital_events_index` (mirror written by Phase 2 EventRepository).
  - `incidents.sql` - `incidents` + `incident_log`; writers land in
    Issues #9/#10.
- **`events.db` schema upgrade**: added the `created_at` column required
  by the Issue #2 field contract; added composite indexes
  `(event_type, timestamp)` and `(symbol, timestamp)` and an
  `order_id` index. The migration auto-upgrades a Phase 1 events.db by
  adding the column and backfilling from `timestamp`.
- **`app/database/connection.DatabaseSet`** - container that opens /
  closes a known set of databases atomically, with typed accessors
  (`.events`, `.trades`, `.positions`, `.capital`, `.incidents`),
  `__iter__`, idempotent `close()`, and an `open_database_set()` context
  manager.
- **`app/database/migrations.migrate_database` and
  `migrate_database_set`** - apply each database's schema; idempotent.
- **`EventRepository` Phase 2 API**:
  - `append_event` / `append_many` (returns events with `created_at`
    populated)
  - `list_events` / `replay_events` (lazy iterator) / `count_events`
  - filters: `event_type`, `event_types` (iterable), `symbol`,
    `source_module`, `position_id`, `order_id`, `since_ts`, `until_ts`,
    `limit`, `offset`
  - persistence failures logged via `loguru` and raised as
    `EventPersistenceError` (no silent loss). Includes a `failed_appends`
    counter for monitoring.
  - capital event helpers: `record_capital_deposit`,
    `record_capital_withdrawal`, `record_profit_harvest`,
    `record_capital_rebase`, `record_risk_budget_recalculated`.
  - **cross-database write**: when constructed with a `capital_conn`
    every `CAPITAL_*` event is mirrored into
    `capital.db.capital_events_index` so Issue #8 has a fast lookup
    table. Mirror failures are logged but do NOT roll back the events
    write (the index is rebuildable from events.db).
- **Phase 1 method aliases preserved** on `EventRepository` (`append`,
  `list`, `replay`, `count`) so the Risk Engine, Telegram bot and
  Execution FSM skeletons keep working unchanged.
- **`scripts/init_db.py`** rewritten to migrate all five databases and
  print each db's journal mode + schema file. Still idempotent.
- **`app/main.py`** opens & migrates all five databases, emits a
  CAPITAL_DEPOSIT marker (paper-mode bookkeeping, amount=0.0) so the
  capital_events_index path is exercised end-to-end. The Phase 1 safety
  lock and `_assert_phase1_safety()` remain unchanged.
- **`app/core/errors.EventPersistenceError`** - typed exception for the
  persistence failure path.
- **`app/core/events.Event.created_at`** - new field; `None` for
  in-memory events, populated by `EventRepository` from the SQLite
  default expression on insert.
- **51 new unit tests**:
  - `tests/unit/test_database_set.py` (12) - DatabaseSet, WAL pragma,
    multi-db migration, Phase-1 -> Phase-2 events.db upgrade.
  - `tests/unit/test_phase2_schemas.py` (8) - column contract for
    trades / positions / capital / incidents tables, event-type
    vocabulary, "no leak from Issue #3/#9/#10" check.
  - `tests/unit/test_event_repository.py` rewritten (31) - full Phase 2
    API surface, filter combinations, persistence failure path, capital
    helpers, capital_events_index mirror.

#### Changed
- `app/__init__.py` - `__phase__` is now `Phase 2 - Event Sourcing and
  Database`; `__version__` is `1.4.0a2`.
- `tests/conftest.py` - new `phase2_dbs` and `events_repo_with_capital`
  fixtures.

#### Not in Phase 2 (deferred)
- Issue #3 - Exchange Gateway (read-only).
- Issue #4 - Market Data Buffer.
- Issue #5 - Regime / Universe / Liquidity engines.
- Issue #6 - Pre-anomaly / Anomaly / Confirmation / Manipulation
  scanners.
- Issue #7 - full Risk Engine; uses positions.db.
- Issue #8 - Capital Flow Engine; uses capital_snapshots and the
  capital_events_index table this PR ships.
- Issue #9 - full Execution FSM + Reconciliation; uses trades.db and
  incidents.db.
- Issue #10 - LLM, Telegram outbound, Replay diff reports, Reflection;
  uses the incidents tables this PR ships.

#### Live trading risk
None. Phase 2 only adds passive SQLite schemas, a connection helper,
the EventRepository extension and tests. No exchange SDK, no outbound
network, no LLM, no Telegram client. Phase 1 safety lock unchanged.

### Phase 1 - Safety Foundation

#### Added
- Project skeleton under `app/`, `tests/`, `scripts/`, `data/`, `docs/`.
- `pyproject.toml` and `requirements.txt` with a minimal dependency set
  (Pydantic, pydantic-settings, PyYAML, loguru, pytest). No exchange SDK,
  no LLM client, no Telegram client.
- Configuration system (`app/config/`) with `defaults.yaml`, `risk.yaml`,
  `strategy.yaml`, validated by Pydantic schemas in `schema.py`. Loader in
  `settings.py` applies a Phase 1 safety lock that hard-codes:
  `trading_mode=paper`, `live_trading_enabled=false`,
  `right_tail_enabled=false`, `llm_enabled=false`,
  `exchange_live_order_enabled=false`. Even malicious env vars cannot
  flip these flags.
- Core domain types: `app/core/enums.py`, `app/core/events.py`,
  `app/core/models.py`, `app/core/clock.py`, `app/core/errors.py`,
  `app/core/constants.py`. Mirrors Spec §11 / §46 / §12.
- SQLite Event Sourcing substrate: `app/database/schema.sql`,
  `connection.py`, `migrations.py`, `repositories.EventRepository`
  (append, append_many, list, replay, count). WAL mode enforced.
- Init script `scripts/init_db.py`.
- Skeletons (no live behaviour):
  - `app/risk/engine.RiskEngine` - rejects any live or right-tail action.
  - `app/execution/fsm.ExecutionFSM` - typed transition table; refuses
    `request_send_order` without a Risk Engine approval.
  - `app/telegram/bot.TelegramCommandCenter` - in-process command bus,
    audit-logs every command, requires confirmation for `/resume`.
  - `app/monitoring/{metrics,health,alerts}.py` - in-memory only.
- Entrypoint `python -m app.main` - asserts the safety lock, initialises
  the events database, drives one Risk Engine self-check + one Telegram
  `/status` audit event, prints a one-line status banner, exits 0.
- Pytest suite covering enums, models, settings safety lock, event
  repository, Risk Engine, Execution FSM, Telegram bus, monitoring, the
  init script, and the entrypoint smoke test.
- `.env.example` (no real keys), `.gitignore` (excludes `.env`,
  `data/sqlite/*`, `*.db`), `docs/CHANGELOG.md`.
- `README.md` re-written to describe Phase 1 scope, paper-mode default,
  and explicit "no live trading" guarantee.

#### Not in Phase 1 (deferred to later issues)
- Issue #2: full Event Sourcing schema for trades / positions / capital /
  incidents databases, replay across multiple databases.
- Issue #3: any Exchange Gateway code, even read-only.
- Issue #4: Market Data Buffer.
- Issue #5: Regime / Universe / Liquidity engines.
- Issue #6: Pre-anomaly / Anomaly / Confirmation / Manipulation scanners.
- Issue #7: full Risk Engine (No-Trade Gate, Account Life Tier,
  circuit breakers).
- Issue #8: Capital Flow Engine (rebase, harvest).
- Issue #9: full Execution FSM with reconciliation against an exchange.
- Issue #10: LLM Interpreter, Telegram outbound, Replay diff reports,
  Reflection.
