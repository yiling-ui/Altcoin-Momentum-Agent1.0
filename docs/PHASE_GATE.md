# AMA-RT Phase Gate Ledger

Single canonical record of which phases have closed, which are open,
and what the gate criteria for the next phase look like. Each phase
must have an explicit acceptance record before the next phase opens.

The five Phase 1 safety flags REMAIN LOCKED across every phase below;
**no phase in this document loosens them**. Loosening any of them is a
Phase 12+ concern and requires the Spec §41 Go/No-Go checklist.

> **Readable milestone names:** this ledger keeps the original phase
> codes as the formal gate identifiers. For the human-readable milestone
> map (`M01`–`M68`, stages `S0`–`S12`) and the legacy-code → milestone
> translation, see **`docs/ROADMAP.md`**. The "Catch-up index" section
> immediately below the "Closed phases" table lists every slice shipped
> **after** the last row of that table.

## Open slice — PR117 — Full-System Single-Altcoin Live Sandbox Audit v0 (IN_REVIEW)

**PR117 — the FINAL full-system sandbox audit.** It runs the real
PR110–PR116 live chain end to end against a single fake altcoin
(`RAVEUSDT_SANDBOX`) with **fake transports only**, to surface串联 (chained)
bugs and prove the chain behaves like a real live system. It is an audit
harness: it does **NOT** loosen any Phase 1 safety flag and sends **no real
order**.

  - **No real order, fake transports only.** `no_real_order_sent=true`,
    `fake_transports_used=true`, `live_trading=false`,
    `exchange_live_orders=false`, `trade_authority=false`,
    `ai_trade_authority=false` — all by default and unconditionally for the
    audit. It is not a unit test, not a blind test, not a replay/backtest,
    and does not re-open the blind route.
  - **Whole chain exercised:** market → strategy (source=LIVE, no future
    labels) → live risk → capital profile → deterministic leverage gate →
    execution gateway (15-point) → fake Binance order (real adapter + fake
    transport) → fills/fees/funding → ledger + funding-aware PnL → Telegram
    cards → DeepSeek explain-only briefing → kill switch / rollback →
    deposit/withdrawal/mismatch/scaling.
  - **AI has no trade authority.** Forbidden trade-authority fields are
    stripped+rejected (incl. nested); AI cannot call execution, mutate live
    state, or decide leverage.
  - **Source isolation re-proven under the full chain.** Only
    `OrderSource.LIVE` reaches the live path; `MockExchange` /
    `HistoricalMarketStore` / `ReplayFeedProvider` / `SimulatedCapitalFlow`
    / blind / paper-shadow can never be a live source.
  - **Capital scales with no code change.** L1_1U … L8_10M reached by an
    operator profile switch; escalation never automatic; mismatch caps
    usable capital and demands operator action.

**Gate result:** sandbox `overall_status=PASS`,
`ready_for_real_key_validation=true`. PR117 sets the *go to real-key
validation* signal; a funded launch still requires
`scripts/live_launch_check.py --require-real-keys` with real credentials
and the full PR113 execution handshake. Tests:
`tests/unit/test_pr117_full_system_sandbox_audit.py` (50-point suite); the
existing PR110–PR116 suites continue to pass.


## Open slice — PR116 — 10U LIVE_LIMITED Launch Pack v0 (IN_REVIEW)

**PR116 — end-to-end live readiness, LIVE_SHADOW run, controlled
operator-confirmed real-order arming, kill switch, and the final operator
runbook.** PR116 is the first slice that **may** support real 10U
`LIVE_LIMITED` operation, but it does **NOT** loosen any Phase 1 safety
flag and stays safe by default:

  - **No default real trading.** A bare boot / default config stays on
    `runtime_mode=LIVE_SHADOW` with `exchange_live_orders=false`,
    `trade_authority=false`, `ai_trade_authority=false`,
    `live_trading=false`, and sends **no real order**. A real order is only
    ever attempted behind the full handshake: operator env flags + Telegram
    `/mode live_limited` + `/confirm_live CODE` + armed kill switch + an
    `L1_10U` (or approved) profile + `LiveExecutionGateway` approval +
    `LiveRiskDecision` approval.
  - **AI has no trade authority.** `ai_trade_authority=false` stays pinned;
    the AI can never trigger a launch/execute.
  - **No automatic profile escalation.** The active capital profile is read
    dynamically; equity above the active band emits
    `CAPITAL_PROFILE_MISMATCH` and caps usable capital until the operator
    explicitly switches profile. Switching profile needs no code change.
  - **Source isolation re-asserted.** Only `OrderSource.LIVE` may drive
    live operation; `MockExchange` / `HistoricalMarketStore` / sim / blind
    / replay / paper-shadow can never reach the live path.

**Gate to close PR116:** the full unit suite passes (including the PR116
readiness / shadow / arming / smoke / kill-switch / isolation /
capital-scaling / safety-default tests), and a real 10U smoke is only ever
sent when every gate above is explicitly satisfied.

## Open slice — PR115 — DeepSeek Live Intelligence v0 (IN_REVIEW)

**PR115 — live-safe operator briefing + evidence compression + risk
explanation + Telegram AI briefing.** PR115 connects DeepSeek to the live
operator workflow **only** as market intelligence and does **NOT** loosen
any Phase 1 safety flag:

  - **No trade authority.** `ai_trade_authority=false` is pinned on every
    evidence bundle, briefing, Telegram card, CLI report, and audit
    payload. The AI cannot output direction / `position_size` / `size` /
    `leverage` / `stop_price` / `take_profit` / `target_price` /
    `order_type` / `entry_price` / `exit_price` / `execute` /
    `trade_decision` / `runtime_config_patch` / `strategy_patch` /
    `risk_limit_patch`; the output guard strips any such field and marks
    the briefing `REJECTED_FOR_TRADE_AUTHORITY`
    (`AI_FORBIDDEN_FIELD_STRIPPED` +
    `DEEPSEEK_OUTPUT_REJECTED_FOR_TRADE_AUTHORITY`).
  - **LIVE-only evidence.** The `LiveAIEvidenceBundle` is
    `source_scope=LIVE_ONLY`; a `SIM`/`BLIND`/`REPLAY`/`PAPER_SHADOW`/
    `BACKTEST`/`OFFLINE_AI`/`TELEGRAM_SANDBOX` source (or an unknown
    source, fail-safe) is refused
    (`LIVE_AI_EVIDENCE_REJECTED_FOR_NONLIVE_SOURCE`). No blind / replay /
    sim / future-label evidence is ever a live AI input.
  - **No execution / no mutation.** The AI modules never import or call
    `LiveExecutionGateway` / `BinanceExecutionAdapter`. The AI cannot
    change runtime mode / capital profile / leverage / stop / take-profit
    / risk limits, cannot auto-switch `LIVE_LIMITED`, and cannot trigger a
    Telegram live order / state-changing command (those are blocked with
    `AI_TELEGRAM_BRIEFING_BLOCKED`).
  - **Informational Telegram only.** `/ai_status`, `/brief`,
    `/explain_risk`, `/explain_position <SYMBOL>`, `/summarize_pnl`,
    `/summarize_rejections` return explanation / summary cards
    (`no_order_instruction=true`, `recommends_action=false`,
    `MARKET_INTELLIGENCE_ONLY`). Funding / commission / PnL summaries are
    explanatory only; deposits / withdrawals stay separate from strategy
    PnL.
  - DeepSeek key held as a `SecretValue` (Authorization header only,
    never logged). Missing / disabled key → `MISSING_SECRET` / `DISABLED`
    (no crash); HTTP error → `ERROR` (safe text). `phase_12_forbidden`
    recorded `True`.

Gate criteria for the NEXT slice (**PR116 — 10U live launch**): the live
real-order path remains blocked unless every PR113 gate + all
confirmation flags are satisfied; the AI remains intelligence-only.
Acceptance evidence: `docs/AMA_RT_DEEPSEEK_LIVE_INTELLIGENCE.md`,
`scripts/live_ai_briefing.py --status-json`,
`tests/unit/test_pr115_deepseek_live_intelligence.py`. **PR115 is not the
final 10U launch.**

## Open slice — PR114 — Telegram Operator Console v0 + Live Funding Attribution (IN_REVIEW)

**PR114 — real Telegram operator desk + first funding/commission
attribution to the live ledger + operator workflow + blind/replay/sim
isolation hardening.** PR114 lets the operator drive the live console
from Telegram but does **NOT** loosen any Phase 1 safety flag:

  - The console holds **no** Binance execution adapter and exposes **no**
    path that flips `exchange_live_orders` / `trade_authority`. A Telegram
    command can never place a naked order, nor bypass the Risk Engine, the
    PR113 Execution Gateway, the Capital Profile, or the kill switch.
  - `runtime_mode` defaults `LIVE_SHADOW`; `LIVE_LIMITED` is never armed by
    default or on a bare restart. `/mode live_limited` only returns a
    confirmation code + risk summary; `/confirm_live CODE` arms
    `LIVE_LIMITED` only when the code matches + is unexpired + the profile
    allows real orders + `LIVE_LIMITED` is in `profile.mode_allowed` + the
    kill switch is off — and arming still does **not** enable real orders.
  - Only allow-listed chat ids may run a command (empty allow-list fails
    closed); unauthorised → `TELEGRAM_UNAUTHORIZED_COMMAND`. Outbound is
    disabled unless `AMA_TELEGRAM_OUTBOUND_ENABLED=true` and not
    `--dry-run`; otherwise `TELEGRAM_OUTBOUND_SUPPRESSED`. No secret ever
    reaches a message body (redactor + `assert_no_forbidden_substrings`).
  - `ai_trade_authority` stays `False`; an AI / `OFFLINE_AI` source can
    never run a state-changing command. A non-`LIVE` source
    (`SIM`/`BLIND`/`REPLAY`/`PAPER_SHADOW`/`BACKTEST`/`OFFLINE_AI`/
    `TELEGRAM_SANDBOX`) attempting any live mutation → `LIVE_SOURCE_REJECTED`;
    order-path attempts remain `LIVE_PATH_BLOCKED` (PR110 guard).
  - Funding attribution: `net_pnl = gross − commission + funding`; funding
    inside a holding interval is attributed to the trade/position; outside
    stays account-level; overlapping same-symbol positions →
    `AMBIGUOUS_MULTIPLE_POSITIONS` (deterministic notional allocation);
    unlinkable → `UNATTRIBUTED_PENDING_POSITION_LINK`. No funding dropped.
  - Persistent state under `data/live_state/` (atomic writes); corrupt /
    armed-without-confirmation both fail safe to `LIVE_SHADOW`.
    `phase_12_forbidden` recorded `True`.

Gate criteria for the NEXT slice (PR115/PR116 — pre-launch hardening +
10U launch): operator can run `scripts/live_telegram_operator.py
--status-json` and see `no_real_order_sent=true`, the current
`LIVE_SHADOW`/`LIVE_LIMITED` source, and every safety flag false; the
real-order path stays blocked unless every PR113 gate + all confirmation
flags are satisfied. Acceptance evidence:
`docs/AMA_RT_TELEGRAM_OPERATOR_CONSOLE.md`,
`docs/AMA_RT_LIVE_OPERATOR_RUNBOOK.md`,
`tests/unit/test_pr114_telegram_operator.py`. **PR114 is not the final
10U launch.**

## Open slice — PR113 — Live Execution Gateway v0 (IN_REVIEW)

**PR113 — Binance order execution adapter + order lifecycle + fill
ledger + strict LIVE_LIMITED gate.** PR113 introduces the first code path
able to compose + send a real Binance order, but it is **blocked by
default** and does **NOT** loosen any Phase 1 safety flag:

  - `exchange_live_orders` defaults `False`; `trade_authority` defaults
    `False`; `live_trading` stays `False`; default runtime mode is
    `LIVE_SHADOW`. With these defaults the gateway returns a `BLOCKED`
    result and the adapter never opens a socket.
  - A real order request leaves the system **only** when all 15 gate
    conditions are true (`LIVE_LIMITED` + `live_limited_confirmed` + an
    allowed profile + `exchange_live_orders` + `trade_authority` +
    private trade enabled + `LiveRiskDecision.approved` +
    `real_order_allowed` + kill switch off + `source=LIVE` +
    `client_order_id` + exchangeInfo precision/minNotional + notional /
    leverage within profile + stop/exit plan or documented emergency
    exception). See `evaluate_execution_permission`.
  - `ai_trade_authority` stays `False` and is a **hard refusal** at the
    gateway (`AiTradeAuthorityForbidden`); AI never places an order.
    Telegram never bypasses the Risk Engine; blind / replay / sim /
    paper-shadow sources are isolated (`LivePathIsolationViolation`).
  - No leverage / margin change (the adapter's `set_leverage` /
    `set_margin_mode` refuse). Orders are idempotent
    (`newClientOrderId`) and never blind-retried.
  - `net_pnl = realized − fee + funding_usdt_attributed`. Funding is
    carried forward (`UNATTRIBUTED_PENDING_POSITION_LINK`); position-level
    attribution is the PR114 handoff. `phase_12_forbidden` recorded
    `True`. PR112's dry `LiveRiskDecision` keeps `real_order_allowed=False`;
    only `authorize_real_order` (gated on a fully-armed context) flips it.

Gate criteria for the NEXT slice (PR114 — funding/position attribution +
real execution dry-run on testnet): operator can run
`scripts/live_execution_smoke.py --permission-check` / `--dry-run-order`
and see `no_real_order_sent=true` and the full gate decision; the
real-order path stays blocked unless every gate + all three confirmation
flags are satisfied. Acceptance evidence:
`docs/AMA_RT_LIVE_EXECUTION_GATEWAY.md`, `tests/unit/test_pr113_*.py`.

## Open slice — PR112 — Live Capital / Risk / Funding-Aware PnL / 10U Profile Enforcement v0 (IN_REVIEW)

**PR112 — wire PR111 real private-read into a live capital / risk
engine + enforce `L1_10U_PROBE`.** PR112 reads real account state only;
it does **NOT** loosen any safety flag:

  - `exchange_live_orders` stays `False`; every `LiveRiskDecision` has
    `real_order_allowed=False`. PR112 builds the dry risk pre-check that
    PR113's execution gateway will consume; it never submits an order.
  - `live_trading` stays `False`; default runtime mode is `LIVE_SHADOW`
    and a real-order intent is rejected in shadow. No auto-switch to
    `LIVE_LIMITED`.
  - No leverage / margin change. No auto-escalation of the capital
    profile — a profile/equity mismatch is detected and surfaced
    (`PROFILE_MISMATCH_EQUITY_ABOVE_RANGE` / `..._BELOW_RANGE`,
    `auto_escalation_allowed=False`); the operator must reselect.
  - `L1_10U_PROBE` caps usable account capital at 10U; a large real
    balance is never used blindly under the small profile.
  - `net_strategy_pnl = realized − commission + funding`. Deposits /
    withdrawals / transfers are separated from strategy PnL; unknown
    income is preserved separately. Account-level funding attribution is
    implemented; position-level attribution is the PR113/PR114 handoff.
  - `ai_trade_authority` / `trade_authority` stay `False`; DeepSeek is
    not used by PR112. Telegram operator payloads are built only (no
    outbound). `phase_12_forbidden` remains recorded `True`.

PR112 also hardens PR111 usability: placeholder-secret detection
(`PLACEHOLDER_SECRET_CONFIGURED` before any real HTTP call), typed health
messages, `.env.live` validation, and capital-profile env compatibility
(`AMA_LIVE_CAPITAL_PROFILE_ID` priority / `AMA_LIVE_CAPITAL_PROFILE`
alias; invalid → `CONFIG_INVALID_CAPITAL_PROFILE`, never silent) — fixing
the PR111 bug where `L1_10U_PROBE` showed as `L0_SHADOW`.

Gate criteria for the NEXT slice (PR113 — real order execution gateway):
operator can run `scripts/live_capital_status.py` against real keys,
confirm the live capital state + funding-aware PnL + `L1_10U_PROBE`
enforcement, and the report shows `real_order_allowed=false` /
`exchange_live_orders=false` / `ai_trade_authority=false`. Acceptance
evidence: `docs/AMA_RT_LIVE_CAPITAL_RISK_PNL.md`,
`tests/unit/test_pr112_*.py`.

## Open slice — PR111 — API Integration Pack v0 (IN_REVIEW)

**PR111 — Binance + Telegram + DeepSeek API Health & Permission Layer.**
PR111 opens the real-capital road map by adding real read-only API
connectivity under `app/live/`. It does **NOT** loosen any safety flag:

  - `exchange_live_orders` stays `False`; the Binance `PRIVATE_TRADE`
    layer is interface-only and blocked (`TRADE_API_BLOCKED_BY_PR111` /
    `LiveTradeNotEnabled`). No HTTP order request is ever built.
  - `live_trading` stays `False`; default runtime mode is `LIVE_SHADOW`
    and PR111 never auto-escalates to `LIVE_LIMITED`.
  - No leverage / margin change.
  - `ai_trade_authority` / `trade_authority` stay `False`; DeepSeek is
    MARKET_INTELLIGENCE_ONLY.
  - `telegram_outbound_enabled` defaults `False`; a test message is only
    sent on explicit `--send-telegram-test` with outbound enabled.
  - No secret is hard-coded / logged / exported / leaked; only masked
    forms surface. `phase_12_forbidden` remains recorded `True` in the
    unified health report's safety flags.

Gate criteria for the NEXT slice (live capital / risk / execution
integration): operator can run the health check against real keys,
confirm `binance_public=PASS`, optional `binance_private_read=PASS`, no
high-risk (withdraw) permission, and the health report shows
`exchange_live_orders=false` / `ai_trade_authority=false` /
`live_runtime_mode=LIVE_SHADOW`. Acceptance evidence:
`docs/AMA_RT_API_INTEGRATION_PACK.md`, `tests/unit/test_pr111_*.py`.

## Closed phases

| #     | Title                                              | Closed (UTC)    | Acceptance evidence                                            |
| ----- | -------------------------------------------------- | --------------- | -------------------------------------------------------------- |
| 1     | Safety Foundation                                  | 2025-10 (est.)  | `docs/CHANGELOG.md`                                            |
| 2     | Event Sourcing + Database Set                      | 2025-10 (est.)  | `docs/CHANGELOG.md`                                            |
| 3     | Exchange Gateway (read-only abstract)              | 2025-11 (est.)  | `docs/CHANGELOG.md`, `tests/unit/test_phase3_no_network.py`    |
| 4     | Market Data Buffer                                 | 2025-11 (est.)  | `docs/CHANGELOG.md`, `tests/unit/test_phase4_no_network.py`    |
| 5     | Regime + Universe + Liquidity                      | 2025-12 (est.)  | `docs/CHANGELOG.md`                                            |
| 6     | Pre-Anomaly + Anomaly + Confirmation + Manipulation | 2025-12 (est.) | `docs/CHANGELOG.md`                                            |
| 7     | Risk Engine + No-Trade Gate + Account Tier         | 2026-01 (est.)  | `docs/CHANGELOG.md`                                            |
| 8     | Capital Flow Engine                                | 2026-02 (est.)  | `docs/CHANGELOG.md`                                            |
| 8.5   | Learning-Ready Data Contract                       | 2026-02 (est.)  | `docs/PHASE_8_5_TELEGRAM_EXPORT_CONTRACT.md`                   |
| 9     | Execution FSM + Reconciliation                     | 2026-03 (est.)  | `docs/CHANGELOG.md`                                            |
| 10A   | Replay Engine substrate                            | 2026-03 (est.)  | `docs/CHANGELOG.md`                                            |
| 10B   | Reflection + Replay (read-only)                    | 2026-04 (est.)  | `docs/CHANGELOG.md`                                            |
| 10C   | LLM Guarded Interpreter (receive-only)             | 2026-04 (est.)  | `docs/CHANGELOG.md`                                            |
| 10D   | Telegram Outbound + Export Commands                | 2026-05 (est.)  | `docs/CHANGELOG.md`                                            |
| 11B   | Cloud Paper Acceptance                             | 2026-05-19      | `docs/PHASE_11B_PAPER_ACCEPTANCE_REPORT.md`                    |
| 11B-HF | Cloud Paper - High-Frequency observation          | 2026-05-19      | 30/30 dry-run PASS; 648/648 24h@2min observations PASS         |
| 11C.1A | Binance Public REST Rate Limit Governor & 418 Protection | 2026-05-21 | PR #31 merged; `tests/unit/test_phase11c1a_rate_limit_governor.py` |
| 11C.1B | WebSocket-First All-Market Demon Coin Radar (incl. SymbolUniverse exchangeInfo-as-truth) | 2026-05-22 | PRs #32 / #33 / #34 merged; 5min / 10min / 1h real WS smoke PASS; export zip generated; events.db readable; safety flags unchanged. See "Phase 11C.1B acceptance summary" below. |
| 11C.1C-A | Adaptive Candidate Regime & Strategy Selector Contracts (paper-only) | 2026-05-22 | PR #36 merged; PR #37 docs closeout; 244/244 phase11c tests + 2219/2219 full pytest pass; 30s dry-run + 5min real public WS smoke PASS (32842 real WS messages, 12 chains, 12 each of the six adaptive event types, 0 stales, 0 reconnects, 0 rate-limit 429/418/ban); daily report contains the Phase 11C.1C-A adaptive section; safety flags unchanged. See "Closed phase: Phase 11C.1C-A (ACCEPTED)" below. |
| 11C.1C-B | Adaptive Candidate Runtime Calibration & Early Tail Discovery v0 (paper-only) | 2026-05-22 | PR #38 merged into `main` (mergeCommit `ce4b6de`); 12/12 brief-mandated tests + 257/257 phase11c tests + 2231/2231 full pytest pass on the PR branch; 30s dry-run + 5min real public WS smoke PASS (`dry_run=false`, `ws_real_transport=true`, 30526 real WS messages, 12 chains, 72 each of the six adaptive event types, runtime calibration block on every adaptive event with all 15 fields, `top_early_tail_candidates` / `top_late_chase_risk_candidates` / `early_tail_score_top_symbols` / `opportunity_score_distribution` in the daily report, `label_queue` contract-only, 0 stales, 0 reconnects, 0 rate-limit 429/418/ban); safety flags unchanged. See "Phase 11C.1C-B acceptance evidence (closeout)" below. |
| 11C.1C-C-A | MFE / MAE Label Queue Runtime & Tail Outcome Tracking (paper-only) | 2026-05-23 | PR #40 merged into `main` (mergeCommit `75d3c7c`); 30/30 brief-mandated tests + 287/287 phase11c tests + 2261/2261 full pytest PASS on the PR branch (no regression vs. post-PR-#38 main 2231 baseline); operator-VPS 10 min real public WS smoke PASS (`duration_seconds=600.0`, `dry_run=false`, `ws_real_transport=true`, `ws_messages_received=56592`, `ws_chains_emitted=27`, `LABEL_TRACKING_STARTED=19` runner / `36` events.db, `LABEL_WINDOW_UPDATED=38` / `82`, `LABEL_WINDOW_COMPLETED=11` / `20`, `TAIL_LABEL_ASSIGNED=11` / `20`, `MISSED_TAIL_DETECTED=0`, `FAKE_BREAKOUT_DETECTED=0`, pending=8 / completed=11 / expired=0 / unresolved=0, `HTTP 429 count=0`, `HTTP 418 count=0`, `rate_limit_ban=False`, `ws_reconnect_count=0`, `ws_stale_count=0`, `ws_currently_stale=False`, `ingestion_errors=0`); safety flags unchanged. See "Closed phase: Phase 11C.1C-C-A (ACCEPTED)" and "Phase 11C.1C-C-A acceptance evidence (closeout)" below. |
| 11C.1C-C-B-A | Strategy Validation Lab v0 & Cluster Exposure Control Contracts (paper / report-only) | 2026-05-23 | PR #42 merged into `main` (mergeCommit `cc18047`); 25/25 brief-mandated tests + 312/312 phase11c tests + 2286/2286 full pytest PASS on the PR branch (no regression vs. post-PR-#41 main 2261 baseline); operator-VPS 10 min real public WS smoke PASS against PR #42 head (commit `0bedcce`): `duration_seconds=600.0`, `uptime=611s`, `dry_run=false`, `ws_real_transport=true`, `ws_messages_received=76324`, `ws_chains_emitted=27`, `learning_ready_attached=27`, `snapshots_emitted=27`, `STRATEGY_VALIDATION_SAMPLE_CREATED=24`, `STRATEGY_VALIDATION_REPORT_GENERATED=1`, `STRATEGY_MODE_VALIDATED=4`, `CANDIDATE_STAGE_VALIDATED=5`, `SCORE_BUCKET_VALIDATED=8`, `CLUSTER_EXPOSURE_ASSESSED=1`, `CLUSTER_LEADER_VALIDATED=1` (authoritative SQLite query captured after shutdown flush), non-empty daily-report cohort lines, `HTTP 429 count=0`, `HTTP 418 count=0`, `rate_limit_ban=False`, `ws_reconnect_count=0`, `ws_stale_count=0`, `ws_currently_stale=False`, `ingestion_errors=0`; safety flags unchanged. See "Closed phase: Phase 11C.1C-C-B-A (ACCEPTED)" and "Phase 11C.1C-C-B-A acceptance evidence (operator-VPS 10 min real public WS smoke PASSED)" below. |
| 11C.1C-C-B-B-A | Strategy Validation Dataset Builder & Quality Gate v0 (paper / report-only) | 2026-05-23 | PR #44 merged into `main` (mergeCommit `3ecfc3b`); 27/27 brief-mandated tests + 339/339 phase11c tests + 2313/2313 full pytest PASS on the PR branch (no regression vs. post-PR-#43 main 2286 baseline); 30 s dry-run smoke generated the dataset and quality-gate report (`STRATEGY_VALIDATION_DATASET_BUILT=1`, `STRATEGY_VALIDATION_DATASET_EXPORTED=1`, `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED=1`, `validation_dataset_records=2`, `validation_dataset_symbols=BTCUSDT,ETHUSDT`, `validation_quality_gate_status=fail` — expected for the low-sample 30 s window, exactly the brief's "empty or low-sample quality gate report" requirement, `validation_dataset_export_ready=True`, `validation_dataset_replay_ready=True`); real WS 10 min smoke NOT required for this PR (smallest Phase 11C.1C-C-A primary tracking window is 5 min and cannot complete in 30 s; reserved for Phase 11C.1C-C-B-B-B closeout); `validation_quality_gate_status` is descriptive only and **MUST NEVER trigger a real trade** (Risk Engine remains the single trade-decision gate); safety flags unchanged. See "Closed phase: Phase 11C.1C-C-B-B-A (ACCEPTED)" and "Phase 11C.1C-C-B-B-A acceptance evidence (closeout)" below. |
| 11C.1C-C-B-B-B-A | Paper Alpha Gate v0 (paper / report / evidence-only first child slice under Phase 11C.1C-C-B-B-B) | 2026-05-24 | PR #52 merged into `main` (mergeCommit `f8ba315`); this docs-only closeout PR #54 records the operator-VPS paper evidence and flips the slice to `ACCEPTED`. Operator-VPS 10 min WS paper smoke PASSED: `duration_seconds=600.0`, `uptime≈608s`, `ws_first=true`, `ws_real_transport=true`, `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`. Daily report contains `"## Phase 11C.1C-C-B-B-B-A Paper Alpha Gate v0"` with `paper_alpha_gate_status=INCONCLUSIVE`, `paper_alpha_gate_sample_count=20`, reason `completed_tail_label_count_below_min=0<10`. `PAPER_ALPHA_GATE_EVALUATED=1`, `PAPER_ALPHA_RULE_EVALUATED=9`, `PAPER_ALPHA_COHORT_EVALUATED=6`, `PAPER_ALPHA_REPORT_GENERATED=1`. Phase 8.5 export bundle: `data/reports/exports/ama_rt_test_data_1779627957433_export_1.zip`, `manifest_event_count=1572`, `redaction_applied=True`, `events.jsonl` exists, export contains `PAPER_ALPHA_*` events, `EXPORT_PAPER_ALPHA_GATE_CHECK=PASS`; export package files observed: `manifest.json`, `summary_report.md`, `events.jsonl`, `opportunities.jsonl`, `signal_snapshots.jsonl`, `risk_decisions.jsonl`, `state_transitions.jsonl`, `capital_events.jsonl`, `virtual_trade_plans.jsonl`. `paper_alpha_gate_status=INCONCLUSIVE` is the **expected and accepted** result for this smoke window because `completed_tail_label_count=0<10` — the Paper Alpha Gate correctly refused to overfit or force a `PASS` when completed tail labels were insufficient; `INCONCLUSIVE` does NOT mean runtime failure, does NOT authorise strategy changes, does NOT authorise live trading, does NOT authorise Phase 12. Paper Alpha Gate verdicts remain paper-only / report-only / evidence-only and cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes; the Risk Engine remains the single trade-decision gate. Safety flags unchanged across the operator-VPS run. See "Closed phase: Phase 11C.1C-C-B-B-B-A (ACCEPTED)" and "Phase 11C.1C-C-B-B-B-A acceptance evidence (operator-VPS 10 min WS paper smoke PASSED)" below. |
| 11C.1C-C-B-B-B-B | Regime & Cluster Cohort Evidence Pack v0 (paper / report / evidence-only second child slice under Phase 11C.1C-C-B-B-B) | 2026-05-24 | PR #56 merged into `main` (mergeCommit `1a9abe2`); this docs-only closeout PR #57 records the operator-VPS paper evidence and flips the slice to `ACCEPTED`. Operator-VPS 10 min WS paper smoke PASSED: `duration_seconds=600.0`, `uptime≈608s`, `ws_first=true`, `ws_real_transport=true`, `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`. Daily report contains `"## Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort Evidence Pack v0"` with `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`, `sample_count=14`, `completed_tail_label_count=0`, `insufficient_sample_reasons=[sample_count_below_min=14<20, completed_tail_label_count_below_min=0<10]`. `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=1`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=5`. Phase 8.5 export bundle: `data/reports/exports/ama_rt_test_data_1779635774169_export_d.zip`, `manifest_event_count=3151`, `redaction_applied=True`, `events.jsonl` exists, export contains `REGIME_CLUSTER_*` events, `EXPORT_REGIME_CLUSTER_EVIDENCE_CHECK=PASS`; export package files observed: `manifest.json`, `summary_report.md`, `events.jsonl`, `opportunities.jsonl`, `signal_snapshots.jsonl`, `risk_decisions.jsonl`, `state_transitions.jsonl`, `capital_events.jsonl`, `virtual_trade_plans.jsonl`. `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` is the **expected and accepted** result for this smoke window because `sample_count=14<20` and `completed_tail_label_count=0<10` — the Regime & Cluster Evidence Pack correctly refused to overfit or force a regime / cluster conclusion when structural samples were insufficient; `INSUFFICIENT_SAMPLE` does NOT mean runtime failure, does NOT authorise strategy changes, does NOT authorise rule relaxation, does NOT authorise live trading, does NOT authorise Phase 12. Regime & Cluster Evidence Pack outputs remain paper-only / report-only / evidence-only and cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes; the Risk Engine remains the single trade-decision gate. Safety flags unchanged across the operator-VPS run. See "Closed phase: Phase 11C.1C-C-B-B-B-B (ACCEPTED)" and "Phase 11C.1C-C-B-B-B-B acceptance evidence (operator-VPS 10 min WS paper smoke PASSED)" below. |
| 11C.1C-C-B-B-B-C | Long-Window Cohort Stability & Sample Sufficiency Protocol v0 (*长窗口 Cohort 稳定性与样本充足协议 v0*; docs / evidence-template-only third child slice under Phase 11C.1C-C-B-B-B) | 2026-05-25 | PR #58 docs-only kickoff merged into `main`; this docs-only closeout PR #59 records the operator-VPS W1 / W1+ 2 h, W2 4 h, and W3 24 h upper-bound early-stop paper WS evidence and flips the slice to `ACCEPTED`. **W1 / W1+ 2 h paper WS run PASSED**: `duration_seconds=7200.0`, `uptime≈7238s`, `ws_first=true`, `ws_real_transport=true`, `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`, `risk_approved=0`, live trading disabled; 2 h event counts `PAPER_ALPHA_COHORT_EVALUATED=18`, `PAPER_ALPHA_GATE_EVALUATED=3`, `PAPER_ALPHA_REPORT_GENERATED=3`, `PAPER_ALPHA_RULE_EVALUATED=27`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=10`, `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=2`; daily report contains both the Paper Alpha Gate section and the Regime & Cluster Cohort Evidence Pack section; `regime_cluster_sample_count=189`, `regime_cluster_completed_tail_label_count=0`, status remained `INSUFFICIENT_SAMPLE` / `INCONCLUSIVE` because `completed_tail_label_count=0<10` (accepted as valid low-completed-label evidence, not runtime failure); 2 h export `data/reports/exports/ama_rt_test_data_1779693570447_export_d.zip`, `manifest_event_count=23001`, `redaction_applied=True`, `EXPORT_LONG_WINDOW_W1_2H_CHECK=PASS`. **W2 4 h paper WS run PASSED**: configured `duration_seconds=14400.0`, actual runtime ≈ `14417s`, `iterations=237`, `chains_emitted=704`, `ws_chains_emitted=704`, `ws_real_transport=True`, `ws_reconnect_count=0`, `ws_staleness_ms_max=0`, `ws_stale_count=0`, `ingestion_errors=0`, `public_endpoint_calls=4226`, `ws_messages_received=1324423`, `radar_candidates_seen=152221`, `candidate_pool_size_max=20`, `liquidation_events_seen=4076`, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `rate_limit_ban=False`, `risk_approved=0`, `risk_rejected=704`; 4 h event counts `PAPER_ALPHA_COHORT_EVALUATED=24`, `PAPER_ALPHA_GATE_EVALUATED=4`, `PAPER_ALPHA_REPORT_GENERATED=4`, `PAPER_ALPHA_RULE_EVALUATED=36`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=15`, `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=3`; daily report `paper_alpha_gate_status=INCONCLUSIVE`, `paper_alpha_gate_sample_count=164`, reason `completed_tail_label_count_below_min=2<10`; `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`, `regime_cluster_sample_count=164`, `regime_cluster_completed_tail_label_count=2`, reason `completed_tail_label_count_below_min=2<10` — progress from 0 to 2 completed labels, still below the 10-label threshold, therefore `INCONCLUSIVE` / `INSUFFICIENT_SAMPLE` remained the correct result (does NOT indicate runtime failure; does NOT authorise rule relaxation); 4 h export `data/reports/exports/ama_rt_test_data_1779708773055_export_8.zip`, `manifest_event_count=61546`, `redaction_applied=True`, `EXPORT_LONG_WINDOW_W2_4H_CHECK=PASS`. **W3 24 h upper-bound run PASSED with watcher early-stop**: `total_elapsed_seconds=900`, `final_tail_labels_since_start=20`, `SAMPLE_SUFFICIENCY_REACHED=final_tail_labels=20>=10`, 24 h full runtime NOT NEEDED — proves the B-B-B-C sample sufficiency protocol can save runtime while preserving evidence; W3 safety summary held end-to-end (`mode=paper`, `live_trading=False`, `right_tail=False`, `llm=False`, `exchange_live_orders=False`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, `risk_approved=0`, `ingestion_errors=0`, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `ws_real_transport=True`); watcher logs `data/logs/pr58_w3_24h_ws_2026-05-25T11:56:10Z.log`, `data/logs/pr58_w3_24h_watch_2026-05-25T11:56:10Z.log`. **W3 export PASSED**: latest export zip after W3 early-stop `data/reports/exports/ama_rt_test_data_1779712866542_export_6.zip`, generated 2026-05-25 12:41 UTC, `manifest_event_count=62761`, `redaction_applied=True`, `events.jsonl` exists, `EXPORT_LONG_WINDOW_W3_EARLY_STOP_CHECK=PASS`; W3 export-range event counts `TAIL_LABEL_ASSIGNED=495`, `LABEL_WINDOW_COMPLETED=495`, `STRATEGY_VALIDATION_SAMPLE_CREATED=397`, `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=4`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=20`, `PAPER_ALPHA_GATE_EVALUATED=5`, `PAPER_ALPHA_RULE_EVALUATED=45`, `PAPER_ALPHA_COHORT_EVALUATED=30`, `PAPER_ALPHA_REPORT_GENERATED=5` (clarification: `final_tail_labels_since_start=20` is the watcher early-stop condition for the 900 s live window; `TAIL_LABEL_ASSIGNED=495` is the 24 h export-range event count — both valid, different scopes). **B-B-B-C acceptance is acceptance of the long-window data collection and sample-sufficiency protocol.** It does **NOT** mean any Regime / Cluster has proven right-tail advantage yet, does **NOT** mean strategy effectiveness is proven, does **NOT** authorise live trading, does **NOT** authorise rule relaxation based on low samples, does **NOT** authorise automatic parameter optimisation, does **NOT** authorise AI Learning, does **NOT** authorise changing the Risk Engine or the Execution FSM, does **NOT** authorise Phase 12. It records: 2 h run works; 4 h run works; completed labels begin to appear over longer windows; 24 h upper-bound early-stop works; completed-tail-label sufficiency threshold can be reached early; export / replay evidence preserves the results; low-sample states remain conservative; no trade authority granted. Long-window protocol outputs (`long_window_run_plan`, `sample_sufficiency_checklist`, `cohort_stability_checklist`, `operator_vps_evidence_template`, `export_replay_evidence_template`, `closeout_acceptance_template`) remain paper-only / report-only / evidence-only and cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes; the Risk Engine remains the single trade-decision gate. Safety flags unchanged across W1 / W1+ 2 h, W2 4 h, and W3 24 h upper-bound early-stop runs. See "Closed phase: Phase 11C.1C-C-B-B-B-C (ACCEPTED)" and "Phase 11C.1C-C-B-B-B-C acceptance evidence (operator-VPS W1 / W1+ 2 h, W2 4 h, W3 24 h upper-bound early-stop paper WS evidence PASSED)" below. |
| 11C.1C-C-B-B-B-D | Mover Capture Recall & Missed-Tail Coverage Audit v0 (*异动币捕捉召回与漏捕右尾覆盖审计 v0*; paper / report / evidence-only fourth child slice under Phase 11C.1C-C-B-B-B) | 2026-05-25 | PR #60 docs-only kickoff merged into `main`; PR #61 implementation merged into `main`; this docs-only closeout PR #62 records the operator-VPS 10 min WS paper smoke evidence + daily report Mover Capture section + `MOVER_CAPTURE_*` event counts + Phase 8.5 export bundle + audit result `mover_capture_audit_status=DEGRADED` and flips the slice to `ACCEPTED`. **Operator-VPS 10 min WS paper smoke PASSED**: `duration_seconds=600.0`, `dry_run=false`, `ws_first=true`, `ws_real_transport=true`, `ingestion_errors=0`, `risk_approved=0`, `HTTP 429=0`, `HTTP 418=0`, `ws_reconnect_count=0`, `ws_stale_count=0`, `live_trading_enabled=False`, `exchange_live_order_enabled=False`, `llm_enabled=False`, `right_tail_enabled=False`. **Mover Capture event counts**: `MOVER_CAPTURE_RECALL_AUDIT_GENERATED=1`, `MOVER_CAPTURE_PATH_AUDITED=20`. **Daily report** contains `## Phase 11C.1C-C-B-B-B-D Mover Capture Recall & Missed-Tail Coverage Audit v0` section. **Audit result**: `mover_capture_audit_status=DEGRADED`, `top_mover_count=20`, `captured_top_mover_count=4`, `missed_top_mover_count=16`, `capture_recall_rate=0.2000`, `data_unreliable_count=4`, `risk_rejected_mover_count=4`. `DEGRADED` is the **expected and accepted** audit output for this smoke window because the audit layer successfully surfaced coverage weakness / uncertainty — `DEGRADED` is **NOT** a runtime failure; captured-but-risk-rejected does **NOT** mean discovery failure; missed-with-unknown reason is a `review` signal, **not** permission to loosen rules; low capture recall does **NOT** authorise automatic `symbol_limit` expansion / anomaly threshold changes / candidate pool capacity changes / Regime weight changes / Risk Engine changes; high capture recall would also **NOT** authorise live trading. **Phase 8.5 export bundle**: `data/reports/exports/ama_rt_test_data_1779721036065_export_d.zip`, `manifest_event_count=63968`, `redaction_applied=True`, `events.jsonl` exists, export contains `MOVER_CAPTURE_*` events, `MOVER_CAPTURE_RECALL_AUDIT_GENERATED=1`, `MOVER_CAPTURE_PATH_AUDITED=20`, `EXPORT_MOVER_CAPTURE_RECALL_CHECK=PASS`; export package files observed: `manifest.json`, `summary_report.md`, `events.jsonl`, `opportunities.jsonl`, `signal_snapshots.jsonl`, `risk_decisions.jsonl`, `state_transitions.jsonl`, `capital_events.jsonl`, `virtual_trade_plans.jsonl`. Mover Capture Recall & Missed-Tail Coverage Audit v0 outputs (`top_mover_capture_summary` / `captured_mover_evidence` / `missed_mover_audit` / `symbol_universe_exclusion_summary` / `candidate_eviction_summary` / `risk_rejection_summary` / `first_seen_latency_summary` / `capture_recall_rate` / `missed_tail_candidate_list` / `coverage_warning` / `insufficient_coverage_reasons`) remain paper-only / report-only / evidence-only and cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes; the Risk Engine remains the single trade-decision gate. Safety flags unchanged across the operator-VPS run. See "Closed phase: Phase 11C.1C-C-B-B-B-D (ACCEPTED)" and "Phase 11C.1C-C-B-B-B-D acceptance evidence (operator-VPS 10 min WS paper smoke PASSED)" below. |
| 11C.1C-C-B-B-B-D-B | Post-Discovery Outcome Metrics v0 (*发现后结果度量 v0*; paper / report / evidence-only fifth child slice under Phase 11C.1C-C-B-B-B) | 2026-05-27 | PR #67 implementation merged into `main`; PR #68 evidence-runner-only PR merged into `main` (empty-workspace `INSUFFICIENT_EVIDENCE` marker); PR #69 merged into `main` and fixed the D-B evidence runner input adapter gap so the runner consumes the **real** D-A export shape (`HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED` events whose payload **is** the per-mover record, not wrapped in `record`); the real VPS D-A export evidence was rerun on `main`; this docs-only closeout PR records the resulting B1 evidence run and flips the slice to **`ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT`** (explicitly **NOT** full quality accepted). **D-A export input check (real VPS rerun on `main`) PASSED**: `HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED=2`, `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED=300`, `D_A_EXPORT_INPUT_CHECK=PASS`. **B1 evidence run output** (`data/reports/post_discovery_outcome/pr69_main_real_d_a_evidence`): `status=EVIDENCE_GENERATED`, `reference_window=60d`, `evaluated_count=300`, `report_generated_count=1`, `output_report=data/reports/post_discovery_outcome/pr69_main_real_d_a_evidence/post_discovery_outcome_report.json`, `output_events=data/reports/post_discovery_outcome/pr69_main_real_d_a_evidence/events.jsonl`. **Outcome label summary**: `INSUFFICIENT_PRICE_PATH=195/300`, `MISSED_STRONG_TAIL=105/300`. **Detection timing summary**: `INSUFFICIENT_DATA=195/300`, `MISSED=105/300`. **Notable symbols (still unresolved by D-B alone)**: `RAVEUSDT=INSUFFICIENT_PRICE_PATH / INSUFFICIENT_DATA`, `STOUSDT=INSUFFICIENT_PRICE_PATH / INSUFFICIENT_DATA`. **Warnings**: `d_a_backfill_records_missing_using_record_audited_fallback` (Format B fallback engaged; expected for the real D-A export shape). **What this acceptance level means**: PR #69 fixed the D-B runner input adapter gap; D-B can now consume real D-A export records; 300 D-A records were evaluated; one `POST_DISCOVERY_OUTCOME_REPORT_GENERATED` was produced; the output is **evidence-generated, but NOT direction-quality accepted**; 195/300 records are `INSUFFICIENT_PRICE_PATH` (the D-A export does not yet carry post-first-seen K-line price paths for those movers); 105/300 records are `MISSED_STRONG_TAIL` (the system never had a first-seen anchor at all); `RAVEUSDT` and `STOUSDT` remain unresolved because they are `INSUFFICIENT_PRICE_PATH / INSUFFICIENT_DATA`; the toolchain works end-to-end against real D-A export records, but the outcome quality is bounded by missing post-first-seen price-path data. **What this acceptance level does NOT mean**: D-B does **NOT** solve direction (long / short / entry / exit / stop / target / position size / leverage); D-B does **NOT** prove strategy profitability (no PnL was simulated, no order was submitted, no Risk Engine decision was reproduced); D-B does **NOT** authorise auto-tuning (no `symbol_limit` expansion, anomaly threshold change, candidate-pool capacity change, Regime weight change, or any other runtime knob — "looking at the answer key" against the post-hoc D-A reference set is forbidden); D-B does **NOT** authorise DeepSeek trade decisions (DeepSeek remains read-only / sandbox-only / offline under the AI Layer Constitution); Phase 12 remains **FORBIDDEN**. **Next allowed route**: B1 closeout accepted as toolchain + partial quality only; then **either** B1.1 *Historical Price Path Completeness / Kline Path Adapter* (recommended; needed because 195/300 records lack sufficient post-first-seen price path and `RAVEUSDT` / `STOUSDT` remain unresolved on price-path / data-gap grounds) **or** B2 *Severe Missed Tail Triage* (admissible only with the explicit note that `RAVEUSDT` and `STOUSDT` currently require price-path / data-gap triage before they can be classified as severe missed tails by D-B alone). **The next allowed route is NOT** to start DeepSeek directly, and is **NOT** to start blind walk-forward directly. **Safety boundary held end-to-end**: `mode=paper`, `live_trading=False`, `exchange_live_orders=False`, `right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, no private API, no live orders, no real Telegram outbound, no DeepSeek trade decision, **Phase 12 = FORBIDDEN**. The Risk Engine remains the single trade-decision gate. This closeout PR is **docs-only**: no file under `app/`, `scripts/`, `tests/`, `configs/`, `risk/`, `execution/`, `exchanges/`, `llm/`, `telegram/` is touched; no event name is changed; no schema version is changed; no test was run; no paper run, export, replay, or historical builder was invoked; no real API was contacted. See "Closed phase: Phase 11C.1C-C-B-B-B-D-B (ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT)" block below. |
| 11C.1C-C-B-B-B-D-B.1 | Historical Price Path Completeness / Kline Path Adapter v0 (*历史价格路径完整性 / K线路径适配器 v0*; paper / report / evidence-only small follow-up patch under Phase 11C.1C-C-B-B-B-D-B; **NOT** an indefinite extension of B1) | 2026-05-27 | PR #71 implementation merged into `main` (record-level price-path resolution, operator-supplied-path Lookahead Guard, daily-bucket adapter from `data/historical_market_store/top_movers/*.jsonl`); the real D-B evidence runner was rerun on `main` from the operator VPS against the new adapter; this docs-only closeout PR records the resulting B1.1 main-evidence run and flips the slice to **`ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY`** (explicitly **NOT** "intraday 1m / 5m kline path solved"). **B1.1 main-evidence check PASSED**: `B1_1_PRICE_PATH_MAIN_EVIDENCE_CHECK=PASS`. **B1.1 evidence run output** (`data/reports/post_discovery_outcome/pr71_main_price_path_evidence`): `status=EVIDENCE_GENERATED`, `evaluated_count=300`, `report_generated_count=1`, `event_counts.POST_DISCOVERY_OUTCOME_EVALUATED=300`, `event_counts.POST_DISCOVERY_OUTCOME_REPORT_GENERATED=1`, `kline_interval_used=1d`. **Price path resolution coverage**: `price_path_records_loaded=17`, `price_path_records_missing=283`. **Price path source summary**: `historical_market_store_daily_top_movers=17`, `absent=283`. **Price path missing-reason summary**: `no_top_mover_row_covering_first_seen_time=133`, `no_first_seen_time=110`, `insufficient_post_first_seen_points=40`. **Notable symbol price-path summary**: `RAVEUSDT` — `loaded=false`, `loaded_record_count=0`, `record_count=17`, `source=absent`, `missing_reason=no_top_mover_row_covering_first_seen_time`; `STOUSDT` — `loaded=false`, `loaded_record_count=0`, `record_count=3`, `source=absent`, `missing_reason=no_top_mover_row_covering_first_seen_time`. **Warnings**: `d_a_backfill_records_missing_using_record_audited_fallback` (Format B fallback engaged; expected for the real D-A export shape; carried over from the B1 closeout and unchanged in B1.1). **What this acceptance level means**: B1.1 toolchain passed; PR #71 evidence runner can evaluate 300 records; 300 `POST_DISCOVERY_OUTCOME_EVALUATED` events were emitted; 1 `POST_DISCOVERY_OUTCOME_REPORT_GENERATED` event was emitted; the price-path adapter is currently **daily-bucket only** (`kline_interval_used=1d`, **not** an intraday 1m / 5m kline path adapter); the local Historical Market Store currently supplies a price path for **17 / 300** records (283 / 300 remain `absent`); `RAVEUSDT` and `STOUSDT` remain unresolved because the local daily-bucket store does not yet contain a top-mover row whose day window covers the record's `first_seen_time_utc_ms`; record-level resolution and the operator-path Lookahead Guard are now enforced (no point with `timestamp > first_seen_time_utc_ms` may serve as `first_seen_price`). **What this acceptance level does NOT mean**: B1.1 does **NOT** mean the intraday 1m / 5m kline path is solved (it is daily-bucket only); B1.1 does **NOT** solve direction (no `long` / `short` / `entry` / `exit` / `stop` / `target` / `position_size` / `leverage` field is emitted); B1.1 does **NOT** prove strategy profitability (no PnL was simulated, no order was submitted, no Risk Engine decision was reproduced); B1.1 does **NOT** authorise auto-tuning (no `symbol_limit` expansion, anomaly threshold change, candidate-pool capacity change, Regime weight change, or any other runtime knob); B1.1 does **NOT** authorise DeepSeek trade decisions (DeepSeek remains read-only / sandbox-only / offline under the AI Layer Constitution); Phase 12 remains **FORBIDDEN**. **Next allowed route: B2 — Severe Missed Tail Triage v0.** B1 is a focused branch off the mainline and is **not** to be extended indefinitely; B1.1 is the small patch on B1, and B1.1 closeout returns the project to the main route. B2 will perform root-cause triage on unresolved severe-miss cases such as `RAVEUSDT` and `STOUSDT`, attributing each into a closed bucket (`PRICE_PATH_GAP` / `DATA_UNRELIABLE` / `EVENT_HISTORY_MISSING` / `UNIVERSE_GAP` / `SYMBOL_LIMIT_GAP` / `CANDIDATE_POOL_EVICTED` / `THRESHOLD_TOO_STRICT` / `WS_DATA_GAP` / `REST_REFERENCE_GAP` / `RISK_REJECTED_BUT_MOVED` / `TRUE_DISCOVERY_FAILURE` / `UNKNOWN`). B2 remains forbidden from authorising auto-tuning, threshold change, `symbol_limit` expansion, candidate-pool capacity change, Regime weight change, live trading, DeepSeek trade decision, or Phase 12. A *Historical Kline Store Builder / Intraday Price Path Backfill* (sometimes referred to as "B1.2") is **NOT** started now; it is recorded as an **optional future data-quality task only**, available only if B2 triage proves severe-miss attribution is blocked by missing intraday price paths, and only with explicit owner approval — it is **not** the recommended next slice, **not** a precondition for B2, and **does not** block B2. **Safety boundary held end-to-end**: `mode=paper`, `live_trading=False`, `exchange_live_orders=False`, `right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, no private API, no live orders, no real Telegram outbound, no DeepSeek trade decision, **Phase 12 = FORBIDDEN**. The Risk Engine remains the single trade-decision gate. This closeout PR is **docs-only**: no file under `app/`, `scripts/`, `tests/`, `configs/`, `risk/`, `execution/`, `exchanges/`, `llm/`, `telegram/`, or database schema is touched; no event name is changed; no schema version is changed; no test was run; no paper run, export, replay, or historical builder was invoked by this PR; no real API was contacted by this PR. See "Closed phase: Phase 11C.1C-C-B-B-B-D-B.1 (ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY)" block below. |


## Catch-up index (slices after `11C.1C-C-B-B-B-C`)

> The "Closed phases" table above visually ends at the `-B-C` long-window
> slice. Everything shipped since then is tracked in the sprawling
> "Open / Reserved phases" table below and in the per-`PR1xx` "Open slice"
> sections near the top of this file. For a **single ordered, readable
> list of every milestone and its status**, use **`docs/ROADMAP.md`**
> (milestones `M01`–`M68`, stages `S0`–`S12`). The condensed catch-up:

| Milestone (ROADMAP) | Legacy code | Status |
| --- | --- | --- |
| M28 Mover Capture Recall & Missed-Tail Coverage Audit | 11C.1C-C-B-B-B-D | CLOSED (PR #62) |
| M29 Historical 60D Mover Coverage Backfill | 11C.1C-C-B-B-B-D-A | CLOSED |
| M30 Post-Discovery Outcome Metrics | 11C.1C-C-B-B-B-D-B | PARTIAL (toolchain; price-path incomplete) |
| M31 Historical Price Path / Kline-Path Adapter | 11C.1C-C-B-B-B-D-B.1 | PARTIAL (daily-bucket only) |
| M32 Reject-to-Outcome Attribution | 11C.1C-C-B-B-B-D-C-A | SHIPPED |
| M33 Severe Missed Tail Triage | 11C.1C-C-B-B-B-D-C-B | IN_REVIEW |
| M34 Discovery Quality Scorecard | 11C.1C-C-B-B-B-D-D | IN_REVIEW |
| M35 Block B Integrated Evidence Checkpoint | 11C.1C-C-B-B-B-D-E | IN_REVIEW |
| M36 Replay Extension for 11C Adaptive Events | 11C.1C-C-B-B-B-E-A | SHIPPED |
| M37 Reflection Extension for 11C Adaptive Events | 11C.1C-C-B-B-B-E-B | SHIPPED |
| M38 Evidence Contract Baseline | 11C.1C-C-B-B-B-E-C | SHIPPED |
| M39 Block C Integrated Checkpoint | 11C.1C-C-B-B-B-E-D | IN_REVIEW |
| M40–M51 Blind Walk-Forward Simulation track | 11C.1D-B / -C / -D / -D-A … -D-I (+ PR104/PR108 fixes) | SHIPPED |
| M52–M58 AI Intelligence Layer | Phase AI-1 … AI-CHECKPOINT | SHIPPED |
| M60 Live Foundation | PR110 | IN_REVIEW |
| M61 API Integration Pack | PR111 | IN_REVIEW |
| M62 Live Capital / Risk / Funding-Aware PnL / 10U Profile | PR112 | IN_REVIEW |
| M63 Live Execution Gateway | PR113 | IN_REVIEW |
| M64 Telegram Operator Console + Live Funding Attribution | PR114 | IN_REVIEW |
| M65 DeepSeek Live Intelligence | PR115 | IN_REVIEW |
| M66 10U LIVE_LIMITED Launch Pack | PR116 | IN_REVIEW |
| M67 Full-System Single-Altcoin Live Sandbox Audit *(current head)* | PR117 | IN_REVIEW |
| — Binance API permission false-positive hotfix *(S11 maintenance; not a milestone)* | PR118 | MERGED |
| M68 Real money / live trading | Phase 12 | **FORBIDDEN** |

> **PR118 (maintenance hotfix).** Fixes a Binance API permission
> parser false positive (the high-risk withdraw warning is now driven
> only by the explicit `apiRestrictions.enableWithdrawals` field, not
> inferred from futures account capability) and hardens the real-key
> health check. **It does not loosen any safety gate:**
> `exchange_live_orders`, `trade_authority`, `live_trading`, and
> `ai_trade_authority` all remain `false`, and the order path is
> untouched. It is `S11` live-chain maintenance — **not** a new
> milestone and **not** Phase 12.

## Open / Reserved phases

| #          | Title                                                                | State                       | Detail                                                                 |
| ---------- | -------------------------------------------------------------------- | --------------------------- | ---------------------------------------------------------------------- |
| PR110 | Live Foundation v0 — Live Path Isolation + LIVE_SHADOW/LIVE_LIMITED Mode Guard + Capital Profile Ladder + Capital Event Contract + Right-tail Leverage Gate + Telegram Operator Contract (live-preparation safety foundation; contract / model / evidence-only) | **IN_REVIEW (after this implementation PR; not `ACCEPTED` until maintainer review)** | PR110 is **`IN_REVIEW`** after the implementation PR. It builds the pre-live safety foundation for the move from large-scale cloud blind testing to a 10U small-capital live-preparation posture, in a new, additive, isolated package `app/live/`: (1) **Live Path Isolation** (`path_isolation.py` + `gateway.py`) — every order intent carries an `OrderSource` (`SIM` / `BLIND` / `REPLAY` / `PAPER_SHADOW` / `LIVE`); `LivePathIsolationGuard` admits ONLY `OrderSource.LIVE`, refusing every other source with a `LIVE_PATH_BLOCKED` event + `LivePathIsolationViolation`; `classify_source_module` fail-safe maps MockExchange / BlindWalkForwardRunner / ReplayFeedProvider / PaperShadowStrategyBridge / SimulatedCapitalFlow to a blocked source (never `LIVE`); `LiveExecutionGateway.submit_order` is the single reserved live entry and refuses all submissions in PR110 (no execution adapter exists). (2) **Runtime Mode Guard** (`runtime_mode.py`) — `LIVE_SHADOW` (空盘跑; read-only, never any real order) vs `LIVE_LIMITED` (有资金跑; real small-capital trading in principle, not implemented in PR110); default is `LIVE_SHADOW` and `LiveModeGuard.from_config` always boots `LIVE_SHADOW` so a restart / default config can never silently enter `LIVE_LIMITED`; arming requires the `/mode live_limited` → `/confirm_live CODE` handshake + a profile that allows real orders + an armed kill switch. (3) **Capital Profile Ladder** (`capital_profile.py`) — `L0_SHADOW` .. `L8_10M_CAPITAL_PRESERVATION` (1U → 10,000,000U); `L0_SHADOW.real_orders_allowed=False`, `L1_10U_PROBE.max_account_capital_usdt=10`; escalation is never automatic (`AUTO_ESCALATION_ALLOWED=False`); `detect_profile_mismatch` demands operator action when adjusted equity leaves the active band; large profiles enforce tighter liquidity floor / symbol exposure / slippage. (4) **Capital Event Contract** (`capital_event.py`) — `CapitalEventType` taxonomy + `CapitalEventLedger` keep trading PnL strictly separate from deposits / withdrawals / fees / funding, so a deposit is never counted as profit and a withdrawal is never counted as a loss. (5) **Right-tail Leverage Gate** (`leverage_gate.py`) — deterministic `evaluate_right_tail_leverage_permission`; inputs are deterministic evidence + capital profile + runtime mode + risk state only; refuses AI / LLM / Telegram / blind / future-label input, missing exit / stop plan, missing liquidity evidence, risk-off regime, systemic risk, drawdown warning, risk halt, profile-disallows-boost, no-floating-profit boost requests, over-threshold slippage / spread / symbol exposure, and over-profile-max leverage; grants limited leverage only on strong deterministic right-tail structure when the profile allows it. (6) **Telegram Operator Contract** (`telegram_operator_contract.py`) — command + card-type taxonomy + card field schema; shadow cards show the planned entry / stop / take-profit but `real_order=False` / `order_id="--"`; live cards carry the real entry / exit / pnl / balance schema but `real_order` is forced False (`LIVE_EXECUTION_ADAPTER_AVAILABLE=False`). Core additions: `OrderSource` + `LiveRuntimeMode` enums, 12 PR110 audit event types, 3 errors; a new locked `live:` config section whose schema refuses to load `live_trading` / `exchange_live_orders` / `binance_private_api_enabled` / `ai_trade_authority` / `trade_authority` / `right_tail_live_boost_enabled` as True and refuses `phase_12_forbidden=False`. Tests: `tests/unit/test_pr110_live_foundation.py` (all 24 brief-mandated cases) + full `tests/unit` green. **NOT live trading. NOT the Binance private API. NOT real orders. NOT real Telegram outbound. NOT AI trade authority. NOT auto-escalation. NOT auto-tuning. NOT Phase 12.** LIVE_SHADOW and LIVE_LIMITED are different and must never be confused. Safety flags unchanged (`phase_12_forbidden=true`, `live_trading=false`, `exchange_live_orders=false`, `binance_private_api_enabled=false`, `telegram_outbound_enabled=false`, `ai_trade_authority=false`, `trade_authority=false`, `right_tail_live_boost_enabled=false`). The Risk Engine remains the single trade-decision gate. Phase 12 remains **FORBIDDEN**. See `docs/AMA_RT_LIVE_FOUNDATION_SPEC.md`, `docs/AMA_RT_LIVE_MODE_AND_CAPITAL_PROFILE.md`, `docs/CHANGELOG.md` (PR110 entry). |
| 11C.1D-D-I | Blind Runner Historical Store Input Glue (*Blind Runner 历史数据存储输入接线 / 最小 glue*; PR103; paper / report / evidence-only) | **IN_REVIEW (after this implementation PR; not `ACCEPTED` until maintainer review)** | Phase 11C.1D-D-I is **`IN_REVIEW`** after the implementation PR. PR103 is a **minimal glue PR** that wires the PR101/PR102 Historical Data Store output (`records.jsonl` + `historical_data_manifest.json` + `universe_manifest.json`) into the PR100 Blind Walk-forward Runner CLI. It adds the `--historical-store-dir` / `--records-path` / `--historical-data-manifest-path` / `--universe-manifest-path` arguments to `scripts/run_blind_walk_forward.py`; restores the PR95 record types (`HistoricalKlineRecord` / `HistoricalMarketRecord` / `SymbolStatusRecord`) from `records.jsonl` into a `HistoricalMarketStore` (dispatch on the explicit `is_*` marker; never fabricates a field); builds the PR96 `ReplayFeedProvider` over that store; lets the PR100 `BlindWalkForwardRunner` consume the **real** records; and pins the **real** `data_manifest_hash` / `universe_manifest_hash` (read from the PR101 manifests) onto the `BlindRunManifest` via two new optional, `sha256:`-validated `BlindWalkForwardRunnerConfig` fields (fallback to hash-of-inline-artefact when absent). Missing / empty `records.jsonl` returns `status = INSUFFICIENT_EVIDENCE` with CLI exit code `3` and the run is NOT started (no fabricated data); missing `historical_data_manifest.json` / `universe_manifest.json` produce a WARN, never a fabricated hash, and never block a kline-only short smoke. A `historical_store_input.json` sidecar records `ingested_record_count` / `record_counts_by_type` / `source_files` / pinned hashes / warnings. **PR94 `TimeWallGuard` and PR96 `ReplayFeedProvider` are NOT bypassed** — every `available_at <= simulated_time` / closed-candle gate stays in force. The CLI imports only `app.sim` + the standard library; it never imports `app.risk` / `app.execution` / `app.exchanges` / `app.telegram` / `app.config` / `app.ai` and opens no network / Binance private API / DeepSeek / LLM transport. Tests on this PR: `tests/unit/test_blind_walk_forward_runner.py` 48/48 PASS (17 new PR103 tests); full `tests/unit` 3645/3645 PASS. **NOT a new blind testing system. NOT a new strategy. NOT a decision callback. NOT the 30D / 60D / 90D / 2Y runner. NOT live trading. NOT auto-tuning. NOT real Telegram outbound. NOT the Binance private API. NOT Phase 12.** A run over a store whose data spans well past the blind window may score `INVALIDATED_LOOKAHEAD_OR_DRIFT` because PR96 records every not-yet-available record as a `FUTURE_AVAILABLE_AT` audit violation and PR100 routes any batch violation into a `FUTURE_RECORD_ACCESS` invalidation — that is existing substrate behaviour (correctly withholding future data), not a PR103 regression. The Risk Engine remains the single trade-decision gate. Phase 12 remains **FORBIDDEN**. See `docs/PHASE_11C_1D_D_I_BLIND_RUNNER_HISTORICAL_STORE_GLUE.md`. |
| 11C.1D-D-J | Blind Runner Store Query Performance Fix (*Blind Runner 历史数据存储查询性能修复*; PR104; paper / report / evidence-only) | **IN_REVIEW (after this implementation PR; not `ACCEPTED` until maintainer review)** | Phase 11C.1D-D-J is **`IN_REVIEW`** after the implementation PR. PR104 is a **performance bugfix** that lets the PR100 Blind Walk-forward Runner consume a real `--historical-store-dir` with **bounded memory**. Root cause: the PR96 `ReplayFeedProvider` re-scanned the entire store via `store.query_records` on **every** 1-minute step and recorded one `FUTURE_AVAILABLE_AT` violation for every not-yet-available record on every tick — O(records × steps) ≈ tens of millions of violation objects accumulated across the store, provider diagnostics, per-step batch snapshots and the runner's violation / failure / invalidation ledgers, driving RES to ~15.8 GB / ~96 % memory and ~4 GB swap on an 8 vCPU / 16 GB host with no output directory for 10+ minutes on a real public 7-day BTC/ETH store (24,192 records: 20,160 `KLINE_1M` + 4,032 `KLINE_5M`) over a 1-day blind window. Fix: (1) `app/sim/historical_market_store.py` gains two **pure, additive, read-only** accessors (`iter_candidate_records`, `iter_symbol_status_records`) that apply no time-wall gate and record no violation; the gated `query_records` / `query_klines` / `query_asof_universe` are **unchanged** (existing store tests stay green). (2) `app/sim/replay_feed_provider.py` builds an `available_at`-ordered index **once** and advances a forward-only `bisect` cursor, emitting only records that became newly visible since the previous tick (`allow_reemit=False`) or the visible prefix (`allow_reemit=True`); future records are **withheld silently** — a not-yet-available record is **not** a no-lookahead violation by itself (Constitution §5, clarified), so no per-step diagnostics explosion is generated; the as-of universe is computed from the visible prefix of the (tiny) symbol-status set. **PR94 `TimeWallGuard` and the closed-candle `CandleVisibilityGuard` remain in force — no-lookahead protection is preserved, not bypassed.** (3) `scripts/run_blind_walk_forward.py` bounds the loader to `available_at <= --blind-end` by default (the out-of-window tail is never materialised; `--load-full-store` opts back into the legacy full load), creates the per-run **output directory at run start**, and emits a **progress heartbeat** every 500 steps via `logging` (never stdout). `data_manifest_hash` / `universe_manifest_hash` are **preserved** exactly as in PR103; missing / empty / all-out-of-window data still returns `INSUFFICIENT_EVIDENCE` (never fabricated). The CLI still imports only `app.sim` + the standard library; it never imports `app.risk` / `app.execution` / `app.exchanges` / `app.telegram` / `app.config` / `app.ai` and opens no network / Binance private API / DeepSeek / LLM transport. Tests on this PR: `tests/unit/test_replay_feed_provider.py` + `tests/unit/test_blind_walk_forward_runner.py` PASS (updated the three provider tests that asserted the old "future ⇒ per-step violation" behaviour to the PR104 "withheld, not a violation" semantics; added provider trip-wire + 7-day-like 1-day-window bounded tests and runner bounded-load + large-store end-to-end completion tests); full `tests/unit` PASS. Expected cloud result after PR104: `status = EVIDENCE_GENERATED` / `PARTIAL_EVIDENCE`, `steps_run > 0`, `batches_consumed > 0`, `violations_count = 0`, `invalidations = []`, memory does not approach 16 GB, swap not heavily used. **NOT a new strategy. NOT the 30D / 60D / 90D / 2Y runner. NOT live trading. NOT auto-tuning. NOT real Telegram outbound. NOT the Binance private API. NOT live orders. NOT AI / DeepSeek in the decision chain. NOT Phase 12.** The Risk Engine remains the single trade-decision gate. Phase 12 remains **FORBIDDEN**. |
| 11C.1D-D | Simulated Capital Safety Floor / Kill Switch / No Negative Equity Guard (*模拟资金安全下限 / 熔断 / 无负权益保护*; PR108; paper / sim-live / evidence-only; capital safety ONLY) | **IN_REVIEW (after this implementation PR; not `ACCEPTED` until maintainer review)** | Phase 11C.1D-D PR108 is **`IN_REVIEW`** after the implementation PR. PR108 is a **capital-safety bugfix** addressing the PR107 finding that the simulated account could still show `equity_after ≈ -309` on a 100 USDT initial capital (cloud `blocked_180d_02_pr106_shadow`: `total_realized_pnl=-409`, `max_drawdown=0.90`). Root cause: the PR98 `SimulatedCapitalFlowEngine` added realised gross PnL straight onto `exchange_equity` with **no floor** and opened new positions checking only `capital_frozen` / `max_active_positions` — no pre-entry equity gate, no no-negative-equity guard, no kill switch. Fix (capital safety ONLY — no strategy parameter tuned, no profitability change attempted): (1) **no-negative-equity guard** clamps the simulated cash balance at `capital_floor` (default 0) and books the excess as a deterministic `liquidation_shortfall` while the ledger keeps the **truthful** realised loss (losses are never hidden, only the account equity floors); (2) **pre-entry gate** `can_open_position(symbol, requested_qty, notional)` returns a closed `CapitalRejectReason` (`insufficient_equity` / `capital_exhausted` / `risk_halt_active` / `max_drawdown_limit_reached` / `max_active_positions_reached`) when an open would be unsafe; (3) **kill switch** `enforce_capital_safety(simulated_time)` (default `--max-drawdown-halt-pct 0.5`) force-exits every open simulated position through the simulated flow (`SIM_LIQUIDATION` on a capital-floor breach, `RISK_HALT` on the hard drawdown limit), latches the halt (`RiskHaltReason` `SIM_CAPITAL_EXHAUSTED` / `MAX_DRAWDOWN_LIMIT_REACHED`), and stops new entries for the rest of the blind window — new entries after the halt become `SIM_REJECT` / `SIM_ACCOUNT_HALTED` (a predictable, paper-only `SimAccountHaltedError`, **never** a bare `RuntimeError`). The runner emits `SIM_FORCED_EXIT` + `SIM_CAPITAL_EXHAUSTED` / `SIM_ACCOUNT_HALTED` transcript entries (each carrying `SIMULATED_ONLY` / `NO_LIVE_ORDER` / `NO_REAL_CAPITAL` / `NO_COMMAND_AUTHORITY` + reason + `equity_before` / `equity_after` / `drawdown`), records forced exits as enriched paper-shadow trades, and the blind report / window summary / trade-ledger payload / paper-shadow sidecar gain `initial_capital`, `final_equity`, `min_equity`, `max_drawdown`, `max_drawdown_limit`, `capital_exhausted`, `halted_by_risk`, `risk_halt_reason`, `forced_exit_count`, `capital_reject_count`, `capital_exhaustion_event_count` / `liquidation_like_event_count`. The bridge stops emitting new entries (and records the suppressed signal) once the capital flow is halted. No-lookahead constraints unchanged: at simulated time T only `available_at <= T` closed candles are used; no future outcome / MFE / MAE / tail label is a decision input; AI text never influences direction / sizing / leverage / stop / target / execution. Scope touches only `app/sim/simulated_capital_flow.py`, `app/sim/blind_walk_forward_runner.py`, `app/sim/paper_shadow_strategy_bridge.py`, `scripts/run_blind_walk_forward.py`, the matching `tests/unit/*`, and the docs; **nothing** under `app/risk/`, `app/execution/`, `app/exchanges/`, `app/telegram/`, `app/config/`. Tests on this PR: new `tests/unit/test_simulated_capital_flow.py` (pre-entry gate, no-negative-equity clamp, liquidation + drawdown kill switch, halt-latched refusal of new opens, deterministic snapshot) + extended `tests/unit/test_blind_walk_forward_runner.py` (kill-switch force-exit + halt, no new entries after halt, ledger/record no-negative continuation, report capital-safety fields, safety flags intact) + `tests/unit/test_paper_shadow_strategy_bridge.py` (bridge suppresses entries while halted); full `tests/unit` 3704/3704 PASS (PR98 / PR106 / PR107 tests unchanged). Expected cloud result after merge (`blocked_180d_02_pr106_shadow` `--initial-capital 100 --enable-paper-shadow-strategy --no-ai-post-window-summary`): `status=EVIDENCE_GENERATED`, `violations_count=0`, `invalidations=[]`, no `RuntimeError`, `final_equity` not silently negative, and if capital is exhausted `capital_exhausted=true` with new entries stopping/rejecting. Safety flags unchanged (`phase_12_forbidden=true`, `live_trading=false`, `exchange_live_orders=false`, `binance_private_api_enabled=false`, `telegram_outbound_enabled=false`, `auto_tuning_allowed=false`, `trade_authority=false`, `ai_trade_authority=false`). **NOT a strategy change. NOT a profitability change. NOT live trading. NOT auto-tuning. NOT real Telegram outbound. NOT the Binance private API. NOT live orders. NOT AI / DeepSeek in the decision chain. NOT Phase 12.** The Risk Engine remains the single trade-decision gate. Phase 12 remains **FORBIDDEN**. See `docs/CHANGELOG.md` (PR108 entry). |
| AI-CHECKPOINT | AI Integrated Checkpoint v0 (*AI 综合检查点 v0*; paper / report / evidence-only end-to-end roll-up of the AI-1 → AI-2 → AI-3 → AI-4 (offline sandbox / fake provider) → AI-5 → AI-6 chain into one descriptive `ai_integrated_checkpoint_report.json`; **NOT** a per-phase `ACCEPTED` gate, **NOT** trade authority, **NOT** auto-tuning, **NOT** the DeepSeek hot path, **NOT** Telegram live outbound, **NOT** Phase 12) | **IN_REVIEW (after this implementation PR; not `ACCEPTED` until maintainer review)** | Phase AI-CHECKPOINT is **`IN_REVIEW`** after the implementation PR. The PR ships `scripts/run_ai_integrated_checkpoint.py` (paper / report / evidence-only runner; reads only local files under `--block-c-report` / `--evidence-bundle` / `--sandbox-output` / `--operator-briefing-dir` and writes only files under `--output-dir`; aggregates the AI-1 / AI-4 / AI-5 / AI-6 simplified outputs into one descriptive `ai_integrated_checkpoint_report.json` plus matching `.md` summary; emits one of three closed statuses (`INSUFFICIENT_EVIDENCE` / `PARTIAL_EVIDENCE` / `EVIDENCE_GENERATED`) and the corresponding `next_allowed_phase` (`Offline Rule Sandbox Replay v0 preparation` / `Offline Rule Sandbox Replay preparation / AI operator evidence run` / `NEEDS_AI_OPERATOR_EVIDENCE`); when an input is missing on disk the runner substitutes a deterministic fallback fixture marked `source=fallback_fixture` and never carries fabricated market conclusions; reuses the existing `app.ai.evidence_bundle.FORBIDDEN_AI_OUTPUT_FIELDS` list and the `app.reflection.ai_reflection.replay_and_reflect_artefacts` convenience wrapper; never imports `app.risk` / `app.execution` / `app.exchanges` / `app.telegram` / `app.config`; never imports any HTTP / network library; hard-pins `phase_12_forbidden=true`, `auto_tuning_allowed=false`, `trade_authority=false`, `ai_output_is_commentary_only=true`, `ai_output_can_be_truth=false`, `ai_output_can_be_training_label=false`, `ai_output_can_be_tail_label=false`, `ai_output_can_be_strategy_sample=false` on every emitted payload), the `tests/unit/test_ai_integrated_checkpoint.py` unit-test module covering every brief-mandated acceptance test (no input → `INSUFFICIENT_EVIDENCE`, partial / fallback input → `PARTIAL_EVIDENCE`, valid AI chain input → `EVIDENCE_GENERATED`, `next_allowed_phase` correct, `phase_12_forbidden=true` on every payload, `auto_tuning_allowed=false` on every payload, `trade_authority=false` on every payload, `ai_output_can_be_truth=false`, `ai_output_can_be_training_label=false`, `ai_output_can_be_tail_label=false`, `ai_output_can_be_strategy_sample=false`, no forbidden trade-authority / runtime-tuning keys at any nesting depth, no banned imports (`app.risk` / `app.execution` / `app.exchanges` / `app.telegram` / `app.config`), no live LLM / DeepSeek network call required (no HTTP-library import + a `socket.socket`-monkeypatched run), deterministic output across two runs, plus output paths and CLI exit codes), and the new phase doc `docs/PHASE_AI_INTEGRATED_CHECKPOINT.md`. **Status taxonomy is intentionally NOT `ACCEPTED`.** Per-phase closeout PRs (AI-1 / AI-2 / AI-3 / AI-4 / AI-5 / AI-6) retain their own `IN_REVIEW` / `ACCEPTED` labels — the integrated checkpoint defers to those labels and never overrides them. The runner connects to no network, calls no LLM / DeepSeek, opens no Telegram socket, signs no request, never modifies `app.config`, and never reads a private API. **NOT live trading. NOT trade authority. NOT auto-tuning. NOT the DeepSeek hot path. NOT Telegram live outbound. NOT a per-phase `ACCEPTED` gate. NOT a strategy profitability proof. NOT a direction call. NOT Phase 12.** A `status = EVIDENCE_GENERATED` does **not** mean live trading is approved; it only authorises the next paper-only step (the *Offline Rule Sandbox Replay v0* preparation work). A `status = INSUFFICIENT_EVIDENCE` does **not** mean live trading is disapproved either; live-trading approval is a Phase 12 concern that requires the Spec §41 Go/No-Go checklist, and the checklist has not been initiated. Every emitted checkpoint carries `auto_tuning_allowed=false`; the constant is hard-pinned in the runner source. The Risk Engine remains the single trade-decision gate. Tests on this PR: `tests/unit/test_ai_integrated_checkpoint.py` 22/22 PASS. Phase 12 remains **FORBIDDEN**. |
| 11C.1C-C-B-B-B-D-E | Block B Integrated Evidence Checkpoint v0 (*Block B 综合证据检查点 v0*; paper / report / evidence-only Block B aggregation checkpoint that rolls up the simplified outputs of D-A / D-B / B1.1 / B2-A / B2-B / B3 into one descriptive integrated evidence report; **NOT** a per-phase `ACCEPTED` gate, **NOT** Replay / Reflection extension, **NOT** strategy profitability proof) | **IN_REVIEW (after this implementation PR; not `ACCEPTED` until evidence closeout)** | Phase 11C.1C-C-B-B-B-D-E is **`IN_REVIEW`** after the implementation PR. The PR ships `scripts/run_block_b_integrated_evidence_checkpoint.py` (paper / report / evidence-only runner; reads only local `events.jsonl` / `*.jsonl` files under `--reports-dir` / `--exports-dir` / `--post-discovery-dir`; reads the most recent `post_discovery_outcome_report.json` under `--post-discovery-dir`; aggregates the simplified D-A / D-B / B1.1 / B2-A / B2-B / B3 outputs into one descriptive `block_b_integrated_evidence_report.json` plus matching `.md` summary; emits one of three closed statuses (`INSUFFICIENT_EVIDENCE` / `PARTIAL_EVIDENCE` / `EVIDENCE_GENERATED`) and the corresponding `next_allowed_phase` (`Phase 11C.1C-C-B-B-B-E-A Replay Extension for 11C Adaptive Events v0` or `NEEDS_OPERATOR_EVIDENCE`); reuses the existing `app.adaptive.discovery_quality_scorecard.build_discovery_quality_scorecard` builder + recursive `assert_payload_has_no_forbidden_keys` guard; never imports `app.risk` / `app.execution` / `app.exchanges` / `app.llm` / `app.telegram` / `app.config`; hard-pins `phase_12_forbidden = true` and `auto_tuning_allowed = false` on every emitted payload), the `tests/unit/test_block_b_integrated_evidence_checkpoint.py` unit-test module covering every brief-mandated acceptance test (`INSUFFICIENT_EVIDENCE` on empty workspace, `PARTIAL_EVIDENCE` when D-B post-discovery is missing OR data-gap is high, `EVIDENCE_GENERATED` when every component is present, `next_allowed_phase` correct, `phase_12_forbidden = true` on every payload, `auto_tuning_allowed = false` on every payload, no forbidden trade-authority / runtime-tuning keys on any payload, no banned imports, CLI exit-codes correct), and the new phase doc `docs/PHASE_11C_1C_C_B_B_B_D_E_BLOCK_B_INTEGRATED_EVIDENCE_CHECKPOINT.md`. **Status taxonomy is intentionally NOT `ACCEPTED`.** Per-phase closeout PRs (D-A, D-B, B1.1) retain their own `ACCEPTED_TOOLCHAIN` / `PARTIAL_QUALITY` / `BLOCK_B_CHECKPOINT_ONLY` labels — the integrated checkpoint defers to those labels and never overrides them. The runner connects to no network, calls no LLM / DeepSeek, opens no Telegram socket, signs no request, never modifies `app.config`, and never reads a private API. **NOT live trading. NOT AI Learning. NOT automatic parameter optimisation. NOT reinforcement learning. NOT a per-phase `ACCEPTED` gate. NOT a strategy profitability proof. NOT a direction call. NOT the Block C Replay / Reflection extension implementation (that is the *next-allowed* phase, not part of this PR). NOT the DeepSeek integration. NOT Phase 12.** A `status = EVIDENCE_GENERATED` does **not** mean live trading is approved. A `status = INSUFFICIENT_EVIDENCE` does **not** mean live trading is disapproved either; live-trading approval is a Phase 12 concern that requires the Spec §41 Go/No-Go checklist, and the checklist has not been initiated. Every emitted checkpoint carries `auto_tuning_allowed = false`; the constant is hard-pinned in the runner source. The Risk Engine remains the single trade-decision gate. Tests on this PR: `tests/unit/test_block_b_integrated_evidence_checkpoint.py` 13/13 PASS; full `tests/unit` 2600/2600 PASS. Phase 12 remains **FORBIDDEN**. |
| 11C.1C-C-B-B-B-E-A | Replay Extension for 11C Adaptive Events v0 (*11C 自适应事件 Replay 扩展 v0*; paper / report / evidence-only next-allowed phase opened by a Phase 11C.1C-C-B-B-B-D-E Block B Integrated Evidence Checkpoint with `status ∈ {EVIDENCE_GENERATED, PARTIAL_EVIDENCE}`) | **NEXT_ALLOWED / NOT_STARTED** | Reserved phase. Will extend the existing Replay engine to play back the Block B adaptive events (D-A / D-B / B1.1 / B2-A / B2-B / B3) over previously captured event streams. Paper / report / evidence-only. **NOT live trading. NOT auto-tuning. NOT DeepSeek trade decisions. NOT Phase 12.** Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B / 11C.1C-C-B-B-B-C / 11C.1C-C-B-B-B-D / 11C.1C-C-B-B-B-D-A / 11C.1C-C-B-B-B-D-B / 11C.1C-C-B-B-B-D-B.1 / 11C.1C-C-B-B-B-D-C-A / 11C.1C-C-B-B-B-D-C-B / 11C.1C-C-B-B-B-D-D / 11C.1C-C-B-B-B-D-E forbidden item verbatim. Will require its own kickoff PR with brief, scope, boundary table, forbidden list, and acceptance evidence. Phase 12 remains **FORBIDDEN**. |
| 11C.1C-C-B-B-B-E-B | Reflection Extension for 11C Adaptive Events v0 (*11C 自适应事件 Reflection 扩展 v0*; paper / report-only Block C2 child slice opened by Phase 11C.1C-C-B-B-B-E-A Replay Extension acceptance via PR #78) | **IN_REVIEW (after this implementation PR; not `ACCEPTED` until maintainer review)** | Phase 11C.1C-C-B-B-B-E-B is **`IN_REVIEW`** after the implementation PR. The PR ships `app/reflection/adaptive_11c.py` (read-only reflection extension; `Reflection11CAdaptiveEngine`, `AdaptiveReflectionTag` closed enum of the 18 brief-mandated tags + `late_discovery`, `AdaptiveReflectionSeverity` closed enum, `AdaptiveReflectionInput` / `AdaptiveReflectionCase` / `AdaptiveReflectionSummary` frozen dataclasses with `to_payload()` plus a recursive `_assert_no_forbidden_keys` guard; `auto_tuning_allowed=False` hard-pinned on every emitted payload; never imports `app.risk` / `app.execution` / `app.exchanges` / `app.llm` / `app.telegram`; never produces `buy` / `sell` / `long` / `short` / `position_size` / `leverage` / `stop` / `target` / `risk_budget` / `runtime_config_patch`), the `tests/unit/test_reflection_11c_adaptive_events.py` unit-test module covering every brief-mandated test (POST_DISCOVERY_OUTCOME → `late_top_chase` / `early_discovery` / `post_discovery_no_edge`; REJECT_TO_OUTCOME → `false_negative_reject` / `correct_protective_reject` / `data_gap`; SEVERE_MISSED_TAIL → `severe_miss` / `needs_data_recovery`; DISCOVERY_QUALITY DEGRADED → `degraded_discovery_quality`; HISTORICAL_MOVER_COVERAGE missed → `missed_tail`; missing-fields-do-not-crash → `insufficient_evidence`; evidence_refs preserved with `event_id` fallback; `auto_tuning_allowed=False` everywhere; forbidden-imports static check; forbidden-fields-absent guard; deterministic ordering), and the new phase doc `docs/PHASE_11C_1C_C_B_B_B_E_B_REFLECTION_EXTENSION_11C_EVENTS.md`. Reflection only emits structured tags / summaries / counts / warnings — **NOT** trade advice, **NOT** AI / DeepSeek output, **NOT** runtime config patches, **NOT** auto-tuning. Tests on this PR: `tests/unit/test_reflection_11c_adaptive_events.py` 42/42 PASS; full `tests/unit` 2680/2680 PASS. **NOT live trading. NOT AI Learning. NOT automatic parameter optimisation. NOT reinforcement learning. NOT DeepSeek integration. NOT Phase 12.** Successful Phase 11C.1C-C-B-B-B-E-B only authorises Phase 11C.1C-C-B-B-B-E-C *C3 Evidence Contract Baseline* to start; no other phase is unlocked. Phase 12 remains **FORBIDDEN**. |
| 11C.1C-C-B-B-B | Strategy Validation Lab (deeper) & richer Cluster Exposure Control follow-up (parent; unchanged definition) | **NEXT_ALLOWED / NOT_STARTED** | Phase 11C.1C-C-B-B-A (PR #44) merged into `main` on 2026-05-23 (mergeCommit `3ecfc3b`) and is the gating predecessor; Phase 11C.1C-C-B-B-B is reserved for the deeper Strategy Validation Lab follow-up (richer cohort comparisons, extended cluster heuristics, longer-window correlations, dataset-driven retrospective audits). The parent phase is **not** renamed by Paper Alpha Gate v0; the Paper Alpha Gate v0 is one *child slice* under this parent (Phase 11C.1C-C-B-B-B-A), not the parent itself. NOT authorised by Phase 11C.1C-C-B-B-A acceptance bypassing the standard gate; will require its own kickoff PRs (one per child slice), brief, scope, boundary table, forbidden list, and acceptance evidence. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A forbidden item verbatim. |
| 11C.1C-C-B-B-B-A | Paper Alpha Gate v0 (paper / report-only first child slice under Phase 11C.1C-C-B-B-B; ACCEPTED via PR #52 + PR #54 docs-only closeout) | **ACCEPTED — see Closed phases table above** | Phase 11C.1C-C-B-B-B-A is now `ACCEPTED` (PR #52 merged into `main` on 2026-05-24, mergeCommit `f8ba315`; this docs-only closeout PR #54 records the operator-VPS paper evidence). The full closeout — including the verbatim operator-VPS 10 min WS paper smoke transcript, the Paper Alpha Gate daily-report excerpt, the four `PAPER_ALPHA_*` event counts, the Phase 8.5 export bundle reference, and the safety-flag invariants — is recorded under "Closed phase: Phase 11C.1C-C-B-B-B-A (ACCEPTED)" and "Phase 11C.1C-C-B-B-B-A acceptance evidence (operator-VPS 10 min WS paper smoke PASSED)" below. `paper_alpha_gate_status=INCONCLUSIVE` was an **expected and accepted** result for this smoke window because `completed_tail_label_count=0<10`; the Paper Alpha Gate correctly refused to overfit or force a `PASS`. `INCONCLUSIVE` does NOT mean runtime failure, does NOT authorise strategy changes, does NOT authorise live trading, does NOT authorise Phase 12. Paper Alpha Gate verdicts remain paper-only / report-only / evidence-only and cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes. Phase 12 remains **FORBIDDEN**. |
| 11C.1C-C-B-B-B-B | Regime & Cluster Cohort Evidence Pack v0 (paper / report / evidence-only second child slice under Phase 11C.1C-C-B-B-B; ACCEPTED via PR #56 implementation + PR #57 docs-only closeout) | **ACCEPTED — see Closed phases table above** | Phase 11C.1C-C-B-B-B-B is now `ACCEPTED` (PR #56 merged into `main` on 2026-05-24, mergeCommit `1a9abe2`; this docs-only closeout PR #57 records the operator-VPS paper evidence). The full closeout — including the verbatim operator-VPS 10 min WS paper smoke transcript, the Regime & Cluster Cohort Evidence Pack daily-report excerpt, the two `REGIME_CLUSTER_*` event counts, the Phase 8.5 export bundle reference, and the safety-flag invariants — is recorded under "Closed phase: Phase 11C.1C-C-B-B-B-B (ACCEPTED)" and "Phase 11C.1C-C-B-B-B-B acceptance evidence (operator-VPS 10 min WS paper smoke PASSED)" below. `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` was an **expected and accepted** result for this smoke window because `sample_count=14<20` and `completed_tail_label_count=0<10`; the Regime & Cluster Evidence Pack correctly refused to overfit or force a regime / cluster conclusion when structural samples were insufficient. `INSUFFICIENT_SAMPLE` does NOT mean runtime failure, does NOT authorise strategy changes, does NOT authorise rule relaxation, does NOT authorise live trading, does NOT authorise Phase 12. Regime & Cluster Evidence Pack outputs remain paper-only / report-only / evidence-only and cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes. Phase 12 remains **FORBIDDEN**. |
| 11C.1C-C-B-B-B-C | Long-Window Cohort Stability & Sample Sufficiency Protocol v0 (*长窗口 Cohort 稳定性与样本充足协议 v0*; docs / evidence-template-only third child slice under Phase 11C.1C-C-B-B-B; ACCEPTED via PR #58 docs-only kickoff + PR #59 docs-only closeout) | **ACCEPTED — see Closed phases table above** | Phase 11C.1C-C-B-B-B-C is now `ACCEPTED` (PR #58 docs-only kickoff merged into `main`; this docs-only closeout PR #59 records the operator-VPS W1 / W1+ 2 h, W2 4 h, and W3 24 h upper-bound early-stop paper WS evidence and flips the slice to `ACCEPTED`). The full closeout — including the W1 / W1+ 2 h paper WS run transcript (`duration_seconds=7200.0`, `uptime≈7238s`, `ws_first=true`, `ws_real_transport=true`, `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`, `risk_approved=0`, live trading disabled; 2 h event counts; daily report with `regime_cluster_sample_count=189`, `completed_tail_label_count=0`, status `INSUFFICIENT_SAMPLE` / `INCONCLUSIVE` accepted as valid low-completed-label evidence; 2 h export `data/reports/exports/ama_rt_test_data_1779693570447_export_d.zip`, `manifest_event_count=23001`, `EXPORT_LONG_WINDOW_W1_2H_CHECK=PASS`), the W2 4 h paper WS run transcript (configured `duration_seconds=14400.0`, actual runtime ≈ `14417s`, `iterations=237`, `chains_emitted=704`, `ws_messages_received=1324423`, `radar_candidates_seen=152221`, `liquidation_events_seen=4076`, `risk_rejected=704`; 4 h event counts; `paper_alpha_gate_status=INCONCLUSIVE` `sample_count=164` reason `completed_tail_label_count_below_min=2<10`; `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` `sample_count=164` `completed_tail_label_count=2` reason `completed_tail_label_count_below_min=2<10` — progress from 0 to 2 completed labels still below the 10-label threshold, therefore `INCONCLUSIVE` / `INSUFFICIENT_SAMPLE` remained the correct result; 4 h export `data/reports/exports/ama_rt_test_data_1779708773055_export_8.zip`, `manifest_event_count=61546`, `EXPORT_LONG_WINDOW_W2_4H_CHECK=PASS`), the W3 24 h upper-bound watcher early-stop transcript (`total_elapsed_seconds=900`, `final_tail_labels_since_start=20>=10`, `SAMPLE_SUFFICIENCY_REACHED=final_tail_labels=20>=10`, 24 h full runtime NOT NEEDED, safety summary held end-to-end; watcher logs `data/logs/pr58_w3_24h_ws_2026-05-25T11:56:10Z.log`, `data/logs/pr58_w3_24h_watch_2026-05-25T11:56:10Z.log`), and the W3 export evidence (latest export zip after W3 early-stop `data/reports/exports/ama_rt_test_data_1779712866542_export_6.zip`, generated 2026-05-25 12:41 UTC, `manifest_event_count=62761`, `EXPORT_LONG_WINDOW_W3_EARLY_STOP_CHECK=PASS`; W3 export-range event counts `TAIL_LABEL_ASSIGNED=495`, `LABEL_WINDOW_COMPLETED=495`, `STRATEGY_VALIDATION_SAMPLE_CREATED=397`, `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=4`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=20`, `PAPER_ALPHA_GATE_EVALUATED=5`, `PAPER_ALPHA_RULE_EVALUATED=45`, `PAPER_ALPHA_COHORT_EVALUATED=30`, `PAPER_ALPHA_REPORT_GENERATED=5`; clarification — `final_tail_labels_since_start=20` is the watcher early-stop condition for the 900 s live window, `TAIL_LABEL_ASSIGNED=495` is the 24 h export-range event count, do not confuse the two numbers, both valid, different scopes) — is recorded under "Closed phase: Phase 11C.1C-C-B-B-B-C (ACCEPTED)" and "Phase 11C.1C-C-B-B-B-C acceptance evidence (operator-VPS W1 / W1+ 2 h, W2 4 h, W3 24 h upper-bound early-stop paper WS evidence PASSED)" below. **B-B-B-C acceptance is acceptance of the long-window data collection and sample-sufficiency protocol** — it does **NOT** mean any Regime / Cluster has proven right-tail advantage yet, does **NOT** mean strategy effectiveness is proven, does **NOT** authorise live trading, does **NOT** authorise rule relaxation based on low samples, does **NOT** authorise automatic parameter optimisation, does **NOT** authorise AI Learning, does **NOT** authorise changing the Risk Engine or the Execution FSM, does **NOT** authorise Phase 12. It records that 2 h works, 4 h works, completed labels begin to appear over longer windows, 24 h upper-bound early-stop works, completed-tail-label sufficiency threshold can be reached early, export / replay evidence preserves the results, low-sample states remain conservative, and no trade authority was granted. Long-window protocol outputs remain paper-only / report-only / evidence-only and cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes. Phase 12 remains **FORBIDDEN**. |
| 11C.1C-C-B-B-B-D | Mover Capture Recall & Missed-Tail Coverage Audit v0 / *异动币捕捉召回与漏捕右尾覆盖审计 v0* (paper / report / evidence-only fourth child slice under Phase 11C.1C-C-B-B-B; ACCEPTED via PR #60 docs-only kickoff + PR #61 implementation + PR #62 docs-only closeout) | **ACCEPTED — see Closed phases table above** | Phase 11C.1C-C-B-B-B-D is now `ACCEPTED` (PR #60 docs-only kickoff merged into `main`; PR #61 implementation merged into `main`; this docs-only closeout PR #62 records the operator-VPS 10 min WS paper smoke evidence + daily report Mover Capture section + `MOVER_CAPTURE_*` event counts + Phase 8.5 export bundle + audit result `mover_capture_audit_status=DEGRADED` and flips the slice to `ACCEPTED`). The full closeout — including the verbatim operator-VPS 10 min WS paper smoke transcript (`duration_seconds=600.0`, `dry_run=false`, `ws_first=true`, `ws_real_transport=true`, `ingestion_errors=0`, `risk_approved=0`, `HTTP 429=0`, `HTTP 418=0`, `ws_reconnect_count=0`, `ws_stale_count=0`, `live_trading_enabled=False`, `exchange_live_order_enabled=False`, `llm_enabled=False`, `right_tail_enabled=False`), the Mover Capture Recall & Missed-Tail Coverage Audit daily-report excerpt (`mover_capture_audit_status=DEGRADED`, `top_mover_count=20`, `captured_top_mover_count=4`, `missed_top_mover_count=16`, `capture_recall_rate=0.2000`, `data_unreliable_count=4`, `risk_rejected_mover_count=4`), the two `MOVER_CAPTURE_*` event counts (`MOVER_CAPTURE_RECALL_AUDIT_GENERATED=1`, `MOVER_CAPTURE_PATH_AUDITED=20`), the Phase 8.5 export bundle reference (`data/reports/exports/ama_rt_test_data_1779721036065_export_d.zip`, `manifest_event_count=63968`, `redaction_applied=True`, `events.jsonl` exists, `EXPORT_MOVER_CAPTURE_RECALL_CHECK=PASS`), and the safety-flag invariants — is recorded under "Closed phase: Phase 11C.1C-C-B-B-B-D (ACCEPTED)" and "Phase 11C.1C-C-B-B-B-D acceptance evidence (operator-VPS 10 min WS paper smoke PASSED)" below. `mover_capture_audit_status=DEGRADED` was an **expected and accepted** audit output for this smoke window — `DEGRADED` means the audit layer successfully surfaced coverage weakness / uncertainty. **`DEGRADED` does NOT mean runtime failure.** captured-but-risk-rejected does NOT mean discovery failure; missed-with-unknown reason is a `review` signal, not permission to loosen rules; low capture recall does NOT authorise automatic `symbol_limit` expansion / anomaly threshold changes / candidate pool capacity changes / Regime weight changes / Risk Engine changes; high capture recall would also NOT authorise live trading. Mover Capture Recall & Missed-Tail Coverage Audit v0 outputs remain paper-only / report-only / evidence-only and cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes. Phase 12 remains **FORBIDDEN**. |
| 11C.1C-C-B-B-B-D-A | Historical 60D Mover Coverage Audit v0 (*历史 60 天异动币覆盖回填审计 v0*) | **ACCEPTED / PARTIAL_QUALITY / TOOLCHAIN_CLOSEOUT_ONLY** | D-A audit toolchain is closed out: the 60D Historical Market Store reference data has been generated under `data/historical_market_store/` (D-A.1 *Historical 60D Mover Reference Store Builder v0* is the data-preparation child task under D-A and has completed its toolchain role); `app.adaptive.historical_mover_coverage_backfill` produced D-A audit records against that reference store; the Phase 8.5 export bundle contains the `HISTORICAL_MOVER_COVERAGE_*` events that surface those records; operator manual review = **PARTIAL** (per-symbol verdict recorded under the D-A closeout block below; `RAVEUSDT` and `STOUSDT` recorded as **severe misses**). **D-A acceptance is `TOOLCHAIN_CLOSEOUT_ONLY`** — it accepts that the audit toolchain works, that records can be generated, and that export / replay evidence surface exists. **D-A acceptance does NOT mean** discovery quality is fully acceptable, strategy profitability is proven, direction classification is solved, live trading is allowed, parameter relaxation is allowed, or DeepSeek may make trade decisions. Severe misses trigger **later triage only** (Severe Missed Tail Triage) — never automatic threshold change, never `symbol_limit` expansion, never candidate-pool capacity change, never Regime weight change, never automatic parameter tuning against the D-A reference set ("looking at the answer key" is forbidden). Phase 12 remains **FORBIDDEN**. The Risk Engine remains the single trade-decision gate. See "Closed phase: Phase 11C.1C-C-B-B-B-D-A (ACCEPTED / PARTIAL_QUALITY / TOOLCHAIN_CLOSEOUT_ONLY)" block below for the gate interpretation, manual review verdict, and next-allowed phases. |
| 11C.1C-C-B-B-B-D-A (placeholder; superseded by D-A closeout above) | Historical 60D Mover Coverage Backfill Audit v0 (*历史 60 天异动币覆盖回填审计 v0*; paper / report / evidence-only next child slice opened by Phase 11C.1C-C-B-B-B-D acceptance via PR #62) | **ACCEPTED via D-A closeout (above) — entry kept as audit trail** | Superseded by the D-A `ACCEPTED / PARTIAL_QUALITY / TOOLCHAIN_CLOSEOUT_ONLY` row above. Original placeholder text retained below for audit trail.<br>Phase 11C.1C-C-B-B-B-D is now `ACCEPTED` (PR #60 docs-only kickoff + PR #61 implementation + PR #62 docs-only closeout merged into `main`), so Phase 11C.1C-C-B-B-B-D-A is **NEXT_ALLOWED**. **Not** complete strategy blind testing. **Not** Phase 12 pre-live validation. **Not** Historical 30D+ full blind replay / complete strategy walk-forward validation (that gate remains reserved until small-money live trading prep and is **out of scope** for D-A). Discovery-layer coverage backfill audit only. The parent phase is **not** renamed: Phase 11C.1C-C-B-B-B remains *Strategy Validation Lab (deeper) & richer Cluster Exposure Control follow-up*. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B / 11C.1C-C-B-B-B-C / 11C.1C-C-B-B-B-D forbidden item verbatim. Paper / report / evidence-only; grants no trade authority. Phase 12 remains **FORBIDDEN**. |
| 11C.1C-C-B-B-B-D-A.1 | Historical 60D Mover Reference Store Builder v0 (*历史 60 天异动币参考数据存储构建器 v0*; paper / report / evidence-only data-preparation child task under Phase 11C.1C-C-B-B-B-D-A; v0 builder via PR #65) | **ACCEPTED as the data-preparation child task for D-A; toolchain role complete** | Data-preparation child task under Phase 11C.1C-C-B-B-B-D-A. The builder has produced the 60D Historical Market Store reference data that the existing `app.adaptive.historical_mover_coverage_backfill.load_historical_market_store(root)` consumes, and that reference data has fed the D-A audit whose records / export evidence is what authorises the D-A `TOOLCHAIN_CLOSEOUT_ONLY` acceptance above. PR #65 retains every Phase 11C public allowlist guarantee (`assert_public_endpoint_allowed`; refuses every credential-shaped kwarg + every signed-request query parameter; refuses to start when any `BINANCE_API_KEY` / `BINANCE_API_SECRET` / `BINANCE_KEY` / `BINANCE_SECRET` / `BINANCE_TOKEN` / `BINANCE_PASSPHRASE` is set; `validate_no_lookahead_fields(...)` on every emitted JSONL row). The reference set remains **post-hoc audit reference only** and MUST NEVER drive live radar score, candidate promotion, the Risk Engine, the Execution FSM, `symbol_limit`, candidate-pool capacity, anomaly thresholds, Regime weights, or any other runtime knob. Phase 12 remains **FORBIDDEN**. |
| 11C.1C-C-B-B-B-D-B | Post-Discovery Outcome Metrics v0 (*发现后结果度量 v0*; paper / report / evidence-only fifth child slice under Phase 11C.1C-C-B-B-B; ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT via PR #67 implementation + PR #68 evidence-runner + PR #69 input-adapter fix + this docs-only closeout PR) | **ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT — see Closed phases table above** | Phase 11C.1C-C-B-B-B-D-B is now **`ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT`** (PR #67 implementation merged into `main`; PR #68 evidence-runner merged into `main` with the empty-workspace `INSUFFICIENT_EVIDENCE` marker; PR #69 merged into `main` and fixed the D-B evidence runner input adapter gap; the real VPS D-A export evidence was rerun on `main`; this docs-only closeout PR records the resulting B1 evidence run). The full closeout — including the D-A export input check (`HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED=2`, `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED=300`, `D_A_EXPORT_INPUT_CHECK=PASS`), the B1 evidence run output (`status=EVIDENCE_GENERATED`, `reference_window=60d`, `evaluated_count=300`, `report_generated_count=1`, output dir `data/reports/post_discovery_outcome/pr69_main_real_d_a_evidence`), the outcome label summary (`INSUFFICIENT_PRICE_PATH=195/300`, `MISSED_STRONG_TAIL=105/300`), the detection timing summary (`INSUFFICIENT_DATA=195/300`, `MISSED=105/300`), the notable-symbols block (`RAVEUSDT` and `STOUSDT` remain unresolved as `INSUFFICIENT_PRICE_PATH / INSUFFICIENT_DATA`), the `d_a_backfill_records_missing_using_record_audited_fallback` warning, and the safety-flag invariants — is recorded under "Closed phase: Phase 11C.1C-C-B-B-B-D-B (ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT)" below. **`ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT` is explicitly NOT full quality accepted.** It records that PR #69 fixed the D-B runner input adapter gap, that D-B can now consume real D-A export records, that 300 D-A records were evaluated, that `POST_DISCOVERY_OUTCOME_REPORT_GENERATED` was produced, and that the output is evidence-generated but **not** direction-quality accepted because 195/300 records are `INSUFFICIENT_PRICE_PATH` and 105/300 records are `MISSED_STRONG_TAIL`. **D-B does NOT solve direction. D-B does NOT prove strategy profitability. D-B does NOT authorise auto-tuning. D-B does NOT authorise DeepSeek trade decisions. Phase 12 remains FORBIDDEN.** Next allowed route: B1 closeout accepted as toolchain + partial quality only; then **either** B1.1 *Historical Price Path Completeness / Kline Path Adapter* (recommended) **or** B2 *Severe Missed Tail Triage* (with explicit note that `RAVEUSDT` and `STOUSDT` currently require price-path / data-gap triage). The next allowed route is **NOT** to start DeepSeek directly and is **NOT** to start blind walk-forward directly. Safety flags unchanged across this docs-only closeout. Phase 12 remains **FORBIDDEN**. |
| 11C.1C-C-B-B-B-D-B.1 | Historical Price Path Completeness / Kline Path Adapter v0 (*历史价格路径完整性 / K线路径适配器 v0*; paper / report / evidence-only small follow-up patch under Phase 11C.1C-C-B-B-B-D-B; ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY via PR #71 implementation + this docs-only closeout PR) | **ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY — see Closed phases table above** | Phase 11C.1C-C-B-B-B-D-B.1 is now **`ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY`** (PR #71 implementation merged into `main`; the real D-B evidence runner was rerun on `main` from the operator VPS against the new adapter; this docs-only closeout PR records the resulting B1.1 main-evidence run). The full closeout — including the B1.1 evidence run output (`status=EVIDENCE_GENERATED`, `evaluated_count=300`, `report_generated_count=1`, `event_counts.POST_DISCOVERY_OUTCOME_EVALUATED=300`, `event_counts.POST_DISCOVERY_OUTCOME_REPORT_GENERATED=1`, `kline_interval_used=1d`, output dir `data/reports/post_discovery_outcome/pr71_main_price_path_evidence`), the price-path coverage block (`price_path_records_loaded=17`, `price_path_records_missing=283`), the source summary (`historical_market_store_daily_top_movers=17`, `absent=283`), the missing-reason summary (`no_top_mover_row_covering_first_seen_time=133`, `no_first_seen_time=110`, `insufficient_post_first_seen_points=40`), the notable-symbols block (`RAVEUSDT` and `STOUSDT` remain unresolved with `missing_reason=no_top_mover_row_covering_first_seen_time`), the `B1_1_PRICE_PATH_MAIN_EVIDENCE_CHECK=PASS` confirmation, the `d_a_backfill_records_missing_using_record_audited_fallback` warning, and the safety-flag invariants — is recorded under "Closed phase: Phase 11C.1C-C-B-B-B-D-B.1 (ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY)" below. **`ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY` is explicitly NOT "intraday 1m / 5m kline path solved".** It records that PR #71 shipped the record-level price-path resolution and operator-path Lookahead Guard, that the daily-bucket adapter (`kline_interval_used=1d`) is in place, that 300 records were evaluated and 1 report was generated, and that the local Historical Market Store currently supplies a price path for 17 / 300 records (283 / 300 remain `absent`). **B1.1 does NOT solve the intraday 1m / 5m kline path problem. B1.1 does NOT solve direction. B1.1 does NOT prove strategy profitability. B1.1 does NOT authorise auto-tuning. B1.1 does NOT authorise DeepSeek trade decisions. Phase 12 remains FORBIDDEN.** **Next allowed route: B2 — Severe Missed Tail Triage v0.** B1 is a focused branch off the mainline and is not to be extended indefinitely; B1.1 closeout returns the project to the main route. B2 attributes unresolved severe-miss cases (e.g. `RAVEUSDT`, `STOUSDT`) into a closed bucket (`PRICE_PATH_GAP` / `DATA_UNRELIABLE` / `EVENT_HISTORY_MISSING` / `UNIVERSE_GAP` / `SYMBOL_LIMIT_GAP` / `CANDIDATE_POOL_EVICTED` / `THRESHOLD_TOO_STRICT` / `WS_DATA_GAP` / `REST_REFERENCE_GAP` / `RISK_REJECTED_BUT_MOVED` / `TRUE_DISCOVERY_FAILURE` / `UNKNOWN`); B2 remains forbidden from authorising auto-tuning, threshold change, `symbol_limit` expansion, candidate-pool capacity change, Regime weight change, live trading, DeepSeek trade decision, or Phase 12. A *Historical Kline Store Builder / Intraday Price Path Backfill* ("B1.2") is **NOT** started now; it is recorded as an **optional future data-quality task only**, available only if B2 triage proves severe-miss attribution is blocked by missing intraday price paths, and only with explicit owner approval — it is **not** the recommended next slice, **not** a precondition for B2, and **does not** block B2. Safety flags unchanged across this docs-only closeout. Phase 12 remains **FORBIDDEN**. |
| 11C.1C-C-B-B-B-D-C-A | Reject-to-Outcome Attribution v0 (*拒绝决策到结果归因 v0*; paper / report / evidence-only small slice that closes the candidate-level loop between RISK_REJECTED / no-trade / strategy_mode and the Phase 11C.1C-C-A tail labels + Phase 11C.1C-C-B-B-B-D-B post-discovery outcome labels; **NOT** Severe Missed Tail Triage and **NOT** an indefinite extension of D-B / D-B.1) | **IN_REVIEW (after this implementation PR; not `ACCEPTED` until evidence closeout)** | Phase 11C.1C-C-B-B-B-D-C-A is **`IN_REVIEW`** after the implementation PR. The PR ships `app/adaptive/reject_to_outcome_attribution.py` (paper / pure / deterministic engine that turns one `RejectAttributionInput` per candidate into one closed `RejectAttributionVerdict`-bearing `RejectAttributionRecord`, and aggregates a sequence of records into one `RejectAttributionReport`), four new typed events in `app/core/events.py` (`REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED`, `REJECT_TO_OUTCOME_CASE_ATTRIBUTED`, `FALSE_NEGATIVE_REJECT_DETECTED`, `CORRECT_PROTECTIVE_REJECT_CONFIRMED`), public exports added to `app/adaptive/__init__.py`, the `tests/unit/test_reject_to_outcome_attribution.py` unit-test module covering every brief-mandated acceptance test (stop safety reject remains protective even when MFE is positive, data quality reject `needs_data_recovery=True`, liquidity protective reject, manipulation protective reject, false negative reject `needs_operator_review=True` `needs_rule_review=True` `auto_tuning_allowed=False`, strategy mode false negative, no reject found, insufficient evidence, forbidden fields absent, no forbidden imports of `app.risk` / `app.execution` / `app.exchanges` / `app.llm` / `app.telegram`), and the new phase doc `docs/PHASE_11C_1C_C_B_B_B_D_C_A_REJECT_TO_OUTCOME_ATTRIBUTION.md`. The 12-label closed taxonomy (`CORRECT_PROTECTIVE_REJECT` / `FALSE_NEGATIVE_REJECT` / `DATA_QUALITY_REJECT` / `LIQUIDITY_PROTECTIVE_REJECT` / `MANIPULATION_PROTECTIVE_REJECT` / `STOP_SAFETY_REJECT` / `REBASE_PROTECTIVE_REJECT` / `SYSTEM_SAFETY_REJECT` / `STRATEGY_MODE_FALSE_NEGATIVE` / `NO_REJECT_FOUND` / `INSUFFICIENT_EVIDENCE` / `UNKNOWN`) is descriptive only. Hard-safety priority (`STOP_SAFETY` > `SYSTEM_SAFETY` > `DATA_QUALITY` > `LIQUIDITY` > `MANIPULATION` > `REBASE`) ALWAYS short-circuits the false-negative check — even if a stop-safety / data-quality / liquidity / manipulation / rebase reject was followed by a positive MFE, the verdict stays protective. `auto_tuning_allowed` is hard-pinned to `False` on every emitted record and on every emitted report; a `FALSE_NEGATIVE_REJECT` count `> 0` flips `needs_operator_review_symbols` / `needs_rule_review_symbols` only — it never authorises rule relaxation, never authorises Risk Engine changes, never authorises threshold / `symbol_limit` / candidate-pool / Regime-weight changes. The `assert_payload_has_no_forbidden_keys` recursive guard refuses to emit any payload that contains `buy` / `sell` / `long` / `short` / `direction` / `side` / `entry` / `exit` / `position_size` / `leverage` / `stop` / `stop_loss` / `target` / `take_profit` / `risk_budget` / `order` / `execution_command` / `runtime_config_patch` / `symbol_limit_patch` / `threshold_patch` / `candidate_pool_patch` / `regime_weight_patch`. **NOT live trading. NOT AI Learning. NOT automatic parameter optimisation. NOT reinforcement learning. NOT a strategy implementation. NOT a trading module. NOT a direction call. NOT Severe Missed Tail Triage (B2; later slice). NOT Replay / Reflection extension (later slice). NOT the DeepSeek integration. NOT Phase 12.** The Risk Engine remains the single trade-decision gate. Tests on this PR: `tests/unit/test_reject_to_outcome_attribution.py` 43/43 PASS; full `tests/unit` 2543/2543 PASS. Phase 12 remains **FORBIDDEN**. |
| 11C.1C-C-B-B-B-D-C-B | Severe Missed Tail Triage v0 (*严重漏捕右尾归因 v0*; paper / report / evidence-only B2-B slice that consumes the simplified outputs of Phase 11C.1C-C-B-B-B-D-A / D-B / D-B.1 / D-C-A and assigns a closed `SevereMissRootCause` + closed `SevereMissSeverity` per audited severe miss; **NOT** Replay / Reflection extension and **NOT** an indefinite extension of D-C-A) | **IN_REVIEW (after this implementation PR; not `ACCEPTED` until evidence closeout)** | Phase 11C.1C-C-B-B-B-D-C-B is **`IN_REVIEW`** after the implementation PR. The PR ships `app/adaptive/severe_missed_tail_triage.py` (paper / pure / deterministic engine that turns one `SevereMissTriageInput` per candidate into one closed `SevereMissRootCause` + closed `SevereMissSeverity`-bearing `SevereMissTriageRecord`, and aggregates a sequence of records into one `SevereMissTriageReport`), three new typed events in `app/core/events.py` (`SEVERE_MISSED_TAIL_TRIAGE_GENERATED`, `SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED`, `SEVERE_MISS_ESCALATION_REQUIRED`), public exports added to `app/adaptive/__init__.py`, the `tests/unit/test_severe_missed_tail_triage.py` unit-test module covering every brief-mandated acceptance test (price path missing RAVE / STO style routes to data-recovery without asserting any threshold problem, candidate pool evicted, symbol limit gap with `needs_rule_review=True` and `auto_tuning_allowed=False`, universe gap, risk rejected protective, risk rejected false negative with severity `CRITICAL` and `auto_tuning_allowed=False`, strategy mode false negative, true discovery failure on positive MFE, insufficient evidence refuses to fabricate, forbidden fields absent on every record / report payload, no forbidden imports of `app.risk` / `app.execution` / `app.exchanges` / `app.llm` / `app.telegram`), and the new phase doc `docs/PHASE_11C_1C_C_B_B_B_D_C_B_SEVERE_MISSED_TAIL_TRIAGE.md`. The 19-label closed root-cause taxonomy (`UNIVERSE_GAP` / `SYMBOL_LIMIT_GAP` / `CANDIDATE_POOL_EVICTED` / `THRESHOLD_TOO_STRICT` / `PRE_ANOMALY_WEAK` / `ANOMALY_TOO_LATE` / `WS_DATA_GAP` / `REST_REFERENCE_GAP` / `EVENT_HISTORY_MISSING` / `PRICE_PATH_MISSING` / `PRICE_PATH_INSUFFICIENT` / `NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME` / `RISK_REJECTED_PROTECTIVE` / `RISK_REJECTED_FALSE_NEGATIVE` / `STRATEGY_MODE_FALSE_NEGATIVE` / `LABEL_WINDOW_TOO_SHORT` / `TRUE_DISCOVERY_FAILURE` / `INSUFFICIENT_EVIDENCE` / `UNKNOWN`) and the 6-label closed severity taxonomy (`LOW` / `MEDIUM` / `HIGH` / `SEVERE` / `CRITICAL` / `INSUFFICIENT_EVIDENCE`) are descriptive only. Triage decision-flow priority: insufficient_evidence → universe_gap → symbol_limit_gap → candidate_pool_evicted → price_path_missing → risk_protective → risk_false_negative → strategy_mode_false_negative → true_discovery_failure → unknown. Price-path-missing cases route to `needs_data_recovery=True` only and **MUST NOT** assert any threshold problem. `auto_tuning_allowed` is hard-pinned to `False` on every emitted record and on every emitted report; a `RISK_REJECTED_FALSE_NEGATIVE` verdict (severity `CRITICAL`) flips `needs_operator_review_symbols` / `needs_rule_review_symbols` only — it never authorises rule relaxation, never authorises Risk Engine changes, never authorises threshold / `symbol_limit` / candidate-pool / Regime-weight changes. The `assert_payload_has_no_forbidden_keys` recursive guard refuses to emit any payload that contains `buy` / `sell` / `long` / `short` / `direction` / `side` / `entry` / `exit` / `position_size` / `leverage` / `stop` / `stop_loss` / `target` / `take_profit` / `risk_budget` / `order` / `execution_command` / `runtime_config_patch` / `symbol_limit_patch` / `threshold_patch` / `candidate_pool_patch` / `regime_weight_patch`. **`RAVEUSDT` / `STOUSDT` are currently classified as `NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME` / `MEDIUM` / `needs_data_recovery=True` / `needs_rule_review=False` / `auto_tuning_allowed=False`** — data-gap triage candidates only. The layer **MUST NOT** assert a parameter error from a single coin against the post-hoc D-A reference set; doing so would be "looking at the answer key" — the auto-tuning failure mode the brief explicitly forbids. **NOT live trading. NOT AI Learning. NOT automatic parameter optimisation. NOT reinforcement learning. NOT a strategy implementation. NOT a trading module. NOT a direction call. NOT a Risk Engine change. NOT an Execution FSM change. NOT evidence closeout. NOT Replay / Reflection extension (later slice). NOT the DeepSeek integration. NOT Phase 12.** The Risk Engine remains the single trade-decision gate. Tests on this PR: `tests/unit/test_severe_missed_tail_triage.py` 22/22 PASS; full `tests/unit` 2565/2565 PASS. Phase 12 remains **FORBIDDEN**. |
| 11C.1C-C-B-B-B-D-D | Discovery Quality Scorecard v0 (*发现质量评分板 v0*; paper / report / evidence-only D-D slice that compresses the simplified outputs of Phase 11C.1C-C-B-B-B-D-A / D-B / D-C-A / D-C-B into one descriptive `quality_bucket` per audit window; **NOT** evidence closeout, **NOT** Replay / Reflection extension, **NOT** auto-tuning, **NOT** trade approval) | **IN_REVIEW (after this implementation PR; not `ACCEPTED` until evidence closeout)** | Phase 11C.1C-C-B-B-B-D-D is **`IN_REVIEW`** after the implementation PR. The PR ships `app/adaptive/discovery_quality_scorecard.py` (paper / pure / deterministic engine that turns one `DiscoveryQualityScorecardInput` per audit window into one closed `DiscoveryQualityBucket`-bearing `DiscoveryQualityScorecard`), two new typed events in `app/core/events.py` (`DISCOVERY_QUALITY_SCORECARD_GENERATED`, `DISCOVERY_QUALITY_BUCKET_EVALUATED`), public exports added to `app/adaptive/__init__.py`, the `tests/unit/test_discovery_quality_scorecard.py` unit-test module covering every brief-mandated acceptance test (insufficient evidence when `coverage_total_count=0` or `evidence_refs=()`, GOOD / PARTIAL on clean high-coverage inputs, PARTIAL / WEAK / DEGRADED with `needs_data_recovery=True` on high data-gap or insufficient-price-path rate, WEAK / DEGRADED with `needs_operator_review=True` on high severe-miss rate, `needs_rule_review=True` with `auto_tuning_allowed=False` on high false-negative-reject rate, `root_cause_summary` preserved on output, forbidden fields absent on every record / scorecard payload, no forbidden imports of `app.risk` / `app.execution` / `app.exchanges` / `app.llm` / `app.telegram`), and the new phase doc `docs/PHASE_11C_1C_C_B_B_B_D_D_DISCOVERY_QUALITY_SCORECARD.md`. The 5-label closed quality-bucket taxonomy (`GOOD` / `PARTIAL` / `WEAK` / `DEGRADED` / `INSUFFICIENT_EVIDENCE`) is *discovery-quality* only - **NOT** trade-approval. Bucket decision-flow priority: insufficient_evidence → degraded → weak → partial → good. Per-axis worst-case fold across {coverage / usable, data-gap, severe-miss, late-chase} drives the bucket; any single axis tripping DEGRADED locks the bucket at DEGRADED. `auto_tuning_allowed` is hard-pinned to `False` on every emitted scorecard; a high `false_negative_reject_rate` flips `needs_rule_review=True` only — it never authorises rule relaxation, never authorises Risk Engine changes, never authorises threshold / `symbol_limit` / candidate-pool / Regime-weight changes. The `assert_payload_has_no_forbidden_keys` recursive guard refuses to emit any payload that contains `buy` / `sell` / `long` / `short` / `direction` / `side` / `entry` / `exit` / `position_size` / `leverage` / `stop` / `stop_loss` / `target` / `take_profit` / `risk_budget` / `order` / `execution_command` / `runtime_config_patch` / `symbol_limit_patch` / `threshold_patch` / `candidate_pool_patch` / `regime_weight_patch`. `GOOD` / `PARTIAL` / `WEAK` / `DEGRADED` describe **discovery health** (how often the discovery pipeline saw the moves the historical reference set lists) — they do **NOT** describe strategy quality, risk-decision quality, outcome quality, or trade-approval quality; a `GOOD` bucket does **NOT** mean live trading is approved, and a `DEGRADED` bucket does **NOT** mean live trading is disapproved. The scorecard is intentionally **non-actionable**: it routes operators to the review / data-recovery / rule-review queues but never turns a runtime knob. **NOT live trading. NOT AI Learning. NOT automatic parameter optimisation. NOT reinforcement learning. NOT a strategy implementation. NOT a trading module. NOT a direction call. NOT a Risk Engine change. NOT an Execution FSM change. NOT evidence closeout. NOT Replay / Reflection extension (later slice). NOT the DeepSeek integration. NOT Phase 12.** The Risk Engine remains the single trade-decision gate. Tests on this PR: `tests/unit/test_discovery_quality_scorecard.py` 22/22 PASS; full `tests/unit` 2587/2587 PASS (no regression vs. post-PR-#74 main 2565 baseline; +22 new tests on the new module). Phase 12 remains **FORBIDDEN**. |
| 12         | Real money / live trading                                            | **FORBIDDEN**               | Phase 12 remains **FORBIDDEN** under the Phase 1 safety lock. Spec §41 Go/No-Go checklist is the only path forward, and it has **not** been initiated. NOT permitted from any Phase 11C sub-phase alone (incl. Phase 11C.1C-C-A acceptance, Phase 11C.1C-C-B-A acceptance, Phase 11C.1C-C-B-B-A acceptance, Phase 11C.1C-C-B-B-B-A acceptance, Phase 11C.1C-C-B-B-B-B acceptance, Phase 11C.1C-C-B-B-B-C acceptance, Phase 11C.1C-C-B-B-B-D acceptance via PR #62 (PR #60 docs-only kickoff + PR #61 implementation + PR #62 docs-only closeout), Phase 11C.1C-C-B-B-B, or any other Phase 11C sub-phase). |


### Phase 11B-HF acceptance summary

```
30x dry-run:        30/30 PASS
24h / 2min HF run observed: 648 PASS
go_decision=GO:     648
accepted=True:      648
FAIL:                 0
ERROR:                0
mode:               paper
live_trading:       False
right_tail:         False
llm:                False
exchange_live_orders: False
telegram_outbound_enabled: False
real Binance API:   not connected
real Telegram:      not connected
real DeepSeek:      not connected
```

### Phase 11C.1B acceptance summary

Phase 11C.1B - WebSocket-First All-Market Demon Coin Radar (incl. the
SymbolUniverse / exchangeInfo-as-truth follow-up) - was accepted on
**2026-05-22 (UTC)**. The acceptance evidence is the cloud real-WS
smoke ladder + the persistence + export sanity checks below; the Phase
1 safety lock is unchanged throughout.

**Composing PRs (all merged):**

  - PR #31 - Phase 11C.1A: Binance Public REST Governor / 429
    backoff / 418 shutdown protection.
  - PR #32 - Phase 11C.1B PR-B: WebSocket-first all-market radar;
    real `StdlibPublicWSTransport`; routed `/public/stream` +
    `/market/stream`.
  - PR #33 - Phase 11C.1B follow-up: fix real WS poll zero-timeout
    that was leaving `ws_messages_received=0`.
  - PR #34 - Phase 11C.1B follow-up: `SymbolUniverse` /
    exchangeInfo-as-truth; non-ASCII Binance contract symbols
    admitted; ASCII-only symbol regex banned on the validation
    path; `CandidatePool` now preserves the canonical exchangeInfo
    string verbatim.

**Real-WS smoke ladder (all PASS):**

```
5 min real WS    PASS
  ws_messages_received           = 30317
  ws_chains_emitted              = 12
  ingestion_errors               = 0
  rate_limit_429_count           = 0
  rate_limit_418_count           = 0
  ws_stale_count                 = 0

10 min real WS   PASS
  duration_seconds               = 608
  ws_messages_received           = 59644
  ws_chains_emitted              = 27
  ingestion_errors               = 0
  rate_limit_429_count           = 0
  rate_limit_418_count           = 0
  ws_stale_count                 = 0

1 h real WS (clean)  PASS
  duration_seconds               = 3600
  dry_run                        = false
  ws_real_transport              = true
  ws_messages_received           = 349134
  ws_chains_emitted              = 177
  ws_learning_ready_attached     = 177
  snapshots_emitted              = 177
  ingestion_errors               = 0
  HTTP 429 count                 = 0
  HTTP 418 count                 = 0
  rate_limit_ban                 = False
  ws_reconnect_count             = 0
  ws_staleness_ms_max            = 0
  ws_stale_count                 = 0
  ws_currently_stale             = False
```

**Persistence + export evidence:**

```
events.db
  events_count                   = 56644
  event-aggregation query        = passed without traceback
Phase 8.5 export
  outcome                        = generated successfully
  format                         = zip archive
Demon-coin discovery sanity
  EDENUSDT in radar top-symbols  = yes
  EDENUSDT in top event volume   = yes
```

**Safety flags held throughout the Phase 11C.1B acceptance run:**

```
trading_mode                    = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
real Binance API key            = not loaded
real Binance API secret         = not loaded
real signed endpoint call       = none
real private WebSocket          = none (`/private` refused at allowlist)
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

**Acceptance conditions checked off:**

  - [x] Real WS 5 min run PASS.
  - [x] Real WS 10 min run PASS.
  - [x] Real WS 1 h run PASS.
  - [x] No HTTP 429 across the ladder.
  - [x] No HTTP 418 across the ladder.
  - [x] No `ws_stale` ticks across the ladder.
  - [x] No ingestion errors across the ladder.
  - [x] Phase 8.5 export zip generated successfully.
  - [x] `events.db` readable + event-aggregation query green.
  - [x] Phase 1 safety flags unchanged (`mode=paper`,
    `live_trading=False`, `right_tail=False`, `llm=False`,
    `exchange_live_orders=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`).

## Closed phase: Phase 11C.1C-A (ACCEPTED)

**Phase 11C.1C-A — Adaptive Candidate Regime & Strategy Selector
Contracts (PR #36).** Status: **ACCEPTED (closed 2026-05-22; PR
#36 merged; PR #37 docs closeout).** PR #36 was merged into
`main` and PR #37 closed out the Phase 11C.1C-A docs gate; the
smoke evidence below was accepted. Phase 11C.1C-A shipped the
**paper-only first version** of the data contracts + scoring +
selector + paper-only routing for the Adaptive Candidate Regime &
Strategy Selector. Phase 11C.1C-B is now **ACCEPTED (closed
2026-05-22; PR #38 merged into `main`, mergeCommit `ce4b6de`)** —
see "Closed phase: Phase 11C.1C-B (ACCEPTED)" below; Phase
11C.1C-C-A is **ACCEPTED (closed 2026-05-23; PR #40 merged
into `main`, mergeCommit `75d3c7c`)** — see "Closed phase:
Phase 11C.1C-C-A (ACCEPTED)" above; Phase 11C.1C-C-B is
**NEXT_ALLOWED / NOT_STARTED** (see "Open phase: Phase
11C.1C-C-B (NEXT_ALLOWED / NOT_STARTED)" above); Phase 12
(live trading) remains **FORBIDDEN**.

## Closed phase: Phase 11C.1C-B (ACCEPTED)

**Phase 11C.1C-B — Adaptive Candidate Runtime Calibration & Early
Tail Discovery v0 (PR #38).** Status: **ACCEPTED (closed
2026-05-22; PR #38 merged into `main`, mergeCommit
`ce4b6de`).** PR #38 has been merged into `main`; the 30s
dry-run + 5min real public WS smoke evidence captured below
under "Phase 11C.1C-B acceptance evidence (closeout)" was
accepted. Phase 11C.1C-B shipped the **paper-only first
version** of the Adaptive Candidate Runtime Calibration & Early
Tail Discovery layer on top of the Phase 11C.1C-A contracts.
Phase 11C.1C-C-A is now **ACCEPTED (closed 2026-05-23; PR #40
merged into `main`, mergeCommit `75d3c7c`)** — see "Closed
phase: Phase 11C.1C-C-A (ACCEPTED)" above; Phase 11C.1C-C-B is
**NEXT_ALLOWED / NOT_STARTED** (see "Open phase: Phase
11C.1C-C-B (NEXT_ALLOWED / NOT_STARTED)" above); Phase 12
(live trading) remains **FORBIDDEN**.

> **Phase 11C.1C-B acceptance does NOT authorise live trading.**
> **Phase 11C.1C-B does NOT authorise API keys.**
> **Phase 11C.1C-B does NOT authorise private endpoints.**
> **Phase 11C.1C-B does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-B does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-B does NOT authorise Phase 12.**

> Phase 11C.1C-B is **paper-mode only**. It is **NOT** live
> trading, **NOT** AI Learning, **NOT** complete Strategy
> Validation, **NOT** the full MFE/MAE processor, **NOT** real
> Telegram outbound, **NOT** real Binance trading API. Phase
> 12 (live trading) stays `FORBIDDEN`.

### Phase 11C.1C-B scope (shipped on `main` via PR #38)

  1. **Runtime calibration metrics** attached to every adaptive
     candidate context (Phase 8.5 ``learning_ready`` +
     ``AdaptiveCandidateContext`` + the six adaptive events):
     - ``candidate_first_seen_ts``
     - ``candidate_first_seen_price``
     - ``current_price``
     - ``price_change_since_first_seen``
     - ``quote_volume_acceleration_1m``
     - ``quote_volume_acceleration_5m``
     - ``price_acceleration_1m``
     - ``price_acceleration_5m``
     - ``volume_rank``
     - ``volume_rank_jump_5m``
     - ``distance_to_24h_high``
     - ``distance_from_first_seen``
     - ``freshness_score``
     - ``late_chase_risk``
     - ``early_tail_score``
  2. **Early Tail Discovery v0.** The candidate pool's capacity
     eviction does NOT discard candidates with high
     ``early_tail_score``. The radar surfaces volume-rank
     jumps, quote-volume accelerations, and price accelerations
     on EDEN / ALT / NEAR-style demon-coin starts EARLIER than
     Phase 11C.1B's flat radar score.
  3. **Stage calibration.** ``early`` + high volume expansion +
     high freshness MAY enter ``follow`` / ``pullback`` (paper /
     virtual). ``late`` / ``blowoff`` MUST NEVER upgrade to
     ``follow``. ``manipulation_risk`` high MUST ``reject`` or
     ``observe``.
  4. **Daily-report enhancements.** New fields:
     - ``top_early_tail_candidates``
     - ``top_late_chase_risk_candidates``
     - ``candidate_stage_counts`` (already present from
       Phase 11C.1C-A; carry forward unchanged)
     - ``strategy_mode_counts`` (already present from
       Phase 11C.1C-A; carry forward unchanged)
     - ``opportunity_score_distribution``
     - ``early_tail_score_top_symbols``
     - ``symbols_promoted_before_24h_top_move``
     - EDEN / ALT / NEAR style candidate examples when present
  5. **Event / export compatibility.** Every new field lands in
     ``EventRepository``, the Phase 8.5 learning-ready payload,
     the daily report, and the Phase 8.5 export. Phase 10A
     replay accepts the new fields without failure.

### Phase 11C.1C-B boundary (held throughout the entire scope)

| Invariant                                   | Required value               |
| ------------------------------------------- | ---------------------------- |
| `mode`                                      | `paper`                      |
| `live_trading`                              | `False`                      |
| `right_tail`                                | `False`                      |
| `llm`                                       | `False`                      |
| `exchange_live_orders`                      | `False`                      |
| `telegram_outbound_enabled`                 | `False`                      |
| `binance_private_api_enabled`               | `False`                      |
| `safety.forbid_*` (11 flags)                | `True` for every flag        |
| Binance API key / secret                    | refused at construction      |
| Signed endpoint                             | refused at allowlist check   |
| `listenKey` / user data stream              | refused at WS allowlist + URL parser |
| Private WebSocket / trading WS API          | refused at WS allowlist      |
| Routed-private endpoint (`/private`)        | refused at path-root allowlist |
| DeepSeek trade-decision authority           | NOT permitted                |
| Real Telegram outbound                      | NOT permitted                |
| Strategy mode (incl. follow / pullback)     | paper / virtual; no real-trade authority |
| `early_tail_score`                          | descriptive only; protects from capacity eviction; NOT a real-trade authority |
| AI Learning                                 | NOT implemented              |
| Full MFE/MAE processor                      | NOT implemented (queue is a contract) |
| Phase 12 (live trading)                     | FORBIDDEN                    |

### Phase 11C.1C-B explicitly forbids (inherited from Phase 11C.1C-A)

  - Connecting to the Binance trading API.
  - Reading or storing any Binance API key / API secret /
    `listenKey`.
  - Calling any signed endpoint.
  - Subscribing to any user data stream / private WebSocket /
    trading WebSocket API / account / margin / position / leverage
    / balance / order private WS variant.
  - Connecting to the routed-private endpoint
    `wss://fstream.binance.com/private` (or any `/ws-api` /
    `/ws-fapi` / `/ws-papi` / `/trading-api` / `/userDataStream`
    path-root variant).
  - Connecting to DeepSeek as a trade-decision authority.
  - Connecting to the real Telegram outbound HTTP transport.
  - Promoting `early_tail_score` / `strategy_mode` (paper /
    virtual) to a real-trade authority.
  - Enabling AI Learning that auto-decides trades.
  - Implementing the full MFE/MAE processor (the queue stays a
    descriptive contract; the processor is reserved for Phase
    11C.1C-C).
  - Issuing any real order.
  - Entering Phase 12.

### Phase 11C.1C-B acceptance criteria (all met)

1. `pytest tests/unit/test_phase11c_1c_b_runtime_calibration.py`
   passed (12 brief-mandated tests).
2. `pytest tests/unit -k phase11c_` passed (257) with no
   regression vs. the post-PR-#37 main baseline.
3. The full `tests/` surface continued to pass (2231) with no
   regression vs. the post-PR-#37 main baseline.
4. The 30 s dry-run produced a `runtime_calibration` block (15
   fields) on every adaptive event and an `early_tail_score`
   per ACTIVE candidate; the daily report included the
   `## Phase 11C.1C-B` section.
5. The 5 min real public WS paper run recorded:
   - `dry_run=false`
   - `ws_real_transport=true`
   - `ws_messages_received=30526` (`> 0`)
   - `ws_chains_emitted=12` (`> 0`)
   - `runtime_calibration` block present on every adaptive event
   - `early_tail_score` generated per ACTIVE candidate
   - `top_early_tail_candidates` present in daily report
   - `top_late_chase_risk_candidates` present in daily report
   - `early_tail_score_top_symbols` present in daily report
   - `opportunity_score_distribution` present in daily report
   - `label_queue` remains contract-only
   - `rate_limit_429_count=0`
   - `rate_limit_418_count=0`
   - `rate_limit_ban=False`
   - `ws_stale_count=0`
   - `ingestion_errors=12` (explainable: sandbox-region
     geoblock HTTP 451 on Binance REST; NOT a 429/418/ban; WS
     pump ran cleanly throughout)
6. Every safety flag remained `False` after running the
   runtime-calibration path end-to-end.
7. No live trading.
8. No API key.
9. No private endpoint.
10. Phase 12 stayed `FORBIDDEN`.

## Closed phase: Phase 11C.1C-C-A (ACCEPTED)

**Phase 11C.1C-C-A — MFE / MAE Label Queue Runtime & Tail
Outcome Tracking (PR #40).** Status: **ACCEPTED (closed
2026-05-23; PR #40 merged into `main`, mergeCommit
`75d3c7c`).** PR #40 (branch
`feature/phase-11c1c-c-mfe-mae-label-queue-runtime`, code
commit `4889087`, docs-gate-fix commit `6d6044d`) has merged
into `main`; the operator-VPS 10 min real public WS smoke
evidence captured below under "Phase 11C.1C-C-A acceptance
evidence (closeout)" was accepted. Phase 11C.1C-C-A shipped
the **paper-only first runtime** that consumes the Phase
11C.1C-A `LABEL_QUEUE_ENQUEUED` contract and produces forward
MFE / MAE / `tail_label` outcomes per ACTIVE candidate over
five tracking windows (5m primary, 15m / 30m / 1h / 4h
secondary). It does NOT ship the deeper Strategy Validation
Lab, AI Learning, or Cluster Exposure Control — those are
reserved for Phase 11C.1C-C-B (see "Open phase: Phase
11C.1C-C-B (NEXT_ALLOWED / NOT_STARTED)" below).

> **Phase 11C.1C-C-A acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-A acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-A acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-A acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-A acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-A acceptance does NOT authorise Phase 12.**
> **Phase 11C.1C-C-A acceptance does NOT authorise Phase
> 11C.1C-C-B kickoff bypassing the standard gate.**
> **`mfe_pct` / `mae_pct` / `tail_label` / `strategy_mode` MUST
> NEVER trigger a real trade.**

> Phase 11C.1C-C-A is **paper-mode only**. It is **NOT** live
> trading, **NOT** AI Learning, **NOT** the complete Strategy
> Validation Lab, **NOT** Cluster Exposure Control, **NOT**
> real Telegram outbound, **NOT** real Binance trading API.
> Phase 12 (live trading) remains `FORBIDDEN`.

### Phase 11C.1C-C-A scope (in PR #40)

  1. **`LabelQueueRuntime`** (`app/adaptive/label_runtime.py`)
     consuming the Phase 11C.1C-A `LABEL_QUEUE_ENQUEUED`
     contract and producing forward outcome labels per ACTIVE
     candidate. Pure helpers: `compute_pct_return`,
     `update_window_with_price`, `assign_tail_label_for_window`.
     Schema-versioned via
     `LABEL_TRACKING_SCHEMA_VERSION = "phase_11c_1c_c_a.label_tracking.v1"`.
  2. **Five tracking windows.** 5m primary; 15m / 30m / 1h / 4h
     secondary. Each window tracks MFE (max favourable excursion,
     %), MAE (max adverse excursion, %), `time_to_mfe`,
     `time_to_mae`, R-multiple flags
     (`reached_2r` / `reached_3r` / `reached_5r` / `reached_10r`)
     when `virtual_risk_unit_pct` is configured.
  3. **Tail label taxonomy (rule-based, no LLM).** Per window,
     once observation is complete, one of:
     `strong_tail` / `moderate_tail` / `weak_tail` /
     `fake_breakout` / `late_chase_failure` / `dumped` /
     `stopped_before_tail` / `unresolved` (default). All
     thresholds are configurable (R-multiples, fake_breakout,
     late_chase_failure, dumped, stopped_before_tail,
     missed_tail). `MISSED_TAIL_DETECTED` is emitted as an
     independent flag, not a tail_label value.
  4. **Six new event types** plumbed through `EventRepository`:
     `LABEL_TRACKING_STARTED`, `LABEL_WINDOW_UPDATED`,
     `LABEL_WINDOW_COMPLETED`, `TAIL_LABEL_ASSIGNED`,
     `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED`. Each
     payload carries identity (`tracking_id` / `opportunity_id`
     / `scan_batch_id` / `symbol` / `source_event_id`) plus the
     `schema_version` stamp.
  5. **Idempotency + capacity guards.** `opportunity_id` index
     dedupes; `(symbol, candidate_first_seen_ts,
     first_seen_price)` is the fallback key.
     `max_pending_records` caps the queue. Records past
     `4h + grace_period_seconds` are auto-expired. Missing
     prices return `None`, never raise.
  6. **`WSRadarChainDriver` integration.** After emitting
     `LABEL_QUEUE_ENQUEUED`, the chain captures the `event_id`
     and calls `runtime.observe(adaptive, source_event_id)` so
     that a `LabelTrackingRecord` is created (idempotent) and
     price ticks advance MFE / MAE on every subsequent chain
     pass.
  7. **Daily-report enhancements.** New
     `DailyReportSnapshot` fields surface every brief-mandated
     metric: tracking-started / window-updated / window-completed
     / tail-label / missed-tail / fake-breakout counts;
     pending / completed / expired / unresolved record counts;
     `tail_label_distribution`; `reached_2r` /  `reached_3r` /
     `reached_5r` / `reached_10r` counts; outcomes by
     `early_tail` / `opportunity` / `strategy_mode` /
     `late_chase_risk` bucket; top-MFE / worst-MAE / missed-tail
     / fake-breakout symbol lists.
  8. **`scripts/run_public_market_paper.py`** instantiates
     `LabelQueueRuntime` from settings, ticks it on every loop
     iteration plus on shutdown, and threads
     `label_runtime_metrics` into the daily report.
  9. **Config schema** (`app/config/schema.py` +
     `app/config/defaults.yaml`): new `label_queue_runtime`
     YAML section with every threshold, `max_pending_records`,
     `grace_period_seconds`, and the five tracking windows.

### Phase 11C.1C-C-A boundary (must hold from day one; inherited)

| Invariant                                   | Required value               |
| ------------------------------------------- | ---------------------------- |
| `mode`                                      | `paper`                      |
| `live_trading`                              | `False`                      |
| `right_tail`                                | `False`                      |
| `llm`                                       | `False`                      |
| `exchange_live_orders`                      | `False`                      |
| `telegram_outbound_enabled`                 | `False`                      |
| `binance_private_api_enabled`               | `False`                      |
| `safety.forbid_*` (11 flags)                | `True` for every flag        |
| Binance API key / secret                    | refused at construction      |
| Signed endpoint                             | refused at allowlist check   |
| `listenKey` / user data stream              | refused at WS allowlist + URL parser |
| Private WebSocket / trading WS API          | refused at WS allowlist      |
| Routed-private endpoint (`/private`)        | refused at path-root allowlist |
| DeepSeek trade-decision authority           | NOT permitted                |
| Real Telegram outbound                      | NOT permitted                |
| `mfe_pct` / `mae_pct` / `tail_label` /      | descriptive label only;       |
|   `strategy_mode`                           | MUST NEVER trigger a real     |
|                                             | trade                         |
| AI Learning                                 | NOT implemented              |
| Strategy Validation Lab (full)              | NOT implemented (reserved for Phase 11C.1C-C-B) |
| Cluster Exposure Control                    | NOT implemented (reserved for Phase 11C.1C-C-B) |
| Phase 12 (live trading)                     | FORBIDDEN                    |

### Phase 11C.1C-C-A explicitly forbids (inherited verbatim)

  - Connecting to the Binance trading API.
  - Reading or storing any Binance API key / API secret /
    `listenKey`.
  - Calling any signed endpoint.
  - Subscribing to any user data stream / private WebSocket /
    trading WebSocket API / account / margin / position /
    leverage / balance / order private WS variant.
  - Connecting to the routed-private endpoint
    `wss://fstream.binance.com/private` (or any `/ws-api` /
    `/ws-fapi` / `/ws-papi` / `/trading-api` / `/userDataStream`
    path-root variant).
  - Connecting to DeepSeek as a trade-decision authority.
  - Connecting to the real Telegram outbound HTTP transport.
  - Auto-retrying after a 418, switching endpoints to evade a
    418, rotating source IP to evade a 418.
  - Promoting any paper / virtual signal (`strategy_mode`,
    `early_tail_score`, `mfe_pct`, `mae_pct`, `tail_label`,
    `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED`) to a
    real-trade authority.
  - Implementing the full Strategy Validation Lab.
  - Implementing Cluster Exposure Control.
  - Implementing AI Learning that auto-decides trades.
  - Issuing any real order.
  - Entering Phase 12.

### Phase 11C.1C-C-A acceptance gate (all met)

1. **Targeted test file** —
   `pytest tests/unit/test_phase11c_1c_c_a_label_queue_runtime.py`
   green. **Status: GREEN on PR branch (30 / 30 PASS).**
2. **Phase 11C focus filter** —
   `pytest tests/unit -k phase11c_` green with no regression
   vs. the post-PR-#38 main baseline of 257.
   **Status: GREEN on PR branch (287 / 287 PASS).**
3. **Full pytest** — `pytest tests/` green with no regression
   vs. the post-PR-#38 main baseline of 2231. **Status: GREEN
   on PR branch (2261 / 2261 PASS).**
4. **30 s dry-run smoke** — runner emits
   `LABEL_TRACKING_STARTED` per ACTIVE candidate and the 5m
   primary window stays `pending` (a 30s run is too short for
   the 5m window to complete). **Status: claimed by PR #40
   commit message; the dry-run path is exercised by the
   integration tests inside the targeted test file.**
5. **10 min real public WS smoke from operator VPS** —
   **PASSED.** The operator-VPS 10 min real WS smoke run from
   the `feature/phase-11c1c-c-mfe-mae-label-queue-runtime`
   branch at commit `6d6044d`
   (`python -m scripts.run_public_market_paper --duration
   10min --symbol-limit 5 --ws-first`) recorded, with the
   verbatim runner output captured below under "Phase
   11C.1C-C-A acceptance evidence (closeout)":
   - `duration_seconds=600.0`
   - `dry_run=false`
   - `ws_real_transport=true`
   - `ws_messages_received=56592` (`> 0`)
   - `LABEL_TRACKING_STARTED=19` (runner) / `36` (events.db)
     (`> 0`)
   - `LABEL_WINDOW_UPDATED=38` (runner) / `82` (events.db)
     (`> 0`)
   - `LABEL_WINDOW_COMPLETED=11` (runner) / `20` (events.db)
     (`> 0` — 5m primary window closed inside the 10 min run)
   - `TAIL_LABEL_ASSIGNED=11` (runner) / `20` (events.db)
     (`> 0`)
   - daily report contains `"Phase 11C.1C-C-A MFE / MAE Label
     Queue Runtime & Tail Outcome Tracking"`
   - `pending_label_records=8` /
     `completed_label_records=11` /
     `expired_label_records=0` /
     `unresolved_label_records=0`
   - `rate_limit_429_count=0`
   - `rate_limit_418_count=0`
   - `rate_limit_ban=False`
   - `ws_reconnect_count=0`
   - `ws_stale_count=0`
   - `ws_currently_stale=False`
   - `ingestion_errors=0`
   - `MISSED_TAIL_DETECTED=0` and `FAKE_BREAKOUT_DETECTED=0`
     are valid outcomes for a 10 min window over five seed
     symbols and are not gate-blocking
   - safety flags unchanged (`live_trading_enabled=False`,
     `right_tail_enabled=False`, `llm_enabled=False`,
     `exchange_live_order_enabled=False`,
     `trading_mode_paper=True`; no API key, no signed
     endpoint, no private websocket, no listenKey, no
     DeepSeek trade decision, no real Telegram outbound,
     Phase 12 remains FORBIDDEN)
6. **Safety regression test** — confirms that running the
   label-runtime path end-to-end leaves every Phase 1 safety
   flag at its locked value and that the runtime never emits
   `ORDER_*`, `POSITION_*`, `STOP_*`, or
   `TELEGRAM_MESSAGE_SENT` events. **Status: GREEN on PR
   branch (covered by `test_no_live_trading_flags_unchanged`
   and
   `test_label_runtime_does_not_open_position_or_authorise_trade`).**

The Kiro-side sandbox could not serve as the smoke host for
#5 because the same Binance-region HTTP 451 geoblock that was
recorded under "Phase 11C.1C-B acceptance evidence (closeout)"
still applies to the Kiro sandbox; the operator therefore ran
the 10 min real WS smoke from a Binance-reachable VPS, and
the verbatim transcript is filed below under "Phase
11C.1C-C-A acceptance evidence (closeout)". A sandbox WS
smoke would **not** have been authoritative evidence and was
**not** filed as such. PR #40 merged into `main` on
2026-05-23 (mergeCommit `75d3c7c`); this docs-only closeout
PR therefore flips Phase 11C.1C-C-A to **ACCEPTED**, mirroring
the PR #36 → PR #37 and PR #38 → PR #39 closeout pattern.

## Closed phase: Phase 11C.1C-C-B-A (ACCEPTED)

**Phase 11C.1C-C-B-A — Strategy Validation Lab v0 & Cluster
Exposure Control Contracts (PR #42).** Status: **ACCEPTED
(closed 2026-05-23; PR #42 merged into `main`, mergeCommit
`cc18047`).** PR #42 (branch
`feature/phase-11c1c-c-b-strategy-validation-cluster-control`,
PR-head commit `0bedcce`) merged into `main` on 2026-05-23
(UTC); the operator-VPS 10 min real public WS smoke evidence
captured below under §"Phase 11C.1C-C-B-A acceptance
evidence (operator-VPS 10 min real public WS smoke PASSED)"
was accepted. Phase 11C.1C-C-B-A shipped the **paper /
report-only first slice** of the deeper Phase 11C.1C-C-B
Strategy Validation Lab work on top of the Phase 11C.1C-C-A
`LabelTrackingRecord` outcomes; it ships the data contracts,
pure aggregators, and the `StrategyValidationRuntime` that
emits the seven new typed events, but it does **NOT** ship
the complete Strategy Validation Lab, AI Learning, automatic
parameter optimisation, reinforcement learning, or richer
cluster heuristics — those are reserved for Phase
11C.1C-C-B-B (see §"Open phase: Phase 11C.1C-C-B-B
(NEXT_ALLOWED / NOT_STARTED)" below).

> **Phase 11C.1C-C-B-A is paper / report only.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise Phase 11C.1C-C-B-B kickoff bypassing the standard gate.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise Phase 12.**
> **Validation result / cluster action / `strategy_mode` /
> `suggested_cluster_action` / `mfe_pct` / `mae_pct` /
> `tail_label` cannot trigger real trading** — they are
> descriptive labels only; the Risk Engine remains the
> single trade-decision gate.
> **Phase 12 (live trading) remains FORBIDDEN.**

### Phase 11C.1C-C-B-A scope (PR #42)

  - **Data contracts** (`app/adaptive/strategy_validation.py`):
    `StrategyValidationSample`, `StrategyValidationWindowStats`,
    `StrategyModeValidationStats`,
    `CandidateStageValidationStats`,
    `OpportunityScoreBucketStats`,
    `EarlyTailScoreBucketStats`, `TailLabelDistribution`,
    `ClusterLeaderValidationStats`,
    `ClusterExposureAssessment`, `StrategyValidationReport`.
  - **Pure aggregators**:
    `build_strategy_validation_sample`,
    `aggregate_by_strategy_mode` (with `observe` + `reject`
    cohorts surfaced even when empty),
    `aggregate_by_candidate_stage` (with `dumped` flagged as
    not-a-long-opportunity),
    `aggregate_by_opportunity_score_bucket` (`0-49 / 50-64 /
    65-79 / 80-100`),
    `aggregate_by_early_tail_score_bucket` (`0-24 / 25-49 /
    50-74 / 75-100`),
    `aggregate_tail_label_distribution`,
    `evaluate_cluster_leader_performance`,
    `assess_cluster_exposure`,
    `build_strategy_validation_report`.
  - **Runtime**
    (`app/adaptive/strategy_validation_runtime.py`):
    `StrategyValidationRuntimeConfig` + `StrategyValidationRuntime`
    (idempotent per `opportunity_id`).
  - **Seven new event types**:
    `STRATEGY_VALIDATION_SAMPLE_CREATED`,
    `STRATEGY_VALIDATION_REPORT_GENERATED`,
    `STRATEGY_MODE_VALIDATED`, `CANDIDATE_STAGE_VALIDATED`,
    `SCORE_BUCKET_VALIDATED`, `CLUSTER_EXPOSURE_ASSESSED`,
    `CLUSTER_LEADER_VALIDATED`. Schema version label
    `phase_11c_1c_c_b_a.strategy_validation.v1`.
  - **Wiring**: `WSRadarChainDriver` accepts a new
    `strategy_validation_runtime` kwarg; runner instantiates
    from `settings.strategy_validation` and flushes a final
    report on shutdown.
  - **Daily-report enhancements**: new section
    `## Phase 11C.1C-C-B-A Strategy Validation Lab v0 &
    Cluster Exposure Control Contracts` with paper /
    report-only boundary preamble + every brief-mandated
    metric.
  - **Configuration**: `StrategyValidationSection` Pydantic
    schema; `strategy_validation:` block in
    `app/config/defaults.yaml`; `Settings.strategy_validation`
    accessor.
  - **Cluster actions** (paper / report only):
    `leader_only` / `observe_followers` / `reject_cluster` /
    `no_action`. **MUST NEVER trigger a real trade.**
  - **Tests**: 25/25 PASS (brief-mandated cases); 312/312
    phase11c\_ tests PASS; 2286/2286 full pytest PASS on the PR
    branch (no regression vs. post-PR-#41 main 2261 baseline).

### Phase 11C.1C-C-B-A inherited boundary (held from day one)

| Invariant                                   | Required value               |
| ------------------------------------------- | ---------------------------- |
| `mode`                                      | `paper`                      |
| `live_trading`                              | `False`                      |
| `right_tail`                                | `False`                      |
| `llm`                                       | `False`                      |
| `exchange_live_orders`                      | `False`                      |
| `telegram_outbound_enabled`                 | `False`                      |
| `binance_private_api_enabled`               | `False`                      |
| `safety.forbid_*` (11 flags)                | `True` for every flag        |
| Binance API key / secret                    | refused at construction      |
| Signed endpoint                             | refused at allowlist check   |
| `listenKey` / user data stream              | refused at WS allowlist + URL parser |
| Private WebSocket / trading WS API          | refused at WS allowlist      |
| Routed-private endpoint (`/private`)        | refused at path-root allowlist |
| DeepSeek trade-decision authority           | NOT permitted                |
| Real Telegram outbound                      | NOT permitted                |
| `suggested_cluster_action`                  | paper / report only;          |
|   (`leader_only` / `observe_followers` /    | MUST NEVER trigger a real     |
|   `reject_cluster` / `no_action`)           | trade                         |
| `mfe_pct` / `mae_pct` / `tail_label` /      | descriptive label only;       |
|   `strategy_mode` / `early_tail_score` /    | MUST NEVER trigger a real     |
|   `MISSED_TAIL_DETECTED` /                  | trade                         |
|   `FAKE_BREAKOUT_DETECTED` /                |                               |
|   `STRATEGY_VALIDATION_*` events            |                               |
| AI Learning                                 | NOT implemented              |
| Automatic parameter optimisation            | NOT implemented              |
| Reinforcement learning                      | NOT implemented              |
| Phase 12 (live trading)                     | FORBIDDEN                    |

### Phase 11C.1C-C-B-A explicitly forbidden (inherited verbatim)

  - Connecting to the Binance trading API.
  - Reading or storing any Binance API key / API secret /
    `listenKey`.
  - Calling any signed endpoint.
  - Subscribing to any user data stream / private WebSocket /
    trading WebSocket API / account / margin / position /
    leverage / balance / order private WS variant.
  - Connecting to the routed-private endpoint
    `wss://fstream.binance.com/private` (or any `/ws-api` /
    `/ws-fapi` / `/ws-papi` / `/trading-api` /
    `/userDataStream` path-root variant).
  - Connecting to DeepSeek as a trade-decision authority.
  - Connecting to the real Telegram outbound HTTP transport.
  - Auto-retrying after a 418, switching endpoints to evade a
    418, rotating source IP to evade a 418.
  - Promoting any paper / virtual signal (including the new
    `STRATEGY_VALIDATION_*` events,
    `suggested_cluster_action`, cohort stats, validation
    samples) to a real-trade authority.
  - Implementing AI Learning that auto-decides trades.
  - Implementing automatic parameter optimisation that
    self-modifies the runtime configuration.
  - Implementing reinforcement learning that drives trade
    decisions.
  - Issuing any real order.
  - Entering Phase 12.

### Phase 11C.1C-C-B-A acceptance gate (status: ALL GATES MET; PR #42 merged into `main`)

  - `python -m pytest tests/unit/test_phase11c_1c_c_b_strategy_validation.py -q`
    → 25/25 PASS.
  - `python -m pytest tests/unit/ -k "phase11c_" -q`
    → 312/312 PASS, no regression.
  - `python -m pytest tests/ -q`
    → 2286/2286 PASS, no regression.
  - 30 s dry-run smoke is **contract-only** (smallest Phase
    11C.1C-C-A tracking window is 5 min; cannot complete in
    30 s); the runner emits an empty-but-well-formed
    `STRATEGY_VALIDATION_REPORT_GENERATED` so the daily report
    still renders the new section.
  - **Operator-VPS 10 min real public WS smoke PASSED** on
    2026-05-23 against PR #42 head (commit `0bedcce`;
    branch
    `feature/phase-11c1c-c-b-strategy-validation-cluster-control`).
    The Kiro-side sandbox cannot host this smoke
    (Binance-region HTTP 451 geoblock — historical context;
    same as the Phase 11C.1C-B / Phase 11C.1C-C-A closeouts).
    The verbatim runner output + the authoritative SQLite
    event-count query are filed under §"Phase 11C.1C-C-B-A
    acceptance evidence (operator-VPS 10 min real public WS
    smoke PASSED)" below. PR #42 has merged into `main`
    (mergeCommit `cc18047`); the smoke evidence above was
    accepted; this docs-only closeout PR therefore flips
    Phase 11C.1C-C-B-A to **ACCEPTED** in the closed-phases
    table at the top of this document, mirroring the PR #36
    → PR #37, PR #38 → PR #39, and PR #40 → PR #41 closeout
    pattern.

## Closed phase: Phase 11C.1C-C-B-B-A (ACCEPTED)

**Phase 11C.1C-C-B-B-A — Strategy Validation Dataset Builder
& Quality Gate v0 (PR #44).** Status: **ACCEPTED (closed
2026-05-23; PR #44 merged into `main`, mergeCommit
`3ecfc3b`).** PR #44 (branch
`feature/phase-11c1c-c-b-b-validation-dataset-quality-gate`)
merged into `main` on 2026-05-23 (UTC); the 30 s dry-run
smoke evidence captured below under §"Phase 11C.1C-C-B-B-A
acceptance evidence (closeout)" was accepted. Phase
11C.1C-C-B-B-A shipped the **paper / report-only first
slice** of the deeper Phase 11C.1C-C-B-B work on top of the
Phase 11C.1C-C-B-A `StrategyValidationSample` /
`StrategyValidationReport` / `ClusterExposureAssessment`
artefacts: the dataset record / dataset / summary /
quality-gate v0 contracts + pure builders + the runtime hook
that emits three new typed events
(`STRATEGY_VALIDATION_DATASET_BUILT`,
`STRATEGY_VALIDATION_DATASET_EXPORTED`,
`STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED`). It does **NOT**
ship the complete Strategy Validation Lab follow-up, the
Paper Alpha Gate v0, AI Learning, automatic parameter
optimisation, reinforcement learning, or richer cluster
heuristics — those are reserved for Phase 11C.1C-C-B-B-B (see
§"Open phase: Phase 11C.1C-C-B-B-B (NEXT_ALLOWED /
NOT_STARTED)" below).

> **Phase 11C.1C-C-B-B-A is paper / report only.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-A does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-A does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-A does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-A does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-A does NOT authorise Phase 11C.1C-C-B-B-B kickoff bypassing the standard gate.**
> **Phase 11C.1C-C-B-B-A does NOT authorise Phase 12.**
> **`validation_quality_gate_status` cannot trigger real trading** — it is a descriptive label only (`pass` / `warn` / `fail`); the Risk Engine remains the single trade-decision gate.
> **Validation result / cluster action / `strategy_mode` /
> `suggested_cluster_action` / `mfe_pct` / `mae_pct` /
> `tail_label` cannot trigger real trading** — they are
> descriptive labels only.
> **Phase 12 (live trading) remains FORBIDDEN.**

### Phase 11C.1C-C-B-B-A scope (PR #44)

  - **New module**
    (`app/adaptive/strategy_validation_dataset.py`):
    `StrategyValidationDatasetRecord`,
    `StrategyValidationDatasetSummary`,
    `StrategyValidationDataset`,
    `StrategyValidationQualityGate`,
    `StrategyValidationQualityGateResult`, plus the five pure
    functions
    (`build_validation_dataset_from_samples` /
    `summarize_validation_dataset` /
    `evaluate_validation_dataset_quality` /
    `export_validation_dataset_payload` /
    `load_validation_dataset_payload`).
  - **Three new typed events**
    (`STRATEGY_VALIDATION_DATASET_BUILT`,
    `STRATEGY_VALIDATION_DATASET_EXPORTED`,
    `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED`) emitted by
    `StrategyValidationRuntime` with the brief-mandated
    identity block (`report_id`, `timestamp`,
    `strategy_version`, `scoring_version`,
    `risk_config_version`, `state_machine_version`,
    `schema_version`).
  - **Schema version**:
    `phase_11c_1c_c_b_b_a.strategy_validation_dataset.v1`.
  - **Quality gate v0** is a *sample trust* gate, not a
    *strategy quality* gate: `min_total_samples`,
    `min_completed_tail_labels`,
    `min_strategy_mode_coverage`,
    `min_candidate_stage_coverage`,
    `min_score_bucket_coverage`,
    `require_export_roundtrip`, `require_replay_readable`.
    Output: `gate_status` (`pass` / `warn` / `fail`) +
    diagnostic reasons.
  - **Daily report** carries a new "Phase 11C.1C-C-B-B-A
    Strategy Validation Dataset Builder & Quality Gate v0"
    section with `validation_dataset_records`,
    `validation_dataset_symbols`,
    `validation_dataset_tail_label_counts`,
    `validation_quality_gate_status`,
    `validation_quality_gate_reasons`,
    `validation_dataset_export_ready`,
    `validation_dataset_replay_ready`.
  - **Export / replay**: the Phase 8.5 export bundle's
    `events.jsonl` carries the three new event types
    automatically; the Phase 10A replay engine accepts the
    rows without raising; legacy / future rows missing
    `schema_version` are tolerated.
  - **Runtime config**:
    `app/config/defaults.yaml > strategy_validation` extended
    with `dataset_enabled` and seven `quality_gate_*` fields.
  - **27 brief-mandated tests** in
    `tests/unit/test_phase11c_1c_c_b_b_validation_dataset_quality_gate.py`.
  - **Real WS 10 min smoke is NOT required for this PR** —
    the smallest Phase 11C.1C-C-A primary tracking window is
    5 min and cannot complete in 30 s; reserved for Phase
    11C.1C-C-B-B-B closeout when non-empty datasets are
    first observable end-to-end.

### Phase 11C.1C-C-B-B-A boundary (held end-to-end)

| Invariant                                   | Required value               |
| ------------------------------------------- | ---------------------------- |
| `mode`                                      | `paper`                      |
| `live_trading`                              | `False`                      |
| `right_tail`                                | `False`                      |
| `llm`                                       | `False`                      |
| `exchange_live_orders`                      | `False`                      |
| `telegram_outbound_enabled`                 | `False`                      |
| `binance_private_api_enabled`               | `False`                      |
| `safety.forbid_*` (11 flags)                | `True` for every flag        |
| Binance API key / secret                    | refused at construction      |
| Signed endpoint                             | refused at allowlist check   |
| `listenKey` / user data stream              | refused at WS allowlist + URL parser |
| Private WebSocket / trading WS API          | refused at WS allowlist      |
| Routed-private endpoint (`/private`)        | refused at path-root allowlist |
| DeepSeek trade-decision authority           | NOT permitted                |
| Real Telegram outbound                      | NOT permitted                |
| `validation_quality_gate_status`            | descriptive label only        |
|   (`pass` / `warn` / `fail`)                | (sample-trust gate);          |
|                                             | MUST NEVER trigger a real     |
|                                             | trade                         |
| `STRATEGY_VALIDATION_DATASET_*` events      | descriptive only;             |
|                                             | MUST NEVER trigger a real     |
|                                             | trade                         |
| `suggested_cluster_action`                  | paper / report only;          |
|   (`leader_only` / `observe_followers` /    | MUST NEVER trigger a real     |
|   `reject_cluster` / `no_action`)           | trade                         |
| `mfe_pct` / `mae_pct` / `tail_label` /      | descriptive label only;       |
|   `strategy_mode` / `early_tail_score` /    | MUST NEVER trigger a real     |
|   `MISSED_TAIL_DETECTED` /                  | trade                         |
|   `FAKE_BREAKOUT_DETECTED` /                |                               |
|   `STRATEGY_VALIDATION_*` events            |                               |
| AI Learning                                 | NOT implemented              |
| Automatic parameter optimisation            | NOT implemented              |
| Reinforcement learning                      | NOT implemented              |
| Paper Alpha Gate v0                         | NOT implemented by Phase 11C.1C-C-B-B-A; implemented and **ACCEPTED** as the Phase 11C.1C-C-B-B-B-A child slice (PR #52 merged 2026-05-24, mergeCommit `f8ba315`; closeout via PR #54; see "Closed phase: Phase 11C.1C-C-B-B-B-A (ACCEPTED)" below). Paper / report-only; verdict (`PASS` / `WARN` / `FAIL` / `INCONCLUSIVE`) MUST NEVER trigger a real trade or modify position size, leverage, stop-loss, target price, the Risk Engine, or the Execution FSM. |
| Complete Strategy Validation Lab follow-up  | NOT implemented              |
| Phase 12 (live trading)                     | FORBIDDEN                    |

### Phase 11C.1C-C-B-B-A explicitly forbidden (inherited verbatim)

  - Real trading.
  - Live trading.
  - Connecting to the Binance trading API.
  - Reading or storing any Binance API key / API secret /
    `listenKey`.
  - Calling any signed endpoint.
  - Subscribing to any user data stream / private WebSocket /
    trading WebSocket API / account / margin / position /
    leverage / balance / order private WS variant.
  - Connecting to the routed-private endpoint
    `wss://fstream.binance.com/private` (or any `/ws-api` /
    `/ws-fapi` / `/ws-papi` / `/trading-api` /
    `/userDataStream` path-root variant).
  - Connecting to DeepSeek as a trade-decision authority.
  - Connecting to the real Telegram outbound HTTP transport.
  - Right-tail score in production scope.
  - `validation_quality_gate_status` (or any other paper /
    virtual signal) triggering real downstream execution.
  - AI deciding direction / position size / leverage /
    stop-loss / target / execution.
  - Automatic parameter optimisation.
  - Reinforcement learning.
  - Risk Engine override / bypass.
  - Implementing the complete Strategy Validation Lab
    follow-up.
  - Implementing Paper Alpha Gate v0 (Paper Alpha Gate v0 is
    NOT implemented by Phase 11C.1C-C-B-B-A; it may only
    start as Phase 11C.1C-C-B-B-B-A under the Phase
    11C.1C-C-B-B-B parent after a separate docs-only kickoff
    is reviewed and a separate implementation PR is reviewed
    and merged; Paper Alpha Gate v0 remains paper / report
    only and grants no trade authority).
  - Implementing AI Learning that auto-decides trades.
  - Issuing any real order.
  - Phase 11C.1C-C-B-B-B implementation.
  - Phase 12 / live trading kickoff.

### Phase 11C.1C-C-B-B-A acceptance gate (status: ALL GATES MET; PR #44 merged into `main`)

  - `python -m pytest tests/unit/test_phase11c_1c_c_b_b_validation_dataset_quality_gate.py -q`
    → 27 / 27 PASS.
  - `python -m pytest tests/unit/ -k "phase11c_" -q`
    → 339 / 339 PASS, no regression vs. the post-PR-#43 main
    312 baseline.
  - `python -m pytest tests/ -q`
    → 2313 / 2313 PASS, no regression vs. the post-PR-#43
    main 2286 baseline.
  - 30 s dry-run smoke generated the dataset and the
    quality-gate report at
    `data/reports/phase11c/2026-05-23-phase11c-public-market.md`
    with the new "Phase 11C.1C-C-B-B-A Strategy Validation
    Dataset Builder & Quality Gate v0" section:
    `STRATEGY_VALIDATION_DATASET_BUILT=1`,
    `STRATEGY_VALIDATION_DATASET_EXPORTED=1`,
    `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED=1`,
    `validation_dataset_records=2`,
    `validation_dataset_symbols=BTCUSDT,ETHUSDT`,
    `validation_quality_gate_status=fail` (expected for the
    low-sample 30 s window — exactly the brief's "empty or
    low-sample quality gate report" requirement),
    `validation_dataset_export_ready=True`,
    `validation_dataset_replay_ready=True`.
  - `validation_quality_gate_status=fail` is the **expected**
    output for a 30 s dry-run because the smallest Phase
    11C.1C-C-A primary tracking window is 5 minutes and
    samples that landed in the 30 s window are necessarily
    in-flight / unresolved; the quality gate correctly
    classifies the dataset as too thin for downstream review.
  - `validation_quality_gate_status` is **descriptive only**
    (`pass` / `warn` / `fail`) and **MUST NEVER trigger a
    real trade**; no module reads `gate_status` to drive
    execution. Pinned by every quality-gate test case.
  - **Real WS 10 min smoke deferred to Phase 11C.1C-C-B-B-B
    closeout.** The smallest Phase 11C.1C-C-A primary
    tracking window is 5 minutes and cannot complete in 30 s;
    a real WS 10 min smoke is reserved for the Phase
    11C.1C-C-B-B-B closeout when non-empty datasets are
    first observable end-to-end.
  - Safety boundary held end-to-end: `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `trading_mode_paper=True`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`; no Binance API key,
    no Binance API secret, no signed endpoint, no account /
    order / position / leverage / margin endpoint, no
    private WebSocket, no `listenKey`, no DeepSeek trade
    decision, no real Telegram outbound; Phase 12 remained
    **FORBIDDEN**.

PR #44 merged into `main` on 2026-05-23 (mergeCommit
`3ecfc3b`); this docs-only closeout PR therefore flips Phase
11C.1C-C-B-B-A to **ACCEPTED** in the closed-phases table at
the top of this document, mirroring the PR #36 → PR #37,
PR #38 → PR #39, PR #40 → PR #41, and PR #42 → PR #43
closeout pattern.

## Open phase: Phase 11C.1C-C-B-B-B (NEXT_ALLOWED / NOT_STARTED)

**Phase 11C.1C-C-B-B-B — Strategy Validation Lab (deeper) &
richer Cluster Exposure Control follow-up.** Status:
**NEXT_ALLOWED / NOT_STARTED.** Phase 11C.1C-C-B-B-A (PR #44)
merged into `main` on 2026-05-23 (mergeCommit `3ecfc3b`); the
30 s dry-run smoke evidence (empty / low-sample quality-gate
report with `validation_quality_gate_status=fail`, exactly
the brief's expectation for a low-sample window) was
accepted; Phase 11C.1C-C-B-B-A is therefore **ACCEPTED**, and
Phase 11C.1C-C-B-B-B is now **NEXT_ALLOWED**. No
implementation has started in this repo state; Phase
11C.1C-C-B-B-B will require its own kickoff PR, brief, scope,
boundary table, forbidden list, and acceptance evidence.

> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise Phase
> 11C.1C-C-B-B-B kickoff bypassing the standard gate.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise Phase 12.**
> **`validation_quality_gate_status` cannot trigger real trading** — it is a descriptive label only.
> **Risk Engine remains the single trade-decision gate.**
> **Phase 12 (live trading) remains FORBIDDEN.**

### Phase 11C.1C-C-B-B-B inherited boundary (must hold from day one)

| Invariant                                   | Required value               |
| ------------------------------------------- | ---------------------------- |
| `mode`                                      | `paper`                      |
| `live_trading`                              | `False`                      |
| `right_tail`                                | `False`                      |
| `llm`                                       | `False`                      |
| `exchange_live_orders`                      | `False`                      |
| `telegram_outbound_enabled`                 | `False`                      |
| `binance_private_api_enabled`               | `False`                      |
| `safety.forbid_*` (11 flags)                | `True` for every flag        |
| Binance API key / secret                    | refused at construction      |
| Signed endpoint                             | refused at allowlist check   |
| `listenKey` / user data stream              | refused                      |
| Private WebSocket / trading WS API          | refused                      |
| Routed-private endpoint (`/private`)        | refused                      |
| DeepSeek trade-decision authority           | NOT permitted                |
| Real Telegram outbound                      | NOT permitted                |
| `validation_quality_gate_status`            | descriptive label only;       |
|                                             | MUST NEVER trigger a real     |
|                                             | trade                         |
| AI Learning                                 | NOT permitted                |
| Automatic parameter optimisation            | NOT permitted                |
| Reinforcement learning                      | NOT permitted                |
| Paper Alpha Gate v0                         | NOT implemented by Phase 11C.1C-C-B-B-A. May only start as Phase 11C.1C-C-B-B-B-A (the first child slice under this parent) after this docs-only kickoff and a separate implementation PR. Paper Alpha Gate v0 remains paper-only / report-only and grants no trade authority; verdict (`PASS` / `WARN` / `FAIL` / `INCONCLUSIVE`) MUST NEVER trigger a real trade or modify position size, leverage, stop-loss, target price, the Risk Engine, or the Execution FSM. |
| Phase 12 (live trading)                     | FORBIDDEN                    |

### Phase 11C.1C-C-B-B-B inherited forbidden list (verbatim)

  - live trading
  - Binance API key / secret
  - signed endpoint
  - private websocket / listenKey
  - account / order / position / leverage / margin endpoint
  - DeepSeek trade decision
  - real Telegram outbound
  - Phase 12
  - real orders
  - promoting any paper / virtual signal
    (`validation_quality_gate_status`,
    `STRATEGY_VALIDATION_DATASET_*` events, the seven
    `STRATEGY_VALIDATION_*` events from Phase 11C.1C-C-B-A,
    `strategy_mode`, `early_tail_score`, `mfe_pct`, `mae_pct`,
    `tail_label`, `MISSED_TAIL_DETECTED`,
    `FAKE_BREAKOUT_DETECTED`, validation cohort stats,
    `suggested_cluster_action`) to a real-trade authority
  - automatic parameter optimisation that self-modifies the
    runtime configuration
  - reinforcement learning that drives trade decisions
  - AI Learning that auto-decides trades
  - the Paper Alpha Gate v0 (Paper Alpha Gate v0 is NOT
    implemented by Phase 11C.1C-C-B-B-A; it may only start
    as the Phase 11C.1C-C-B-B-B-A child slice after this
    docs-only kickoff and a separate implementation PR;
    Paper Alpha Gate v0 remains paper-only / report-only and
    grants no trade authority — verdict MUST NEVER trigger a
    real trade or modify position size, leverage, stop-loss,
    target price, the Risk Engine, or the Execution FSM)
  - the complete Strategy Validation Lab follow-up
    (Phase 11C.1C-C-B-B-B will define and ship this in a
    separate kickoff PR)

### Phase 11C.1C-C-B-B-B acceptance gate (placeholder)

The Phase 11C.1C-C-B-B-B kickoff PR will define the detailed
gate criteria (richer cohort comparisons, extended cluster
heuristics, longer-window correlations, dataset-driven
retrospective audits, real public WS 10 min smoke when
non-empty datasets are first observable end-to-end). This
docs-only closeout intentionally records only the inherited
boundary + forbidden list; the substantive gate criteria
will be authored alongside the kickoff PR and reviewed
against the Phase 1 safety lock + the AMOS governance rails
in `docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md`.

## Closed phase: Phase 11C.1C-C-B-B-B-A (ACCEPTED)

**Phase 11C.1C-C-B-B-B-A — Paper Alpha Gate v0 (PR #52
merged into `main` on 2026-05-24, mergeCommit `f8ba315`;
docs-only closeout via PR #54 records the operator-VPS
paper evidence).** Status: **ACCEPTED (closed 2026-05-24).**
Branch (implementation): `feature/phase-11c1c-c-b-b-b-a-paper-alpha-gate-v0`.
PR #51 (the docs-only kickoff) merged into `main` on
2026-05-24 and is the gating predecessor; PR #52 shipped the
runtime implementation and merged into `main` on 2026-05-24
(mergeCommit `f8ba315`); PR #53 was a docs-only status repair
recording the post-PR-#52 `MERGED /
AWAITING_OPERATOR_VPS_EVIDENCE / CLOSEOUT_PENDING` state;
PR #54 (this docs-only closeout) records the operator-VPS
paper evidence and flips the slice to `ACCEPTED`.

This docs-only closeout PR mirrors the PR #36 → PR #37, PR
#38 → PR #39, PR #40 → PR #41, PR #42 → PR #43, and PR #44
→ PR #50 closeout pattern.

This section records the **first child slice** under the
Phase 11C.1C-C-B-B-B parent. The parent phase is **not**
renamed: Phase 11C.1C-C-B-B-B remains *Strategy Validation
Lab (deeper) & richer Cluster Exposure Control follow-up*.
Phase 11C.1C-C-B-B-B-A carves out **only** the *Paper Alpha
Gate v0* — the smallest auditable evidence-gate on top of
the Phase 11C.1C-C-B-B-A artefacts — leaving the remaining
deeper Lab follow-up work for later child slices (B-B-B-B,
B-B-B-C, …) under the same parent.

The full Phase 11C.1C-C-B-B-B-A scope, boundary, forbidden
list, and acceptance evidence are recorded in
`docs/PHASE_11C_1C_C_B_B_B_PAPER_ALPHA_GATE.md`,
`docs/PR52_DESCRIPTION.md`, and
`docs/PR54_DESCRIPTION.md`.

> **Phase 11C.1C-C-B-B-B-A is paper / report / evidence only.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise AI Learning.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise automatic parameter optimisation.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise reinforcement learning.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise the complete Strategy Validation Lab follow-up.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise Phase 12.**
> **Paper Alpha Gate v0 verdict (`PASS` / `WARN` / `FAIL` / `INCONCLUSIVE`) cannot trigger real trading**, modify position size, modify leverage, modify stop-loss, modify target price, modify the Risk Engine, or modify the Execution FSM — it is a descriptive label only.
> **Paper Alpha Gate verdicts remain paper-only / report-only / evidence-only.**
> **Paper Alpha Gate verdicts cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes.**
> **Risk Engine remains the single trade-decision gate.**
> **Execution FSM remains paper today.**
> **Phase 12 (live trading) remains FORBIDDEN.**

### Phase 11C.1C-C-B-B-B-A scope (Paper Alpha Gate v0; docs-only kickoff)

  - **Read-only consumer** of the existing Phase
    11C.1C-C-B-B-A `StrategyValidationDataset` /
    `StrategyValidationQualityGate` /
    `StrategyValidationReport` artefacts (and, transitively,
    the Phase 11C.1C-C-B-A samples and the Phase 11C.1C-C-A
    label runtime outcomes).
  - **Descriptive verdict**: `PASS` / `WARN` / `FAIL` /
    `INCONCLUSIVE`. The verdict is recorded into the daily
    Markdown report and into a typed event so a human
    reviewer can audit the alpha evidence *post-hoc*.
  - **No execution surface reads the verdict.** The verdict
    is not consumed by the Risk Engine, the Execution FSM,
    the Capital Engine, the position sizer, the stop-loss
    placer, the target-price placer, or any other path that
    can trigger or modify a trade.
  - **The detailed runtime contract** (event names, schema
    versions, dataclasses, threshold defaults, daily-report
    fields, replay compatibility, test matrix, dry-run /
    real-WS smoke evidence) **will be authored alongside the
    Phase 11C.1C-C-B-B-B-A implementation PR** — not in this
    docs-only kickoff.

### Phase 11C.1C-C-B-B-B-A boundary (must hold from day one)

| Invariant                                   | Required value                |
| ------------------------------------------- | ----------------------------- |
| `mode`                                      | `paper`                       |
| `live_trading`                              | `False`                       |
| `right_tail`                                | `False`                       |
| `llm`                                       | `False`                       |
| `exchange_live_orders`                      | `False`                       |
| `telegram_outbound_enabled`                 | `False`                       |
| `binance_private_api_enabled`               | `False`                       |
| `safety.forbid_*` (11 flags)                | `True` for every flag         |
| Binance API key / secret                    | refused at construction       |
| Signed endpoint                             | refused at allowlist check    |
| `listenKey` / user data stream              | refused                       |
| Private WebSocket / trading WS API          | refused                       |
| Routed-private endpoint (`/private`)        | refused                       |
| DeepSeek trade-decision authority           | NOT permitted                 |
| Real Telegram outbound                      | NOT permitted                 |
| Paper Alpha Gate v0 verdict                 | descriptive label only        |
|   (`PASS` / `WARN` / `FAIL` /               | (`PASS` / `WARN` / `FAIL` /   |
|   `INCONCLUSIVE`)                           | `INCONCLUSIVE`); MUST NEVER   |
|                                             | trigger a real trade or       |
|                                             | modify position size,         |
|                                             | leverage, stop-loss, target   |
|                                             | price, the Risk Engine, or    |
|                                             | the Execution FSM             |
| `validation_quality_gate_status`            | descriptive label only        |
|   (input to Paper Alpha Gate v0)            | (`pass` / `warn` / `fail`);   |
|                                             | MUST NEVER trigger a real     |
|                                             | trade                         |
| AI Learning                                 | NOT permitted                 |
| Automatic parameter optimisation            | NOT permitted                 |
| Reinforcement learning                      | NOT permitted                 |
| Risk Engine override / bypass               | NOT permitted                 |
| Execution FSM override / bypass             | NOT permitted                 |
| Complete Strategy Validation Lab follow-up  | NOT in Paper Alpha Gate v0    |
|                                             | scope                         |
| Phase 12 (live trading)                     | FORBIDDEN                     |

### Phase 11C.1C-C-B-B-B-A explicitly forbidden (inherited verbatim)

  - Real trading.
  - Live trading.
  - Connecting to the Binance trading API.
  - Reading or storing any Binance API key / API secret /
    `listenKey`.
  - Calling any signed endpoint.
  - Subscribing to any user data stream / private WebSocket /
    trading WebSocket API / account / margin / position /
    leverage / balance / order private WS variant.
  - Connecting to the routed-private endpoint
    `wss://fstream.binance.com/private` (or any `/ws-api` /
    `/ws-fapi` / `/ws-papi` / `/trading-api` /
    `/userDataStream` path-root variant).
  - Connecting to DeepSeek as a trade-decision authority.
  - Connecting to the real Telegram outbound HTTP transport.
  - Right-tail score in production scope.
  - Promoting the Paper Alpha Gate v0 verdict (or any other
    paper / virtual signal) to a real-trade authority.
  - Letting the Paper Alpha Gate v0 verdict modify position
    size, leverage, stop-loss, target price, the Risk
    Engine, or the Execution FSM.
  - AI deciding direction / position size / leverage /
    stop-loss / target / execution.
  - Automatic parameter optimisation that self-modifies the
    runtime configuration.
  - Reinforcement learning that drives trade decisions.
  - AI Learning that auto-decides trades.
  - Risk Engine override / bypass.
  - Execution FSM override / bypass.
  - Phase Gate override / bypass.
  - Issuing any real order.
  - Implementing the complete Strategy Validation Lab
    follow-up (reserved for later child slices under
    Phase 11C.1C-C-B-B-B; out of scope for Phase
    11C.1C-C-B-B-B-A).
  - Phase 12 / live trading kickoff.

### Phase 11C.1C-C-B-B-B-A acceptance gate (post-merge; operator-VPS evidence filed via PR #54)

PR #52 merged the Phase 11C.1C-C-B-B-B-A *implementation*
into `main` on 2026-05-24 (mergeCommit `f8ba315`). The
implementation PR landed the Paper Alpha Gate v0 dataclasses,
the deterministic evaluator, the four new typed events, the
daily-report section, the brief-mandated tests, and the 30 s
dry-run evidence. **The merge did not by itself flip Phase
11C.1C-C-B-B-B-A to `ACCEPTED`.** This docs-only closeout
PR #54 records the **operator-VPS paper evidence** required
to flip Phase 11C.1C-C-B-B-B-A to `ACCEPTED` (mirroring the
PR #36 → PR #37, PR #38 → PR #39, PR #40 → PR #41, PR #42
→ PR #43, and PR #44 → PR #50 docs-only closeout pattern).

The closeout PR was reviewed against:

  - the Phase 1 safety lock (held end-to-end);
  - the AMOS governance rails in
    `docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md`
    (Truth Layer / Reality Check / Anti-overfitting /
    Feedback Isolation / Limited Complexity);
  - the requirement that the verdict is descriptive only and
    grants no trade authority;
  - the requirement that no module reads the verdict to drive
    execution, sizing, leverage, stops, targets, the Risk
    Engine, or the Execution FSM;
  - the requirement that Phase 12 stays `FORBIDDEN`.

This docs-only closeout PR therefore flips Phase
11C.1C-C-B-B-B-A to **ACCEPTED**. Phase 11C.1C-C-B-B-A
remains `ACCEPTED`. Phase 11C.1C-C-B-B-B remains
`NEXT_ALLOWED / NOT_STARTED` (parent; unchanged definition).
Phase 11C.1C-C-B-B-B-B is now `NEXT_ALLOWED / NOT_STARTED`
(the next child slice; cannot start without its own kickoff
PR + brief + scope + boundary table + forbidden list +
acceptance evidence). Phase 12 remains `FORBIDDEN`.

### Phase 11C.1C-C-B-B-B-A acceptance evidence (operator-VPS 10 min WS paper smoke PASSED)

> The transcript below is the verbatim runner / events.db /
> daily-report / export-bundle output captured from the
> operator-VPS 10 min WS paper smoke run against the
> post-PR-#52 `main` branch. The Kiro-side sandbox could
> **not** host the smoke (the same Binance-region HTTP 451
> geoblock recorded under the Phase 11C.1C-B / 11C.1C-C-A /
> 11C.1C-C-B-A closeouts still applies to the Kiro sandbox),
> so the operator ran it from a Binance-reachable VPS and
> back-filled the verbatim transcript below. A sandbox WS
> smoke would **not** have been authoritative evidence and
> was **not** filed as such.
>
> The operator-VPS 10 min WS paper smoke **PASSED** and was
> accepted as Phase 11C.1C-C-B-B-B-A acceptance evidence.

```
branch                          : main (post-PR-#52)
mergeCommit                     : f8ba315
host                            : operator-VPS (Binance-reachable)
mode                            : paper

# WS / runner-level metrics
duration_seconds                = 600.0
uptime                          ≈ 608s
ws_first                        = true
ws_real_transport               = true
ingestion_errors                = 0
HTTP 429 count                  = 0
HTTP 418 count                  = 0

# Phase 11C.1C-C-B-B-B-A new section in daily report
daily report contains           : "## Phase 11C.1C-C-B-B-B-A Paper Alpha Gate v0"
paper_alpha_gate_status         = INCONCLUSIVE
paper_alpha_gate_sample_count   = 20
reason                          : completed_tail_label_count_below_min=0<10

# Paper Alpha Gate event counts (runner snapshot + events.db type-count cross-check, after shutdown flush)
PAPER_ALPHA_GATE_EVALUATED      = 1
PAPER_ALPHA_RULE_EVALUATED      = 9
PAPER_ALPHA_COHORT_EVALUATED    = 6
PAPER_ALPHA_REPORT_GENERATED    = 1

# Phase 8.5 export evidence
export_test_data                = OK
export zip generated            : data/reports/exports/ama_rt_test_data_1779627957433_export_1.zip
manifest_event_count            = 1572
redaction_applied               = True
events.jsonl                    : exists
export contains PAPER_ALPHA_*   = yes
EXPORT_PAPER_ALPHA_GATE_CHECK   = PASS

# Export package files observed
manifest.json                   : present
summary_report.md               : present
events.jsonl                    : present
opportunities.jsonl             : present
signal_snapshots.jsonl          : present
risk_decisions.jsonl            : present
state_transitions.jsonl         : present
capital_events.jsonl            : present
virtual_trade_plans.jsonl       : present

# Safety boundary (Phase 1 lock unchanged end-to-end)
mode                            = paper
exchange_live_order_enabled     = False
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
trading_mode_paper              = True
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
no Binance API key              = confirmed
no Binance API secret           = confirmed
no signed endpoint              = confirmed
no account / order / position / leverage / margin endpoint = confirmed
no private websocket            = confirmed
no listenKey                    = confirmed
no DeepSeek trade decision      = confirmed
no real Telegram outbound       = confirmed
Phase 12                        = FORBIDDEN (gate unchanged)
```

#### Why `paper_alpha_gate_status=INCONCLUSIVE` was the expected and accepted result

`paper_alpha_gate_status=INCONCLUSIVE` is the **expected and
accepted** result for this 10 min smoke window because
`completed_tail_label_count = 0 < 10`. This means the Paper
Alpha Gate **correctly refused to overfit or force a `PASS`**
when completed tail labels were insufficient. The Paper Alpha
Gate's first version is, by design, a *sample-trust* /
*sample-sufficiency* gate rather than a *strategy quality* /
*profitability* oracle. A 10 min run produces zero completed
5 m primary-window tail labels in a quiet market, which means
the gate has no observed forward outcome to compare; the gate
*should* refuse to assert "no alpha" or "yes alpha" in that
condition, and `INCONCLUSIVE` is exactly that explicit refusal.

  - **`INCONCLUSIVE` does NOT mean runtime failure.** The
    gate emitted all four typed events, the daily report
    rendered the new section, and the export bundle
    round-trips cleanly through Phase 8.5 / Phase 10A.
  - **`INCONCLUSIVE` does NOT authorise strategy changes.**
    No threshold / parameter / strategy change is implied by
    or permitted on the basis of this verdict.
  - **`INCONCLUSIVE` does NOT authorise live trading.** The
    Risk Engine remains the single trade-decision gate, and
    no execution surface reads the verdict.
  - **`INCONCLUSIVE` does NOT authorise Phase 12.** Phase
    12 stays `FORBIDDEN` under the Phase 1 safety lock.

#### Acceptance criteria — every gate met

  - PR #52 merged into `main` (mergeCommit `f8ba315`,
    merged 2026-05-24 UTC) ✅
  - operator-VPS 10 min WS paper smoke PASSED:
    `duration_seconds=600.0`, `uptime≈608s`,
    `ws_first=true`, `ws_real_transport=true`,
    `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0` ✅
  - daily report contains
    `"## Phase 11C.1C-C-B-B-B-A Paper Alpha Gate v0"` ✅
  - `paper_alpha_gate_status = INCONCLUSIVE` (expected for
    `completed_tail_label_count=0<10`; accepted as
    sample-insufficient ⇒ auditable INCONCLUSIVE) ✅
  - `paper_alpha_gate_sample_count = 20` ✅
  - `PAPER_ALPHA_GATE_EVALUATED = 1` ✅
  - `PAPER_ALPHA_RULE_EVALUATED = 9` ✅
  - `PAPER_ALPHA_COHORT_EVALUATED = 6` ✅
  - `PAPER_ALPHA_REPORT_GENERATED = 1` ✅
  - `export_test_data = OK`,
    `manifest_event_count = 1572`,
    `redaction_applied = True`,
    `events.jsonl` exists,
    export contains `PAPER_ALPHA_*` events,
    `EXPORT_PAPER_ALPHA_GATE_CHECK = PASS` ✅
  - export package files observed: `manifest.json`,
    `summary_report.md`, `events.jsonl`,
    `opportunities.jsonl`, `signal_snapshots.jsonl`,
    `risk_decisions.jsonl`, `state_transitions.jsonl`,
    `capital_events.jsonl`, `virtual_trade_plans.jsonl` ✅
  - Safety flags unchanged across the operator-VPS run
    (`mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`) ✅
  - No Binance API key, no Binance API secret, no signed
    endpoint, no account / order / position / leverage /
    margin endpoint, no private WebSocket, no `listenKey`,
    no DeepSeek trade decision, no real Telegram
    outbound ✅
  - No `ORDER_*` / `POSITION_*` / `STOP_*` /
    `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` event was
    emitted by the Paper Alpha Gate slice ✅
  - Paper Alpha Gate verdicts remain paper-only /
    report-only / evidence-only and cannot trigger orders,
    leverage, position sizing, stop changes, target
    changes, Risk Engine changes, or Execution FSM
    changes ✅
  - Phase 12 stayed **FORBIDDEN** ✅

## Closed phase: Phase 11C.1C-C-B-B-B-B (ACCEPTED)

**Phase 11C.1C-C-B-B-B-B — Regime & Cluster Cohort Evidence
Pack v0 (*Regime 与 Cluster 分组证据包 v0*; PR #56
implementation + PR #57 docs-only closeout).** Status:
**ACCEPTED (closed 2026-05-24; PR #56 merged into `main` on
2026-05-24, mergeCommit `1a9abe2`; this docs-only closeout
PR #57 records the operator-VPS paper evidence that flips
the slice to `ACCEPTED`).** Second child slice under Phase
11C.1C-C-B-B-B (parent; *Strategy Validation Lab (deeper) &
richer Cluster Exposure Control follow-up*; the parent
phase is **not** renamed by this closeout). Phase
11C.1C-C-B-B-B-A (*Paper Alpha Gate v0*) was previously
**ACCEPTED** (PR #52 merged into `main` on 2026-05-24,
mergeCommit `f8ba315`; closeout via PR #54). PR #55 was
the docs-only kickoff for B-B-B-B; PR #56 shipped the
substantive implementation (paper / report / evidence-only)
and merged into `main` on 2026-05-24; PR #57 (this
docs-only closeout) records the operator-VPS paper
evidence and flips Phase 11C.1C-C-B-B-B-B to `ACCEPTED`,
mirroring the PR #36 → PR #37, PR #38 → PR #39, PR #40 →
PR #41, PR #42 → PR #43, PR #44 → PR #50, and PR #52 → PR
#54 docs-only closeout pattern. Full scope + allowed
outputs + boundary + forbidden list + acceptance evidence
is recorded in
`docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md`.

> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise AI Learning.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise automatic parameter optimisation.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise reinforcement learning.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise the complete Strategy Validation Lab follow-up.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise Phase 11C.1C-C-B-B-B-C kickoff bypassing the standard gate.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise Phase 12.**
> **Regime & Cluster Evidence Pack outputs (per-cohort `status` and top-level `regime_cluster_evidence_status` — `INSUFFICIENT_SAMPLE` / `OBSERVE_ONLY` / `WARNING` / `EVIDENCE_SIGNAL`) cannot trigger real trading**, modify position size, modify leverage, modify stop-loss, modify target price, modify the Risk Engine, or modify the Execution FSM — they are descriptive labels only.
> **Regime & Cluster Evidence Pack outputs remain paper-only / report-only / evidence-only.**
> **Regime & Cluster Evidence Pack outputs cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes.**
> **Risk Engine remains the single trade-decision gate.**
> **Execution FSM remains paper today.**
> **Phase 12 (live trading) remains FORBIDDEN.**

### Phase 11C.1C-C-B-B-B-B acceptance evidence (operator-VPS 10 min WS paper smoke PASSED)

> The transcript below is the verbatim operator-VPS 10 min
> WS paper smoke output captured against the PR #56 branch
> head and accepted as Phase 11C.1C-C-B-B-B-B acceptance
> evidence.

#### Operator-VPS 10 min WS paper smoke

```
duration_seconds                = 600.0
uptime                          ≈ 608s
ws_first                        = true
ws_real_transport               = true
ingestion_errors                = 0
HTTP 429 count                  = 0
HTTP 418 count                  = 0
```

#### Phase 11C.1C-C-B-B-B-B new section in daily report

```
daily report contains           : "## Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort Evidence Pack v0"
regime_cluster_evidence_status  = INSUFFICIENT_SAMPLE
sample_count                    = 14
completed_tail_label_count      = 0
insufficient_sample_reasons     :
  - sample_count_below_min=14<20
  - completed_tail_label_count_below_min=0<10
```

#### Regime & Cluster event counts (runner snapshot + events.db type-count cross-check, after shutdown flush)

```
REGIME_CLUSTER_EVIDENCE_PACK_GENERATED  = 1
REGIME_CLUSTER_COHORT_SUMMARY_GENERATED = 5
```

#### Phase 8.5 export bundle

```
export_test_data                = OK
export zip                      = data/reports/exports/ama_rt_test_data_1779635774169_export_d.zip
manifest_event_count            = 3151
redaction_applied               = True
events.jsonl                    = exists
export contains REGIME_CLUSTER_* events                  = yes
EXPORT_REGIME_CLUSTER_EVIDENCE_CHECK                     = PASS
```

#### Export package files observed

```
manifest.json
summary_report.md
events.jsonl
opportunities.jsonl
signal_snapshots.jsonl
risk_decisions.jsonl
state_transitions.jsonl
capital_events.jsonl
virtual_trade_plans.jsonl
```

#### Why `regime_cluster_evidence_status = INSUFFICIENT_SAMPLE` was the expected and accepted result

`regime_cluster_evidence_status = INSUFFICIENT_SAMPLE` is
an **expected and accepted** result for this smoke window
because `sample_count = 14 < 20` and
`completed_tail_label_count = 0 < 10`. This means the
Regime & Cluster Evidence Pack **correctly refused to
overfit or force a regime / cluster conclusion when
structural samples were insufficient**. The brief's
"forbid loosening rules on low samples" rule was honoured
end-to-end:

  - **`INSUFFICIENT_SAMPLE` does NOT mean runtime failure.**
    The runtime emitted both new event types
    (`REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=1`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=5`), the
    daily report rendered the new section, and the export
    bundle round-trips cleanly through Phase 8.5 / Phase
    10A.
  - **`INSUFFICIENT_SAMPLE` does NOT authorise strategy
    changes.** No threshold / parameter / strategy change
    is implied by or permitted on the basis of this
    status.
  - **`INSUFFICIENT_SAMPLE` does NOT authorise rule
    relaxation.** No cohort minimum, no quality-gate
    threshold, no Paper Alpha Gate threshold, and no
    Risk Engine threshold may be widened in response.
  - **`INSUFFICIENT_SAMPLE` does NOT authorise live
    trading.** The Risk Engine remains the single
    trade-decision gate, and no execution surface reads
    the evidence pack.
  - **`INSUFFICIENT_SAMPLE` does NOT authorise Phase 12.**
    Phase 12 stays `FORBIDDEN` under the Phase 1 safety
    lock.

#### Safety boundary held end-to-end across the operator-VPS run

```
mode                            = paper
live_trading                    = False
exchange_live_orders            = False
right_tail                      = False
llm                             = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
no Binance API key
no Binance API secret
no signed endpoint
no account / order / position / leverage / margin endpoint
no private websocket
no listenKey
no DeepSeek trade decision
no real Telegram outbound
Phase 12                        = FORBIDDEN
```

#### Acceptance conditions checked off

  - [x] Operator-VPS 10 min WS paper smoke PASSED
    (`duration_seconds=600.0`, `uptime≈608s`,
    `ws_first=true`, `ws_real_transport=true`,
    `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`).
  - [x] Daily report contains
    `"## Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort
    Evidence Pack v0"`.
  - [x] `regime_cluster_evidence_status =
    INSUFFICIENT_SAMPLE` is correctly recorded as the
    expected and accepted result for `sample_count=14<20`
    + `completed_tail_label_count=0<10`.
  - [x] `insufficient_sample_reasons` populated with
    explicit reasons (`sample_count_below_min=14<20`,
    `completed_tail_label_count_below_min=0<10`).
  - [x] `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=1` and
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=5`
    cross-checked against the events.db type-count query
    after shutdown flush.
  - [x] Phase 8.5 export zip generated successfully
    (`data/reports/exports/ama_rt_test_data_1779635774169_export_d.zip`,
    `manifest_event_count=3151`,
    `redaction_applied=True`, `events.jsonl` exists,
    export contains `REGIME_CLUSTER_*` events,
    `EXPORT_REGIME_CLUSTER_EVIDENCE_CHECK=PASS`).
  - [x] Export package files observed (`manifest.json`,
    `summary_report.md`, `events.jsonl`,
    `opportunities.jsonl`, `signal_snapshots.jsonl`,
    `risk_decisions.jsonl`, `state_transitions.jsonl`,
    `capital_events.jsonl`,
    `virtual_trade_plans.jsonl`).
  - [x] Phase 1 safety flags unchanged (`mode=paper`,
    `live_trading=False`, `exchange_live_orders=False`,
    `right_tail=False`, `llm=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`).
  - [x] No Binance API key.
  - [x] No Binance API secret.
  - [x] No signed endpoint.
  - [x] No account / order / position / leverage / margin
    endpoint.
  - [x] No private WebSocket.
  - [x] No `listenKey`.
  - [x] No DeepSeek trade decision.
  - [x] No real Telegram outbound.
  - [x] No `ORDER_*` / `POSITION_*` / `STOP_*` /
    `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` event
    emitted by the new pipeline.
  - [x] No evidence-pack output is read by the Risk Engine
    or the Execution FSM.
  - [x] Phase 12 stays `FORBIDDEN`.

## Closed phase: Phase 11C.1C-C-B-B-B-C (ACCEPTED)

**Phase 11C.1C-C-B-B-B-C — Long-Window Cohort Stability &
Sample Sufficiency Protocol v0 / 长窗口 Cohort 稳定性与样
本充足协议 v0.** Status: **ACCEPTED (closed 2026-05-25;
PR #58 docs-only kickoff merged into `main`; this
docs-only closeout PR #59 records the operator-VPS W1 /
W1+ 2 h, W2 4 h, and W3 24 h upper-bound early-stop paper
WS evidence and flips the slice to `ACCEPTED`).** PR #58
defined the slice in place via docs-only kickoff; PR #59
(this PR) records the operator-VPS long-window paper
evidence and flips the slice to `ACCEPTED`. The slice
remains intentionally **docs / evidence-template only**
end-to-end (no future implementation PR will add a new
runtime module under this slice — if such a need emerges
it must be opened as a separate child slice with its own
kickoff / implementation / closeout cycle). Phase
11C.1C-C-B-B-B-D is now **NEXT_ALLOWED / NOT_STARTED**
(placeholder; not yet defined).

The parent phase is **not** renamed: Phase 11C.1C-C-B-B-B
remains *Strategy Validation Lab (deeper) & richer Cluster
Exposure Control follow-up*. Phase 11C.1C-C-B-B-B-C carves
out the third small, auditable slice under that parent —
following B-B-B-A (Paper Alpha Gate v0) and B-B-B-B
(Regime & Cluster Cohort Evidence Pack v0).

> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise Phase 11C.1C-C-B-B-B-C kickoff bypassing the standard gate.**
> **Phase 11C.1C-C-B-B-B-C is paper / report / evidence-only.**
> **Phase 11C.1C-C-B-B-B-C grants no trade authority.**
> **Phase 11C.1C-C-B-B-B-C is NOT a strategy implementation.**
> **Phase 11C.1C-C-B-B-B-C is NOT a trading module.**
> **Phase 11C.1C-C-B-B-B-C is NOT a new runtime module.**
> **Phase 11C.1C-C-B-B-B-C is NOT AI Learning.**
> **Phase 11C.1C-C-B-B-B-C is NOT automatic parameter optimisation.**
> **Phase 11C.1C-C-B-B-B-C is NOT reinforcement learning.**
> **Phase 11C.1C-C-B-B-B-C is NOT the complete Strategy Validation Lab follow-up.**
> **Phase 11C.1C-C-B-B-B-C is NOT Phase 12.**
> **Phase 11C.1C-C-B-B-B-C inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B forbidden item verbatim.**
> **Phase 12 (live trading) remains FORBIDDEN.**

### Why Phase 11C.1C-C-B-B-B-C exists (positioning under AMOS)

PR #56 merged the Regime & Cluster Cohort Evidence Pack v0
implementation into `main` (mergeCommit `1a9abe2`); PR #57
merged the docs-only closeout and flipped Phase
11C.1C-C-B-B-B-B to `ACCEPTED`. The operator-VPS 10 min WS
paper smoke evidence was accepted as well-formed
(`duration_seconds=600.0`, `uptime≈608s`, `ws_first=true`,
`ws_real_transport=true`, `ingestion_errors=0`, `HTTP
429=0`, `HTTP 418=0`), and the runtime / daily-report /
Phase 8.5 export pipeline is functional
(`REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=1`,
`REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=5`, the daily
report contains the new `## Phase 11C.1C-C-B-B-B-B Regime
& Cluster Cohort Evidence Pack v0` section).

**However**: the window's
`regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`,
`sample_count=14<20`, and
`completed_tail_label_count=0<10`. **Runtime / report /
export are correct, but the 10 min observation window is
too short to support a Regime / Cluster right-tail
conclusion.** The right next step is **not** to add a new
strategy module, a new AI authority, or a new optimiser;
the right next step is to **accumulate structural data
across longer paper observation windows** until cohort
samples are large enough for the Regime & Cluster Cohort
Evidence Pack and the Paper Alpha Gate to produce
non-`INSUFFICIENT_SAMPLE` / non-`INCONCLUSIVE` verdicts
that a human can act on as evidence.

This slice codifies that step as a **protocol** — a
long-window paper data-collection cadence, a sample
sufficiency rule, and cohort stability acceptance criteria
— while keeping all of the Phase 1 safety lock invariants
in force.

### Phase 11C.1C-C-B-B-B-C scope (defined by PR #58 docs-only kickoff)

  - **Long-window paper data-collection cadence
    (operator-driven; not auto-scheduled in this PR or
    any future PR under this slice):**
      - **W1 — 1 h paper WS run** (first meaningful sample
        window).
      - **W2 — 4 h paper WS run** (cohort stability check).
      - **W3 — 24 h paper WS run** (day-level structural
        evidence).
      - **W4+ — multi-day paper observation** (reserved;
        out of scope; not implemented in this PR; not
        auto-scheduled in this PR; will require its own
        child slice when formally opened).
  - **Per-window evidence the operator must capture
    verbatim:**
      - `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED` count.
      - `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED` count.
      - `PAPER_ALPHA_GATE_EVALUATED` count.
      - `PAPER_ALPHA_RULE_EVALUATED` count.
      - `PAPER_ALPHA_COHORT_EVALUATED` count.
      - `PAPER_ALPHA_REPORT_GENERATED` count.
      - daily report Regime & Cluster section
        (`## Phase 11C.1C-C-B-B-B-B …` header + body).
      - daily report Paper Alpha Gate section
        (`## Phase 11C.1C-C-B-B-B-A …` header + body).
      - `sample_count`.
      - `completed_tail_label_count`.
      - `regime_cluster_evidence_status` (one of
        `INSUFFICIENT_SAMPLE` / `OBSERVE_ONLY` / `WARNING`
        / `EVIDENCE_SIGNAL`).
      - `paper_alpha_gate_status` (one of `PASS` / `WARN`
        / `FAIL` / `INCONCLUSIVE`).
      - `insufficient_sample_reasons` (verbatim list).
      - Phase 8.5 export package (zip generated, manifest
        event count sane, redaction applied,
        `events.jsonl` exists).
      - export contains `REGIME_CLUSTER_*` events.
      - export contains `PAPER_ALPHA_*` events.
      - safety flags (`mode=paper`, `live_trading=False`,
        `exchange_live_orders=False`, `right_tail=False`,
        `llm=False`, `telegram_outbound_enabled=False`,
        `binance_private_api_enabled=False`, no API key,
        no signed endpoint, no private WS, no `listenKey`,
        no DeepSeek trade decision, no real Telegram
        outbound).
  - **Allowed outputs (docs / evidence templates only):**
      - `long_window_run_plan`.
      - `sample_sufficiency_checklist`.
      - `cohort_stability_checklist`.
      - `operator_vps_evidence_template`.
      - `export_replay_evidence_template`.
      - `closeout_acceptance_template`.

### Phase 11C.1C-C-B-B-B-C sample sufficiency principle (carries forward verbatim)

  - Low samples cannot output strong conclusions.
  - When `completed_tail_label_count` is below the Regime
    & Cluster Evidence Pack v0 minimum, no Regime /
    Cluster right-tail conclusion is permitted from the
    cohort rows.
  - `INSUFFICIENT_SAMPLE` (Regime & Cluster) and
    `INCONCLUSIVE` (Paper Alpha Gate) are **valid
    outputs, not failures**.
  - Cohort signals are only allowed once samples are
    sufficient.
  - Cohort signals — even when sample-sufficient — remain
    paper-only / report-only / evidence-only.
  - Cohort signals cannot trigger trades, modify
    parameters, relax rules, or enter Phase 12.

### Phase 11C.1C-C-B-B-B-C cohort stability principle (carries forward verbatim)

  - A signal that appears in one short window and
    disappears in the next is **not** treated as evidence.
  - A signal that persists across W1 / W2 / W3 *and*
    survives the Phase 8.5 export / Phase 10A replay
    round-trip is treated as a **paper-only candidate
    signal worth continued observation** — but it still
    does not authorise any runtime change, parameter
    optimisation, rule relaxation, or trade.
  - A signal whose direction inverts across consecutive
    windows is logged as `regime_outcome_inverted_warning`
    and is **not** acted on.
  - The protocol is biased toward "do nothing" when
    stability is unclear.

### Phase 11C.1C-C-B-B-B-C boundary (must hold from day one)

| Invariant                                   | Required value               |
| ------------------------------------------- | ---------------------------- |
| `mode`                                      | `paper`                      |
| `live_trading`                              | `False`                      |
| `right_tail`                                | `False`                      |
| `llm`                                       | `False`                      |
| `exchange_live_orders`                      | `False`                      |
| `telegram_outbound_enabled`                 | `False`                      |
| `binance_private_api_enabled`               | `False`                      |
| `safety.forbid_*` (11 flags)                | `True` for every flag        |
| Binance API key / secret                    | refused at construction      |
| Signed endpoint                             | refused at allowlist check   |
| `listenKey` / user data stream              | refused                      |
| Private WebSocket / trading WS API          | refused                      |
| Routed-private endpoint (`/private`)        | refused                      |
| DeepSeek trade-decision authority           | NOT permitted                |
| Real Telegram outbound                      | NOT permitted                |
| Risk Engine authority                       | unchanged; remains the single trade-decision gate |
| Execution FSM authority                     | unchanged                    |
| Position size / leverage / stop-loss / target price | unchanged; cannot be modified by any protocol output |
| `long_window_run_plan`                      | descriptive document only; MUST NEVER trigger a real trade |
| `sample_sufficiency_checklist`              | descriptive document only; MUST NEVER trigger a real trade |
| `cohort_stability_checklist`                | descriptive document only; MUST NEVER trigger a real trade |
| `operator_vps_evidence_template`            | descriptive document only; MUST NEVER trigger a real trade |
| `export_replay_evidence_template`           | descriptive document only; MUST NEVER trigger a real trade |
| `closeout_acceptance_template`              | descriptive document only; MUST NEVER trigger a real trade |
| AI authority                                | NOT permitted to decide direction / position size / leverage / stop / target / execution |
| Automatic parameter optimisation            | NOT permitted                |
| Reinforcement learning                      | NOT permitted                |
| Auto-rule-relaxation on low samples         | NOT permitted                |
| Automatic scheduling of W1 / W2 / W3 / W4+  | NOT permitted                |
| Phase 12 (live trading)                     | FORBIDDEN                    |

### Phase 11C.1C-C-B-B-B-C explicitly forbidden

This slice carries forward every Phase 1 / 11C.1B /
11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A /
11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B
forbidden item verbatim, and adds the following
slice-specific forbidden items:

  - Triggering a real trade.
  - Modifying position size.
  - Modifying leverage.
  - Modifying stop-loss.
  - Modifying target price.
  - Modifying the Risk Engine.
  - Modifying the Execution FSM.
  - Letting AI / LLM decide direction, position size,
    leverage, stop-loss, target price, or execution.
  - Auto-optimising parameters in response to long-window
    cohort signals.
  - Auto-relaxing rules in response to low-sample windows.
  - Auto-scheduling W1 / W2 / W3 / W4+ runs from runtime
    code.
  - Replacing the Regime & Cluster Cohort Evidence Pack v0
    `INSUFFICIENT_SAMPLE` rule with a relaxed rule.
  - Replacing the Paper Alpha Gate v0 `INCONCLUSIVE` rule
    with a relaxed rule.
  - Implementing the Long-Window Cohort Stability & Sample
    Sufficiency Protocol v0 as a new runtime module — the
    slice is intentionally **docs / evidence template
    only** end-to-end.
  - Adding new event types, new Python modules, or new
    runtime behaviour at any point in this slice's
    lifecycle.
  - Modifying `app/`, `scripts/`, `tests/`, `configs/`,
    `risk/`, `execution/`, `llm/`, `telegram/`, or
    `exchange/` at any point in this slice's lifecycle.
  - Modifying configuration schemas, defaults, or YAML.
  - Adding or modifying tests.
  - Running tests as part of this kickoff PR.
  - Flipping any phase's acceptance state.
  - Renaming Phase 11C.1C-C-B-B-B.
  - Phase 11C.1C-C-B-B-B-C *closeout* (out of scope for
    this kickoff PR; will be authored after the operator
    captures W1 / W2 / W3 paper evidence).
  - Phase 12 / live trading kickoff.

### Phase 11C.1C-C-B-B-B-C acceptance gate (placeholder; will be detailed by the closeout PR)

The Phase 11C.1C-C-B-B-B-C closeout PR (a **future**
docs-only PR; not this one) will be authored only **after**
the operator-VPS captures the W1 / W2 / W3 paper evidence
required by this protocol. The placeholders below record
what the gate is **expected** to require:

  - W1 (1 h) operator-VPS evidence captured verbatim
    (event counts, daily-report sections, sufficiency
    fields, export-bundle reference, safety-flag
    invariants).
  - W2 (4 h) operator-VPS evidence captured verbatim
    (same fields).
  - W3 (24 h) operator-VPS evidence captured verbatim
    (same fields).
  - Cohort stability checklist filled in across W1 / W2 /
    W3.
  - Either at least one window with non-`INSUFFICIENT_SAMPLE`
    Regime & Cluster verdict, **or** an explicit recorded
    statement that all three windows returned
    `INSUFFICIENT_SAMPLE` and that further W4+ multi-day
    observation is therefore the next-step
    recommendation. **Either outcome is acceptable.**
  - Phase 8.5 export bundle round-trip evidence captured
    for W1 / W2 / W3.
  - Phase 10A replay engine accepts each window's export
    bundle without raising.
  - Safety flags unchanged across every window
    (`mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance API
    key, no Binance API secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound).
  - No `ORDER_*` / `POSITION_*` / `STOP_*` /
    `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` event
    emitted by any window.
  - No protocol artefact is read by the Risk Engine or
    the Execution FSM.
  - Phase 12 stays `FORBIDDEN`.

### Phase 11C.1C-C-B-B-B-C kickoff acceptance gate (PR #58 docs-only)

  - Docs-only PR. **No code modified** under `app/`,
    `scripts/`, `tests/`, `configs/`, `risk/`,
    `execution/`, `llm/`, `telegram/`, or `exchange/`.
  - **No new Python files.**
  - **No new event types.**
  - **No new tests.**
  - **No tests run.**
  - **No dry-run / smoke required** (no runtime change).
  - **No phase acceptance state flipped.**
  - Safety boundary held end-to-end (`mode=paper`,
    `live_trading=False`, `exchange_live_orders=False`,
    `right_tail=False`, `llm=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance API
    key, no Binance API secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound).
  - **Phase 12 remains FORBIDDEN.**

## Phase 11C.1C-C-B-B-B-C acceptance evidence (operator-VPS W1 / W1+ 2 h, W2 4 h, W3 24 h upper-bound early-stop paper WS evidence PASSED)

> The transcripts below are the verbatim runner /
> events.db / daily-report / Phase 8.5 export output
> captured from the operator-VPS long-window paper WS runs
> against `main` post-PR-#58. The Kiro-side sandbox could
> not host these smokes (Binance-region geoblock —
> historical context, same as the Phase 11C.1C-B / Phase
> 11C.1C-C-A / Phase 11C.1C-C-B-A / Phase 11C.1C-C-B-B-B-A
> / Phase 11C.1C-C-B-B-B-B closeouts; this is **not** the
> current blocker), so the operator ran them from a
> Binance-reachable VPS. **The W1 / W1+ 2 h, W2 4 h, and
> W3 24 h upper-bound early-stop paper WS runs PASSED and
> are accepted as Phase 11C.1C-C-B-B-B-C acceptance
> evidence.**
>
> PR #58 docs-only kickoff merged into `main` on
> 2026-05-25; this docs-only closeout PR #59 records the
> long-window paper evidence and flips Phase
> 11C.1C-C-B-B-B-C to **ACCEPTED**. This docs-only
> closeout PR mirrors the PR #36 → PR #37, PR #38 → PR
> #39, PR #40 → PR #41, PR #42 → PR #43, PR #44 → PR #50,
> PR #52 → PR #54, and PR #56 → PR #57 closeout pattern.

### W1 / W1+ — 2 h Long-Window Paper WS Run (PASS)

```
host                            : operator VPS (Binance-reachable region)
mode                            : paper
command                         : python -m scripts.run_public_market_paper \
                                    --duration 2h --ws-first

# WS / runner-level metrics
duration_seconds                = 7200.0
uptime                          ≈ 7238s
ws_first                        = true
ws_real_transport               = true
ingestion_errors                = 0
HTTP 429 count                  = 0
HTTP 418 count                  = 0
risk_approved                   = 0
live_trading                    = disabled

# 2 h event counts (runner snapshot + events.db type-count cross-check)
PAPER_ALPHA_COHORT_EVALUATED                 = 18
PAPER_ALPHA_GATE_EVALUATED                   = 3
PAPER_ALPHA_REPORT_GENERATED                 = 3
PAPER_ALPHA_RULE_EVALUATED                   = 27
REGIME_CLUSTER_COHORT_SUMMARY_GENERATED      = 10
REGIME_CLUSTER_EVIDENCE_PACK_GENERATED       = 2

# 2 h Daily report content
daily_report_section_present (Paper Alpha Gate)                   = "## Phase 11C.1C-C-B-B-B-A Paper Alpha Gate v0"
daily_report_section_present (Regime & Cluster Evidence Pack)     = "## Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort Evidence Pack v0"
regime_cluster_sample_count                  = 189
regime_cluster_completed_tail_label_count    = 0
regime_cluster_evidence_status               = INSUFFICIENT_SAMPLE
paper_alpha_gate_status                      = INCONCLUSIVE
insufficient_sample_reasons                  = [completed_tail_label_count_below_min=0<10]

# 2 h Phase 8.5 export evidence
export_test_data                = OK
export zip path                 = data/reports/exports/ama_rt_test_data_1779693570447_export_d.zip
manifest_event_count            = 23001
redaction_applied               = True
events.jsonl exists             = True
EXPORT_LONG_WINDOW_W1_2H_CHECK  = PASS

# Safety boundary (Phase 1 lock unchanged end-to-end)
mode                            = paper
live_trading                    = False
exchange_live_orders            = False
right_tail                      = False
llm                             = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
no Binance API key
no Binance API secret
no signed endpoint
no account / order / position / leverage / margin endpoint
no private websocket
no listenKey
no DeepSeek trade decision
no real Telegram outbound
Phase 12                        = FORBIDDEN (gate unchanged)
```

The W1 / W1+ window's
`regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` and
`paper_alpha_gate_status=INCONCLUSIVE` are **expected and
accepted** results because
`completed_tail_label_count=0<10`. The Regime & Cluster
Cohort Evidence Pack v0 and the Paper Alpha Gate v0
correctly refused to overfit or force a regime / cluster
conclusion on a low-completed-tail-label window. **This is
valid low-completed-label evidence, not runtime failure,
and it does NOT authorise rule relaxation.**

### W2 — 4 h Long-Window Paper WS Run (PASS)

```
host                            : operator VPS (Binance-reachable region)
mode                            : paper
command                         : python -m scripts.run_public_market_paper \
                                    --duration 4h --ws-first

# WS / runner-level metrics
configured duration_seconds     = 14400.0
actual runtime                  ≈ 14417s
iterations                      = 237
chains_emitted                  = 704
ws_chains_emitted               = 704
ws_real_transport               = True
ws_reconnect_count              = 0
ws_staleness_ms_max             = 0
ws_stale_count                  = 0
ingestion_errors                = 0
public_endpoint_calls           = 4226
ws_messages_received            = 1324423
radar_candidates_seen           = 152221
candidate_pool_size_max         = 20
liquidation_events_seen         = 4076
rate_limit_429_count            = 0
rate_limit_418_count            = 0
rate_limit_ban                  = False
risk_approved                   = 0
risk_rejected                   = 704

# 4 h event counts (runner snapshot + events.db type-count cross-check)
PAPER_ALPHA_COHORT_EVALUATED                 = 24
PAPER_ALPHA_GATE_EVALUATED                   = 4
PAPER_ALPHA_REPORT_GENERATED                 = 4
PAPER_ALPHA_RULE_EVALUATED                   = 36
REGIME_CLUSTER_COHORT_SUMMARY_GENERATED      = 15
REGIME_CLUSTER_EVIDENCE_PACK_GENERATED       = 3

# 4 h Daily report content
paper_alpha_gate_status                      = INCONCLUSIVE
paper_alpha_gate_sample_count                = 164
paper_alpha_gate_reason                      = completed_tail_label_count_below_min=2<10
regime_cluster_evidence_status               = INSUFFICIENT_SAMPLE
regime_cluster_sample_count                  = 164
regime_cluster_completed_tail_label_count    = 2
regime_cluster_reason                        = completed_tail_label_count_below_min=2<10

# 4 h Phase 8.5 export evidence
export_test_data                = OK
export zip path                 = data/reports/exports/ama_rt_test_data_1779708773055_export_8.zip
manifest_event_count            = 61546
redaction_applied               = True
events.jsonl exists             = True
EXPORT_LONG_WINDOW_W2_4H_CHECK  = PASS

# Safety boundary (Phase 1 lock unchanged end-to-end)
mode                            = paper
live_trading                    = False
exchange_live_orders            = False
right_tail                      = False
llm                             = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
no Binance API key
no Binance API secret
no signed endpoint
no account / order / position / leverage / margin endpoint
no private websocket
no listenKey
no DeepSeek trade decision
no real Telegram outbound
Phase 12                        = FORBIDDEN (gate unchanged)
```

**Important interpretation of W2.** The 4 h window showed
**progress** from `completed_tail_label_count=0` (W1 / W1+
2 h) to `completed_tail_label_count=2` (W2 4 h) — completed
tail labels are starting to appear as the observation
window lengthens, exactly as the protocol predicted.
However, `2` is still **below the 10 completed-tail-label
sufficiency threshold**, so
`regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` and
`paper_alpha_gate_status=INCONCLUSIVE` remained the
**correct** results for W2. **This does NOT indicate
runtime failure.** **This does NOT authorise rule
relaxation** — the protocol's central rule is that low
samples cannot output strong conclusions, and the rule
holds verbatim. The right next step was therefore to
extend the observation window further (W3 24 h
upper-bound), which we did.

### W3 — 24 h upper-bound run with watcher early-stop (PASS)

```
host                            : operator VPS (Binance-reachable region)
mode                            : paper
command                         : python -m scripts.run_public_market_paper \
                                    --duration 24h --ws-first
watcher                         : early-stop on
                                  final_tail_labels_since_start>=10

# Early-stop outcome
total_elapsed_seconds                        = 900
final_tail_labels_since_start                = 20
SAMPLE_SUFFICIENCY_REACHED                   = final_tail_labels=20>=10
24 h full runtime                            = NOT NEEDED (early stop triggered)

# Runtime safety summary (held end-to-end across the 900 s window)
mode                            = paper
live_trading                    = False
right_tail                      = False
llm                             = False
exchange_live_orders            = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
risk_approved                   = 0
ingestion_errors                = 0
rate_limit_429_count            = 0
rate_limit_418_count            = 0
ws_real_transport               = True

# Watcher logs (filenames as recorded by the operator)
run_log                         = data/logs/pr58_w3_24h_ws_2026-05-25T11:56:10Z.log
watch_log                       = data/logs/pr58_w3_24h_watch_2026-05-25T11:56:10Z.log
```

**Interpretation of W3.** W3 was started as a **24 h
upper-bound** paper WS run. A watcher monitored
`final_tail_labels_since_start` and stopped the run early
once tail-label sufficiency was reached
(`final_tail_labels_since_start=20>=10`). The run
terminated cleanly at `total_elapsed_seconds=900`; the
full 24 h runtime was **not needed**. **This proves the
B-B-B-C sample sufficiency protocol can save runtime while
preserving evidence:** the protocol does not require the
operator to run a fixed 24 h window when sufficiency has
already been demonstrated within a shorter window — it
allows early-stop on the existing Regime & Cluster Cohort
Evidence Pack v0 / Paper Alpha Gate v0 sufficiency
thresholds.

### W3 Phase 8.5 export evidence (PASS)

```
# Latest export zip generated after W3 early-stop
export_test_data                = OK
export zip path                 = data/reports/exports/ama_rt_test_data_1779712866542_export_6.zip
generated at                    = 2026-05-25 12:41 UTC
manifest_event_count            = 62761
redaction_applied               = True
events.jsonl exists             = True
EXPORT_LONG_WINDOW_W3_EARLY_STOP_CHECK = PASS

# W3 export event counts (export-range, full 24 h export window)
TAIL_LABEL_ASSIGNED                          = 495
LABEL_WINDOW_COMPLETED                       = 495
STRATEGY_VALIDATION_SAMPLE_CREATED           = 397
REGIME_CLUSTER_EVIDENCE_PACK_GENERATED       = 4
REGIME_CLUSTER_COHORT_SUMMARY_GENERATED      = 20
PAPER_ALPHA_GATE_EVALUATED                   = 5
PAPER_ALPHA_RULE_EVALUATED                   = 45
PAPER_ALPHA_COHORT_EVALUATED                 = 30
PAPER_ALPHA_REPORT_GENERATED                 = 5
```

> **Clarification on the two W3 numbers.**
> `final_tail_labels_since_start=20` is the **watcher
> early-stop condition** for this W3 run — it counts the
> tail labels that completed during the **900 s** window
> the operator actually ran, and it is the threshold
> against which the watcher decided to stop early.
> `TAIL_LABEL_ASSIGNED=495` is the **24 h export-range
> event count** captured from the Phase 8.5 export bundle
> — it counts tail labels assigned across the **full 24 h
> export window** (which includes pre-existing
> events.db-resident tail-label records that the export
> range covers, not just the 900 s that the runner was
> live for). **Do not confuse the two numbers.** Both are
> valid; they represent different scopes (live-run window
> vs. export-range window).

### Acceptance criteria — every gate met

  - W1 / W1+ 2 h paper WS run PASS ✅
  - W2 4 h paper WS run PASS ✅
  - W3 24 h upper-bound run PASS ✅ with watcher
    early-stop at `total_elapsed_seconds=900`,
    `final_tail_labels_since_start=20>=10`,
    `SAMPLE_SUFFICIENCY_REACHED=final_tail_labels=20>=10`,
    24 h full runtime NOT NEEDED.
  - 2 h event counts PASS ✅
    (`PAPER_ALPHA_COHORT_EVALUATED=18`,
    `PAPER_ALPHA_GATE_EVALUATED=3`,
    `PAPER_ALPHA_REPORT_GENERATED=3`,
    `PAPER_ALPHA_RULE_EVALUATED=27`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=10`,
    `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=2`).
  - 4 h event counts PASS ✅
    (`PAPER_ALPHA_COHORT_EVALUATED=24`,
    `PAPER_ALPHA_GATE_EVALUATED=4`,
    `PAPER_ALPHA_REPORT_GENERATED=4`,
    `PAPER_ALPHA_RULE_EVALUATED=36`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=15`,
    `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=3`).
  - W3 export event counts PASS ✅
    (`TAIL_LABEL_ASSIGNED=495`,
    `LABEL_WINDOW_COMPLETED=495`,
    `STRATEGY_VALIDATION_SAMPLE_CREATED=397`,
    `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=4`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=20`,
    `PAPER_ALPHA_GATE_EVALUATED=5`,
    `PAPER_ALPHA_RULE_EVALUATED=45`,
    `PAPER_ALPHA_COHORT_EVALUATED=30`,
    `PAPER_ALPHA_REPORT_GENERATED=5`).
  - W1 / W1+ 2 h sufficiency fields PASS ✅
    (`regime_cluster_sample_count=189`,
    `regime_cluster_completed_tail_label_count=0`,
    status remained `INSUFFICIENT_SAMPLE` /
    `INCONCLUSIVE` because
    `completed_tail_label_count=0<10` — accepted as valid
    low-completed-label evidence, not runtime failure).
  - W2 4 h sufficiency fields PASS ✅
    (`paper_alpha_gate_status=INCONCLUSIVE`,
    `paper_alpha_gate_sample_count=164`, reason
    `completed_tail_label_count_below_min=2<10`;
    `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`,
    `regime_cluster_sample_count=164`,
    `regime_cluster_completed_tail_label_count=2`,
    reason `completed_tail_label_count_below_min=2<10` —
    progress from 0 to 2 completed labels, still below
    the 10-label threshold, therefore `INCONCLUSIVE` /
    `INSUFFICIENT_SAMPLE` remained the correct result;
    does NOT indicate runtime failure; does NOT authorise
    rule relaxation).
  - W1 / W1+ 2 h export PASS ✅
    (`data/reports/exports/ama_rt_test_data_1779693570447_export_d.zip`,
    `manifest_event_count=23001`,
    `EXPORT_LONG_WINDOW_W1_2H_CHECK=PASS`).
  - W2 4 h export PASS ✅
    (`data/reports/exports/ama_rt_test_data_1779708773055_export_8.zip`,
    `manifest_event_count=61546`,
    `EXPORT_LONG_WINDOW_W2_4H_CHECK=PASS`).
  - W3 24 h export PASS ✅ (latest export zip after W3
    early-stop
    `data/reports/exports/ama_rt_test_data_1779712866542_export_6.zip`,
    generated 2026-05-25 12:41 UTC,
    `manifest_event_count=62761`,
    `redaction_applied=True`, `events.jsonl` exists,
    `EXPORT_LONG_WINDOW_W3_EARLY_STOP_CHECK=PASS`).
  - Safety boundary held end-to-end across W1 / W1+ 2 h,
    W2 4 h, and W3 24 h upper-bound early-stop
    (`mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance API
    key, no Binance API secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound)
    ✅.
  - No `ORDER_*` / `POSITION_*` / `STOP_*` /
    `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` event
    emitted by any of W1 / W1+ / W2 / W3 ✅.
  - No protocol artefact is read by the Risk Engine or the
    Execution FSM ✅.
  - Phase 12 stayed **FORBIDDEN** ✅.

Phase 1 safety lock held end-to-end across W1 / W1+ 2 h,
W2 4 h, and W3 24 h upper-bound early-stop; no real order,
no signed endpoint call, no private WebSocket connection,
no listenKey allocation, no DeepSeek trade decision, no
real Telegram outbound, and Phase 12 stayed **FORBIDDEN**.

### Closeout interpretation

**B-B-B-C acceptance is acceptance of the long-window data
collection and sample-sufficiency protocol.** It does
**NOT** mean any Regime / Cluster has proven right-tail
advantage yet. It does **NOT** mean strategy effectiveness
is proven. It does **NOT** authorise live trading, API
keys, private endpoints, DeepSeek trade decisions, real
Telegram outbound, AI Learning, automatic parameter
optimisation, reinforcement learning, rule relaxation
based on low samples, Risk Engine changes, Execution FSM
changes, or Phase 12. It records only that:

  - 2 h paper WS run works.
  - 4 h paper WS run works.
  - completed labels begin to appear over longer windows.
  - the 24 h upper-bound early-stop works.
  - the completed-tail-label sufficiency threshold can be
    reached early.
  - export / replay evidence preserves the results.
  - low-sample states remain conservative
    (`INSUFFICIENT_SAMPLE` / `INCONCLUSIVE` are valid
    outputs not failures).
  - no trade authority was granted by any window.

## Closed phase: Phase 11C.1C-C-B-B-B-D (ACCEPTED)

**Phase 11C.1C-C-B-B-B-D — Mover Capture Recall &
Missed-Tail Coverage Audit v0 / *异动币捕捉召回与漏捕右尾
覆盖审计 v0*.** Status: **ACCEPTED (closed 2026-05-25; PR
#60 docs-only kickoff merged into `main`; PR #61
implementation merged into `main`; this docs-only
closeout PR #62 records the operator-VPS 10 min WS paper
smoke evidence + daily report Mover Capture section +
`MOVER_CAPTURE_*` event counts + Phase 8.5 export bundle +
audit result `mover_capture_audit_status=DEGRADED` and
flips the slice to `ACCEPTED`).**
Phase 11C.1C-C-B-B-B-C (*Long-Window Cohort Stability &
Sample Sufficiency Protocol v0*) is **ACCEPTED** (PR
#58 docs-only kickoff merged into `main`; closeout via PR
#59), so Phase 11C.1C-C-B-B-B-D is **NEXT_ALLOWED**.

This docs-only kickoff PR #60 **defines** the slice in
place — name, scope, boundary, allowed outputs, forbidden
list, key metrics, interpretation principles, audit
cadence, audit input sources, audit objects, and
acceptance-gate placeholder. It does **not** flip the
slice's acceptance state, does **not** add any new Python
module, does **not** add any new event type, does **not**
modify runtime behaviour, and does **not** authorise Phase
12. Phase 11C.1C-C-B-B-B-D remains `NEXT_ALLOWED /
NOT_STARTED` after this PR; a separate docs-only closeout
PR will be authored after the operator captures A1 / A2
audit evidence and will flip the slice to `ACCEPTED`.

The slice answers seven coverage questions, **and only
these seven**:

  1. **Did real market movers get captured by the system?**
  2. **If captured, at which discovery layer?**
     (`MARKET_SNAPSHOT` / `PRE_ANOMALY_DETECTED` /
     `ANOMALY_DETECTED` / `MARKET_REGIME_ASSESSED` /
     `CANDIDATE_STAGE_CLASSIFIED` / `OPPORTUNITY_SCORED` /
     `STRATEGY_MODE_SELECTED` /
     `CLUSTER_CONTEXT_ATTACHED` / `LABEL_QUEUE_ENQUEUED` /
     `LABEL_TRACKING_STARTED` / `LABEL_WINDOW_COMPLETED` /
     `TAIL_LABEL_ASSIGNED` /
     `STRATEGY_VALIDATION_SAMPLE_CREATED`.)
  3. **If not captured, why?** Allowed missed-mover
     reasons (taxonomy): `not_in_futures_universe`,
     `not_in_exchange_info`, `not_usdt_perpetual`,
     `symbol_limit_excluded`,
     `candidate_pool_capacity_evicted`, `score_too_low`,
     `liquidity_insufficient`,
     `data_stale_or_degraded_or_unreliable`,
     `risk_rejected`, `no_completed_tail_label_yet`.
  4. **Were the top movers captured early enough?**
     (`first_seen_latency_seconds` per captured mover,
     `median_first_seen_latency_seconds` per audit
     window.)
  5. **Did captured movers proceed into the label /
     validation pipeline?** (`label_tracking_rate`,
     `tail_label_assigned_rate`,
     `strategy_validation_sample_rate`.)
  6. **Are missed movers a system-coverage problem or a
     market / exchange-coverage problem?**
  7. **Were captured-but-rejected movers rejected for
     sound conservative reasons?** (`risk_rejected_mover_count`
     is **not** treated as a system failure.)

The trigger for this slice is concrete: B-B-B-C proved that
long-window paper data collection works end-to-end, but it
did **not** prove that the discovery layer covers the
real market movers the operator can see on Binance's
public 24 h gainer board. The operator observed SAGAUSDT
on the gainer board during a B-B-B-C window; cross-check
showed the system did capture SAGAUSDT through the full
discovery chain (`PRE_ANOMALY_DETECTED` →
`ANOMALY_DETECTED` → `MARKET_REGIME_ASSESSED` →
`CANDIDATE_STAGE_CLASSIFIED` → `OPPORTUNITY_SCORED` →
`STRATEGY_MODE_SELECTED` → `CLUSTER_CONTEXT_ATTACHED` →
`LABEL_QUEUE_ENQUEUED` → `LABEL_TRACKING_STARTED` →
`TAIL_LABEL_ASSIGNED` →
`STRATEGY_VALIDATION_SAMPLE_CREATED`). One coin proves
nothing; the audit institutionalises "human looks at
gainer board vs. did the system see it" as a coverage
protocol, not as ad-hoc human screenshots.

The parent phase is **not** renamed: Phase 11C.1C-C-B-B-B
remains *Strategy Validation Lab (deeper) & richer Cluster
Exposure Control follow-up*.

> **Phase 11C.1C-C-B-B-B-D kickoff (PR #60) does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-B-D kickoff does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-B-D kickoff does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-B-D kickoff does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-B-D kickoff does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-B-D kickoff does NOT authorise Phase 12.**
> **Phase 11C.1C-C-B-B-B-D kickoff does NOT authorise automatic parameter optimisation.**
> **Phase 11C.1C-C-B-B-B-D kickoff does NOT authorise AI Learning.**
> **Phase 11C.1C-C-B-B-B-D kickoff does NOT authorise reinforcement learning.**
> **Phase 11C.1C-C-B-B-B-D kickoff does NOT authorise rule relaxation on the basis of a single-coin or "妖币" case (incl. SAGAUSDT).**
> **Phase 11C.1C-C-B-B-B-D kickoff does NOT authorise changing the Risk Engine or the Execution FSM.**
> **Phase 11C.1C-C-B-B-B-D kickoff does NOT stand in for a Historical 30D+ Blind Replay / Walk-forward Validation (that gate is reserved for a Phase 12 candidate review and is explicitly out of scope here).**
> **Phase 11C.1C-C-B-B-B-D kickoff does NOT flip the slice's acceptance state.**
> **Phase 12 (live trading) remains FORBIDDEN.**

### Phase 11C.1C-C-B-B-B-D allowed outputs (docs / evidence templates only)

  - `top_mover_capture_summary`
  - `captured_mover_evidence`
  - `missed_mover_audit`
  - `symbol_universe_exclusion_summary`
  - `candidate_eviction_summary`
  - `risk_rejection_summary`
  - `first_seen_latency_summary`
  - `capture_recall_rate`
  - `missed_tail_candidate_list`
  - `coverage_warning`
  - `insufficient_coverage_reasons`

Each is a **descriptive document, evidence row, or
summary**. None has trade authority. None is read by the
Risk Engine or the Execution FSM. None is a new Python
module, a new event type, or a new runtime hook.

### Phase 11C.1C-C-B-B-B-D allowed input sources (read-only; reuse existing surfaces)

  - Binance **public** 24 h ticker / public market data
    (existing public REST surface; rate-limit governed by
    Phase 11C.1A; not a private endpoint).
  - `EventRepository` (existing events.db).
  - Daily report (existing Phase 11B + 11C sections).
  - Phase 8.5 export bundle / Phase 10A replay bundle.
  - `StrategyValidationDataset` (Phase 11C.1C-C-B-B-A).
  - `PaperAlphaGateReport` (Phase 11C.1C-C-B-B-B-A).
  - `RegimeClusterEvidencePack` (Phase 11C.1C-C-B-B-B-B).
  - `SymbolUniverse` and `exchangeInfo`-as-truth catalogue
    (Phase 11C.1B).
  - Candidate pool logs / capacity-eviction evidence
    (where available from existing runtime
    instrumentation).

### Phase 11C.1C-C-B-B-B-D inherited forbidden items

Phase 11C.1C-C-B-B-B-D inherits every Phase 1 / 11C.1B /
11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A /
11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B /
11C.1C-C-B-B-B-C forbidden item verbatim, plus the
slice-specific items recorded in
`docs/PHASE_11C_1C_C_B_B_B_D_MOVER_CAPTURE_RECALL_AUDIT.md`
(no triggering of real trades; no modifying position size,
leverage, stop-loss, target price, the Risk Engine, or the
Execution FSM; no AI / LLM trade authority; no auto
parameter optimisation; no auto rule relaxation on low
coverage or single-coin cases; no auto-scheduling of A1 /
A2 / A3+; no promotion of any audit artefact to a
real-trade authority; no rewriting of the Regime & Cluster
Evidence Pack v0 `INSUFFICIENT_SAMPLE` rule or the Paper
Alpha Gate v0 `INCONCLUSIVE` rule; no new event types in
this kickoff PR or in any future Phase 11C.1C-C-B-B-B-D
PR; no `app/` / `scripts/` / `tests/` / `configs/` /
`risk/` / `execution/` / `llm/` / `telegram/` / `exchange/`
modifications in this kickoff PR; no Historical 30D+
Blind Replay / Walk-forward Validation under this slice;
Phase 12 stays `FORBIDDEN`).

Paper / report / evidence-only by default until the
slice's own *closeout* PR opens it for review. Grants no
trade authority.

### Phase 11C.1C-C-B-B-B-D acceptance gate (placeholder; will be detailed by the closeout PR)

  - A1 (first end-to-end coverage audit pass) operator-VPS
    evidence captured verbatim, including audit window
    timestamps, `top_mover_count`,
    `captured_top_mover_count`,
    `missed_top_mover_count`, `capture_recall_rate`,
    `anomaly_detected_rate`, `label_tracking_rate`,
    `tail_label_assigned_rate`,
    `strategy_validation_sample_rate`,
    `risk_rejected_mover_count`,
    `not_in_universe_count`, `capacity_evicted_count`,
    `data_unreliable_count`,
    `median_first_seen_latency_seconds`, per-captured-mover
    evidence rows, per-missed-mover audit rows, any
    `coverage_warning` raised, and any
    `insufficient_coverage_reasons` recorded.
  - A2 (second audit pass against an independent paper
    observation window) operator-VPS evidence captured
    verbatim, including the same fields.
  - Cross-window stability check: any signal that this
    slice would otherwise call out as a coverage warning
    must persist across A1 and A2; one-window-only
    warnings are recorded but not elevated.
  - Phase 8.5 export bundle includes the discovery-layer
    events used by the audit.
  - Phase 10A replay engine accepts each window's export
    bundle without raising.
  - Safety flags unchanged across every audit window
    (`mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance API
    key, no Binance API secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound).
  - No `ORDER_*` / `POSITION_*` / `STOP_*` /
    `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` event
    emitted by any audit.
  - No new event type emitted by any audit.
  - No audit artefact is read by the Risk Engine or the
    Execution FSM.
  - Phase 12 stays `FORBIDDEN`.

The protocol explicitly accepts "we still do not have
enough coverage data" as a valid closeout result — exactly
the way Phase 11C.1C-C-B-B-B-A and Phase 11C.1C-C-B-B-B-B
accepted `INCONCLUSIVE` / `INSUFFICIENT_SAMPLE`, and the
way Phase 11C.1C-C-B-B-B-C accepted W1 / W2 windows whose
`completed_tail_label_count<10`. Either outcome is
acceptable as long as the audit transcript is well-formed
and the safety lock holds.

## Phase 11C.1C-C-B-B-B-D acceptance evidence (operator-VPS 10 min WS paper smoke PASSED)

> The transcript below is the verbatim operator-VPS run
> evidence captured for Phase 11C.1C-C-B-B-B-D and is
> recorded by this docs-only closeout PR #62. It records
> what the operator-VPS observed during the 10 min real
> public WS paper smoke against PR #61 head; it does
> **not** modify any runtime behaviour, does **not**
> enable live trading, does **not** authorise Phase 12,
> and does **not** authorise any rule relaxation.
> `mover_capture_audit_status=DEGRADED` is the **expected
> and accepted** audit output for this smoke window
> because the audit layer successfully surfaced coverage
> weakness / uncertainty (only 4 of 20 top movers reached
> a captured discovery layer; 4 movers had unreliable
> data; 4 movers were captured-but-risk-rejected; the
> remaining were missed for reasons spread across the
> taxonomy). **`DEGRADED` does NOT mean runtime failure.**
> captured-but-risk-rejected does **NOT** mean discovery
> failure (the Risk Engine remains the single
> trade-decision gate). Missed-with-unknown reason is a
> `review` signal, **not** permission to loosen rules. Low
> capture recall does **NOT** authorise automatic
> `symbol_limit` expansion / anomaly threshold changes /
> candidate pool capacity changes / Regime weight changes
> / Risk Engine changes; high capture recall would also
> **NOT** authorise live trading. The Risk Engine remains
> the single trade-decision gate.

### Operator-VPS 10 min WS paper smoke

```
duration_seconds                = 600.0
dry_run                         = false
ws_first                        = true
ws_real_transport               = true
ingestion_errors                = 0
risk_approved                   = 0
HTTP 429                        = 0
HTTP 418                        = 0
ws_reconnect_count              = 0
ws_stale_count                  = 0
live_trading_enabled            = False
exchange_live_order_enabled     = False
llm_enabled                     = False
right_tail_enabled              = False
```

### Mover Capture event counts (events.db, authoritative)

```
MOVER_CAPTURE_RECALL_AUDIT_GENERATED = 1
MOVER_CAPTURE_PATH_AUDITED           = 20
```

### Daily report excerpt — `## Phase 11C.1C-C-B-B-B-D Mover Capture Recall & Missed-Tail Coverage Audit v0`

```
mover_capture_audit_status      = DEGRADED
top_mover_count                 = 20
captured_top_mover_count        = 4
missed_top_mover_count          = 16
capture_recall_rate             = 0.2000
data_unreliable_count           = 4
risk_rejected_mover_count       = 4
```

### Audit-result interpretation (must be read verbatim)

  - `DEGRADED` is an **accepted audit output**, **not** a
    runtime failure.
  - `DEGRADED` means the audit layer **successfully
    surfaced** coverage weakness / uncertainty.
  - Captured-but-risk-rejected does **not** mean discovery
    failure (the Risk Engine remains the single
    trade-decision gate).
  - Missed-with-`unknown` reason is a `review` signal,
    **not** permission to loosen rules.
  - Low capture recall does **NOT** authorise automatic
    `symbol_limit` expansion.
  - Low capture recall does **NOT** authorise automatic
    anomaly threshold changes.
  - Low capture recall does **NOT** authorise automatic
    candidate-pool capacity changes.
  - Low capture recall does **NOT** authorise automatic
    Regime weight changes.
  - Low capture recall does **NOT** authorise Risk Engine
    changes.
  - High capture recall would also **NOT** authorise live
    trading.

### Phase 8.5 export evidence

```
export_test_data                = OK
export zip                      = data/reports/exports/ama_rt_test_data_1779721036065_export_d.zip
manifest_event_count            = 63968
redaction_applied               = True
events.jsonl exists             = True
export contains MOVER_CAPTURE_* events
MOVER_CAPTURE_RECALL_AUDIT_GENERATED = 1
MOVER_CAPTURE_PATH_AUDITED           = 20
EXPORT_MOVER_CAPTURE_RECALL_CHECK = PASS
```

Export package files observed (under the export zip):

  - `manifest.json`
  - `summary_report.md`
  - `events.jsonl`
  - `opportunities.jsonl`
  - `signal_snapshots.jsonl`
  - `risk_decisions.jsonl`
  - `state_transitions.jsonl`
  - `capital_events.jsonl`
  - `virtual_trade_plans.jsonl`

### Safety boundary held end-to-end (Phase 1 lock unchanged)

```
trading_mode                    = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
real Binance API key            = not loaded
real Binance API secret         = not loaded
real signed endpoint call       = none
real account / order / position / leverage / margin endpoint = none
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

### Closeout interpretation (must be read verbatim)

  - **Phase 11C.1C-C-B-B-B-D acceptance is acceptance of
    the Mover Capture Recall & Missed-Tail Coverage Audit
    v0 layer.**
  - It does **NOT** mean strategy effectiveness is proven.
  - It does **NOT** mean any Regime / Cluster has proven
    right-tail advantage yet.
  - It does **NOT** mean the discovery layer is "good
    enough" — the audit explicitly returned `DEGRADED` and
    surfaced a 0.2000 capture recall on this 10 min
    window.
  - It does **NOT** authorise live trading.
  - It does **NOT** authorise API keys, private endpoints,
    DeepSeek trade decisions, or real Telegram outbound.
  - It does **NOT** authorise AI Learning, automatic
    parameter optimisation, or reinforcement learning.
  - It does **NOT** authorise rule relaxation based on
    SAGAUSDT or any small number of movers.
  - It does **NOT** authorise changing the Risk Engine or
    the Execution FSM.
  - It does **NOT** authorise automatic `symbol_limit`
    expansion.
  - It does **NOT** authorise automatic anomaly threshold
    changes.
  - It does **NOT** authorise automatic candidate-pool
    capacity changes.
  - It does **NOT** authorise automatic Regime weight
    changes.
  - It does **NOT** authorise Phase 11C.1C-C-B-B-B-D-A
    kickoff bypassing the standard gate.
  - It does **NOT** authorise Phase 12.
  - It records that:
      - the Mover Capture Recall & Missed-Tail Coverage
        Audit v0 layer runs end-to-end against real
        public Binance WS data,
      - `MOVER_CAPTURE_RECALL_AUDIT_GENERATED` and
        `MOVER_CAPTURE_PATH_AUDITED` events are emitted
        and exported to the Phase 8.5 export bundle,
      - the daily report renders the Mover Capture section
        with every brief-mandated field,
      - `DEGRADED` is a valid coverage-audit output and
        is accepted as such,
      - the Risk Engine remains the single trade-decision
        gate,
      - the Phase 1 safety lock held end-to-end,
      - no trade authority was granted,
      - no rule relaxation was triggered.

## Closed phase: Phase 11C.1C-C-B-B-B-D-B (ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT)

**Phase:** Phase 11C.1C-C-B-B-B-D-B — Post-Discovery Outcome
Metrics v0 (*发现后结果度量 v0*).

**Status:** `ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY /
PRICE_PATH_INSUFFICIENT` (explicitly **NOT** full quality
accepted).

**Closeout PR type:** docs-only.

### What this closeout records

  - **PR #69 fixed the D-B evidence runner input adapter gap.**
    The runner now consumes the **real** D-A export shape:
    `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED` events whose
    payload **is** the per-mover record (not wrapped in a
    `record` key), with the symbol-fallback chain
    `record["symbol"]` → `record["reference"]["symbol"]` →
    `record["capture_path"]["symbol"]` → event-level
    `symbol`.
  - **D-B can now consume real D-A export records.**
  - **300 D-A records were evaluated** by the D-B runner
    against the real D-A export rerun on `main` from the
    operator VPS.
  - **`POST_DISCOVERY_OUTCOME_REPORT_GENERATED` was
    produced** (one report per batch), alongside 300
    `POST_DISCOVERY_OUTCOME_EVALUATED` events (one per
    record).
  - **The output is evidence-generated, but NOT
    direction-quality accepted.**
  - **195 / 300 records are `INSUFFICIENT_PRICE_PATH`.**
  - **105 / 300 records are `MISSED_STRONG_TAIL`.**
  - **`RAVEUSDT` and `STOUSDT` remain unresolved** because
    they are `INSUFFICIENT_PRICE_PATH / INSUFFICIENT_DATA`.

### D-A export input check (real VPS rerun on `main`)

  - `HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED = 2`
  - `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED = 300`
  - `D_A_EXPORT_INPUT_CHECK = PASS`

### B1 evidence run output

Output directory:
`data/reports/post_discovery_outcome/pr69_main_real_d_a_evidence`

Summary:

  - `status = EVIDENCE_GENERATED`
  - `reference_window = 60d`
  - `evaluated_count = 300`
  - `report_generated_count = 1`
  - `output_report =
    data/reports/post_discovery_outcome/pr69_main_real_d_a_evidence/post_discovery_outcome_report.json`
  - `output_events =
    data/reports/post_discovery_outcome/pr69_main_real_d_a_evidence/events.jsonl`

Outcome label summary:

  - `INSUFFICIENT_PRICE_PATH = 195 / 300`
  - `MISSED_STRONG_TAIL = 105 / 300`

Detection timing summary:

  - `INSUFFICIENT_DATA = 195 / 300`
  - `MISSED = 105 / 300`

Notable symbols:

  - `RAVEUSDT` — `INSUFFICIENT_PRICE_PATH /
    INSUFFICIENT_DATA`.
  - `STOUSDT` — `INSUFFICIENT_PRICE_PATH /
    INSUFFICIENT_DATA`.

Warnings:

  - `d_a_backfill_records_missing_using_record_audited_fallback`
    (Format B fallback engaged; expected for the real D-A
    export shape, where
    `HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED.payload.records`
    is `None` and the per-mover records ride on
    `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED`).

### What `ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT` means

  - **The D-B toolchain works end-to-end against real D-A
    export records.** The runner reads the real D-A export,
    adapts the `RECORD_AUDITED` events into post-discovery
    outcome inputs, evaluates each one, emits one
    `POST_DISCOVERY_OUTCOME_EVALUATED` per record, aggregates
    them into one `POST_DISCOVERY_OUTCOME_REPORT_GENERATED`,
    and writes the JSON / JSONL / markdown artefacts under
    `data/reports/post_discovery_outcome/pr69_main_real_d_a_evidence/`.
    This is the **toolchain** half of the acceptance.
  - **The output is evidence-generated, but NOT
    direction-quality accepted.** 195/300 records (65%) are
    `INSUFFICIENT_PRICE_PATH` because the D-A export does
    not yet carry post-first-seen K-line price paths for
    those movers; 105/300 records (35%) are
    `MISSED_STRONG_TAIL` (the system never had a first-seen
    anchor at all). Neither outcome class lets the report
    classify the *quality* of the system's timing — we
    cannot tell from this run whether the first sighting
    was early, late, choppy, late-reversal, or
    fake-breakout, because the price path that would allow
    that classification is missing for every evaluable
    record. This is the **partial quality** half of the
    acceptance.
  - **`RAVEUSDT` and `STOUSDT` remain unresolved by D-B
    alone.** Both show up in this run as
    `INSUFFICIENT_PRICE_PATH / INSUFFICIENT_DATA`; they
    require price-path completeness or explicit data-gap
    triage before the Severe Missed Tail Triage slice can
    consume them.

### What `ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT` does NOT mean

  - **D-B does NOT solve direction.** The runner does not
    emit, and is forbidden to emit, any `long` / `short` /
    `entry` / `exit` / `stop` / `target` / `position_size`
    / `leverage` field. The two label sets
    (`detection_timing_label`, `outcome_label`) are
    descriptive only.
  - **D-B does NOT prove strategy profitability.** No PnL
    was simulated; no order was submitted; no Risk Engine
    decision was reproduced. The labels describe what the
    reference set already recorded; they do not measure
    P&L.
  - **D-B does NOT authorise auto-tuning.** The labels
    MUST NOT drive `symbol_limit` expansion, anomaly
    threshold changes, candidate-pool capacity changes,
    Regime weight changes, or any other runtime knob.
    "Looking at the answer key" against the post-hoc D-A
    reference set is forbidden.
  - **D-B does NOT authorise DeepSeek trade decisions.**
    DeepSeek remains read-only / sandbox-only / offline
    under the AI Layer Constitution; D-B's labels are
    **not** trade authorisation surface for DeepSeek or
    any other LLM.
  - **Phase 12 remains FORBIDDEN.** No Phase 1 safety flag
    is loosened by this closeout; Spec §41 Go/No-Go has
    not been initiated.

### Next allowed route (paper-only; gated, sequential)

  - **B1 (this slice) closeout** — accepted as
    **toolchain + partial quality only**, NOT
    direction-quality. This is the closeout currently
    being recorded.
  - Then **either** (operator's choice, gated by an
    explicit kickoff PR per slice):
      - **B1.1** — *Historical Price Path Completeness /
        Kline Path Adapter* — likely needed because
        195/300 records lack sufficient post-first-seen
        price path, and `RAVEUSDT` / `STOUSDT` remain
        unresolved on price-path / data-gap grounds.
        Improving D-B outcome quality before B2 is the
        **recommended** next route.
      - **B2** — *Severe Missed Tail Triage* —
        admissible **only with the explicit note that
        `RAVEUSDT` and `STOUSDT` currently require
        price-path / data-gap triage** before they can be
        classified as severe missed tails by D-B alone.
  - The **next allowed route is NOT** to start DeepSeek
    directly, and is **NOT** to start blind walk-forward
    directly.
  - Recommended next slice after this docs PR: **B1.1
    Price Path Completeness / Kline Path Adapter.**

### Forbidden surface (verbatim; held under D-B PARTIAL_QUALITY closeout)

  - `app/risk/**`, `app/execution/**`, `app/exchanges/**`,
    `app/llm/**`, `app/telegram/**`.
  - Binance private API (no API key, no API secret, no
    signed endpoint, no `listenKey`, no private WS).
  - Live orders.
  - Real Telegram outbound.
  - DeepSeek / LLM trade decisions (direction, position
    size, leverage, stop-loss, target price, execution
    command, runtime config patch).
  - Automatic parameter tuning (incl. `symbol_limit`
    expansion, anomaly threshold change, candidate pool
    capacity change, Regime weight change).
  - Blind walk-forward via D-B alone.
  - Any rule relaxation based on D-B labels.
  - Phase 12 (real money / live trading).

### Safety boundary (held end-to-end)

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - no private API
  - no live orders
  - no real Telegram outbound
  - no DeepSeek trade decision
  - **Phase 12 = FORBIDDEN**

**The Risk Engine remains the single trade-decision gate.**

### What this docs-only closeout PR did NOT change

  - **No** file under `app/`, `scripts/`, `tests/`,
    `configs/`, `risk/`, `execution/`, `exchanges/`,
    `llm/`, `telegram/`, or `database` schema is touched.
  - **No** event name is added, removed, or renamed.
  - **No** schema version is changed.
  - **No** runtime behaviour is changed.
  - **No** test was run by this PR.
  - **No** paper run, export, replay, or historical builder
    was invoked by this PR.
  - **No** real API was contacted by this PR.

## Closed phase: Phase 11C.1C-C-B-B-B-D-A (ACCEPTED / PARTIAL_QUALITY / TOOLCHAIN_CLOSEOUT_ONLY)

**Phase:** Phase 11C.1C-C-B-B-B-D-A — Historical 60D Mover
Coverage Audit v0.

**Status:** **ACCEPTED / PARTIAL_QUALITY /
TOOLCHAIN_ACCEPTED_ONLY.**

### Acceptance evidence

  - 60D Historical Market Store reference data has been
    generated under `data/historical_market_store/` (D-A.1
    *Historical 60D Mover Reference Store Builder v0* is
    the data-preparation child task under D-A and has
    completed its toolchain role).
  - `app.adaptive.historical_mover_coverage_backfill` has
    produced D-A audit records against that reference
    store.
  - The Phase 8.5 export bundle now contains the
    `HISTORICAL_MOVER_COVERAGE_*` events that surface
    those records (audit output is replayable and
    externally reviewable).
  - Operator manual review result = **PARTIAL** (per-symbol
    verdict recorded below).
  - Severe misses identified: **`RAVEUSDT`** and
    **`STOUSDT`**.

### D-A manual review (operator sample, recorded verbatim)

  - `PLAYUSDT` — qualified.
  - `AGTUSDT` — discovered ~2 days ahead; mid-window chop
    is small; qualified provided the system is not shaken
    off by the chop.
  - `BEATUSDT` — qualified.
  - `VICUSDT` — marginally usable.
  - `BIOUSDT` — usable, including the subsequent rally.
  - `PROVEUSDT` — long-side entry was poor; if the system
    had classified it as exhaustion / short, the result
    could have been positive.
  - `USUSDT` — not qualified.
  - `RAVEUSDT` — **severely missed** (not qualified).
  - `STOUSDT` — **severely missed** (not qualified).

### Gate interpretation

  - **PASS** in this gate means the audit toolchain and
    evidence surface are usable.
  - **PARTIAL_QUALITY** means discovery quality remains
    unresolved — this gate does **not** assert that
    AMA-RT discovers altcoin movers well in general.
  - **Severe misses trigger later triage only** (Severe
    Missed Tail Triage). They do **not** authorise any
    automatic threshold change, any `symbol_limit`
    expansion, any candidate-pool capacity change, any
    Regime weight change, or any other automatic
    parameter tuning.
  - **No "looking at the answer key."** Auto-tuning
    thresholds against the D-A reference set is forbidden.
  - **No live trading authority is granted by D-A
    acceptance.**

### Next allowed phases

  - **Post-Discovery Outcome Metrics.**
  - **Severe Missed Tail Triage** (covers `RAVEUSDT`,
    `STOUSDT`, and any later additions).
  - **Replay / Reflection extension for 11C events.**
  - **AI Layer Constitution docs baseline** — see
    `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`.

### Forbidden transitions (under D-A acceptance)

  - **Direct Phase 12** — Phase 12 (real money / live
    trading) remains **FORBIDDEN**.
  - **Private Binance API** — no API key, no API secret,
    no signed endpoint, no `listenKey`, no private WS.
  - **Live orders.**
  - **DeepSeek / LLM trade decision** — no direction, no
    position size, no leverage, no stop-loss, no target
    price, no execution command, no runtime config patch.
  - **Real Telegram outbound.**
  - **Automatic parameter tuning.**

The Risk Engine remains the single trade-decision gate.
The four `ExchangeClientBase` write surfaces
(`create_order`, `cancel_order`, `set_leverage`,
`set_margin_mode`) continue to raise `SafeModeViolation`.

The "Open phase: Phase 11C.1C-C-B-B-B-D-A (NEXT_ALLOWED /
NOT_STARTED)" block below is **superseded** by this
closeout block. It is kept for audit trail.

## Open phase: Phase 11C.1C-C-B-B-B-D-A (NEXT_ALLOWED / NOT_STARTED)

**Phase 11C.1C-C-B-B-B-D-A — Historical 60D Mover Coverage
Backfill Audit v0 / *历史 60 天异动币覆盖回填审计 v0*.**
Status: **NEXT_ALLOWED / NOT_STARTED.** Phase
11C.1C-C-B-B-B-D (*Mover Capture Recall & Missed-Tail
Coverage Audit v0*) is now **ACCEPTED** (PR #60 docs-only
kickoff + PR #61 implementation + PR #62 docs-only
closeout merged into `main`), so Phase 11C.1C-C-B-B-B-D-A
is **NEXT_ALLOWED**. This docs-only kickoff PR #63
**defines** the slice in place — name, scope, boundary,
allowed outputs, forbidden list, eight audit questions,
60D top-mover reference set fields, per-captured-mover
audit row fields, miss-reason taxonomy, allowed input
sources, audit objects, audit cadence (B1 / B2 with
B3+ reserved; operator-driven, **not** auto-scheduled),
interpretation principles, safety boundary, and
acceptance-gate placeholder — but **does NOT flip its
state**.

The full scope, audit shape, miss-reason taxonomy,
allowed outputs, interpretation principles, and forbidden
list are now recorded under
`docs/PHASE_11C_1C_C_B_B_B_D_A_HISTORICAL_60D_MOVER_COVERAGE_BACKFILL.md`.
This section is the phase-gate ledger view of that
document. The two views must remain consistent across
future PRs.

**Not** complete strategy blind testing. **Not** Phase 12
pre-live validation. **Not** Historical 30D+ / 60D
*complete strategy* blind replay / walk-forward
validation (that gate remains reserved until small-money
live trading prep and is **out of scope** for D-A).
Discovery-layer historical coverage backfill audit only.

### Phase 11C.1C-C-B-B-B-D-A rationale

PR #61 proved the Mover Capture Recall & Missed-Tail
Coverage Audit v0 layer can run in real paper mode and
export `MOVER_CAPTURE_*` evidence. However:

  - A 10 min live window may be too short and
    market-dependent. Example: a real mover like SAGAUSDT
    can be missed or classified as `unknown` in a short
    audit window.
  - Waiting several quiet days to accumulate more 10 min
    windows may waste time if the market is calm.
  - Therefore the next slice should evaluate
    **discovery-layer coverage over the past 60 days** —
    a structured backfill audit, not a live observation
    window.

This is **not** complete strategy blind testing. It is
**not** Phase 12 pre-live validation. It is **only** a
discovery-layer coverage backfill audit. Historical 30D+
full blind replay / complete strategy walk-forward
validation remains reserved for small-money live trading
prep and is **not** in scope for D-A.

### Phase 11C.1C-C-B-B-B-D-A is allowed to answer

  - Over the past 60 days, **which eligible movers did
    AMA-RT detect**?
  - **When did AMA-RT first detect them**?
  - **Which capture-path layer did they reach**?
  - **Which movers were missed**?
  - **Why were they missed**?
  - **Which misses are universe-coverage issues** vs.
    discovery-layer warnings?

### Phase 11C.1C-C-B-B-B-D-A must NOT answer

  - whether the strategy is profitable;
  - whether live trading is allowed;
  - whether leverage / position / stops should change;
  - whether `symbol_limit` should auto-expand;
  - whether anomaly thresholds should auto-change;
  - whether candidate pool capacity should auto-change;
  - whether Phase 12 can begin.

### Phase 11C.1C-C-B-B-B-D-A must require

  - a 60D top mover reference set;
  - an eligible USDT-perpetual universe filter;
  - `first_seen_time_utc` for every captured mover;
  - `first_seen_event_type`;
  - `first_seen_latency_seconds` where a mover reference
    timestamp exists;
  - `capture_path_depth`;
  - per-mover status (`captured` / `partially_captured` /
    `missed` / `excluded`);
  - miss-reason classification;
  - report / export / replay evidence.

### Phase 11C.1C-C-B-B-B-D-A inherited forbidden items

Phase 11C.1C-C-B-B-B-D-A inherits every Phase 1 / 11C.1B /
11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A /
11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B /
11C.1C-C-B-B-B-C / 11C.1C-C-B-B-B-D forbidden item
verbatim. Specifically (non-exhaustive):

  - no live trading;
  - no API keys / secrets;
  - no signed endpoints;
  - no account / order / position / leverage / margin
    endpoints;
  - no private WebSocket / `listenKey` / user data
    stream;
  - no DeepSeek trade decisions;
  - no real Telegram outbound;
  - no AI Learning, automatic parameter optimisation, or
    reinforcement learning;
  - no rule relaxation based on single-coin / "妖币"
    cases;
  - no automatic `symbol_limit` / anomaly threshold /
    candidate pool capacity / Regime weight changes;
  - no Risk Engine or Execution FSM changes;
  - no Phase 11C.1C-C-B-B-B-D-A kickoff bypassing the
    standard gate (D-A still requires its own kickoff PR,
    brief, scope, boundary table, forbidden list, and
    acceptance evidence);
  - Phase 12 remains **FORBIDDEN**.

### Phase 11C.1C-C-B-B-B-D-A acceptance gate (placeholder)

The Phase 11C.1C-C-B-B-B-D-A kickoff PR is **this docs-only
kickoff PR #63** (it scopes the slice in place; it does not
flip the slice's state). A subsequent implementation +
closeout PR cycle will produce the backfill audit transcript
and flip D-A to `ACCEPTED`. The exact gate criteria (60D
window end-date selection, top-N gainer cutoff per window,
eligible-vs-non-eligible classification rule, allowed
deviations between B1 and B2 replay passes, coverage warning
thresholds) are recorded in the dedicated phase doc
`docs/PHASE_11C_1C_C_B_B_B_D_A_HISTORICAL_60D_MOVER_COVERAGE_BACKFILL.md`
and may be refined by future implementation / closeout PRs
without flipping D-A's state at kickoff time. This kickoff
PR #63 **only** scopes the slice; it does **not** flip
D-A's state. The closeout PR (a **future** PR; not this
one) will record the operator-driven B1 / B2 backfill audit
evidence and flip D-A to `ACCEPTED`.

## Phase 11C.1C-C-B-B-B-D-A kickoff (PR #63)

> **Status: docs-only kickoff / scope alignment.** This
> kickoff PR #63 scopes Phase 11C.1C-C-B-B-B-D-A in place;
> it does **not** flip the slice's state. Phase
> 11C.1C-C-B-B-B-D-A remains `NEXT_ALLOWED / NOT_STARTED`
> after this PR.

### Phase 11C.1C-C-B-B-B-D-A kickoff scope (PR #63 summary)

  - Defines Phase 11C.1C-C-B-B-B-D-A as the *Historical 60D
    Mover Coverage Backfill Audit v0 / 历史 60 天异动币覆盖
    回填审计 v0* — the next allowed child slice under Phase
    11C.1C-C-B-B-B (on top of the `ACCEPTED`
    11C.1C-C-B-B-B-D track).
  - Records the rationale (PR #61 proved the Mover Capture
    Recall & Missed-Tail Coverage Audit v0 layer can run in
    real paper mode; however a 10 min live audit window is
    too short and market-dependent — a real mover like
    SAGAUSDT can be missed or classified as `unknown` in a
    short window, and waiting several quiet days to
    accumulate more 10 min windows wastes operator time —
    therefore the next slice evaluates discovery-layer
    coverage over the past 60 days as a structured
    historical backfill audit).
  - Defines the eight audit questions and **only those
    eight** (over the past 60 days: did AMA-RT discover the
    eligible USDT perpetual movers; if discovered, when
    (`first_seen_time_utc`); what was the first event
    (`first_seen_event_type`); how deep did the capture
    path go (`capture_path_depth` + `reached_*` booleans);
    if not, why (`miss_reason`); is each missed mover a
    universe-coverage issue or a discovery-layer warning;
    which captured movers were rejected by the Risk Engine
    (`risk_rejected = true`; conservative paper outcome,
    **not** discovery failure); which captured movers only
    made it partway (`status = partially_captured`)).
  - Defines the 60D top-mover reference set fields per
    window / per symbol: `reference_window_start_utc`,
    `reference_window_end_utc`, `top_mover_symbol`,
    `top_mover_rank`, `max_window_gain`, `max_24h_gain`,
    `reference_timestamp_utc`, `eligible_usdt_perpetual`
    (true / false). Excluded: non-futures listings,
    non-USDT-margined, non-perpetual, not-in-`exchangeInfo`,
    delisted / inactive symbols.
  - Defines the per-captured-mover audit row:
    `top_mover_symbol`, `mover_window_start_utc`,
    `mover_window_end_utc`, `top_mover_rank`,
    `max_window_gain`, `max_24h_gain`,
    `eligible_usdt_perpetual`, `system_captured`,
    `first_seen_time_utc`, `first_seen_event_type`,
    `first_seen_latency_seconds` where a mover reference
    timestamp exists, `capture_path_depth`,
    `reached_anomaly`, `reached_label_queue`,
    `reached_tail_label`,
    `reached_strategy_validation_sample`, `risk_rejected`,
    `status` (`captured` / `partially_captured` / `missed`
    / `excluded`), `miss_reason`.
  - Defines the fixed `miss_reason` taxonomy:
    `not_in_futures_universe`,
    `symbol_not_in_exchange_info`, `not_usdt_perpetual`,
    `missing_historical_reference_data`,
    `missing_event_history`, `below_liquidity_threshold`,
    `symbol_limit_excluded`, `candidate_pool_evicted`,
    `insufficient_ws_data`, `stale_data`,
    `data_unreliable`, `no_anomaly_threshold_cross`,
    `risk_rejected`, `no_completed_tail_label_yet`,
    `unknown` (and `unknown` is a `review` signal —
    **not** a `relax` signal).
  - Lists the allowed outputs (descriptive templates only):
    `historical_60d_mover_reference_set`,
    `historical_60d_capture_path_audit`,
    `historical_60d_miss_reason_summary`,
    `historical_60d_first_seen_summary`,
    `historical_60d_capture_recall_summary`,
    `historical_60d_coverage_warning`,
    `historical_60d_export_replay_evidence_template`.
  - Defines the audit cadence (operator-driven; **not**
    auto-scheduled): B1 (first end-to-end 60D historical
    backfill audit pass), B2 (second pass against an
    independent operator-VPS replay window), B3+ reserved
    for later child slices and out of scope here.
  - Lists the allowed input sources (read-only; reuse
    existing surfaces): Binance public 24 h ticker /
    public klines / public market data,
    `EventRepository` / events.db, daily report, Phase
    8.5 export bundle / Phase 10A replay bundle over the
    60D window, `StrategyValidationDataset`,
    `PaperAlphaGateReport`, `RegimeClusterEvidencePack`,
    `MoverCaptureRecallAuditReport`, `SymbolUniverse` /
    `exchangeInfo`-as-truth catalogue, candidate pool logs
    / capacity-eviction evidence.
  - Records the eight interpretation principles verbatim:
    captured ≠ tradable; captured early ≠ strategy
    profitable; missed and not-in-futures-universe ≠
    system failure; missed and in-eligible-universe IS a
    coverage warning (for human review only);
    `risk_rejected` ≠ discovery failure; `missed` and
    `unknown` are `review` signals (no auto rule
    relaxation, no auto `symbol_limit` expansion, no auto
    anomaly threshold change, no auto candidate-pool
    capacity change, no auto Regime weight change); high
    `capture_recall_rate` does NOT authorise live trading;
    low `capture_recall_rate` does NOT authorise parameter
    changes (no "looking at the answer key" — no
    auto-tuning thresholds against the historical reference
    set).
  - Records the slice-specific forbidden items verbatim
    (no live trading, no API keys, no private endpoints,
    no signed endpoints, no `listenKey`, no private
    WebSocket, no DeepSeek trade decisions, no real
    Telegram outbound, no AI Learning, no automatic
    parameter optimisation, no reinforcement learning, no
    rule relaxation based on historical movers, no auto
    `symbol_limit` expansion, no auto anomaly threshold
    changes, no auto candidate-pool capacity changes, no
    auto Regime weight changes, no Risk Engine override /
    bypass, no Execution FSM override / bypass, no Phase
    Gate override / bypass, no triggering a real trade
    from any audit artefact, no modifying position size /
    leverage / stops / targets from any audit artefact, no
    auto-scheduling B1 / B2 / B3+, no replacing the Mover
    Capture Recall & Missed-Tail Coverage Audit v0
    `DEGRADED` rule with a relaxed rule, no replacing the
    Regime & Cluster Evidence Pack v0 `INSUFFICIENT_SAMPLE`
    rule with a relaxed rule, no replacing the Paper Alpha
    Gate v0 `INCONCLUSIVE` rule with a relaxed rule, no
    replacing the Long-Window Cohort Stability & Sample
    Sufficiency Protocol v0 cadence with a relaxed
    cadence, no implementing the Phase 11C.1C-C-B-B-B-D-A
    backfill as a new runtime module — the slice is
    intentionally docs / evidence-template only end-to-end
    at kickoff, no treating Phase 11C.1C-C-B-B-B-D-A as a
    Historical 30D+ / 60D *complete strategy* blind replay
    / walk-forward validation, no adding new Python
    modules under `app/`, no adding new event types, no
    modifying `app/` / `scripts/` / `tests/` / `configs/`
    / `risk/` / `execution/` / `llm/` / `telegram/` /
    `exchange/`, no modifying configuration schemas /
    defaults / YAML, no adding or modifying tests, no
    running tests, no modifying strategy runtime code, no
    modifying runtime behaviour, no implementing new
    functionality, no flipping any phase's acceptance
    state, no renaming Phase 11C.1C-C-B-B-B, no Phase
    11C.1C-C-B-B-B-D-A *implementation* (out of scope), no
    Phase 11C.1C-C-B-B-B-D-A *closeout* (out of scope), no
    Phase 11C.1C-C-B-B-B-D-B / further child slices, no
    Phase 12 / live trading kickoff).
  - Refreshes the `## Open phase: Phase 11C.1C-C-B-B-B-D-A
    (NEXT_ALLOWED / NOT_STARTED)` section above so the
    slice is now scoped by name and shape, while remaining
    `NEXT_ALLOWED / NOT_STARTED`.
  - Records this PR in `docs/CHANGELOG.md > [Unreleased]`
    and `docs/PR63_DESCRIPTION.md`.

### Phase 11C.1C-C-B-B-B-D-A kickoff safety boundary (PR #63)

```
trading_mode                    = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
real Binance API key            = not loaded
real Binance API secret         = not loaded
real signed endpoint call       = none
real account / order / position / leverage / margin endpoint = none
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

### Phase 11C.1C-C-B-B-B-D-A kickoff confirmation checklist (PR #63)

  - Docs-only PR; no runtime code modified.
  - No new Python files.
  - No new event types.
  - No new tests.
  - No tests run.
  - No runtime behaviour changed.
  - No `app/` / `scripts/` / `tests/` / `configs/`
    changes.
  - No `execution/` / `risk/` / `llm/` / `telegram/` /
    `exchange/` changes.
  - No strategy runtime code changes.
  - No phase's acceptance state flipped — Phase
    11C.1C-C-B-B-A remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`;
    Phase 11C.1C-C-B-B-B-A remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-B remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-C remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-D remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-D-A remains `NEXT_ALLOWED /
    NOT_STARTED` (scoped by this PR; not flipped).
  - Phase 11C.1C-C-B-B-B parent is **not** renamed; it
    remains *Strategy Validation Lab (deeper) & richer
    Cluster Exposure Control follow-up*.
  - Phase 11C.1C-C-B-B-B-D-A is recorded as the next
    allowed child slice on top of the
    Phase 11C.1C-C-B-B-B-D track = Historical 60D Mover
    Coverage Backfill Audit v0 / *历史 60 天异动币覆盖
    回填审计 v0*.
  - Phase 12 remains `FORBIDDEN`.

## Phase 11C.1C-C-B-B-A acceptance evidence (closeout)

> The transcript below is the verbatim runner / events.db
> output captured from the 30 s dry-run smoke run against the
> PR #44 branch
> (`feature/phase-11c1c-c-b-b-validation-dataset-quality-gate`).
> Real WS 10 min smoke was **NOT required** for this PR — the
> smallest Phase 11C.1C-C-A primary tracking window is 5 min
> and cannot complete in 30 s. The 30 s dry-run is exactly
> the brief's "empty or low-sample quality gate report"
> evidence; **the smoke PASSED and was accepted as Phase
> 11C.1C-C-B-B-A acceptance evidence.**
>
> PR #44 merged into `main` on 2026-05-23 (mergeCommit
> `3ecfc3b`); Phase 11C.1C-C-B-B-A is now recorded as
> **ACCEPTED** in the closed-phases table at the top of this
> document and in the `## Closed phase: Phase 11C.1C-C-B-B-A
> (ACCEPTED)` section above. This docs-only closeout PR
> mirrors the PR #36 → PR #37, PR #38 → PR #39, PR #40 → PR
> #41, and PR #42 → PR #43 closeout pattern.

```
branch                          : feature/phase-11c1c-c-b-b-validation-dataset-quality-gate
mergeCommit                     : 3ecfc3b
host                            : Kiro sandbox (dry-run; no network)
command                         : python -m scripts.run_public_market_paper \
                                    --duration 30s --symbol-limit 5 --dry-run

# WS / runner-level metrics
duration_seconds                = 30
dry_run                         = True
ws_real_transport               = False
chains_emitted                  = 2
ws_chains_emitted               = 2
risk_approved                   = 0
risk_rejected                   = 2
learning_ready_attached         = 2
ingestion_errors                = 0
HTTP 429 count                  = 0
HTTP 418 count                  = 0
rate_limit_ban                  = False
ws_reconnect_count              = 0
ws_stale_count                  = 0

# Phase 11C.1C-C-B-B-A new section in daily report
STRATEGY_VALIDATION_DATASET_BUILT count       = 1
STRATEGY_VALIDATION_DATASET_EXPORTED count    = 1
STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED    = 1
validation_dataset_records                     = 2
validation_dataset_symbols                     = 2  (BTCUSDT, ETHUSDT)
quality_gate_status                            = fail
validation_dataset_export_ready                = True
validation_dataset_replay_ready                = True
quality_gate_reasons:
  - sample_count_below_half_min=2<10
  - completed_tail_labels_below_min=0<10
  - strategy_mode_coverage_below_min=1<2
  - candidate_stage_coverage_below_min=1<2
  - score_bucket_coverage_below_min=1<2

# Safety boundary (Phase 1 lock unchanged end-to-end)
mode                            = paper
exchange_live_order_enabled     = False
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
trading_mode_paper              = True
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
no API key                      = confirmed
no signed endpoint              = confirmed
no private websocket            = confirmed
no listenKey                    = confirmed
no DeepSeek trade decision      = confirmed
no real Telegram outbound       = confirmed
Phase 12                        = FORBIDDEN (gate unchanged)
```

### Acceptance criteria — every gate met

  - `dry_run = true` (the 30 s window is the contract; real
    WS 10 min smoke deferred to Phase 11C.1C-C-B-B-B
    closeout) ✅
  - `STRATEGY_VALIDATION_DATASET_BUILT = 1` ✅
  - `STRATEGY_VALIDATION_DATASET_EXPORTED = 1` ✅
  - `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED = 1` ✅
  - `validation_dataset_records = 2` ✅
  - `validation_dataset_symbols = {BTCUSDT, ETHUSDT}` ✅
  - `validation_quality_gate_status = fail` (expected for
    the low-sample 30 s window) ✅
  - `validation_dataset_export_ready = True` ✅
  - `validation_dataset_replay_ready = True` ✅
  - 27 brief-mandated tests PASS ✅
  - Phase 11C focus filter PASS (339 / 339) ✅
  - Full pytest PASS (2313 / 2313, no regression vs.
    post-PR-#43 main 2286 baseline) ✅
  - Safety flags unchanged
    (`mode=paper`, `live_trading=False`, `right_tail=False`,
    `llm=False`, `exchange_live_orders=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`) ✅
  - `HTTP 429 count = 0`, `HTTP 418 count = 0`,
    `rate_limit_ban = False` ✅
  - `ws_reconnect_count = 0`, `ws_stale_count = 0`,
    `ingestion_errors = 0` ✅
  - No `ORDER_*` / `POSITION_*` / `STOP_*` /
    `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` event
    emitted by the dataset / quality-gate slice ✅
  - `validation_quality_gate_status` is descriptive only
    (`pass` / `warn` / `fail`); no module reads it to drive
    execution; the Risk Engine remains the single
    trade-decision gate ✅
  - Phase 12 stayed **FORBIDDEN** ✅

`validation_quality_gate_status=fail` is the **expected**
output for the low-sample 30 s dry-run, exactly the brief's
"empty or low-sample quality gate report" requirement: the
smallest Phase 11C.1C-C-A primary tracking window is 5
minutes, so samples that landed in the 30 s window are
necessarily in-flight / unresolved. The quality gate
correctly classifies the dataset as too thin for downstream
review and emits the diagnostic reasons listed above. The
field is descriptive only — no execution surface reads it.

Phase 1 safety lock held end-to-end across the smoke run; no
real order, no signed endpoint call, no private WebSocket
connection, no listenKey allocation, no DeepSeek trade
decision, no real Telegram outbound, and Phase 12 stayed
**FORBIDDEN**.

## Phase 11C.1C-C-A acceptance evidence (closeout)

> The transcript below is the verbatim runner / events.db
> output captured from the operator-VPS 10 min real public WS
> smoke run against the PR #40 branch
> (`feature/phase-11c1c-c-mfe-mae-label-queue-runtime`) at
> commit `6d6044d`. The Kiro-side sandbox could not host this
> smoke (Binance-region HTTP 451 geoblock; same as the Phase
> 11C.1C-B closeout), so the operator ran it from a
> Binance-reachable VPS. **The smoke PASSED and was accepted
> as Phase 11C.1C-C-A acceptance evidence.**
>
> PR #40 merged into `main` on 2026-05-23 (mergeCommit
> `75d3c7c`); Phase 11C.1C-C-A is now recorded as **ACCEPTED**
> in the closed-phases table at the top of this document and
> in the `## Closed phase: Phase 11C.1C-C-A (ACCEPTED)`
> section above. This docs-only closeout PR mirrors the PR
> #36 → PR #37 and PR #38 → PR #39 closeout pattern.

```
branch                          : feature/phase-11c1c-c-mfe-mae-label-queue-runtime
commit                          : 6d6044d
host                            : operator VPS (Binance-reachable region)
command                         : python -m scripts.run_public_market_paper \
                                    --duration 10min --symbol-limit 5 --ws-first

# WS / runner-level metrics
duration_seconds                = 600.0
uptime                          = 608s
dry_run                         = false
ws_real_transport               = true
ws_messages_received            = 56592
ws_chains_emitted               = 27
learning_ready_attached         = 27
snapshots_emitted               = 27
ingestion_errors                = 0
HTTP 429 count                  = 0
HTTP 418 count                  = 0
rate_limit_ban                  = False
ws_reconnect_count              = 0
ws_stale_count                  = 0
ws_currently_stale              = False

# Phase 11C.1C-C-A label-runtime metrics (runner / daily report)
LABEL_TRACKING_STARTED count    = 19
LABEL_WINDOW_UPDATED count      = 38
LABEL_WINDOW_COMPLETED count    = 11
TAIL_LABEL_ASSIGNED count       = 11
MISSED_TAIL_DETECTED count      = 0
FAKE_BREAKOUT_DETECTED count    = 0
pending_label_records           = 8
completed_label_records         = 11
expired_label_records           = 0
unresolved_label_records        = 0

# events.db SQLite confirmation
LABEL_TRACKING_STARTED          | 36
LABEL_WINDOW_UPDATED            | 82
LABEL_WINDOW_COMPLETED          | 20
TAIL_LABEL_ASSIGNED             | 20

# Safety boundary (held end-to-end)
exchange_live_order_enabled     = False
live_trading_enabled            = False
llm_enabled                     = False
right_tail_enabled              = False
trading_mode_paper              = True
no live trading                 = confirmed
no API key                      = confirmed
no signed endpoint              = confirmed
no private websocket            = confirmed
no listenKey                    = confirmed
no DeepSeek trade decision      = confirmed
no real Telegram outbound       = confirmed
Phase 12                        = FORBIDDEN (gate unchanged)
```

The runner-level event counters and the events.db SQLite
counts diverge (e.g. `LABEL_TRACKING_STARTED=19` runner vs.
`36` events.db) because the runner snapshots its in-memory
aggregates at the shutdown tick while events.db captures every
emission across the full 608 s uptime including the
chain-passes that fired after the runner's last aggregate
snapshot. Both views satisfy the brief's `> 0` thresholds and
corroborate the chain-driver integration end-to-end.

`MISSED_TAIL_DETECTED=0` and `FAKE_BREAKOUT_DETECTED=0` are
valid outcomes for a 10 min window over five seed symbols and
are not gate-blocking; they record that no candidate hit the
missed-tail / fake-breakout thresholds during this particular
run.

The 5m primary tracking window closed inside the 10 min run
(11 runner / 20 events.db `LABEL_WINDOW_COMPLETED`), matching
the brief; 8 records remained `pending` (correctly waiting on
the longer 15m / 30m / 1h / 4h secondary windows) and 0
records were `expired` or `unresolved`.

Phase 1 safety lock held end-to-end across the smoke run; no
real order, no signed endpoint call, no private WebSocket
connection, no listenKey allocation, no DeepSeek trade
decision, no real Telegram outbound, and Phase 12 stayed
**FORBIDDEN**.

## Phase 11C.1C-C-B-A acceptance evidence (operator-VPS 10 min real public WS smoke PASSED)

> The transcript below is the verbatim runner output and the
> authoritative `events.db` SQLite query captured from the
> operator-VPS 10 min real public WS smoke run against the
> PR #42 branch
> (`feature/phase-11c1c-c-b-strategy-validation-cluster-control`)
> at commit `0bedcce`. The Kiro-side sandbox could not host
> this smoke (Binance-region HTTP 451 geoblock — historical
> context, same as the Phase 11C.1C-B / Phase 11C.1C-C-A
> closeouts; this is **not** the current blocker), so the
> operator ran it from a Binance-reachable VPS. **The smoke
> PASSED and was accepted as Phase 11C.1C-C-B-A acceptance
> evidence.**
>
> PR #42 merged into `main` on 2026-05-23 (mergeCommit
> `cc18047`); Phase 11C.1C-C-B-A is now recorded as
> **ACCEPTED** in the closed-phases table at the top of this
> document and in the `## Closed phase: Phase 11C.1C-C-B-A
> (ACCEPTED)` section above. This docs-only closeout PR
> mirrors the PR #36 → PR #37, PR #38 → PR #39, and PR #40 →
> PR #41 closeout pattern.
>
> Phase 11C.1C-C-B-B remains **NEXT_ALLOWED / NOT_STARTED**;
> Phase 11C.1C-C-B-A acceptance does **NOT** authorise Phase
> 11C.1C-C-B-B kickoff bypassing the standard gate; Phase 12
> remains **FORBIDDEN**.

```
branch                          : feature/phase-11c1c-c-b-strategy-validation-cluster-control
commit                          : 0bedcce
host                            : operator VPS (Binance-reachable region)
command                         : python -m scripts.run_public_market_paper \
                                    --duration 10min --symbol-limit 5 --ws-first

# Note on banner flag
# The runner does NOT support --emit-banner. The banner is emitted
# by default; pass --no-banner to suppress.

# WS / runner-level metrics
duration_seconds                = 600.0
uptime                          = 611s
dry_run                         = false
ws_real_transport               = true
ws_messages_received            = 76324
ws_chains_emitted               = 27
learning_ready_attached         = 27
snapshots_emitted               = 27
ingestion_errors                = 0

# Rate-limit / health
HTTP 429 count                  = 0
HTTP 418 count                  = 0
rate_limit_ban                  = False
ws_reconnect_count              = 0
ws_stale_count                  = 0
ws_currently_stale              = False

# Strategy Validation events (authoritative, from events.db SQLite query
# `SELECT event_type, COUNT(*) FROM events GROUP BY event_type;`,
# captured AFTER shutdown flush)
STRATEGY_VALIDATION_SAMPLE_CREATED       = 24
STRATEGY_VALIDATION_REPORT_GENERATED     =  1
STRATEGY_MODE_VALIDATED                  =  4
CANDIDATE_STAGE_VALIDATED                =  5
SCORE_BUCKET_VALIDATED                   =  8
CLUSTER_EXPOSURE_ASSESSED                =  1
CLUSTER_LEADER_VALIDATED                 =  1

# Daily-report content
daily_report_section_present    = "Phase 11C.1C-C-B-A Strategy Validation Lab v0 & Cluster Exposure Control Contracts"

# Non-empty cohort lines from the daily report
strategy_mode=reject                  n=24
candidate_stage=early                 n=24
opportunity_score_bucket=0-49         n=13
opportunity_score_bucket=50-64        n=11
early_tail_score_bucket=0-24          n=24
cluster=USDT size=22 correlated=24 leader=PAXGUSDT action=no_action

# tail_label_distribution (10 min run; 5m primary windows still in-flight)
tail_label_distribution         = unresolved x 24

# Safety boundary (Phase 1 lock unchanged end-to-end)
exchange_live_order_enabled     = False
live_trading_enabled            = False
llm_enabled                     = False
right_tail_enabled              = False
trading_mode_paper              = True
no live trading                 : confirmed
no API key                      : confirmed
no signed endpoint              : confirmed
no private websocket            : confirmed
no listenKey                    : confirmed
no DeepSeek trade decision      : confirmed
no real Telegram outbound       : confirmed
Phase 12                        : remains FORBIDDEN
```

> **Important note on the daily report's top event-count
> lines.** The daily report's top event-count lines may show
> `STRATEGY_VALIDATION_REPORT_GENERATED` /
> `STRATEGY_MODE_VALIDATED` / `CANDIDATE_STAGE_VALIDATED` /
> `SCORE_BUCKET_VALIDATED` / `CLUSTER_*` counts as **0**
> because those event counters appear to be snapshotted
> **before** shutdown flush. The **authoritative** event
> repository SQLite query (above) confirms those events were
> emitted. The daily report **section itself** rendered the
> Strategy Validation cohorts non-empty and correctly. This
> snapshot-vs-flush gap is a daily-report instrumentation
> nuance that does **not** invalidate the smoke; the SQLite
> ground truth is conclusive. A future daily-report polish
> can move the counter snapshot after the shutdown flush; it
> is **not** in scope for Phase 11C.1C-C-B-A.

### Acceptance criteria — every gate met

  - `dry_run = false` ✅
  - `ws_real_transport = true` ✅
  - `ws_messages_received = 76324` (≥ 5000) ✅
  - `ws_chains_emitted = 27` (≥ 1) ✅
  - `STRATEGY_VALIDATION_SAMPLE_CREATED = 24` (≥ 1) ✅
  - `STRATEGY_VALIDATION_REPORT_GENERATED = 1` (≥ 1) ✅
  - `STRATEGY_MODE_VALIDATED = 4` ✅ (the four canonical
    modes `follow` / `pullback` / `observe` / `reject` are
    emitted even when a cohort is empty — observed `reject`
    cohort `n=24`)
  - `CANDIDATE_STAGE_VALIDATED = 5` ✅
  - `SCORE_BUCKET_VALIDATED = 8` ✅
  - `CLUSTER_EXPOSURE_ASSESSED = 1` ✅
  - `CLUSTER_LEADER_VALIDATED = 1` ✅
  - Daily report contains the new Phase 11C.1C-C-B-A section
    with non-empty `strategy_mode` and `candidate_stage`
    cohort lines ✅
  - Safety flags unchanged (`mode=paper`,
    `live_trading=False`, `right_tail=False`, `llm=False`,
    `exchange_live_orders=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`) ✅
  - `HTTP 429 count = 0`, `HTTP 418 count = 0`,
    `rate_limit_ban = False` ✅
  - `ws_reconnect_count = 0`, `ws_stale_count = 0`,
    `ws_currently_stale = False`, `ingestion_errors = 0` ✅

The 5 m primary tracking windows that opened during the 10
min run had not all completed by shutdown, so `unresolved`
is the expected dominant `tail_label` for a 10 min run; the
`STRATEGY_VALIDATION_SAMPLE_CREATED = 24` count confirms the
runtime fired end-to-end on real Binance public WS data, and
the `STRATEGY_VALIDATION_REPORT_GENERATED = 1` event records
the shutdown flush.

Phase 1 safety lock held end-to-end across the smoke run;
no real order, no signed endpoint call, no private
WebSocket connection, no listenKey allocation, no DeepSeek
trade decision, no real Telegram outbound, and Phase 12
stayed **FORBIDDEN**.

## Phase 11C.1C-B acceptance evidence (closeout)

> The smoke-evidence transcript below is the verbatim runner
> output captured from the PR #38 branch at acceptance time.
> The banner string `Phase 11C.1C-B-IN_REVIEW v1.4.0a11c.1c.b`
> is the literal `__phase__` / `__version__` value that the
> Python runtime printed on `main` when the smoke runs were
> performed; it is preserved here because rewriting verbatim
> historical evidence would mis-state what the runner actually
> printed. Bumping the banner to drop the trailing `-IN_REVIEW`
> suffix would require a runtime-code change to
> `app/__init__.py` and is therefore reserved for a separate
> follow-up code PR; this docs-only closeout intentionally does
> NOT touch any runtime code. The Phase 11C.1C-B gate state
> recorded in the closed-phases table at the top of this
> document and in the `## Closed phase: Phase 11C.1C-B
> (ACCEPTED)` section above is the authoritative one and reads
> **ACCEPTED**.

```
test_phase11c_1c_b_runtime_calibration.py  12 passed   (brief-mandated cases)
tests/unit/ -k phase11c_                  257 passed   (no regression vs. post-PR-#37 main)
tests/                                    2231 passed   (no regression vs. post-PR-#37 main)

30 s dry-run smoke
  command:                              python -m scripts.run_public_market_paper \
                                          --duration 30s --symbol-limit 3 --dry-run \
                                          --poll-interval-seconds 1
  banner phase tag                      Phase 11C.1C-B-IN_REVIEW v1.4.0a11c.1c.b
                                        (banner now reflects the
                                        post-bump label
                                        `Phase 11C.1C-B-IN_REVIEW
                                        v1.4.0a11c.1c.b`; the
                                        underlying smoke numerics
                                        are unchanged because the
                                        bump is a code-label-only
                                        change.)
  dry_run                               True
  ws_real_transport                     False (in-process pump as expected
                                                under --dry-run)
  duration_seconds                      30
  iterations                            30
  chains_emitted                        3
  ws_chains_emitted                     60
  ws_messages_received                  122 (in-process pump)
  ws_risk_rejected                      60
  learning_ready_attached               3
  ws_learning_ready_attached            60
  snapshots_emitted                     3
  radar_candidates_seen                 60
  candidate_pool_size_max               2
  MARKET_REGIME_ASSESSED                fired per ACTIVE candidate
  CANDIDATE_STAGE_CLASSIFIED            fired per ACTIVE candidate
  OPPORTUNITY_SCORED                    fired per ACTIVE candidate
  STRATEGY_MODE_SELECTED                fired per ACTIVE candidate
  CLUSTER_CONTEXT_ATTACHED              fired per ACTIVE candidate
  LABEL_QUEUE_ENQUEUED                  fired per ACTIVE candidate
  runtime_calibration block             present on every adaptive event
                                        (15 fields verified)
  early_tail_score                      computed per ACTIVE candidate
  daily report                          contains "## Phase 11C.1C-B Adaptive
                                        Candidate Runtime Calibration &
                                        Early Tail Discovery v0"
  top_early_tail_candidates             present
  top_late_chase_risk_candidates        present (10 entries)
  early_tail_score_top_symbols          present (EDEN/ALT/NEAR slot)
  opportunity_score_distribution        present (50-60 x30, 70-80 x30)
  label_queue                           contract-only (no MFE/MAE processor)
  events.db readable                    yes
  ingestion_errors                      57  (REST budget-exhaustion refusals
                                              from the in-process governor;
                                              NOT a 429, NOT a 418, NOT a
                                              ban; expected under --dry-run
                                              once the bootstrap weight is
                                              consumed)
  rate_limit_429_count                  0
  rate_limit_418_count                  0
  rate_limit_ban                        False
  rate_limit_protection_triggered       False
  ws_stale_count                        0
  ws_reconnect_count                    0
  ws_data_degraded_ticks                0
  used_weight_1m_max                    0

5 min real public WS smoke (--ws-first, no --dry-run)
  command:                              python -m scripts.run_public_market_paper \
                                          --duration 5min --symbol-limit 5 --ws-first \
                                          --symbols BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,ADAUSDT
  banner phase tag                      Phase 11C.1C-B-IN_REVIEW v1.4.0a11c.1c.b
                                        (banner now reflects the
                                        post-bump label; the
                                        underlying smoke numerics
                                        are unchanged because the
                                        bump is a code-label-only
                                        change.)
  dry_run                               False
  ws_real_transport                     True (real RFC 6455 stdlib transport;
                                              wss://fstream.binance.com routed
                                              PUBLIC + MARKET endpoints)
  duration_seconds                      302
  iterations                            5
  chains_emitted                        12
  ws_chains_emitted                     12
  ws_messages_received                  30526
  ws_risk_rejected                      12
  ws_learning_ready_attached            12
  snapshots_emitted                     12
  radar_candidates_seen                 3029
  candidate_pool_size_max               20
  liquidation_events_seen               133
  MARKET_REGIME_ASSESSED count          72 (events.db)
  CANDIDATE_STAGE_CLASSIFIED count      72 (events.db)
  OPPORTUNITY_SCORED count              72 (events.db)
  STRATEGY_MODE_SELECTED count          72 (events.db)
  CLUSTER_CONTEXT_ATTACHED count        72 (events.db)
  LABEL_QUEUE_ENQUEUED count            72 (events.db)
  PRE_ANOMALY_DETECTED                  87
  ANOMALY_DETECTED                      87
  STATE_TRANSITION                      87
  RISK_REJECTED                         87 (`stop_unconfirmed` x24 + others)
  PUBLIC_WS_CONNECTED                   2
  PUBLIC_WS_DISCONNECTED                2
  runtime_calibration block             present on every adaptive event
                                        (15 fields verified)
  early_tail_score                      generated per ACTIVE candidate
  top_early_tail_candidates             present in daily report
                                        (3 entries: BEATUSDT 13.98, BEATUSDT
                                         4.09, NEARUSDT 0.06)
  top_late_chase_risk_candidates        present in daily report
                                        (8 entries: SOPHUSDT 17.71, PLAYUSDT
                                         16.72, WIFUSDT 14.76, SYRUPUSDT
                                         14.33, BEATUSDT 13.86 / 12.80,
                                         PROMPTUSDT 9.39, NEARUSDT 1.68)
  early_tail_score_top_symbols          present in daily report
                                        (EDEN/ALT/NEAR slot: NEARUSDT 0.06)
  opportunity_score_distribution        present in daily report
                                        (40-50 x7, 50-60 x3, 60-70 x2)
  symbols_promoted_before_24h_top_move  0 (chain), 0 (pool)
  early_tail_protect_threshold          60.00 (DEFAULT_EARLY_TAIL_PROTECT_THRESHOLD)
  label_queue                           contract-only (LABEL_QUEUE_ENQUEUED
                                        emitted; no MFE/MAE processor)
  rate_limit_429_count                  0
  rate_limit_418_count                  0
  rate_limit_ban                        False
  rate_limit_protection_triggered       False
  ws_stale_count                        0
  ws_reconnect_count                    0
  ws_currently_stale                    False
  ws_data_degraded_ticks                0
  used_weight_1m_max                    0
  public_endpoint_calls                 0  (REST fully geo-blocked at the
                                            sandbox edge; see ingestion_errors
                                            note below)
  ingestion_errors                      12  (explainable: sandbox-region
                                              geo-block on Binance REST
                                              `fapi.binance.com` returned
                                              HTTP 451 for the active-head
                                              detail REST ladder
                                              (`/fapi/v1/exchangeInfo`,
                                              `/fapi/v1/aggTrades`,
                                              `/fapi/v1/depth`,
                                              `/fapi/v1/fundingRate`,
                                              `/fapi/v1/openInterest`,
                                              `/fapi/v1/premiumIndex`,
                                              `/fapi/v1/ticker/bookTicker`).
                                              SymbolUniverse fell back to the
                                              admit-all empty universe per
                                              the documented fallback path.
                                              All 146 transport-level 451s
                                              are HTTP 451 (region geoblock),
                                              NOT a 429, NOT a 418, NOT a
                                              Binance ban, NOT a TLS / WS
                                              issue. The real WS pump
                                              (`wss://fstream.binance.com/public/stream`
                                              + `/market/stream`) ran cleanly
                                              throughout: 30526 frames, 0
                                              stales, 0 reconnects.)
  events.db readable                    yes (855 events; all six Phase
                                              11C.1C-A adaptive event types
                                              present at 72 each)
  Phase 8.5 export                      generated successfully
                                        (`ama_rt_test_data_..._export_e.zip`,
                                         438711 bytes, 855 events, 750
                                         opportunities, 87 rejections, 87
                                         state transitions, redaction
                                         applied)
```

Safety flags held throughout the Phase 11C.1C-B acceptance smoke
runs (30s dry-run + 5min real WS):

```
trading_mode                    = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
real Binance API key            = not loaded
real Binance API secret         = not loaded
real signed endpoint call       = none
real private WebSocket          = none (`/private` refused at allowlist)
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

## Phase 11C.1C-A acceptance evidence (closeout)

**Phase 11C.1C-A - Adaptive Candidate Regime & Strategy Selector
Contracts (PR #36, ACCEPTED).** Phase 11C.1C-A is the
**paper-only first version** of the data contracts + scoring +
selector + paper-only routing for the Adaptive Candidate Regime &
Strategy Selector. PR #36 has merged into `main` and PR #37
closed the docs gate. The PR shipped:

  - new `app/adaptive/` package with
    `MarketRegimeAssessment` / `CandidateStageAssessment` /
    `OpportunityScore` / `StrategyModeDecision` / `ClusterContext`
    / `LabelQueueContract` / `AdaptiveCandidateContext` value
    objects + the cheap `assess_market_regime` /
    `classify_candidate_stage` / `compute_opportunity_score` /
    `select_strategy_mode` / `build_cluster_context` /
    `build_label_queue_contract` /
    `build_adaptive_candidate_context` pure functions;
  - six new EventType entries (`MARKET_REGIME_ASSESSED` /
    `CANDIDATE_STAGE_CLASSIFIED` / `OPPORTUNITY_SCORED` /
    `STRATEGY_MODE_SELECTED` / `CLUSTER_CONTEXT_ATTACHED` /
    `LABEL_QUEUE_ENQUEUED`) emitted alongside the existing
    Phase 11C.1B WS-radar event chain;
  - Phase 8.5 `LearningReadyContext` extended with an optional
    `adaptive_candidate` field;
  - Phase 8.5 `VirtualTradePlan` extended with eleven optional
    adaptive fields (`opportunity_score`, `opportunity_grade`,
    `candidate_stage`, `strategy_mode`, `cluster_id`,
    `cluster_leader`, `label_queue_pending`, `follow_allowed`,
    `pullback_allowed`, `observe_only`, `reject_reason`);
  - `WSRadarChainDriver` builds and emits the adaptive context per
    ACTIVE candidate, attaches it to `learning_ready`, and exposes
    `adaptive_metrics_payload()` for the runner / daily report;
  - `DailyReportBuilder` accepts a new `adaptive_metrics` kwarg
    and renders the
    `## Phase 11C.1C-A Adaptive Candidate Regime & Strategy Selector`
    Markdown section.

### Phase 11C.1C-A boundary (held throughout the entire scope)

| Invariant                                   | Required value               |
| ------------------------------------------- | ---------------------------- |
| `mode`                                      | `paper`                      |
| `live_trading`                              | `False`                      |
| `right_tail`                                | `False`                      |
| `llm`                                       | `False`                      |
| `exchange_live_orders`                      | `False`                      |
| `telegram_outbound_enabled`                 | `False`                      |
| `binance_private_api_enabled`               | `False`                      |
| `safety.forbid_*` (11 flags)                | `True` for every flag        |
| Strategy mode                               | paper / virtual; not a real-trade authority |
| Adaptive event emission                     | descriptive only; never opens an order |
| MFE/MAE processor                           | NOT implemented (queue is a contract) |
| AI Learning                                 | NOT implemented              |
| Phase 12                                    | FORBIDDEN                    |

### Phase 11C.1C-A acceptance criteria (all met)

1. `pytest tests/unit/test_phase11c_1c_a_adaptive_candidate.py`
   passed (31 brief-mandated tests).
2. The full Phase 11C test surface continued to pass; total
   `tests/unit/` test count after PR #36: **2219 passed**.
3. The 30 s dry-run produced an `AdaptiveCandidateContext` for
   every active candidate and wrote the six adaptive events into
   `events.db`.
4. The 5 min real-WS paper run produced adaptive fields on every
   chain (no regression in the Phase 11C.1B 5min smoke ladder).
5. The Phase 8.5 export zip + Phase 10A replay accepted the six
   new event types without failure.
6. Every safety flag remained `False` after running the adaptive
   path end-to-end.
7. No live trading.
8. No API key.
9. No private endpoint.
10. Phase 12 stayed `FORBIDDEN`.

### Phase 11C.1C-A acceptance smoke evidence (closeout)

```
test_phase11c_1c_a_adaptive_candidate.py  31 PASS
tests/unit/                               2219 PASS  (no regression; PR #36 branch)

30 s dry-run smoke
  command:                              python -m scripts.run_public_market_paper \
                                          --duration 30s --symbol-limit 3 --dry-run
  banner phase tag                      Phase 11C.1C-B-IN_REVIEW v1.4.0a11c.1c.b
  dry_run                               True
  adaptive_candidate context generated  yes (per ACTIVE candidate)
  ws_messages_received                  6 (in-process pump)
  ws_chains_emitted                     2
  MARKET_REGIME_ASSESSED                2
  CANDIDATE_STAGE_CLASSIFIED            2
  OPPORTUNITY_SCORED                    2
  STRATEGY_MODE_SELECTED                2
  CLUSTER_CONTEXT_ATTACHED              2
  LABEL_QUEUE_ENQUEUED                  2
  daily report                          contains "## Phase 11C.1C-A Adaptive
                                        Candidate Regime & Strategy Selector"
  events.db readable                    yes
  Phase 8.5 export                      generated successfully (zip)
  ingestion_errors                      0
  rate_limit_429_count                  0
  rate_limit_418_count                  0
  rate_limit_ban                        False

5 min real public WS smoke (--ws-first, no --dry-run)
  command:                              python -m scripts.run_public_market_paper \
                                          --duration 5min --symbol-limit 5 --ws-first \
                                          --symbols BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,ADAUSDT
  banner phase tag                      Phase 11C.1C-B-IN_REVIEW v1.4.0a11c.1c.b
  dry_run                               False
  ws_real_transport                     True (real RFC 6455 stdlib transport;
                                              wss://fstream.binance.com routed
                                              PUBLIC + MARKET endpoints)
  duration_seconds                      301
  iterations                            5
  ws_messages_received                  32842
  ws_chains_emitted                     12
  candidate_pool_size_max               20
  radar_candidates_seen                 3043
  MARKET_REGIME_ASSESSED count          12
  CANDIDATE_STAGE_CLASSIFIED count      12
  OPPORTUNITY_SCORED count              12
  STRATEGY_MODE_SELECTED count          12
  CLUSTER_CONTEXT_ATTACHED count        12
  LABEL_QUEUE_ENQUEUED count            12
  adaptive_metrics section in report    present
  label_queue_enqueued                  12
  rate_limit_429_count                  0
  rate_limit_418_count                  0
  rate_limit_ban                        False
  ws_stale_count                        0
  ws_reconnect_count                    0
  ws_currently_stale                    False
  ingestion_errors                      12  (explainable: sandbox-region
                                              geo-block on REST fapi.binance.com
                                              returned HTTP 451 for active-head
                                              detail REST and exchangeInfo
                                              bootstrap; SymbolUniverse fell
                                              back to the empty admit-all
                                              universe per the documented
                                              fallback. NOT a 429, NOT a 418,
                                              NOT a Binance ban, NOT an
                                              ingestion bug. The real WS pump
                                              ran cleanly throughout.)
  events.db readable                    yes (270 events; 14 each of the six
                                              adaptive event types across the
                                              30s + 5min runs)
  Phase 8.5 export                      generated successfully (zip,
                                              119699 bytes)
```

Safety flags held throughout the Phase 11C.1C-A pre-merge smoke
runs (30s dry-run + 5min real WS):

```
trading_mode                    = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
real Binance API key            = not loaded
real Binance API secret         = not loaded
real signed endpoint call       = none
real private WebSocket          = none (`/private` refused at allowlist)
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

## Closed phase: Phase 11C.1B (historical reference)

(See "Phase 11C.1B acceptance summary" above for the full closeout
record.)

## Open phase (legacy): Phase 11C.1C

The original "Phase 11C.1C" placeholder has been split into
sequential sub-phases. Phase 11C.1C-A is **ACCEPTED (closed
2026-05-22; PR #36 merged; PR #37 docs closeout)**. Phase
11C.1C-B (Adaptive Candidate Runtime Calibration & Early Tail
Discovery v0) is **ACCEPTED (closed 2026-05-22; PR #38 merged
into `main`, mergeCommit `ce4b6de`)** — see "Closed phase: Phase
11C.1C-B (ACCEPTED)" above. Phase 11C.1C-C-A (MFE / MAE Label
Queue Runtime & Tail Outcome Tracking) is **ACCEPTED (closed
2026-05-23; PR #40 merged into `main`, mergeCommit `75d3c7c`)**
— see "Closed phase: Phase 11C.1C-C-A (ACCEPTED)" above. Phase
11C.1C-C-B (Adaptive Candidate Strategy Validation Lab &
Cluster Exposure Control) is **NEXT_ALLOWED / NOT_STARTED** —
see "Open phase: Phase 11C.1C-C-B (NEXT_ALLOWED / NOT_STARTED)"
above. Phase 12 (live trading) remains **FORBIDDEN**.

### Phase 11C.1C boundary (must hold from day one)

| Invariant                                   | Required value               |
| ------------------------------------------- | ---------------------------- |
| `mode`                                      | `paper`                      |
| `live_trading`                              | `False`                      |
| `right_tail`                                | `False`                      |
| `llm`                                       | `False`                      |
| `exchange_live_orders`                      | `False`                      |
| `telegram_outbound_enabled`                 | `False`                      |
| `binance_private_api_enabled`               | `False`                      |
| `safety.forbid_*` (11 flags)                | `True` for every flag        |
| Binance API key / secret                    | refused at construction      |
| Signed endpoint                             | refused at allowlist check   |
| `listenKey` / user data stream              | refused at WS allowlist + URL parser |
| Private WebSocket / trading WS API          | refused at WS allowlist      |
| Routed-private endpoint (`/private`)        | refused at path-root allowlist |
| DeepSeek trade-decision authority           | NOT permitted                |
| Real Telegram outbound                      | NOT permitted                |
| Phase 12 (live trading)                     | FORBIDDEN                    |

### Phase 11C.1C explicitly forbids (inherited from Phase 11C.1B)

  - Connecting to the Binance trading API.
  - Reading or storing any Binance API key / API secret /
    `listenKey`.
  - Calling any signed endpoint.
  - Subscribing to any user data stream / private WebSocket /
    trading WebSocket API / account / margin / position / leverage
    / balance / order private WS variant.
  - Connecting to the routed-private endpoint
    `wss://fstream.binance.com/private` (or any `/ws-api` /
    `/ws-fapi` / `/ws-papi` / `/trading-api` / `/userDataStream`
    path-root variant).
  - Connecting to DeepSeek as a trade-decision authority.
  - Connecting to the real Telegram outbound HTTP transport.
  - Auto-retrying after a 418, switching endpoints to evade a 418,
    rotating source IP to evade a 418.
  - Introducing a Strategy Selector with live-trading authority.
  - Enabling AI Learning that auto-decides trades.
  - Entering Phase 12.

### Phase 11C.1C acceptance gate (placeholder)

To be filled in by the Phase 11C.1C kickoff PR. At minimum the gate
will require:

  1. The Phase 1 safety lock unchanged.
  2. A real-WS smoke ladder analogous to Phase 11C.1B's 5min / 10min
     / 1h ladder, with zero 429 / 418 / stale / ingestion errors.
  3. Adaptive candidate-regime / strategy-selector decisions emitted
     as typed events into `events.db` with a Phase 8.5
     `LearningReadyContext`, but **without** authority to issue real
     orders.
  4. A source-tree audit refusing any third-party HTTP / WebSocket /
     SDK / LLM / Telegram / trading-API import on the Phase 11C.1C
     surface.
  5. The four `ExchangeClientBase` write surfaces still raise
     `SafeModeViolation` after every Phase 11C.1C run.

## Closed phase: Phase 11C.1B

**Phase 11C.1B - WebSocket-First All-Market Demon Coin Radar (PR-B).**
Phase 11C.1A (PR-A) shipped the rate-limit governor and capped per-loop
REST detail; the trade-off was that the runner could see only the
symbols the bootstrap already knew about. PR-B adds the WebSocket-first
all-market radar so the runner can discover demon coins (妖币) without
per-symbol REST detail polling. The goal is not to lower discovery
capability - it is to *raise* discovery throughput while keeping REST
pressure near zero.

PR-B subscribes to FIVE public Binance WebSocket streams only,
routed through the documented public + market USDⓈ-M Futures
WebSocket endpoints:

  - PUBLIC route (`wss://fstream.binance.com/public/stream`):
    - `!bookTicker`
  - MARKET route (`wss://fstream.binance.com/market/stream`):
    - `!ticker@arr`
    - `!miniTicker@arr`
    - `!markPrice@arr`
    - `!forceOrder@arr`

PR-B does NOT subscribe to `listenKey`, the user data stream, the
trading WebSocket API, the `/private` routed surface, or any
other private WebSocket. The default WS transport refuses to open
a real socket (`NotImplementedError`); the in-process pump is
wired under `--dry-run`; **the real-network stdlib WS adapter
(`StdlibPublicWSTransport`) and the routed
`MultiTransportPublicWSManager` ship in this PR**. The runner
refuses to silently fall back to REST under `--ws-first` without
`--dry-run`: if the real public WS pump cannot be constructed,
the runner exits with `rc=2`. Operators who genuinely cannot
reach `fstream.binance.com` use `--ws-disabled` (PR-A
bootstrap-only REST), which is documented as **not** the Phase
11C.1B all-market demon-radar acceptance path.

### Phase 11C.1B boundary (must hold for the entire PR-B scope)

| Invariant                                   | Required value               |
| ------------------------------------------- | ---------------------------- |
| `mode`                                      | `paper`                      |
| `live_trading`                              | `False`                      |
| `right_tail`                                | `False`                      |
| `llm`                                       | `False`                      |
| `exchange_live_orders`                      | `False`                      |
| `telegram_outbound_enabled`                 | `False`                      |
| `binance_private_api_enabled`               | `False`                      |
| `safety.forbid_*` (11 flags)                | `True` for every flag        |
| Binance API key / secret                    | refused at construction      |
| Signed endpoint                             | refused at allowlist check   |
| `listenKey` / user data stream              | refused at WS allowlist + URL parser |
| Private WebSocket / trading WS API          | refused at WS allowlist      |
| Routed-private endpoint (`/private`)        | refused at path-root allowlist (`FORBIDDEN_WS_PATH_ROOTS`) |
| Routed acceptance path                      | `/public/{ws,stream}` + `/market/{ws,stream}` (`ALLOWED_PUBLIC_WS_PATH_ROOTS`) |
| Stream route classification                 | `!bookTicker` -> PUBLIC; `!ticker@arr` / `!miniTicker@arr` / `!markPrice@arr` / `!forceOrder@arr` -> MARKET |
| `market_data.provider`                      | `binance_public`             |
| `market_data.read_only`                     | `True`                       |
| `candidate_pool_size` (default)             | `20`                         |
| `active_detail_limit` (default)             | `3`                          |
| `candidate_ttl_seconds` (default)           | `900`                        |
| `ws_staleness_threshold_ms` (default)       | `3000`                       |
| `radar_score_threshold` (default)           | `30.0`                       |

### Phase 11C.1B acceptance criteria

1. `pytest` 全部通过. Currently `2184 passed`.
2. The new test files
   `tests/unit/test_phase11c_1b_ws_radar.py` (scaffold + radar +
   pool + chain),
   `tests/unit/test_phase11c_1b_real_ws_adapter.py` (real public
   WS adapter + runner refusal + reconnect backoff + staleness
   gate + safety flags + RFC 6455 handshake / frame audit),
   `tests/unit/test_phase11c_1b_routed_public_market_ws.py`
   (routed `/public/{ws,stream}` + `/market/{ws,stream}`
   acceptance, `/private` refusal, stream-route classification,
   `MultiTransportPublicWSManager` merge, runner uses both
   routed transports, no follow-up wording in source / docs), and
   `tests/unit/test_phase11c_1b_symbol_universe.py`
   (exchangeInfo-as-truth gate + non-ASCII contract admission +
   `WS_SYMBOL_REJECTED` audit + source-tree audit refusing any
   ASCII-only symbol regex)
   pin every behaviour the brief calls out (15 brief-mandated +
   11 routed-endpoint + 4 SymbolUniverse + supporting). Full list
   in `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md` §11C.1B.
3. The four `ExchangeClientBase` write surfaces still raise
   `SafeModeViolation`.
4. No file in the Phase 11C source set imports a third-party HTTP /
   WebSocket / SDK / LLM / Telegram bot package. The
   `StdlibPublicWSTransport` is implemented entirely on top of
   `socket` + `ssl` + `select` + `struct` + `base64` + `hashlib`
   + `json` + `os.urandom` (RFC 6455 client).
5. The Phase 11B daily-report Markdown body contains the new
   `Phase 11C.1B WebSocket all-market radar` section with every
   brief-mandated metric, including the new `ws_real_transport`
   and `ws_data_degraded_ticks` fields.
6. The Phase 8.5 export, Phase 10A replay, and Phase 10B reflection
   pipelines accept the three new `PUBLIC_WS_*` event types.
7. Under `--ws-first` without `--dry-run`, the runner uses the real
   `StdlibPublicWSTransport` and does NOT silently fall back to
   REST bootstrap. If the transport factory returns `None` or
   raises, the runner exits with `rc=2` and the message
   `real public WebSocket transport is required for --ws-first
   without --dry-run`.

### Phase 11C.1B explicitly forbids

  - Connecting to the Binance trading API.
  - Reading or storing any Binance API key / API secret /
    `listenKey`.
  - Calling any signed endpoint.
  - Subscribing to any user data stream / private WebSocket /
    trading WebSocket API / account / margin / position / leverage
    / balance / order private WS variant.
  - Connecting to the routed-private endpoint
    `wss://fstream.binance.com/private` (or any
    `/ws-api` / `/ws-fapi` / `/ws-papi` / `/trading-api` /
    `/userDataStream` path-root variant).
  - Treating the unrouted `wss://fstream.binance.com/stream` URL
    as the WS-first acceptance path (Binance silently drops
    market-class streams over an unrouted connection).
  - Connecting to DeepSeek.
  - Connecting to the real Telegram outbound HTTP transport.
  - Connecting to Binance Square.
  - Auto-retrying after a 418.
  - Switching endpoints to evade a 418.
  - Rotating source IP to evade a 418.
  - Entering Phase 12.

### How Phase 11C.1B unblocks the Phase 11C real-data acceptance run

After PR #32 merges (which ships the routed real-network
`MultiTransportPublicWSManager` inline), the Phase 11C real-data
24h acceptance run resumes with:

  - bootstrap REST: one `exchangeInfo` + one `ticker/24hr`.
  - public routed WS:
    `wss://fstream.binance.com/public/stream?streams=!bookTicker`.
  - market routed WS:
    `wss://fstream.binance.com/market/stream?streams=!ticker@arr/!miniTicker@arr/!markPrice@arr/!forceOrder@arr`.
  - candidate pool: top N (default 20) demon coins, active head 3.
  - per-loop REST detail: ONLY for the active head, gated on the
    PR-A rate-limit governor.

### Phase 11C.1B acceptance ladder (smoke runs)

| Cloud smoke         | Command                                                                                                                              | Status (UTC)                |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | --------------------------- |
| 30 s dry-run        | `python -m scripts.run_public_market_paper --duration 30s --symbol-limit 5 --dry-run`                                                | PASS                        |
| 5 min real WS       | `python -m scripts.run_public_market_paper --duration 5min --symbol-limit 5 --ws-first`                                              | **PASS (2026-05-22)**       |
| 10 min real WS      | `python -m scripts.run_public_market_paper --duration 10min --symbol-limit 5 --ws-first`                                             | **PASS (2026-05-22)**       |
| 1 h real WS (clean) | `python -m scripts.run_public_market_paper --duration 1h --symbol-limit 5 --ws-first`                                                | **PASS (2026-05-22)**       |
| 6 h WS-first        | `python -m scripts.run_public_market_paper --duration 6h --symbol-limit 5 --ws-first`                                                | optional / not required for Phase 11C.1B closeout |
| 24 h WS-first       | `python -m scripts.run_public_market_paper --duration 24h --symbol-limit 5 --ws-first`                                               | optional / parent Phase 11C longer-window, not required for Phase 11C.1B closeout |

All three Phase 11C.1B acceptance rungs (5min / 10min / 1h) record:
`ws_messages_received > 0`, `ws_chains_emitted > 0`,
`radar_candidates_seen >= 0` (no longer stuck at 0 due to no
messages), `PUBLIC_WS_CONNECTED` written, no 429 / 418, no
`ws_stale_count`, no ingestion errors, every safety flag
unchanged. Full numerics live in
"Phase 11C.1B acceptance summary" above. The earlier failure mode
(`ws_messages_received=0` for the full 300s window of the first
5-min run) was a zero-timeout `recv` short-circuit in the stdlib
WS transport; fixed by draining the recv buffer non-blockingly at
the top of every `poll` call (PR #33).

The 6h / 24h rungs are intentionally **optional**: Phase 11C.1B
closure does NOT require them. They belong to the parent Phase
11C longer-window observation work (or to a future Phase 11C+
multi-week paper window) and remain available to anyone who wants
extra confidence before Phase 11C.1C kicks off.

The legacy command
`python -m scripts.run_public_market_paper --duration 1h --symbol-limit 20 --poll-interval-seconds 5`
is **deprecated**. It exercises the pre-PR-A "fetch every detail
endpoint for every symbol every loop" pattern that triggered HTTP
418, and it predates routed WS endpoints.

### Phase 11C.1B follow-up: SymbolUniverse (exchangeInfo-as-truth)

Binance USDⓈ-M Futures lists non-ASCII contracts in production -
documented examples include `我踏马来了USDT` and `币安人生USDT`. Each
is a real Binance contract with its own `/fapi/v1/exchangeInfo`
entry, its own all-market WS push, and its own REST detail
endpoints. The Phase 11C.1B brief therefore forbids any
character-class regex (`^[A-Z0-9_]{2,30}(USDT|USDC)$` or any
equivalent) on the symbol-validation path; the only authoritative
source is the snapshot pulled from `/fapi/v1/exchangeInfo` at
runner startup.

Implementation:

  - `app/market_data_public/symbol_universe.py` -
    `SymbolUniverse.from_exchange_info(symbols)` builds the
    bootstrapped set; `SymbolUniverse.empty()` is the back-compat
    "admit everything" fallback for dry-run / fixture tests.
  - `CandidatePool.offer()` consults the universe; symbols missing
    from the bootstrapped set surface a typed `WS_SYMBOL_REJECTED`
    event (new entry on `EventType`) and the candidate is dropped
    before it enters the pool's accounting.
  - The runner (`scripts/run_public_market_paper.main`) bootstraps
    the universe from `client.get_symbols()` before constructing
    the candidate pool. On bootstrap failure (rate-limit
    protection, network error, etc.) the runner falls back to the
    empty universe and logs the degraded note - safety flags stay
    unchanged and the pool admits everything to avoid blocking the
    smoke ladder on a transient REST fault.
  - Source-tree audit: `tests/unit/test_phase11c_1b_symbol_universe.py
    ::test_symbol_validation_uses_exchange_info_not_ascii_regex`
    walks every WS-radar / symbol-validation file and refuses
    any `re.compile|match|fullmatch|search` whose pattern smells
    like an ASCII-only symbol regex. The next PR that re-introduces
    one fails this test.

The brief is explicit: **the rejection reason is "not in
exchangeInfo", NEVER "non-ASCII character class".** A pure-ASCII
symbol that is missing from the snapshot (e.g. a brand-new listing
that came online mid-run, or a delisting whose WS pushes arrived
between bootstrap and subscribe) is treated identically to a
Chinese symbol that is missing.

PR-C (priority_score / cluster classifier / same-cluster leader /
multi-candidate arbitration) remains a separate branch.

## Closed phase: Phase 11C.1A

**Phase 11C.1A - Binance Public REST Rate Limit Governor & 418
Protection (PR-A).** Merged. The Phase 11C real-data acceptance
pause that motivated this PR was **resolved** by the combined work
of PRs #31 + #32 + #33 + #34: PR #31 shipped the rate-limit
governor here; PR #32 shipped the WebSocket-first all-market radar
+ the routed real-network public WS adapter; PR #33 fixed the
real-WS poll zero-timeout; PR #34 enforced exchangeInfo-as-truth
symbol validation. Phase 11C.1B is now ACCEPTED.

  - **PR-A** (closed, merged in PR #31)
    ships `BinancePublicRestGovernor` (sliding-window weight budget,
    429 backoff, 418 shutdown, `Retry-After`, used-weight tracking),
    lower defaults, and the layered REST runner. NO new candidate
    ranking, NO WebSocket transport.
  - **PR-B** (closed, merged in PR #32, with follow-ups PR #33 +
    PR #34)
    ships the WebSocket-first all-market radar, candidate pool
    plumbing, `candidate_detail_limit` consumption for REST detail
    enrichment, the real-network `StdlibPublicWSTransport` (RFC
    6455 over `socket` + `ssl`, stdlib only), and the routed
    `MultiTransportPublicWSManager` (one `StdlibPublicWSTransport`
    per route - PUBLIC at `/public/stream`, MARKET at
    `/market/stream`). The default WS transport still refuses to
    open a real socket (`NotImplementedError`); the in-process
    pump covers `--dry-run`; the
    `MultiTransportPublicWSManager` is selected by the runner
    whenever `--ws-first` is set without `--dry-run`. The
    routed-private endpoint `/private` is on
    `FORBIDDEN_WS_PATH_ROOTS` and is never opened.
    Multi-candidate priority ranking, `priority_score`, cluster
    classifier, same-cluster leader selection, and strategy
    selector are explicitly **NOT** in Phase 11C.1B scope: most
    of those contracts subsequently landed in Phase 11C.1C-A
    (ACCEPTED) and Phase 11C.1C-B (ACCEPTED). The MFE/MAE
    Label Queue Runtime & Tail Outcome Tracking subsequently
    landed in Phase 11C.1C-C-A (ACCEPTED 2026-05-23, PR #40
    merged, mergeCommit `75d3c7c`). The remainder (deeper
    Strategy Validation Lab, Cluster Exposure Control) is Phase
    11C.1C-C-B scope (NEXT_ALLOWED /
    NOT_STARTED).
  - **PR-C** (priority_score / cluster classifier / same-cluster
    leader / multi-candidate arbitration) is **not** Phase 11C.1B
    work. The data-contract / scoring / selector first version
    shipped in Phase 11C.1C-A (ACCEPTED); the runtime-calibration
    + Early Tail Discovery first version shipped in Phase
    11C.1C-B (ACCEPTED); the MFE/MAE Label Queue Runtime + Tail
    Outcome Tracking first version shipped in Phase 11C.1C-C-A
    (ACCEPTED). The remaining work (deeper Strategy Validation
    Lab, Cluster Exposure Control) rolls into Phase 11C.1C-C-B,
    which is currently NEXT_ALLOWED / NOT_STARTED (see "Open
    phase: Phase 11C.1C-C-B (NEXT_ALLOWED / NOT_STARTED)"
    above).

### Phase 11C.1A boundary (must hold for the entire PR-A scope)

| Invariant                                   | Required value               |
| ------------------------------------------- | ---------------------------- |
| `mode`                                      | `paper`                      |
| `live_trading`                              | `False`                      |
| `right_tail`                                | `False`                      |
| `llm`                                       | `False`                      |
| `exchange_live_orders`                      | `False`                      |
| `telegram_outbound_enabled`                 | `False`                      |
| `telegram.outbound_enabled` (schema-locked) | `False`                      |
| `binance_private_api_enabled`               | `False`                      |
| `safety.forbid_*` (11 flags)                | `True` for every flag        |
| `market_data.provider`                      | `binance_public`             |
| `market_data.read_only`                     | `True`                       |
| `market_data.symbol_limit` (default)        | `5` (was `20`, lowered)      |
| `market_data.rest_poll_interval_seconds` (default) | `60.0` (was `5.0`)    |
| `market_data.rest_governor.weight_budget_per_minute` | `300`              |
| `market_data.rest_governor.soft_weight_ratio`        | `0.50`             |
| `market_data.rest_governor.hard_weight_ratio`        | `0.75`             |
| `market_data.rest_governor.retry_after_default_seconds` | `300`           |
| `market_data.rest_governor.on_429`          | `"backoff"` (only allowed)   |
| `market_data.rest_governor.on_418`          | `"shutdown"` (only allowed)  |
| `market_data.rest_governor.candidate_detail_limit` | `3`                   |
| `market_data.rest_governor.rest_layering_enabled`  | `True`                |

### Phase 11C.1A acceptance criteria

1. `pytest` 全部通过 (currently `2089 passed`).
2. The new test file `tests/unit/test_phase11c1a_rate_limit_governor.py`
   pins, at minimum, every behaviour the brief calls out:
   - `test_429_triggers_backoff_and_stops_batch`
   - `test_418_triggers_shutdown_without_retry`
   - `test_retry_after_header_is_respected`
   - `test_used_weight_header_is_recorded`
   - `test_rest_governor_blocks_when_budget_exceeded`
   - `test_default_phase11c_polling_is_conservative`
   - `test_rest_not_called_for_all_symbols_every_loop`
   - `test_no_live_trading_flags_after_429`
   - `test_no_live_trading_flags_after_418`
   - `test_daily_report_contains_rate_limit_metrics`
3. The four `ExchangeClientBase` write surfaces still raise
   :class:`SafeModeViolation` (asserted by
   `test_phase_11c_write_surfaces_still_refuse_after_418` even after
   the governor latches into protection mode).
4. The Phase 8.5 export pipeline accepts the five new
   `RATE_LIMIT_*` event types.
5. The Phase 10A replay engine accepts the new events (no schema
   regression - asserted by the existing replay test suite).
6. The Phase 10B reflection engine accepts the new events.
7. The daily Markdown report contains the `Phase 11C.1A
   rate-limit governor` section with every required field.
8. No `binance_rate_limit.py` import touches a third-party HTTP /
   WebSocket / SDK / LLM / Telegram bot package; only stdlib +
   loguru + the existing `app.*` modules.

### Phase 11C.1A explicitly forbids

  - Connecting to the Binance trading API.
  - Reading or storing any Binance API key / API secret.
  - Calling any signed endpoint.
  - Calling any /order, /account, /position, /leverage, /margin endpoint.
  - Connecting to DeepSeek.
  - Connecting to the real Telegram outbound HTTP transport.
  - Auto-retrying after a 418.
  - Switching endpoints to evade a 418.
  - Rotating source IP to evade a 418.
  - Entering Phase 12.

### How Phase 11C.1A unblocks the Phase 11C real-data acceptance run

After PR-A merges:

  - The runner caps total per-IP weight at 300/min.
  - Bootstrap costs ~41 weight (one `exchangeInfo` + one
    `ticker/24hr`) and the steady-state loop costs ~0 weight in PR-A
    (no candidates -> no detail REST).
  - Any 429 sleeps the `Retry-After` window and emits the
    `RATE_LIMIT_429` / `RATE_LIMIT_BACKOFF_STARTED` /
    `RATE_LIMIT_BACKOFF_ENDED` audit trail.
  - Any 418 latches protection mode, opens a P1 incident, and
    stops the runner with `rc=2`. The runner does NOT auto-retry,
    does NOT switch endpoints, does NOT rotate source IP.

The Phase 11C real-data acceptance pause **was resolved** once
PR-B (WebSocket-first radar) landed alongside PR-A and its
follow-ups. Candidate ranking remains Phase 11C.1C scope. PR-B
merged via PR #32, with follow-ups in PR #33 and PR #34; the
Phase 11C.1B real-WS smoke ladder (5min / 10min / 1h) ran cleanly
on 2026-05-22 (UTC) and Phase 11C.1B is ACCEPTED.

## Phase 11C parent (open, follow-ups landed)

Phase 11C remains open as a parent / umbrella phase. Phase 11C.1A,
Phase 11C.1B, Phase 11C.1C-A, Phase 11C.1C-B, and Phase
11C.1C-C-A have all **shipped** (PRs #31 / #32 / #33 / #34 /
#36 / #38 / #40 merged into `main`); Phase 11C.1B, Phase
11C.1C-A, Phase 11C.1C-B, and Phase 11C.1C-C-A are ACCEPTED.
Phase 11C.1C-C-B (Adaptive Candidate Strategy Validation Lab +
Cluster Exposure Control) is **NEXT_ALLOWED /
NOT_STARTED**. The longer-window real-data observation rungs
(6h / 24h / multi-week) remain optional under the parent and are
NOT required for Phase 11C.1C-C-A closure. The public-market
client, allowlist, event chain, and runner skeleton continue to
satisfy the original Phase 11C acceptance gates; only the cadence
and detail-REST behaviour have been narrowed.

## Closed phases (carry-forward)

The closed-phase ledger above remains unchanged. The Phase 11C
parent phase stays open while Phase 11C.1C is drafted; longer
real-data windows (6h / 24h / multi-week) are tracked here but
are **not** Phase 11C.1B closure prerequisites.

### Phase 11C acceptance criteria

1. `pytest` 全部通过.
2. `python -m scripts.run_public_market_paper --duration 1h --symbol-limit 5 --ws-first`
   completes without exception, producing a daily report at
   `data/reports/phase11c/{date}-phase11c-public-market.md`. The
   1h WS-first run is the active Phase 11C acceptance gate; the
   6h / 24h WS-first runs are **optional** parent Phase 11C
   longer-window observation rungs (or part of a future Phase
   11C+ multi-week paper window) and are NOT required to close
   Phase 11C.1B. The legacy command
   `python -m scripts.run_public_market_paper --duration 1h --symbol-limit 20 --poll-interval-seconds 5`
   is **deprecated and must not be used** - it predates the
   PR-A rate-limit governor and the PR-B routed WS endpoints,
   and exercises the pre-PR-A "fetch every detail endpoint for
   every symbol every loop" pattern that triggered HTTP 418.
3. Real `MARKET_SNAPSHOT` events written to `events.db` carry the
   Phase 11C tag (`provider="binance_public"`, `phase="11C"`).
4. `SignalSnapshot` is built from real market data and written into
   the `learning_ready.signal_snapshot` block of every `RISK_REJECTED`
   / `STATE_TRANSITION` event.
5. `RISK_REJECTED` events carry `learning_ready.opportunity` with a
   real `opportunity_id` / `scan_batch_id` / `symbol` /
   `source_phase = "phase_11c_public_market_paper"` plus typed
   `reject_reasons` containing `"stop_unconfirmed"`.
6. `VirtualTradePlan` saved and round-trips through
   `payload_to_virtual_trade_plan`.
7. The Phase 8.5 export zip contains the dedicated streams
   (`opportunities.jsonl`, `signal_snapshots.jsonl`,
   `virtual_trade_plans.jsonl`, `risk_decisions.jsonl`,
   `state_transitions.jsonl`) populated from real-data events.
8. The Replay engine reads every Phase 11C event type without error.
9. The Reflection engine reads the Phase 11C event payload shape
   without error.
10. `assert_public_endpoint_allowed` rejects every signed / private
    endpoint listed in `FORBIDDEN_PRIVATE_ENDPOINTS`.
11. The four `ExchangeClientBase` write surfaces continue to raise
    `SafeModeViolation` on the public client.
12. The Phase 11C source-tree audit
    (`tests/unit/test_phase11c_no_network.py`) holds: no third-party
    HTTP / WebSocket / SDK / LLM / Telegram bot import; no write
    surface call; no credential-shaped parameter; no env-var read.

### What Phase 11C is allowed to read from Binance

```
GET /fapi/v1/exchangeInfo
GET /fapi/v1/ticker/24hr
GET /fapi/v1/ticker/bookTicker
GET /fapi/v1/klines
GET /fapi/v1/aggTrades
GET /fapi/v1/trades
GET /fapi/v1/depth
GET /fapi/v1/fundingRate
GET /fapi/v1/openInterest
GET /fapi/v1/premiumIndex
```

### What Phase 11C is NOT allowed to do (refused by the client)

- API key
- API secret
- any signed endpoint
- `signature` / `timestamp` / `recvWindow` / `apiKey` query parameter
- `/fapi/v1/order` / `/fapi/v1/order/test` / `/fapi/v1/batchOrders`
- `/fapi/v1/allOrders` / `/fapi/v1/openOrders` / `/fapi/v1/openOrder`
- `/fapi/v2/account` / `/fapi/v2/balance` / `/fapi/v2/positionRisk`
- `/fapi/v1/positionRisk` / `/fapi/v1/positionSide/dual`
- `/fapi/v1/leverage` / `/fapi/v1/marginType` / `/fapi/v1/positionMargin`
- `/fapi/v1/income` / `/fapi/v1/leverageBracket`
- `/fapi/v1/multiAssetsMargin` / `/fapi/v1/listenKey`
- any other non-allowlisted path

## Future phases

| Candidate          | Gate                                                                                   |
| ------------------ | -------------------------------------------------------------------------------------- |
| Phase 11C.1C-A (Adaptive Candidate Regime & Strategy Selector Contracts) | **ACCEPTED (closed 2026-05-22; PR #36 merged; PR #37 docs closeout).** Paper-mode only. See "Closed phase: Phase 11C.1C-A (ACCEPTED)" above for the closeout record. |
| Phase 11C.1C-B (Adaptive Candidate Runtime Calibration & Early Tail Discovery v0) | **ACCEPTED (closed 2026-05-22; PR #38 merged into `main`, mergeCommit `ce4b6de`).** Paper-mode only. See "Closed phase: Phase 11C.1C-B (ACCEPTED)" above for the closeout record and "Phase 11C.1C-B acceptance evidence (closeout)" below for the verbatim smoke transcript. **Phase 11C.1C-B acceptance does NOT authorise live trading, API keys, private endpoints, DeepSeek trade decisions, real Telegram outbound, or Phase 12.** |
| Phase 11C.1C-C-A (MFE / MAE Label Queue Runtime & Tail Outcome Tracking) | **ACCEPTED (closed 2026-05-23; PR #40 merged into `main`, mergeCommit `75d3c7c`).** Paper-mode only. See "Closed phase: Phase 11C.1C-C-A (ACCEPTED)" above for the closeout record and "Phase 11C.1C-C-A acceptance evidence (closeout)" above for the verbatim operator-VPS smoke transcript. **Phase 11C.1C-C-A acceptance does NOT authorise live trading, API keys, private endpoints, DeepSeek trade decisions, real Telegram outbound, Phase 11C.1C-C-B kickoff bypassing the standard gate, or Phase 12.** |
| Phase 11C.1C-C (deeper Strategy Validation + Cluster Exposure Control + full MFE/MAE processor) | Split into Phase 11C.1C-C-A (MFE / MAE Label Queue Runtime & Tail Outcome Tracking) and Phase 11C.1C-C-B (deeper Strategy Validation Lab + Cluster Exposure Control). Phase 11C.1C-C-A is now **ACCEPTED**; Phase 11C.1C-C-B is **NEXT_ALLOWED / NOT_STARTED**. Paper-mode only. See "Open phase: Phase 11C.1C-C-B (NEXT_ALLOWED / NOT_STARTED)" above. |
| Phase 11C.1C (parent, legacy) | **OPEN.** Split into 11C.1C-A (ACCEPTED), 11C.1C-B (ACCEPTED), 11C.1C-C-A (ACCEPTED), and 11C.1C-C-B (NEXT_ALLOWED / NOT_STARTED). Paper-mode only. |
| Phase 11C+ (longer paper window, e.g. 7d / 14d) | Phase 11C parent 24h acceptance closed (still optional after the 11C.1B 1h PASS).      |
| Phase 11D (DeepSeek READ-ONLY narrative interpreter) | Phase 11C closed; Phase 11C dataset reviewed.                                    |
| Phase 12 (Limited live trading) | **FORBIDDEN.** NOT permitted from Phase 11C.1B alone, NOT permitted from Phase 11C.1C-A alone, NOT permitted from Phase 11C.1C-B alone, NOT permitted from Phase 11C.1C-C-A alone, NOT permitted from Phase 11C.1C-C-B alone, NOT permitted from any Phase 11C sub-phase alone. Requires Spec §41 Go/No-Go. |

**Phase 11C.1B closing does NOT authorise Phase 12.** Phase 12 is gated
by:

  - Spec §41 Go/No-Go checklist
  - Phase 11C.1C closed
  - Phase 11D (or another Phase 11C+ window) closed
  - Multi-week paper-mode dataset reviewed
  - Operational evidence the four write surfaces, the No-Trade Gate,
    and the Reconciliation loop have held under real-data load
  - Explicit operator sign-off; Phase 12 is never auto-promoted


## Architecture governance (guidance-only; no phase change)

**Document added:**
`docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md` —
*AMA-RT Adaptive Market Operating System Governance /
自适应市场操作系统架构治理文档*.

**Type:** Guidance-only architecture governance.
**Phase ledger effect:** **none.**
**Trade authority granted:** **none.**
**Safety flag effect:** **none.**

The governance document records the long-term architectural
rails of AMA-RT (core positioning as an Adaptive Market
Operating System rather than an auto-trading bot, AI authority
boundary, stateless AI cognition, the Truth Layer, the Reality
Check Layer, anti-overfitting governance, feedback isolation,
the nine-layer architecture annotated with current state, the
not-implemented-yet backlog, and the explicit rejections list).

The governance document **does NOT** open a new phase, **does
NOT** close any existing phase, **does NOT** flip any
acceptance state on this ledger, **does NOT** advance Phase
11C.1C-C-B-B-A to ACCEPTED, **does NOT** kick off Phase
11C.1C-C-B-B-B, and **does NOT** authorise Phase 12. It is
binding as architectural guidance, **not** as a phase
transition.

The Phase 1 safety lock continues to hold and is **not**
modified by this document:

```
trading_mode                    = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
real Binance API key            = not loaded
real Binance API secret         = not loaded
real signed endpoint call       = none
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

The current state of the open phases (as recorded throughout
this document) is: **Phase 11C.1C-C-B-B-A = ACCEPTED** (PR
#44 merged into `main`, mergeCommit `3ecfc3b`); **Phase
11C.1C-C-B-B-B = NEXT_ALLOWED / NOT_STARTED** (parent;
unchanged definition — *Strategy Validation Lab (deeper) &
richer Cluster Exposure Control follow-up*); **Phase
11C.1C-C-B-B-B-A = ACCEPTED** (first child slice under Phase
11C.1C-C-B-B-B — *Paper Alpha Gate v0*; PR #52 merged into
`main` on 2026-05-24, mergeCommit `f8ba315`; closeout via PR
#54; paper / report / evidence-only — verdict is descriptive
only and grants no trade authority); **Phase
11C.1C-C-B-B-B-B = ACCEPTED** (second child slice under
Phase 11C.1C-C-B-B-B — *Regime & Cluster Cohort Evidence
Pack v0 / Regime 与 Cluster 分组证据包 v0*; PR #56 merged
into `main` on 2026-05-24, mergeCommit `1a9abe2`; closeout
via PR #57; paper / report / evidence-only — per-cohort
`status` and top-level `regime_cluster_evidence_status` are
descriptive labels only and grant no trade authority;
operator-VPS 10 min WS paper smoke PASSED with
`regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`,
`sample_count=14<20`, `completed_tail_label_count=0<10`,
`REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=1`,
`REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=5`, Phase 8.5
export bundle generated and verified, Phase 1 safety lock
held end-to-end); **Phase 11C.1C-C-B-B-B-C = ACCEPTED**
(third child slice under Phase 11C.1C-C-B-B-B —
*Long-Window Cohort Stability & Sample Sufficiency Protocol
v0 / 长窗口 Cohort 稳定性与样本充足协议 v0*; PR #58
docs-only kickoff merged into `main`; closeout via PR #59;
operator-VPS W1 / W1+ 2 h paper WS run PASSED
[`duration_seconds=7200.0`, `uptime≈7238s`, 2 h event
counts `PAPER_ALPHA_*` 18/3/3/27 + `REGIME_CLUSTER_*` 10/2,
`regime_cluster_sample_count=189`,
`completed_tail_label_count=0`, status `INSUFFICIENT_SAMPLE`
/ `INCONCLUSIVE` accepted as valid low-completed-label
evidence, 2 h export
`data/reports/exports/ama_rt_test_data_1779693570447_export_d.zip`
`manifest_event_count=23001`
`EXPORT_LONG_WINDOW_W1_2H_CHECK=PASS`], W2 4 h paper WS run
PASSED [configured `duration_seconds=14400.0`, runtime ≈
`14417s`, `iterations=237`, `chains_emitted=704`,
`ws_messages_received=1324423`,
`radar_candidates_seen=152221`,
`liquidation_events_seen=4076`, 4 h event counts
`PAPER_ALPHA_*` 24/4/4/36 + `REGIME_CLUSTER_*` 15/3,
`paper_alpha_gate_status=INCONCLUSIVE`
`sample_count=164`, `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`
`completed_tail_label_count=2` reason
`completed_tail_label_count_below_min=2<10` — progress from
0 to 2 completed labels still below 10-label threshold,
correct result, 4 h export
`data/reports/exports/ama_rt_test_data_1779708773055_export_8.zip`
`manifest_event_count=61546`
`EXPORT_LONG_WINDOW_W2_4H_CHECK=PASS`], W3 24 h upper-bound
run PASSED with watcher early-stop
[`total_elapsed_seconds=900`,
`final_tail_labels_since_start=20>=10`,
`SAMPLE_SUFFICIENCY_REACHED=final_tail_labels=20>=10`, 24 h
full runtime NOT NEEDED — proves the B-B-B-C sample
sufficiency protocol can save runtime while preserving
evidence], W3 export PASSED [latest export zip after W3
early-stop
`data/reports/exports/ama_rt_test_data_1779712866542_export_6.zip`
generated 2026-05-25 12:41 UTC `manifest_event_count=62761`
`EXPORT_LONG_WINDOW_W3_EARLY_STOP_CHECK=PASS`; W3
export-range event counts `TAIL_LABEL_ASSIGNED=495`,
`LABEL_WINDOW_COMPLETED=495`,
`STRATEGY_VALIDATION_SAMPLE_CREATED=397`,
`REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=4`,
`REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=20`,
`PAPER_ALPHA_GATE_EVALUATED=5`,
`PAPER_ALPHA_RULE_EVALUATED=45`,
`PAPER_ALPHA_COHORT_EVALUATED=30`,
`PAPER_ALPHA_REPORT_GENERATED=5`; `final_tail_labels_since_start=20`
is the watcher early-stop condition for the 900 s live
window, `TAIL_LABEL_ASSIGNED=495` is the 24 h export-range
event count — different scopes, both valid]; **B-B-B-C
acceptance is acceptance of the long-window data collection
and sample-sufficiency protocol — does NOT mean any Regime
/ Cluster has proven right-tail advantage yet, does NOT
mean strategy effectiveness is proven, does NOT authorise
live trading, does NOT authorise rule relaxation based on
low samples, does NOT authorise automatic parameter
optimisation, does NOT authorise AI Learning, does NOT
authorise changing the Risk Engine or the Execution FSM,
does NOT authorise Phase 12**; long-window protocol outputs
remain paper-only / report-only / evidence-only and grant
no trade authority; Phase 1 safety lock held end-to-end
across every window); **Phase 11C.1C-C-B-B-B-D =
NEXT_ALLOWED / NOT_STARTED** (fourth child slice under
Phase 11C.1C-C-B-B-B — *Mover Capture Recall & Missed-Tail
Coverage Audit v0 / 异动币捕捉召回与漏捕右尾覆盖审计 v0*;
defined in place by docs-only kickoff PR #60 — name, scope,
boundary, allowed outputs [`top_mover_capture_summary`,
`captured_mover_evidence`, `missed_mover_audit`,
`symbol_universe_exclusion_summary`,
`candidate_eviction_summary`, `risk_rejection_summary`,
`first_seen_latency_summary`, `capture_recall_rate`,
`missed_tail_candidate_list`, `coverage_warning`,
`insufficient_coverage_reasons`], forbidden list, key
metrics [`top_mover_count`, `captured_top_mover_count`,
`missed_top_mover_count`, `capture_recall_rate`,
`anomaly_detected_rate`, `label_tracking_rate`,
`tail_label_assigned_rate`,
`strategy_validation_sample_rate`,
`risk_rejected_mover_count`, `not_in_universe_count`,
`capacity_evicted_count`, `data_unreliable_count`,
`median_first_seen_latency_seconds`], interpretation
principles [captured-but-rejected ≠ failure;
missed-but-not-in-universe ≠ failure; coverage warning only
when in eligible universe AND clear right-tail AND
system-correctable reason; a single mover proves nothing
incl. SAGAUSDT; capture audit ≠ trading-profit evidence;
low coverage = `review`, not `relax`; high coverage does
not authorise live trading; single-coin / "妖币" reframing
forbidden], audit cadence [A1 / A2 with A3+ reserved;
operator-driven; not auto-scheduled], audit input sources
[Binance public 24 h ticker / public market data,
`EventRepository`, daily report, Phase 8.5 export / Phase
10A replay, `StrategyValidationDataset`,
`PaperAlphaGateReport`, `RegimeClusterEvidencePack`,
`SymbolUniverse` / `exchangeInfo`-as-truth catalogue,
candidate pool logs / capacity-eviction evidence], and
acceptance-gate placeholder all defined; **does NOT** flip
the slice's state — slice remains `NEXT_ALLOWED /
NOT_STARTED` after this PR, a separate docs-only closeout
PR will be authored after the operator captures A1 / A2
audit evidence and will flip the slice to `ACCEPTED`; Phase
11C.1C-C-B-B-B-C acceptance does NOT authorise Phase
11C.1C-C-B-B-B-D kickoff bypassing the standard gate
[satisfied: this is a docs-only kickoff PR with full scope,
boundary, and forbidden list]; **NOT** a new strategy,
**NOT** a trading module, **NOT** AI Learning, **NOT**
automatic parameter optimisation, **NOT** Historical 30D+
Blind Replay / Walk-forward Validation [that gate is
reserved for a Phase 12 candidate review and is explicitly
out of scope here], **NOT** a continued widening of system
complexity; inherits every prior forbidden item verbatim);
and **Phase 12 remains FORBIDDEN**.



## Closed phase: Phase 11C.1C-C-B-B-B-D-B.1 (ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY)

**Phase:** Phase 11C.1C-C-B-B-B-D-B.1 — Historical Price Path
Completeness / Kline Path Adapter v0 (*历史价格路径完整性 /
K线路径适配器 v0*).

**Status:** `ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE /
DAILY_BUCKET_ONLY` — explicitly **NOT** "intraday 1m / 5m
kline path solved".

**Type:** Paper / report / evidence-only small follow-up patch
under Phase 11C.1C-C-B-B-B-D-B. **NOT** an indefinite
extension of B1. Closeout returns the project to the main
route.

**Acceptance route:** PR #71 implementation merged into `main`
(record-level price-path resolution; operator-supplied-path
Lookahead Guard; daily-bucket adapter from
`data/historical_market_store/top_movers/*.jsonl`). The real
D-B evidence runner was rerun on `main` from the operator
VPS against the new adapter. This docs-only closeout PR
records the resulting B1.1 main-evidence run and flips the
slice from `IN_REVIEW` to `ACCEPTED_TOOLCHAIN /
PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY`.

### Required closeout statements (verbatim)

  1. **B1.1 toolchain passed.**
  2. **PR #71 evidence runner can evaluate 300 records.**
  3. **300 `POST_DISCOVERY_OUTCOME_EVALUATED` events were
     emitted.**
  4. **1 `POST_DISCOVERY_OUTCOME_REPORT_GENERATED` event was
     emitted.**
  5. **The price-path adapter is currently daily-bucket
     only (`kline_interval_used = 1d`).**
  6. **The local Historical Market Store currently supplies
     a price path for 17 of 300 records.**
  7. **283 of 300 records still lack a price path.**
  8. **`RAVEUSDT` and `STOUSDT` remain unresolved with
     `missing_reason =
     no_top_mover_row_covering_first_seen_time`.**
  9. **B1.1 does NOT mean intraday 1m / 5m kline path is
     solved.**
  10. **B1.1 does NOT solve direction.**
  11. **B1.1 does NOT prove strategy profitability.**
  12. **B1.1 does NOT authorise auto-tuning.**
  13. **B1.1 does NOT authorise DeepSeek trade decisions.**
  14. **Phase 12 remains FORBIDDEN.**

### B1.1 evidence run output (operator VPS, real D-A export)

Output directory:
`data/reports/post_discovery_outcome/pr71_main_price_path_evidence`

Summary:

  - `status = EVIDENCE_GENERATED`
  - `evaluated_count = 300`
  - `report_generated_count = 1`
  - `event_counts.POST_DISCOVERY_OUTCOME_EVALUATED = 300`
  - `event_counts.POST_DISCOVERY_OUTCOME_REPORT_GENERATED = 1`
  - `kline_interval_used = 1d`

Price path resolution coverage:

  - `price_path_records_loaded = 17`
  - `price_path_records_missing = 283`

Price path source summary:

  - `historical_market_store_daily_top_movers = 17`
  - `absent = 283`

Price path missing-reason summary:

  - `no_top_mover_row_covering_first_seen_time = 133`
  - `no_first_seen_time = 110`
  - `insufficient_post_first_seen_points = 40`

Notable symbol price-path summary:

  - `RAVEUSDT` — `loaded = false`,
    `loaded_record_count = 0`, `record_count = 17`,
    `source = absent`, `missing_reason =
    no_top_mover_row_covering_first_seen_time`.
  - `STOUSDT` — `loaded = false`,
    `loaded_record_count = 0`, `record_count = 3`,
    `source = absent`, `missing_reason =
    no_top_mover_row_covering_first_seen_time`.

Warnings:

  - `d_a_backfill_records_missing_using_record_audited_fallback`
    (Format B fallback engaged; expected for the real D-A
    export shape; carried over from the B1 closeout and
    unchanged in B1.1).

Main-evidence check: **`B1_1_PRICE_PATH_MAIN_EVIDENCE_CHECK
= PASS`**.

### What this acceptance level MEANS

  - **The B1.1 toolchain works end-to-end against the real
    D-A export.** The price-path adapter
    (`app/adaptive/post_discovery_price_path_adapter.py`)
    resolves price paths at **record level** (not
    symbol-only and not first-record-wins) and enforces the
    operator-supplied-path Lookahead Guard (no point with
    `timestamp > first_seen_time_utc_ms` may serve as
    `first_seen_price`). The runner emits 300
    `POST_DISCOVERY_OUTCOME_EVALUATED` events plus 1
    `POST_DISCOVERY_OUTCOME_REPORT_GENERATED` event under
    `data/reports/post_discovery_outcome/pr71_main_price_path_evidence/`.
  - **Coverage is partial.** Only 17 of 300 records have an
    adapter-loaded price path today; 283 of 300 remain
    `absent`. The dominant missing reasons are
    `no_top_mover_row_covering_first_seen_time = 133`,
    `no_first_seen_time = 110`, and
    `insufficient_post_first_seen_points = 40`.
  - **The price-path resolution is daily-bucket only.**
    `kline_interval_used = 1d`. For the containing day only
    the close at `day_end_ms` is emitted (intra-day
    open / high / low timestamps are unknown and may have
    been before `first_seen_time`); for subsequent days the
    daily high / low are stamped at `day_end_ms`, surfaced
    as `approximate_intra_day_timestamps = true`. **B1.1
    does NOT solve the intraday 1m / 5m kline path
    problem.**

### What this acceptance level does NOT MEAN

  - **B1.1 does NOT mean intraday 1m / 5m kline path is
    solved.** It is daily-bucket only.
  - **B1.1 does NOT solve direction.** No `long` / `short`
    / `entry` / `exit` / `stop` / `target` /
    `position_size` / `leverage` field is emitted.
  - **B1.1 does NOT prove strategy profitability.** No PnL
    was simulated; no order was submitted; no Risk Engine
    decision was reproduced.
  - **B1.1 does NOT authorise auto-tuning.** No
    `symbol_limit` expansion, anomaly threshold change,
    candidate-pool capacity change, Regime weight change,
    or any other runtime knob is authorised by this
    closeout. "Looking at the answer key" against the
    post-hoc reference set is forbidden.
  - **B1.1 does NOT authorise DeepSeek trade decisions.**
    DeepSeek remains read-only / sandbox-only / offline
    under the AI Layer Constitution.
  - **Phase 12 remains FORBIDDEN.**

### Next allowed route (mainline; back on the main route)

> **Next allowed route: B2 — Severe Missed Tail Triage v0.**

B1 is a focused branch off the mainline and is **not** to
be extended indefinitely. B1.1 is the small patch on B1,
and B1.1 closeout returns the project to the main route.
The next allowed slice is **B2 — Severe Missed Tail Triage
v0**.

B2 will perform root-cause triage on unresolved
severe-miss cases such as `RAVEUSDT` and `STOUSDT`,
attributing each into a **closed bucket** that includes
(but is not limited to):

  - `PRICE_PATH_GAP`
  - `DATA_UNRELIABLE`
  - `EVENT_HISTORY_MISSING`
  - `UNIVERSE_GAP`
  - `SYMBOL_LIMIT_GAP`
  - `CANDIDATE_POOL_EVICTED`
  - `THRESHOLD_TOO_STRICT`
  - `WS_DATA_GAP`
  - `REST_REFERENCE_GAP`
  - `RISK_REJECTED_BUT_MOVED`
  - `TRUE_DISCOVERY_FAILURE`
  - `UNKNOWN`

B2 remains forbidden from authorising:

  - auto-tuning;
  - any threshold change;
  - `symbol_limit` expansion;
  - candidate-pool capacity change;
  - Regime weight change;
  - live trading;
  - DeepSeek trade decision;
  - Phase 12.

A *Historical Kline Store Builder / Intraday Price Path
Backfill* (sometimes referred to as "B1.2") is **NOT**
started now. It is recorded as an **optional future
data-quality task only**, available **only if** B2 triage
proves that severe-miss attribution is blocked by missing
intraday price paths, and **only with explicit owner
approval**. It is **not** the recommended next slice, **not**
a precondition for B2, and **does not** block B2.

### Forbidden (under B1.1 closeout and remaining so)

  - **Phase 12** (real money / live trading) — remains
    **FORBIDDEN**;
  - Binance private API (no API key, no API secret, no
    signed endpoint, no `listenKey`, no private WS);
  - live orders;
  - real Telegram outbound;
  - DeepSeek / LLM trade decisions (direction, position
    size, leverage, stop-loss, target price, execution
    command, runtime config patch);
  - automatic parameter tuning (incl. `symbol_limit`
    expansion, anomaly threshold change, candidate pool
    capacity change, Regime weight change);
  - blind walk-forward via D-B / B1.1 alone;
  - any rule relaxation based on D-B / B1.1 labels;
  - any Telegram command that bypasses the Risk Engine;
  - extending B1 / B1.1 indefinitely instead of returning
    to the main route.

### Safety boundary (held end-to-end)

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - no private API
  - no live orders
  - no real Telegram outbound
  - no DeepSeek trade decision
  - **Phase 12 = FORBIDDEN**

The Risk Engine remains the single trade-decision gate.

### Docs-only invariants (this closeout PR)

  - **Docs-only.** Only files under `docs/` are modified.
  - **No runtime files changed.** No file under `app/`,
    `scripts/`, `tests/`, `configs/`, `risk/`,
    `execution/`, `exchanges/`, `llm/`, `telegram/`, or
    database schema is touched by this PR.
  - **No event names changed.** No `EventType` enum /
    event-name string is added, removed, or renamed.
  - **No tests run.** This PR did not invoke `pytest`,
    `unittest`, or any test runner.
  - **No paper run / export / replay / historical builder
    invoked.**
  - **No real API contacted.**




## Phase 11C.1C-C-B-B-B-E-B — Reflection Extension for 11C Adaptive Events v0 (IN_REVIEW)

**Status:** IN_REVIEW (implementation PR; awaits maintainer review).
**Block:** Block C2 (Reflection Extension v0).
**Predecessors:** Phase 11C.1C-C-B-B-B-E-A *Replay Extension for 11C
Adaptive Events v0* merged via PR #78. Block C2 is therefore allowed
to start.
**Successor allowed by this phase:** Phase 11C.1C-C-B-B-B-E-C *C3
Evidence Contract Baseline* only. **No other phase is unlocked.**

### What this phase does

Adds a read-only reflection extension under `app/reflection/` that
turns every supported Phase 11C adaptive event into one
deterministic `AdaptiveReflectionCase` and aggregates them into one
`AdaptiveReflectionSummary`. Public surface:

  - `AdaptiveReflectionTag` — closed enum of 19 tags including the
    18 brief-mandated tags (`early_discovery`, `late_discovery`,
    `missed_tail`, `severe_miss`, `candidate_evicted_before_tail`,
    `risk_rejected_then_moved`, `false_negative_reject`,
    `correct_protective_reject`, `weak_pre_anomaly`,
    `fake_breakout_detected`, `late_top_chase`,
    `post_discovery_no_edge`, `data_gap`, `insufficient_history`,
    `degraded_discovery_quality`, `insufficient_evidence`,
    `needs_operator_review`, `needs_data_recovery`,
    `needs_rule_review`).
  - `AdaptiveReflectionSeverity` — closed severity enum
    (`info` / `low` / `medium` / `high` / `severe` / `unknown`).
  - `AdaptiveReflectionInput`, `AdaptiveReflectionCase`,
    `AdaptiveReflectionSummary` — frozen dataclasses with
    deterministic `to_payload()` and a recursive
    `_assert_no_forbidden_keys` guard.
  - `Reflection11CAdaptiveEngine` — pure stateless engine with
    `reflect_event(ev)` and `reflect_events(events)`.

The supported event groups are `LABEL_*`, `TAIL_LABEL_*`,
`MISSED_TAIL_*`, `FAKE_BREAKOUT_*`, `STRATEGY_VALIDATION_*`,
`PAPER_ALPHA_*`, `REGIME_CLUSTER_*`, `MOVER_CAPTURE_*`,
`HISTORICAL_MOVER_COVERAGE_*`, `POST_DISCOVERY_OUTCOME_*`,
`REJECT_TO_OUTCOME_*`, `SEVERE_MISSED_TAIL_*`, and
`DISCOVERY_QUALITY_*`. No new event types are introduced.

### What this phase does NOT do

  - Reflection only emits **structured tags / summaries / counts /
    warnings**. No trade advice, no AI / DeepSeek text, no
    natural-language hallucination.
  - It does **NOT** authorise live trading.
  - It does **NOT** authorise auto-tuning.
    `auto_tuning_allowed=False` is hard-pinned on every emitted
    case + summary; even a malicious caller that overrides the
    field gets `False` back from `to_payload()`.
  - It does **NOT** call an LLM, DeepSeek, or any natural-language
    model.
  - It does **NOT** depend on chat history.
  - It does **NOT** mutate `events.db` or any runtime knob.
  - It does **NOT** close out cloud evidence.
  - It does **NOT** start C3 Evidence Contract Baseline.
  - It does **NOT** unlock Phase 12. Phase 12 remains **FORBIDDEN**.

### Safety boundary (held end-to-end)

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - no Binance API key / secret
  - no signed endpoint
  - no private websocket
  - no `listenKey`
  - no real Telegram outbound
  - no DeepSeek trade decision
  - **Phase 12 = FORBIDDEN**

### Forbidden modifications (held end-to-end)

  - no edit under `app/risk/**`
  - no edit under `app/execution/**`
  - no edit under `app/exchanges/**`
  - no edit under `app/llm/**`
  - no edit under `app/telegram/**`
  - no edit under `app/config/**`
  - no change to `symbol_limit`
  - no change to anomaly thresholds
  - no change to `candidate_pool`
  - no change to regime weights
  - no `runtime_config_patch` produced
  - no `buy` / `sell` / `long` / `short` / `position_size` /
    `leverage` / `stop` / `target` / `risk_budget` produced

### Acceptance signal

The implementation PR ships:

  - `app/reflection/adaptive_11c.py` (new module)
  - `app/reflection/__init__.py` (re-export of new symbols)
  - `tests/unit/test_reflection_11c_adaptive_events.py` (new
    test module covering the brief's required test surface)
  - `docs/PHASE_11C_1C_C_B_B_B_E_B_REFLECTION_EXTENSION_11C_EVENTS.md`
    (this phase's design + acceptance doc)
  - `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
    `docs/CHANGELOG.md` updates

Tests on this PR:
`tests/unit/test_reflection_11c_adaptive_events.py` 42/42 PASS;
full `tests/unit` 2680/2680 PASS.

The phase is marked **IN_REVIEW** here. Maintainer-led review of
the implementation PR is the only path to **ACCEPTED**.



## Phase 11C.1C-C-B-B-B-E-A — Replay Extension for 11C Adaptive Events v0 (IN_REVIEW)

**Status:** IN_REVIEW (implementation PR; awaits maintainer review).
**Block:** Block C1 (Replay Extension v0).
**Predecessors:** Block A complete; Block B implementation chain
complete (D-A, D-B, B1.1, B2-A, B2-B, B3); Block B Integrated
Evidence Checkpoint = `PARTIAL_EVIDENCE` with
`next_allowed_phase = Phase 11C.1C-C-B-B-B-E-A`,
`phase_12_forbidden = True`, `auto_tuning_allowed = False`,
`known_blockers = []`. Block C1 is therefore allowed.
**Successor allowed by this phase:** Phase 11C.1C-C-B-B-B-E-B
*Reflection Extension for 11C Adaptive Events v0*. **No other
phase is unlocked.**

### What this phase does

Adds a read-only replay extension under `app/replay/` that
reconstructs the Phase 11C adaptive / discovery / evidence event
chain into eight deterministic value objects:

  - `ReplayDiscoveryTimeline`
  - `ReplayCandidateLifecycle`
  - `ReplayTailOutcome`
  - `ReplayMoverCoverageCase`
  - `ReplayPostDiscoveryOutcomeCase`
  - `ReplayRejectAttributionCase`
  - `ReplaySevereMissCase`
  - `ReplayDiscoveryQualityCase`

The supported event groups are `LABEL_*`, `TAIL_LABEL_*`,
`MISSED_TAIL_*`, `FAKE_BREAKOUT_*`, `STRATEGY_VALIDATION_*`,
`PAPER_ALPHA_*`, `REGIME_CLUSTER_*`, `MOVER_CAPTURE_*`,
`HISTORICAL_MOVER_COVERAGE_*`, `POST_DISCOVERY_OUTCOME_*`,
`REJECT_TO_OUTCOME_*`, `SEVERE_MISSED_TAIL_*`, and
`DISCOVERY_QUALITY_*`.

### What this phase does NOT do

  - It does **NOT** authorise live trading.
  - It does **NOT** authorise auto-tuning. The replay extension
    explicitly carries `auto_tuning_allowed=False` where applicable
    and never produces a `runtime_config_patch`.
  - It does **NOT** close out cloud evidence.
  - It does **NOT** start Reflection (Phase 11C.1C-C-B-B-B-E-B).
  - It does **NOT** wire in DeepSeek.
  - It does **NOT** unlock Phase 12. Phase 12 remains **FORBIDDEN**.

### Safety boundary (held end-to-end)

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - no Binance API key / secret
  - no signed endpoint
  - no private websocket
  - no `listenKey`
  - no real Telegram outbound
  - no DeepSeek trade decision
  - **Phase 12 = FORBIDDEN**

### Forbidden modifications (held end-to-end)

  - no edit under `app/risk/**`
  - no edit under `app/execution/**`
  - no edit under `app/exchanges/**`
  - no edit under `app/llm/**`
  - no edit under `app/telegram/**`
  - no edit under `app/config/**`
  - no change to `symbol_limit`
  - no change to anomaly thresholds
  - no change to `candidate_pool`
  - no change to regime weights
  - no `runtime_config_patch` produced
  - no buy / sell / long / short / position_size / leverage /
    stop / target / risk_budget produced

### Acceptance signal

The implementation PR ships:

  - `app/replay/adaptive_replay_11c.py` (new module)
  - `tests/unit/test_replay_11c_adaptive_events.py` (new test
    module covering the brief's 10 numbered checks)
  - `docs/PHASE_11C_1C_C_B_B_B_E_A_REPLAY_EXTENSION_11C_EVENTS.md`
    (this phase's design + acceptance doc)
  - `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
    `docs/CHANGELOG.md` updates

The phase is marked **IN_REVIEW** here. Maintainer-led review of
the implementation PR is the only path to **ACCEPTED**.




## Phase 11C.1C-C-B-B-B-E-C — Evidence Contract Baseline v0 (IN_REVIEW)

**Status:** IN_REVIEW (implementation PR; awaits maintainer review).
**Block:** Block C3 (Evidence Contract Baseline v0).
**Predecessors:** Block A complete; Block B implementation chain
complete; Block B Integrated Evidence Checkpoint =
`PARTIAL_EVIDENCE` (advance allowed); Block C1
(Phase 11C.1C-C-B-B-B-E-A *Replay Extension for 11C Adaptive Events
v0*) merged; Block C2 (Phase 11C.1C-C-B-B-B-E-B *Reflection
Extension for 11C Adaptive Events v0*) merged.
**Successor allowed by this phase:** Block C closeout (whole-block,
**not** per-PR) **OR** AI Evidence Bundle preparation later. **No
other phase is unlocked.**

### What this phase does

Adds a paper / report / evidence-only `evidence_refs` contract under
`app/evidence/` so every Block A / Block B output surface that
today carries a free-form `evidence_refs` tuple (report / replay /
reflection / discovery-quality / post-discovery / severe-miss /
reject-attribution) can be validated against a single rule:

> Any claim must be traceable to evidence; a claim that lacks
> evidence MUST be degraded, NEVER accepted as fact, and NEVER
> silently dropped.

The package ships:

  - `EvidenceRefType` (closed enum: `EVENT`, `SYMBOL`,
    `OPPORTUNITY`, `SCAN_BATCH`, `METRIC`, `REPORT`, `UNKNOWN`)
  - `ClaimStatus` (closed enum: `ACCEPTED`,
    `DEGRADED_NO_EVIDENCE`, `REJECTED_INVALID_EVIDENCE`,
    `PARTIAL`, `INSUFFICIENT_EVIDENCE`)
  - `EvidenceRef`, `EvidenceClaimInput`, `EvidenceClaim`,
    `EvidenceContractResult` value objects
  - `parse_evidence_ref(raw)`, `EvidenceContractValidator`,
    `validate_claims(claims)`
  - three new descriptive event types on
    `app.core.events.EventType`: `EVIDENCE_CONTRACT_VALIDATED`,
    `EVIDENCE_CLAIM_DEGRADED`, `EVIDENCE_CLAIM_REJECTED`.

### What this phase does NOT do

  - It does **NOT** authorise live trading.
  - It does **NOT** authorise auto-tuning. Every emitted
    `EvidenceContractResult` carries `auto_tuning_allowed=False`,
    hard-pinned at the `to_dict` boundary.
  - It does **NOT** call DeepSeek / any LLM. It is rule-based.
  - It does **NOT** retrofit existing surfaces. Block A / Block B
    surfaces continue to ship `evidence_refs: tuple[str, ...]`
    fields exactly as they did before this phase.
  - It does **NOT** close out cloud evidence (closeout is done
    per-block, not per-PR).
  - It does **NOT** start Phase 12. **Phase 12 remains
    FORBIDDEN.**

### Safety boundary (held end-to-end)

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - no Binance API key / secret
  - no signed endpoint
  - no private websocket
  - no `listenKey`
  - no real Telegram outbound
  - no DeepSeek trade decision
  - **Phase 12 = FORBIDDEN**

### Forbidden modifications (held end-to-end)

  - no edit under `app/risk/**`
  - no edit under `app/execution/**`
  - no edit under `app/exchanges/**`
  - no edit under `app/llm/**`
  - no edit under `app/telegram/**`
  - no edit under `app/config/**`
  - no change to `symbol_limit`
  - no change to anomaly thresholds
  - no change to `candidate_pool`
  - no change to regime weights
  - no `runtime_config_patch` produced
  - no buy / sell / long / short / position_size / leverage /
    stop / target / risk_budget produced

### Acceptance signal

The implementation PR ships:

  - `app/evidence/__init__.py` (new package)
  - `app/evidence/evidence_contract.py` (new module)
  - `app/core/events.py` — three new descriptive event types only
  - `tests/unit/test_evidence_contract_baseline.py` (covers the
    brief's 10 numbered checks plus closed-vocabulary integrity
    and Mapping-input compatibility)
  - `docs/PHASE_11C_1C_C_B_B_B_E_C_EVIDENCE_CONTRACT_BASELINE.md`
    (this phase's design + acceptance doc)
  - `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
    `docs/CHANGELOG.md` updates

The phase is marked **IN_REVIEW** here. Maintainer-led review of
the implementation PR is the only path to **ACCEPTED**.



## Phase AI-CHECKPOINT — AI Integrated Checkpoint v0 (IN_REVIEW)

**Status:** IN_REVIEW (implementation PR; awaits maintainer review).
**Block:** AI Layer — end-to-end paper / report / evidence-only
roll-up of the AI-1 → AI-2 → AI-3 → AI-4 (offline sandbox / fake
provider) → AI-5 → AI-6 chain into one descriptive
`ai_integrated_checkpoint_report.json` (plus a Markdown twin).
**Predecessors:** Phase AI-1 (PR #82), Phase AI-2 (PR #83),
Phase AI-3 (PR #84), Phase AI-4 (PR #85), Phase AI-5 (PR #86),
and Phase AI-6 (PR #87) all merged into `main`.
**Type:** Implementation PR (paper / report / evidence-only).
**Runtime effect:** **none on real trading.** One new runner
`scripts/run_ai_integrated_checkpoint.py`, one new unit-test
module `tests/unit/test_ai_integrated_checkpoint.py` (22
PASSING tests), and one new phase doc
`docs/PHASE_AI_INTEGRATED_CHECKPOINT.md`. No file under
`app/risk/`, `app/execution/`, `app/exchanges/`,
`app/telegram/`, `app/config/`, no file under `app/ai/`,
`app/replay/`, or `app/reflection/`, no event type wired into
the runtime hot path, and no database schema / migration is
touched. The runner is read-only / write-only; it reads only
local files under `--block-c-report` / `--evidence-bundle` /
`--sandbox-output` / `--operator-briefing-dir` and writes only
files under `--output-dir`. The runner imports only
`app.ai.evidence_bundle` (for the canonical forbidden-field
list) and `app.reflection.ai_reflection` (for the AI-6
convenience wrapper); it does **NOT** import `app.risk`,
`app.execution`, `app.exchanges`, `app.telegram`, or
`app.config`; it does **NOT** import any HTTP / network
library (`openai` / `anthropic` / `deepseek` / `httpx` /
`requests` / `aiohttp` / `urllib3` / `websocket` /
`websockets` / `grpc` / `boto3` / `socket`). A unit test
additionally monkeypatches `socket.socket` to refuse-on-call
and runs the full `EVIDENCE_GENERATED` path to prove no
socket is opened. The `--use-fake-provider` flag is
descriptive only; the runner NEVER opens the network
regardless of its value. **Phase ledger effect:** opens Phase
AI-CHECKPOINT as **`IN_REVIEW`** (not `ACCEPTED` until
maintainer review of the PR). **Safety flag effect:** **none.**
`mode=paper`, `live_trading=False`,
`exchange_live_orders=False`, `right_tail=False`, `llm=False`,
`llm_outbound_enabled=False`, `sandbox_only=True`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`, `trade_authority=False`,
`auto_tuning_allowed=False`, `phase_12_forbidden=True`,
`stateless_inference=True`, `feedback_isolation=True`,
`ai_output_is_commentary_only=True`,
`ai_output_can_be_truth=False`,
`ai_output_can_be_training_label=False`,
`ai_output_can_be_tail_label=False`,
`ai_output_can_be_strategy_sample=False` are re-pinned at
every `to_dict()` boundary; the recursive
`_assert_no_forbidden_keys` guard refuses to emit any
payload that carries a trade-action / runtime-config-patch
/ "live ready" / "trading approved" / "phase_12_allowed"
key at any nesting depth.

### Status taxonomy (intentionally NOT `ACCEPTED`)

  - `INSUFFICIENT_EVIDENCE` — none of the AI-1 / AI-4 /
    AI-5 artefacts are on disk AND no Block C report is on
    disk; `next_allowed_phase = NEEDS_AI_OPERATOR_EVIDENCE`.
  - `PARTIAL_EVIDENCE` — the AI-1 → AI-6 chain runs end-
    to-end but at least one stage uses
    `source=fallback_fixture`, OR the AI-4 sandbox carries
    degraded / rejected / reality-check-failed claims, OR
    the AI-6 axes did not produce a case;
    `next_allowed_phase = Offline Rule Sandbox Replay
    preparation / AI operator evidence run (paper /
    read-only)`.
  - `EVIDENCE_GENERATED` — the AI-1 → AI-6 chain runs end-
    to-end with operator-supplied artefacts, no fallback
    fixture is in the chain, AI-4 claims are
    `SUPPORTED_INTELLIGENCE` /
    `reality_check_status=SUPPORTED`, AI-6 produced ≥1
    replay case AND ≥1 reflection case;
    `next_allowed_phase = Offline Rule Sandbox Replay v0
    preparation (paper / read-only)`.

### What this phase does NOT do

  - It does **NOT** authorise live trading. **NOT** trade
    authority. **NOT** auto-tuning.
  - It does **NOT** authorise the DeepSeek hot path; the
    DeepSeek HTTP transport remains a refusal-only
    skeleton.
  - It does **NOT** authorise Telegram live outbound. The
    runner never imports `app.telegram` and never calls a
    Telegram transport.
  - It does **NOT** make any live LLM call; the runner
    cannot open a socket.
  - It does **NOT** modify any runtime knob
    (`symbol_limit`, anomaly thresholds, `candidate_pool`,
    Regime weights, strategy parameters).
  - It does **NOT** retrofit `app/risk/`,
    `app/execution/`, `app/exchanges/`, `app/telegram/`,
    or `app/config/`.
  - It does **NOT** wire AI output into any trade-decision
    surface; AI output is *commentary substrate* only.
  - **AI output cannot become Truth Layer fact, training
    label, tail label, or strategy validation sample.**
  - It does **NOT** start Phase 12. **Phase 12 remains
    FORBIDDEN.**

### Tests

`python -m pytest tests/unit/test_ai_integrated_checkpoint.py -q`
ships 22 PASSING tests covering all 15 brief-mandated
scenarios plus output paths, CLI exit codes, the
degraded-claim path, and the socket-monkeypatched no-network
test.

### Successor allowed

A successful AI integrated checkpoint only authorises the
next allowed paper-only step:

  - **`Offline Rule Sandbox Replay v0` preparation (paper /
    read-only)** when `status=EVIDENCE_GENERATED`.
  - **`Offline Rule Sandbox Replay preparation / AI
    operator evidence run` (paper / read-only)** when
    `status=PARTIAL_EVIDENCE`.
  - **`NEEDS_AI_OPERATOR_EVIDENCE`** when
    `status=INSUFFICIENT_EVIDENCE`.

No other phase is unlocked. Phase 12 remains **FORBIDDEN**.

The phase is marked **IN_REVIEW** here. Maintainer-led
review of the implementation PR is the only path to
**ACCEPTED**.



## Phase AI-6 — AI Replay / Reflection Integration v0 (IN_REVIEW)

**Status:** IN_REVIEW (implementation PR; awaits maintainer review).
**Block:** AI Layer — first audit integration runtime artefact
that projects Phase AI-1 / AI-4 / AI-5 JSON artefacts into
deterministic replay / reflection cases. Sixth runtime artefact
gated by `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`.
**Predecessors:** Phase AI-1 *AI Evidence Bundle Builder v0*
merged into `main` (PR #82). Phase AI-2 *Truth Layer / AI
Evidence Citation Contract v0* merged into `main` (PR #83).
Phase AI-3 *Reality Check Layer v0* merged into `main`
(PR #84). Phase AI-4 *DeepSeek Offline Sandbox v0* merged
into `main` (PR #85). Phase AI-5 *Operator Briefing /
Evidence Compression v0* merged into `main` (PR #86).
**Type:** Implementation PR (paper / report / sandbox-only).
**Runtime effect:** **none on real trading.** Two new read-only
modules `app/replay/ai_replay.py` and
`app/reflection/ai_reflection.py` are added alongside the
existing Phase 10A / 10B / 11C replay / reflection surfaces, with
`app/replay/__init__.py` and `app/reflection/__init__.py`
extended to re-export the Phase AI-6 public surface, and a
matching unit-test module under
`tests/unit/test_ai_replay_reflection_integration.py` (177 unit
tests). No file under `app/risk/`, `app/execution/`,
`app/exchanges/`, `app/telegram/`, `app/config/`, no file under
`app/ai/`, no event type wired into the runtime hot path, no
database schema / migration is touched. The modules are read-
only: they never append, mutate, or reorder rows in
`events.db`; they never produce direction, sizing, leverage,
stop, target, or risk-budget fields; they never produce a
`runtime_config_patch`; and they never call an LLM / DeepSeek /
Telegram outbound. No runtime knob (`symbol_limit`, anomaly
threshold, candidate-pool capacity, Regime weights) is changed.
**Phase ledger effect:** opens Phase AI-6 as **`IN_REVIEW`**
(not `ACCEPTED` until maintainer review of the PR).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False`,
`llm_outbound_enabled=False`, `sandbox_only=True`,
`allow_trade_decision=False`,
`allow_runtime_config_change=False`,
`require_evidence_refs=True`, `require_reality_check=True`,
`stateless_inference=True`, `feedback_isolation=True`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`. No Binance API key, no
API secret, no signed endpoint, no private WebSocket, no
`listenKey`, no DeepSeek trade decision, no real DeepSeek HTTP
transport, no real Telegram outbound. **Phase 12 remains
FORBIDDEN.**
**Auto-tuning effect:** **none.**
`auto_tuning_allowed=False` is hard-pinned at every
`to_dict()` boundary even if a caller flips the dataclass
field. The recursive `_assert_no_forbidden_fields` guard
refuses to emit any payload carrying a `*_patch` key.
**AI output isolation:** every emitted payload re-pins
`ai_output_can_be_truth=False`,
`ai_output_can_be_training_label=False`,
`ai_output_can_be_tail_label=False`,
`ai_output_can_be_strategy_sample=False`,
`ai_output_is_commentary_only=True`. Even if a downstream
caller flips the dataclass field via `object.__setattr__`,
the serialiser re-emits the safe values.
**Reflection-tag forbid-list:** the closed
`AIReflectionTag` enum intentionally **omits**
`ai_said_buy` / `ai_said_long` / `ai_target_hit` /
`ai_direction_correct` / `ai_trade_signal_correct`. These
five tags are exposed as `FORBIDDEN_REFLECTION_TAGS` for
downstream audit and the engine never emits them.
**Successor allowed:** later (separately gated) **AI
Integrated Checkpoint** that aggregates Phase AI-1 / AI-2 /
AI-3 / AI-4 / AI-5 / AI-6 outputs into one offline audit
report. **NOT** the real DeepSeek HTTP transport. **NOT**
DeepSeek trade decisions. **NOT** the AI Layer's
involvement in the Risk Engine. **NOT** the AI Layer's
involvement in the Execution FSM. **NOT** auto-tuning.
**NOT** real Telegram outbound. **NOT** Operator Briefing
live publishing. **NOT** Rule Sandbox. **NOT** Paper
Shadow. **NOT** Phase 12.

This slice ships:

  - `app/replay/ai_replay.py` —
    `AIReplaySourceKind` (4-value closed vocabulary),
    `AIReplayCase` / `AIReplaySummary` frozen dataclasses,
    `AIReplayBuilder`, `build_ai_replay_case` /
    `build_ai_replay_summary` convenience wrappers, plus
    closed event-type string constants
    `AI_REPLAY_CASE_RECONSTRUCTED` /
    `AI_REPLAY_SUMMARY_GENERATED`.
  - `app/reflection/ai_reflection.py` —
    `AIReflectionTag` (10-value closed enum; the
    brief-forbidden 5 tags are intentionally omitted),
    `AIReflectionSeverity` (5-value closed enum),
    `FORBIDDEN_REFLECTION_TAGS` frozenset (5 forbidden
    tags), `AIReflectionCase` / `AIReflectionSummary`
    frozen dataclasses, `AIReplayReflectionEngine`
    one-shot wrapper, plus closed event-type string
    constants `AI_REFLECTION_CASE_GENERATED` /
    `AI_REFLECTION_SUMMARY_GENERATED`. Convenience
    wrappers: `reflect_replay_case`,
    `reflect_replay_cases`,
    `replay_and_reflect_artefacts`.
  - `app/replay/__init__.py` and
    `app/reflection/__init__.py` — extended re-exports.
  - `tests/unit/test_ai_replay_reflection_integration.py`
    — 164 unit tests covering every brief-mandated
    scenario.
  - New phase doc
    `docs/PHASE_AI_6_REPLAY_REFLECTION_INTEGRATION.md`.
  - `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md` (this
    section), `docs/CHANGELOG.md` updates.

Tests on this PR:
`tests/unit/test_ai_replay_reflection_integration.py` PASS;
full `tests/unit` 3305/3305 PASS (no regression vs.
post-PR-#86 main 3141 baseline; +164 new tests on the new
modules).

The phase is marked **IN_REVIEW** here. Maintainer-led
review of the implementation PR is the only path to
**ACCEPTED**.



## Phase AI-3 — Reality Check Layer v0 (IN_REVIEW)

**Status:** IN_REVIEW (implementation PR; awaits maintainer review).
**Block:** AI Layer — deterministic / statistical Reality Check
verifier. Third runtime artefact gated by
`docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`.
**Predecessors:** Phase AI-1 *AI Evidence Bundle Builder v0* merged
into `main` (PR #82, IN_REVIEW). Phase AI-2 *Truth Layer / AI
Evidence Citation Contract v0* merged into `main` (PR #83, IN_REVIEW).
**Type:** Implementation PR (paper / report / read-only).
**Runtime effect:** **none on real trading.** A new read-only
module `app/ai/reality_check.py` is added alongside the existing
`app/ai/evidence_bundle.py` (Phase AI-1) and
`app/ai/claim_contract.py` (Phase AI-2), with `app/ai/__init__.py`
extended to re-export the Phase AI-3 public surface, and a
matching unit-test module under
`tests/unit/test_ai_reality_check_layer.py` (70 tests). No file
under `app/risk/`, `app/execution/`, `app/exchanges/`,
`app/telegram/`, `app/config/`, `app/ai/evidence_bundle.py`,
`app/ai/claim_contract.py`, no event type, no database schema /
migration is touched. The module is read-only: it never appends,
mutates, or reorders rows in `events.db`; it never produces
direction, sizing, leverage, stop, target, or risk-budget fields;
it never produces a `runtime_config_patch`; and it never calls an
LLM / DeepSeek / Telegram outbound. No runtime knob
(`symbol_limit`, anomaly threshold, candidate pool capacity,
Regime weights) is changed.
**Phase ledger effect:** opens Phase AI-3 as **`IN_REVIEW`**
(not `ACCEPTED` until maintainer review of the PR).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`. No Binance API key, no API
secret, no signed endpoint, no private WebSocket, no `listenKey`,
no DeepSeek trade decision, no real Telegram outbound. **Phase 12
remains FORBIDDEN.**
**Auto-tuning effect:** **none.** `auto_tuning_allowed=false` is
hard-pinned at every `to_dict()` boundary even if a caller flips
the dataclass field. The recursive `_assert_no_forbidden_fields`
guard refuses to emit any payload carrying a `*_patch` key.
**Successor allowed:** later (separately gated) **Phase AI-4
DeepSeek Offline Sandbox** that consumes the Reality Check
substrate plus the Phase AI-1 Evidence Bundle in an offline /
sandboxed environment. **NOT** the runtime hot path. **NOT**
DeepSeek trade decisions. **NOT** the AI Layer's involvement in
the Risk Engine. **NOT** the AI Layer's involvement in the
Execution FSM. **NOT** auto-tuning. **NOT** real Telegram
outbound. **NOT** Phase 12.

> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).** This slice ships the
> AI Layer's *deterministic / statistical* Reality Check
> verifier. Having `evidence_refs` is necessary but **not
> sufficient**; an AI claim is also cross-checked against
> the Truth Layer that its `evidence_refs` point at, plus
> the market / system-behavior / outcome facts pinned in the
> Phase AI-1 Evidence Bundle. Reality Check is **not** an
> LLM, **not** a DeepSeek client, **not** a network
> transport, and **not** a prompt template. Claims with
> citations but no facts are demoted to
> `INSUFFICIENT_EVIDENCE`; claims that contradict the bundle
> are demoted to `CONTRADICTED` (or `PARTIALLY_SUPPORTED`
> for single-axis contradictions); claims that smuggle
> unverifiable narrative ("smart money is definitely
> entering" / "whales are accumulating" / "faith is
> returning" / "main force intention is clear") with no
> computable backing are rejected via
> `REJECTED_UNVERIFIABLE_NARRATIVE`; claims that depend on a
> future / unsealed window are rejected via
> `REJECTED_LOOKAHEAD`. Confidence calibration is always
> non-increasing
> (`confidence_reality_checked <= confidence_raw`). The
> maximum authority any claim can reach is
> `SUPPORTED_INTELLIGENCE`, which is *commentary substrate*
> only — **no member of `AIRealityCheckAuthorityLevel`
> grants trade authority**. The four AI root constraints in
> `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md` are enforced in
> code AND in tests. **Phase 12 remains FORBIDDEN.** The Risk
> Engine remains the single trade-decision gate.

**What this PR ships**

  - `app/ai/reality_check.py` — paper / pure / deterministic
    schema, engine, and recursive guards (closed
    `AIRealityCheckStatus` / `AIRealityCheckCategory` /
    `AIRealityCheckAuthorityLevel` enums, frozen
    `AIRealityCheckInput` / `AIRealityCheckResult`
    dataclasses, `AIRealityCheckEngine` plus the
    `reality_check_claim` convenience wrapper, closed
    contradiction-signal vocabulary, closed
    unverifiable-narrative vocabulary, closed lookahead-policy
    flag set).
  - `app/ai/__init__.py` — extended to re-export the Phase
    AI-3 public API alongside the Phase AI-1 + AI-2 surface.
  - `tests/unit/test_ai_reality_check_layer.py` — 70 unit
    tests covering every brief-mandated scenario: supported
    claim → `SUPPORTED`, partial support → confidence
    downgrade, contradicted → `CONTRADICTED` /
    `REJECTED_BY_REALITY_CHECK`, missing evidence →
    `INSUFFICIENT_EVIDENCE`, lookahead violation →
    `REJECTED_LOOKAHEAD`, unverifiable narrative →
    `REJECTED_UNVERIFIABLE_NARRATIVE`,
    `confidence_reality_checked <= confidence_raw`,
    no-trade-authority on result, forbidden-fields absent on
    serialised payload (parametrised over 25 fields),
    forbidden imports
    (`app.risk` / `app.execution` / `app.exchanges` /
    `app.llm` / `app.telegram` / `app.config`) absent, no
    LLM / DeepSeek / HTTP / network call path (AST + source +
    public-callable check), deterministic output across six
    status classes.
  - `docs/PHASE_AI_3_REALITY_CHECK_LAYER.md` — new phase
    doc.

**What this PR does NOT ship**

  - No change to `app/risk/`, `app/execution/`,
    `app/exchanges/`, `app/telegram/`, `app/config/`,
    `app/ai/evidence_bundle.py`, `app/ai/claim_contract.py`.
  - No change to `symbol_limit`, anomaly thresholds,
    candidate-pool capacity, Regime weights, or any other
    runtime knob.
  - No new private API surface, no signed endpoint, no
    `listenKey`, no real Telegram outbound, no DeepSeek
    trade decision, no LLM call path.
  - No new event type, no new database schema, no new
    migration.
  - No Operator Briefing. No DeepSeek Offline Sandbox (the
    *next-allowed* phase, not part of this PR). No Rule
    Sandbox. No trading logic.
  - No automatic parameter tuning.
  - **No Phase 12.**

**Safety boundary (held end-to-end)**

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - no Binance API key / secret
  - no signed endpoint
  - no private WebSocket
  - no `listenKey`
  - no real Telegram outbound
  - no DeepSeek trade decision
  - **Phase 12 = FORBIDDEN**

**Tests**

  - `python -m pytest tests/unit/test_ai_reality_check_layer.py -q`:
    70 PASS / 0 fail.
  - `python -m pytest tests/unit -q`: 2921 PASS / 0 fail
    (was 2851 before this phase; +70 from this phase).



## Phase AI-2 — Truth Layer / AI Evidence Citation Contract v0 (IN_REVIEW)

**Status:** IN_REVIEW (implementation PR; awaits maintainer review).
**Block:** AI Layer — claim-level citation contract. Second runtime
artefact gated by `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`.
**Predecessors:** Phase AI-1 *AI Evidence Bundle Builder v0* merged
into `main` (PR #82, IN_REVIEW). Block A complete; Block B complete
and Block B Integrated Evidence Checkpoint = `PARTIAL_EVIDENCE`;
Block C complete (C1 *Replay Extension for 11C Adaptive Events v0*
merged, C2 *Reflection Extension for 11C Adaptive Events v0*
merged, C3 *Evidence Contract Baseline v0* merged); Block C
Integrated Checkpoint driven on the operator server with
`status=EVIDENCE_GENERATED`,
`replay_status=EVIDENCE_GENERATED`,
`reflection_status=EVIDENCE_GENERATED`,
`evidence_contract_status=EVIDENCE_GENERATED`,
`accepted_claim_count=2704`,
`degraded/rejected/missing/invalid=0`,
`phase_12_forbidden=true`, `auto_tuning_allowed=false`,
`known_blockers=[]`.
**Successor allowed by this phase:** the later (separately gated)
**AI Reality Check Layer** that cross-verifies an AI claim's
`claim_text` against the Phase AI-1 Evidence Bundle cited in
`evidence_refs`, **OR** later offline AI / operator-briefing
report generation that consumes `AIClaimCitationResult` as a
frozen input, **OR** the eventual **Operator Briefing** layer.
**No other phase is unlocked.** **NOT** DeepSeek trade
decisions. **NOT** the AI Layer's involvement in the Risk
Engine. **NOT** the AI Layer's involvement in the Execution FSM.
**NOT** auto-tuning. **NOT** real Telegram outbound. **NOT**
Phase 12.

### What this phase does

Adds the AI Layer's *claim-level* citation contract as a closed
schema, a deterministic validator, a closed evidence-ref grammar,
and a 70-test unit harness. Every AI claim MUST cite Truth-Layer
evidence via `evidence_refs`; claims that fail to cite are
demoted; claims that cite malformed references are rejected
(strict mode) or demoted (non-strict mode):

  - `AIClaimAuthorityLevel` closed enum (6 values:
    `COMMENTARY_ONLY`, `SUPPORTED_INTELLIGENCE`,
    `UNSUPPORTED_INTELLIGENCE`, `DEGRADED_NO_EVIDENCE`,
    `REJECTED_BY_SCHEMA`, `REJECTED_INVALID_EVIDENCE`).
    **No member grants trade authority.** The maximum any
    claim can reach is `SUPPORTED_INTELLIGENCE`, which is
    *commentary substrate* only.
    `UNSUPPORTED_INTELLIGENCE` is reserved for the later
    Reality Check Layer; the v0 validator never produces it.
  - `AIClaimType` closed enum (10 values: `REGIME`,
    `NARRATIVE`, `LIQUIDITY`, `RISK`, `COVERAGE`, `OUTCOME`,
    `CONTRADICTION`, `REPLAY_SUMMARY`, `REFLECTION_SUMMARY`,
    `EVIDENCE_QUALITY`).
  - `AIClaimInput` / `AIClaim` frozen dataclasses preserving
    `claim_id`, `claim_type`, `claim_text`, `evidence_refs`,
    `truth_layer_fields_used`, `authority_level`,
    `confidence_raw`, `warnings`, `schema_version`. The
    validator NEVER paraphrases `claim_text`, NEVER invents a
    missing `evidence_refs`, NEVER fabricates a
    `truth_layer_fields_used` entry.
  - `AIClaimCitationResult` frozen dataclass carrying
    `claims`, `accepted_claim_count`, `degraded_claim_count`,
    `rejected_claim_count`, `missing_evidence_count`,
    `invalid_evidence_count`, `warnings`, `strict`, plus the
    hard-pinned `ai_output_is_commentary_only=True`,
    `ai_output_can_be_training_label=False`,
    `phase_12_forbidden=true`, `auto_tuning_allowed=false`
    flags.
  - `AIClaimCitationValidator` (and the
    `validate_ai_claims` convenience wrapper) -
    deterministic; coerces every input to a JSON-serializable
    form; rejects unknown `claim_type` / missing `claim_id` /
    missing `claim_text` / forbidden-field smuggling via
    `REJECTED_BY_SCHEMA`; demotes claims without
    `evidence_refs` via `DEGRADED_NO_EVIDENCE`; rejects
    (strict) or demotes (non-strict) claims with malformed
    `evidence_refs`; runs the recursive
    `_assert_no_forbidden_fields` guard at the serialisation
    boundary.

### Supported evidence-ref grammar (closed)

  - `event:<EVENT_TYPE>:<event_id>`
  - `symbol:<SYMBOL>`
  - `opportunity:<opportunity_id>`
  - `scan_batch:<scan_batch_id>`
  - `metric:<metric_name>:<window>`
  - `report:<report_id>`

Adding a new prefix is a deliberate code change AND a brief
amendment.

### AI four root constraints (enforced in code + tests)

  1. **Responsibility Isolation.** Claims and result
     payloads are scrubbed of every forbidden trade-action /
     runtime-config-patch field via the recursive
     `_assert_no_forbidden_fields` guard imported from
     `app.ai.evidence_bundle`, plus the per-claim
     `_find_forbidden_field_in_claim` check that rejects
     claims whose `claim_id` / `claim_type` / `claim_text` /
     `evidence_refs` / `truth_layer_fields_used` contains a
     forbidden trade-action / runtime-config-patch field name
     verbatim.
  2. **Stateless Inference.** Each
     `AIClaimCitationValidator.validate(...)` call is
     independent. The validator carries no instance state
     between calls. It never reads previous AI answers, chat
     history, `listenKey` payloads, signed-endpoint payloads,
     or any private exchange / account state.
  3. **Hard Rule Anchoring.** *No `evidence_refs` => no
     accepted AI conclusion.* Claims without `evidence_refs`
     are demoted to `DEGRADED_NO_EVIDENCE`; claims with
     malformed `evidence_refs` are rejected
     (`REJECTED_INVALID_EVIDENCE`) in strict mode or demoted
     in non-strict mode. The validator NEVER invents a
     missing `evidence_refs` entry.
  4. **Feedback Isolation.** `ai_output_is_commentary_only`
     is hard-pinned to `True` and
     `ai_output_can_be_training_label` is hard-pinned to
     `False`; both are re-emitted at every `to_dict()`
     boundary, even if a downstream caller flips the
     dataclass field via `object.__setattr__`.

### Hard-pinned invariants on every emitted result

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - `phase_12_forbidden = true`
  - `auto_tuning_allowed = false`
  - `ai_output_is_commentary_only = true`
  - `ai_output_can_be_training_label = false`

### Forbidden imports

`app/ai/__init__.py` and `app/ai/claim_contract.py` import
nothing from `app.risk`, `app.execution`, `app.exchanges`,
`app.llm`, `app.telegram`, or `app.config`. They do not import
`openai`, `anthropic`, `deepseek`, `httpx`, `requests`,
`aiohttp`, `urllib3`, `websocket`, `websockets`, `grpc`, or
`boto3`. Both invariants are AST-asserted in the test suite on
every CI run.

### What this phase does NOT do

  - **NOT** call DeepSeek; **NOT** call any LLM; **NOT** open
    any network socket; **NOT** authorise live trading;
    **NOT** authorise auto-tuning; **NOT** modify
    `app.risk` / `app.execution` / `app.exchanges` /
    `app.telegram` / `app.config`; **NOT** add any event type
    or database migration; **NOT** ship the AI Reality Check
    Layer; **NOT** ship Operator Briefing; **NOT** ship Rule
    Sandbox; **NOT** ship any trading logic; **NOT** open
    Phase 12.

### Files shipped

  - `app/ai/__init__.py` (extended re-exports)
  - `app/ai/claim_contract.py` (new schema + validator)
  - `tests/unit/test_ai_evidence_citation_contract.py` (70
    cases)
  - `docs/PHASE_AI_2_TRUTH_LAYER_EVIDENCE_CITATION_CONTRACT.md`
  - `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
    `docs/CHANGELOG.md` updates

### Tests

`python -m pytest tests/unit/test_ai_evidence_citation_contract.py -q`
ships 70 PASS / 0 fail;
`python -m pytest tests/unit -q` reports 2851 PASS / 0 fail
(was 2781 before this phase; +70 from this phase).

The phase is marked **IN_REVIEW** here. Maintainer-led review of
the implementation PR is the only path to **ACCEPTED**.



## Phase AI-1 — AI Evidence Bundle Builder v0 (IN_REVIEW)

**Status:** IN_REVIEW (implementation PR; awaits maintainer review).
**Block:** AI Layer kickoff. First runtime artefact gated by
`docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`.
**Predecessors:** Block A complete; Block B complete and Block B
Integrated Evidence Checkpoint = `PARTIAL_EVIDENCE`; Block C
complete (C1 *Replay Extension for 11C Adaptive Events v0* merged,
C2 *Reflection Extension for 11C Adaptive Events v0* merged, C3
*Evidence Contract Baseline v0* merged); Block C Integrated
Checkpoint driven on the operator server with
`status=EVIDENCE_GENERATED`,
`replay_status=EVIDENCE_GENERATED`,
`reflection_status=EVIDENCE_GENERATED`,
`evidence_contract_status=EVIDENCE_GENERATED`,
`accepted_claim_count=2704`,
`degraded/rejected/missing/invalid=0`,
`phase_12_forbidden=true`, `auto_tuning_allowed=false`,
`known_blockers=[]`.
**Successor allowed by this phase:** later (separately gated)
**offline AI / operator-briefing report generation** that
consumes the bundle as a frozen input **OR** the eventual **AI
Reality Check** layer that verifies AI commentary against the
Truth Layer cited in the bundle. **No other phase is unlocked.**
**NOT** DeepSeek trade decisions. **NOT** the AI Layer's
involvement in the Risk Engine. **NOT** the AI Layer's
involvement in the Execution FSM. **NOT** auto-tuning. **NOT**
real Telegram outbound. **NOT** Phase 12.

### What this phase does

Adds the AI Layer's only allowed read surface as a closed
schema, a deterministic builder, a paranoid intake guard, and a
55-test unit harness. The builder constructs frozen,
evidence-cited, deterministic, JSON-serializable
`AIEvidenceBundle` objects from Truth-Layer facts at call time:

  - `AIEvidenceBundleTaskType` closed enum (10 values:
    `OPERATOR_BRIEFING`, `MARKET_INTELLIGENCE_SUMMARY`,
    `COVERAGE_AUDIT_INTERPRETATION`,
    `POST_DISCOVERY_OUTCOME_SUMMARY`,
    `REJECT_TO_OUTCOME_SUMMARY`, `SEVERE_MISS_SUMMARY`,
    `REPLAY_REFLECTION_SUMMARY`, `EVIDENCE_COMPRESSION`,
    `CONTRADICTION_SUMMARY`, `EVIDENCE_QUALITY_ASSESSMENT`).
  - `AIEvidenceBundleBuildStatus` closed enum
    (`EVIDENCE_BUNDLE_BUILT` / `EVIDENCE_BUNDLE_DEGRADED` /
    `EVIDENCE_BUNDLE_INSUFFICIENT_EVIDENCE`).
  - `AIEvidenceBundleFactInput` / `AIEvidenceBundleFact`
    frozen dataclasses preserving `fact_id`, `fact_type`,
    `content`, `evidence_refs`, `source_report`, `status`,
    `degradation_reason`, `schema_version`.
  - `AIEvidenceBundle` frozen dataclass carrying the six
    accepted-only `*_facts` collections, the
    `degraded_facts` collection, the deduplicated
    `evidence_refs` and `source_reports` lists, the pinned
    `forbidden_fields` / `lookahead_policy` /
    `consumer_contract` blocks, the `warnings` list, the
    `build_status`, the `accepted_fact_count` /
    `degraded_fact_count` counters, and the hard-pinned
    `ai_output_is_commentary_only=True`,
    `ai_output_can_be_training_label=False`,
    `phase_12_forbidden=true`, `auto_tuning_allowed=false`
    flags.
  - `AIEvidenceBundleBuilder` (and the
    `build_ai_evidence_bundle` convenience wrapper)
    deterministically coerces every input to a
    JSON-serializable form, rejects forbidden input keys
    with `ForbiddenAIInputError` (a `ValueError` subclass),
    demotes facts without `evidence_refs`, deduplicates
    `evidence_refs` / `source_reports` in first-seen order,
    and runs the recursive `_assert_no_forbidden_fields`
    guard at the serialisation boundary.

### AI four root constraints (enforced in code + tests)

  1. **Responsibility Isolation.** The bundle's
     `forbidden_fields` block is a sorted tuple of every
     trade-action / runtime-config-patch field name (`buy`,
     `sell`, `long`, `short`, `direction`, `side`, `entry`,
     `exit`, `position_size`, `leverage`, `stop`, `stop_loss`,
     `stop_price`, `target`, `target_price`, `take_profit`,
     `risk_budget`, `order`, `order_type`, `execution_command`,
     `runtime_config_patch`, `symbol_limit_patch`,
     `threshold_patch`, `candidate_pool_patch`,
     `regime_weight_patch`, `strategy_parameter_patch`,
     `signal_to_trade`, `should_buy`, `should_short`, plus
     defensive aliases `trading_approved`, `live_ready`,
     `live_trading_allowed`). The recursive
     `_assert_no_forbidden_fields` guard refuses to emit any
     payload carrying any of these keys at any nesting depth,
     both on intake and at the serialisation boundary.
  2. **Stateless Inference.** The
     `_scan_for_forbidden_input` guard rejects
     `previous_ai_answer`, `prior_ai_answer`,
     `last_ai_answer`, `ai_session_history`,
     `ai_chat_history`, `chat_history`,
     `conversation_history`, `assistant_history`,
     `previous_briefing`, `previous_summary`,
     `previous_reflection`, `private_account_state`,
     `account_state`, `account_balance`, `account_balances`,
     `account_positions`, `account_orders`,
     `account_leverage`, `account_margin`, `wallet_balance`,
     `binance_account_state`,
     `binance_private_account_state`, `listen_key`,
     `listenkey`, `signed_endpoint_payload` and any
     credential-shaped key (substring tokens `api_key`,
     `api_secret`, `private_key`, `secret_key`,
     `auth_token`, `bearer_token`, `access_token`,
     `refresh_token`, `credential`, `password`,
     `passphrase`, `deepseek_api`, `binance_secret`,
     `telegram_token`, `telegram_bot_token` plus the
     bare-token names `secret`, `secrets`, `token`) at any
     nesting depth in any input mapping.
     `ForbiddenAIInputError` is raised on the first hit; the
     builder fails *closed*, never silently strips or
     transforms a forbidden input.
  3. **Hard Rule Anchoring.** Facts without `evidence_refs`
     are demoted to `degraded_facts` with
     `degradation_reason="no_evidence_refs_supplied"` and a
     matching warning entry; such facts NEVER appear in the
     accepted `*_facts` collections.
  4. **Feedback Isolation.** `ai_output_is_commentary_only`
     is hard-pinned to `True` and
     `ai_output_can_be_training_label` is hard-pinned to
     `False`; both are re-emitted at every `to_dict()`
     boundary, even if a downstream caller flips the
     dataclass field.

### Hard-pinned invariants on every emitted bundle

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - `phase_12_forbidden = true`
  - `auto_tuning_allowed = false`
  - `ai_output_is_commentary_only = true`
  - `ai_output_can_be_training_label = false`

### Consumer contract

  - `allowed_consumers`: `human_operator`, `export_bundle`,
    `replay_annotation`, `reflection_annotation`,
    `operator_briefing_report`.
  - `forbidden_consumers`: `RiskEngine`, `ExecutionFSM`,
    `StrategyEngine`, `ExchangeGateway`, `RuntimeConfig`,
    `TelegramLiveCommand`, `CapitalFlow`, `PositionManager`.

The two lists are *disjoint*. The runtime trade-authority and
runtime-config surfaces are explicitly named as *forbidden*
consumers - even structurally, the bundle MUST NEVER be wired
into the Risk Engine, the Execution FSM, or any
runtime-config-patch path.

### Lookahead policy (every flag pinned True)

  - `frozen_evidence_only`
  - `no_future_market_data`
  - `no_training_from_ai_output`
  - `no_runtime_feedback`
  - `post_hoc_analysis_only_when_window_closed`

### Forbidden imports

`app/ai/__init__.py` and `app/ai/evidence_bundle.py` import
nothing from `app.risk`, `app.execution`, `app.exchanges`,
`app.llm`, `app.telegram`, or `app.config`. They do not import
`openai`, `anthropic`, `deepseek`, `httpx`, `requests`,
`aiohttp`, `urllib3`, `websocket`, `websockets`, `grpc`, or
`boto3`. Both invariants are AST-asserted in the test suite on
every CI run.

### What this phase does NOT do

  - **NOT** call DeepSeek; **NOT** call any LLM; **NOT** open
    any network socket; **NOT** authorise live trading;
    **NOT** authorise auto-tuning; **NOT** modify
    `app.risk` / `app.execution` / `app.exchanges` /
    `app.telegram` / `app.config`; **NOT** add any event
    type or database migration; **NOT** ship Operator
    Briefing; **NOT** ship Reality Check; **NOT** ship Rule
    Sandbox; **NOT** ship any trading logic; **NOT** open
    Phase 12.

### Files shipped

  - `app/ai/__init__.py`
  - `app/ai/evidence_bundle.py`
  - `tests/unit/test_ai_evidence_bundle_builder.py` (55
    cases)
  - `docs/PHASE_AI_1_EVIDENCE_BUNDLE_BUILDER.md`
  - `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
    `docs/CHANGELOG.md` updates

### Tests

`python -m pytest tests/unit/test_ai_evidence_bundle_builder.py -q`
ships 55 PASS / 0 fail;
`python -m pytest tests/unit -q` reports 2781 PASS / 0 fail
(was 2726 before this phase; +55 from this phase).

The phase is marked **IN_REVIEW** here. Maintainer-led review of
the implementation PR is the only path to **ACCEPTED**.



## Phase 11C.1C-C-B-B-B-E-D — Block C Integrated Checkpoint v0 (IN_REVIEW)

**Status:** IN_REVIEW (implementation PR; awaits maintainer review).
**Block:** Block C wrap-up checkpoint.
**Predecessors:** Block A complete; Block B complete and Block B
Integrated Evidence Checkpoint = `PARTIAL_EVIDENCE` (advance
allowed); Block C1
(Phase 11C.1C-C-B-B-B-E-A *Replay Extension for 11C Adaptive Events
v0*) merged; Block C2 (Phase 11C.1C-C-B-B-B-E-B *Reflection
Extension for 11C Adaptive Events v0*) merged; Block C3
(Phase 11C.1C-C-B-B-B-E-C *Evidence Contract Baseline v0*) merged.
**Successor allowed by this phase:** Block C closeout (whole-block,
**not** per-PR) **OR** the AI **read-only** Evidence Bundle
preparation (Phase AI-0). **No other phase is unlocked.**

### What this phase does

Adds a paper / report / evidence-only Block C integrated
checkpoint v0 under `scripts/run_block_c_integrated_checkpoint.py`
that aggregates the simplified outputs of:

  - C1 *Replay Extension for 11C Adaptive Events v0*
    (`app/replay/adaptive_replay_11c.py`),
  - C2 *Reflection Extension for 11C Adaptive Events v0*
    (`app/reflection/adaptive_11c.py`), and
  - C3 *Evidence Contract Baseline v0*
    (`app/evidence/evidence_contract.py`),

into one descriptive `block_c_integrated_checkpoint_report.json`
(plus matching `.md` summary) under
`data/reports/block_c_integrated_checkpoint/`. The checkpoint is
the input to the Block C / Block D decision: did the C1 + C2 + C3
triplet produce enough evidence to authorise the next-allowed
phase (the Phase AI-0 / AI Evidence Bundle preparation)?

The runner is a thin file-based aggregator. It reads only local
files under `--reports-dir` / `--exports-dir` / `--block-b-dir`
and writes only files under `--output-dir`. It runs the C1 pure
builder functions (`build_discovery_timelines`,
`build_candidate_lifecycles`, `build_tail_outcomes`,
`build_mover_coverage_cases`, `build_post_discovery_outcome_cases`,
`build_reject_attribution_cases`, `build_severe_miss_cases`,
`build_discovery_quality_cases`), the C2
`Reflection11CAdaptiveEngine`, and the C3
`EvidenceContractValidator` against the events it parses out of
the JSONL streams. It NEVER opens a socket. It NEVER imports
`app.risk` / `app.execution` / `app.exchanges` / `app.llm` /
`app.telegram` / `app.config`.

The status taxonomy is intentionally **not** `ACCEPTED`:

  - `INSUFFICIENT_EVIDENCE` — no usable input (no adaptive events
    AND no Block B report); `next_allowed_phase =
    NEEDS_OPERATOR_EVIDENCE`.
  - `PARTIAL_EVIDENCE` — Replay / Reflection / Evidence Contract
    are at least partially runnable but missing evidence /
    degraded claims / a `known_blockers` entry remains;
    `next_allowed_phase = Phase AI-0 / AI Evidence Bundle
    preparation (paper / read-only)`.
  - `EVIDENCE_GENERATED` — Replay, Reflection and the Evidence
    Contract all produce valid output and no blocker remains;
    `next_allowed_phase = Phase AI-0 / AI Evidence Bundle
    preparation (paper / read-only)`.

`phase_12_forbidden = true` and `auto_tuning_allowed = false` are
hard-pinned on every emitted payload, asserted recursively at the
serialisation boundary alongside a closed forbidden-key
vocabulary (direction / sizing / risk-budget / runtime-config
patch keys plus the defensive aliases `trading_approved`,
`live_ready`, `live_trading_allowed`).

### What this phase does NOT do

  - It does **NOT** authorise live trading.
  - It does **NOT** authorise auto-tuning.
  - It does **NOT** call DeepSeek / any LLM.
  - It does **NOT** build the AI Evidence Bundle (that is the
    *next-allowed* phase).
  - It does **NOT** ship Paper Shadow / Rule Sandbox.
  - It does **NOT** modify any runtime knob (`symbol_limit`,
    anomaly thresholds, `candidate_pool`, Regime weights).
  - It does **NOT** retrofit existing C1 / C2 / C3 surfaces.
  - It does **NOT** close out cloud evidence (closeout is done
    per-block, not per-PR).
  - It does **NOT** start Phase 12. **Phase 12 remains
    FORBIDDEN.**

### Safety boundary (held end-to-end)

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - no Binance API key / secret
  - no signed endpoint
  - no private websocket
  - no `listenKey`
  - no real Telegram outbound
  - no DeepSeek trade decision
  - **Phase 12 = FORBIDDEN**

### Forbidden modifications (held end-to-end)

  - no edit under `app/risk/**`
  - no edit under `app/execution/**`
  - no edit under `app/exchanges/**`
  - no edit under `app/llm/**`
  - no edit under `app/telegram/**`
  - no edit under `app/config/**`
  - no change to `symbol_limit`
  - no change to anomaly thresholds
  - no change to `candidate_pool`
  - no change to regime weights
  - no `runtime_config_patch` produced
  - no buy / sell / long / short / position_size / leverage /
    stop / target / risk_budget produced

### Acceptance signal

The implementation PR ships:

  - `scripts/run_block_c_integrated_checkpoint.py` (new runner)
  - `tests/unit/test_block_c_integrated_checkpoint.py` (15 tests
    covering the brief's 10 numbered checks plus output-path /
    CLI exit-code / event-group surfacing)
  - `docs/PHASE_11C_1C_C_B_B_B_E_D_BLOCK_C_INTEGRATED_CHECKPOINT.md`
    (this phase's design + acceptance doc)
  - `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
    `docs/CHANGELOG.md` updates

Test commands:
`python -m pytest tests/unit/test_block_c_integrated_checkpoint.py -q`
ships 15 tests, all PASS;
`python -m pytest tests/unit -q` reports 2726 PASS, 0 failures
(was 2711 before this phase; +15 from this phase).

The phase is marked **IN_REVIEW** here. Maintainer-led review of
the implementation PR plus the eventual whole-block Block C
closeout PR are the only paths to **ACCEPTED**.



## Open phase: Phase AI-5 (IN_REVIEW)

> **Title:** Phase AI-5 — Operator Briefing / Evidence
> Compression v0 (*操作员简报 / 证据压缩 v0*).
> **Status:** IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).
>
> Block C is complete. PR #82 (Phase AI-1 Evidence Bundle
> Builder v0), PR #83 (Phase AI-2 Truth Layer / AI Evidence
> Citation Contract v0), PR #84 (Phase AI-3 Reality Check
> Layer v0), and PR #85 (Phase AI-4 DeepSeek Offline Sandbox
> v0) are merged into `main`. Phase AI-5 is the AI Layer's
> first **human-readable operator briefing** runtime
> artefact - a deterministic offline builder that consumes
> the Phase AI-1 evidence bundle JSON, the Phase AI-4
> sandbox output JSON, and an optional Block C Integrated
> Checkpoint report JSON, classifies every claim into the
> closed compression vocabulary, groups findings into the
> closed :class:`OperatorBriefingSection` vocabulary, and
> emits two artefacts: :class:`OperatorBriefing` and
> :class:`EvidenceCompressionReport`. The builder NEVER
> calls an LLM, NEVER opens a network socket, NEVER imports
> `app.risk` / `app.execution` / `app.exchanges` /
> `app.telegram` / `app.config`, NEVER reads private
> exchange / account state, and NEVER authorises a trade
> decision or auto-tuning. The project remains **paper
> only**; **Phase 12 remains FORBIDDEN**.

### What this phase does

  - Ships the closed :class:`OperatorBriefingSection` enum
    (12 values: `EXECUTIVE_SUMMARY`,
    `MARKET_INTELLIGENCE`, `DISCOVERY_QUALITY`,
    `COVERAGE_AUDIT`, `POST_DISCOVERY_OUTCOME`,
    `REJECT_ATTRIBUTION`, `SEVERE_MISS_TRIAGE`,
    `REPLAY_REFLECTION`, `CONTRADICTIONS`,
    `UNSUPPORTED_CLAIMS`, `DATA_GAPS`,
    `OPERATOR_ACTION_ITEMS`),
    :class:`OperatorBriefingAuthorityLevel` enum (4 values:
    `COMMENTARY_SUBSTRATE`, `DEGRADED_PARTIAL_EVIDENCE`,
    `DEGRADED_NO_EVIDENCE`, `REJECTED`; **no member grants
    trade authority**), :class:`OperatorBriefingFinding`
    (with `review_only=True` hard-pinned),
    :class:`OperatorBriefingSectionRecord`,
    :class:`OperatorBriefing` dataclass, and
    :class:`OperatorBriefingBuilder` under
    `app/ai/operator_briefing.py`.
  - Ships the closed :class:`CompressedClaim`,
    :class:`EvidenceCompressionReport`, and
    :class:`EvidenceCompressionReportBuilder` under
    `app/ai/evidence_compression.py`, plus the
    :func:`classify_claim` helper that maps the Phase AI-2
    citation authority + Phase AI-3 Reality Check status
    into the closed compression vocabulary
    (`SUPPORTED` / `UNSUPPORTED` / `DEGRADED_NO_EVIDENCE`
    / `REJECTED` / `CONTRADICTED` / `COMMENTARY_ONLY`).
  - Ships the closed event-type constants
    `AI_OPERATOR_BRIEFING_GENERATED`,
    `AI_EVIDENCE_COMPRESSION_GENERATED`, and
    `AI_UNSUPPORTED_CLAIMS_SUMMARIZED`. None are wired into
    the runtime hot path; they are report / export /
    replay-shaped only.
  - Ships the offline CLI runner
    `scripts/run_ai_operator_briefing.py` that reads the
    AI-1 evidence bundle JSON, the AI-4 sandbox output
    JSON, and an optional Block C report JSON; writes
    `operator_briefing.json` / `operator_briefing.md` /
    `evidence_compression_report.json` /
    `evidence_compression_report.md`.
  - Ships 113 unit tests under
    `tests/unit/test_ai_operator_briefing.py` covering
    every brief-mandated scenario (builds operator briefing
    from evidence bundle + sandbox output, preserves
    `evidence_refs`, unsupported claims appear ONLY in the
    `UNSUPPORTED_CLAIMS` section / NEVER in `key_findings`,
    rejected / contradicted claims do not become supported
    findings, data gaps surfaced via the `DATA_GAPS`
    section, operator action items are review-only,
    forbidden fields stripped (parametrised over 25
    fields), `trade_authority=False`,
    `auto_tuning_allowed=False`,
    `phase_12_forbidden=True`, no Telegram outbound, no
    Risk / Execution / Strategy / Telegram / Config
    consumer of `app.ai`, no private account state / API
    secret leaks, Markdown output generated, JSON output
    serialisable, deterministic output with fake input,
    forbidden imports absent, no live LLM call shape).
  - Ships
    `docs/PHASE_AI_5_OPERATOR_BRIEFING_EVIDENCE_COMPRESSION.md`.

### What this phase does NOT do

  - It does **NOT** authorise live trading.
  - It does **NOT** authorise auto-tuning.
  - It does **NOT** call DeepSeek live.
  - It does **NOT** publish any briefing to real Telegram
    outbound (live publishing is gated by Spec §41).
  - It does **NOT** ship Rule Sandbox or Paper Shadow.
  - It does **NOT** modify any runtime knob (`symbol_limit`,
    anomaly thresholds, `candidate_pool`, Regime weights).
  - It does **NOT** retrofit `app/risk/`, `app/execution/`,
    `app/exchanges/`, `app/telegram/`, or `app/config/`.
  - It does **NOT** modify
    `app/ai/evidence_bundle.py`,
    `app/ai/claim_contract.py`,
    `app/ai/reality_check.py`,
    `app/ai/intelligence_schema.py`, or
    `app/ai/deepseek_sandbox.py`.
  - It does **NOT** wire briefing output into any
    trade-decision surface; the briefing is *commentary
    substrate* only.
  - It does **NOT** start Phase 12. **Phase 12 remains
    FORBIDDEN.**

### Safety boundary (held end-to-end)

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `llm_outbound_enabled = False`
  - `sandbox_only = True`
  - `allow_trade_decision = False`
  - `allow_runtime_config_change = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - no Binance API key / secret
  - no signed endpoint
  - no private websocket
  - no `listenKey`
  - no real Telegram outbound
  - no DeepSeek trade decision
  - no real DeepSeek HTTP transport
  - **Phase 12 = FORBIDDEN**

### Forbidden modifications (held end-to-end)

  - no edit under `app/risk/**`
  - no edit under `app/execution/**`
  - no edit under `app/exchanges/**`
  - no edit under `app/telegram/**`
  - no edit under `app/config/**`
  - no edit under
    `app/ai/evidence_bundle.py`,
    `app/ai/claim_contract.py`,
    `app/ai/reality_check.py`,
    `app/ai/intelligence_schema.py`, or
    `app/ai/deepseek_sandbox.py`
  - no change to `symbol_limit`
  - no change to anomaly thresholds
  - no change to `candidate_pool`
  - no change to regime weights
  - no `runtime_config_patch` produced
  - no buy / sell / long / short / position_size / leverage
    / stop / target / risk_budget produced

### Tests

`python -m pytest tests/unit/test_ai_operator_briefing.py -q`
ships 113 tests, all PASS;
`python -m pytest tests/unit -q` reports 3128 PASS, 0
failures (was 3015 before this phase; +113 from this
phase).

### Successor allowed

Successful Phase AI-5 only authorises the later (separately
gated) **Phase AI-6 — Replay / Reflection Integration of AI
outputs** that consumes the Phase AI-5
:class:`OperatorBriefing` artefact and records it in the
replay / reflection artefacts as an *annotation* (still
paper / report / sandbox-only). It does **NOT** authorise
the real DeepSeek HTTP transport, Operator Briefing live
publishing, the AI Layer's involvement in the Risk Engine /
Execution FSM / Capital Flow Engine, auto-tuning, real
Telegram outbound, or **Phase 12**.


## Open phase: Phase AI-4 (IN_REVIEW)

> **Title:** Phase AI-4 — DeepSeek Offline Sandbox v0
> (*DeepSeek 离线沙箱 v0*).
> **Status:** IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).
>
> Block C is complete. PR #82 (Phase AI-1 Evidence Bundle
> Builder v0), PR #83 (Phase AI-2 Truth Layer / AI Evidence
> Citation Contract v0), and PR #84 (Phase AI-3 Reality Check
> Layer v0) are merged into `main`. Phase AI-4 is the AI
> Layer's first **outbound-capable** runtime artefact - a
> deterministic offline runner that consumes a frozen Phase
> AI-1 evidence bundle, validates every model-emitted claim
> through the Phase AI-2 citation contract, cross-verifies
> through the Phase AI-3 Reality Check engine, and emits one
> schema-checked, redacted, commentary-only
> :class:`AIIntelligenceOutput`. The runner is **disabled by
> default** (`enabled=False`), **outbound is closed by
> default** (`outbound_enabled=False`), and the v0 HTTP
> provider skeleton refuses to actually contact the network
> even when both gates are open. The project remains **paper
> only**; **Phase 12 remains FORBIDDEN**.

### What this phase does

  - Ships the closed :class:`AIIntelligenceOutput` schema and
    the recursive `strip_forbidden_fields` /
    `redact_secrets` helpers under
    `app/ai/intelligence_schema.py`.
  - Ships the closed :class:`DeepSeekSandboxConfig` (15
    disabled-by-default gates), :class:`DeepSeekSandboxInput`,
    :class:`DeepSeekProviderProtocol`,
    :class:`FakeDeepSeekProvider`,
    :class:`OptionalDeepSeekHTTPProvider` (refusal-only
    skeleton), and :class:`DeepSeekOfflineSandboxRunner`
    under `app/ai/deepseek_sandbox.py`.
  - Ships the offline CLI runner
    `scripts/run_deepseek_offline_sandbox.py` that reads a
    frozen Phase AI-1 evidence bundle JSON, hands it to the
    runner, and writes
    `deepseek_sandbox_output.json` /
    `deepseek_sandbox_output.md`.
  - Ships 94 unit tests under
    `tests/unit/test_deepseek_offline_sandbox.py` covering
    every brief-mandated scenario plus defensive companions.
  - Ships `docs/PHASE_AI_4_DEEPSEEK_OFFLINE_SANDBOX.md` and
    `docs/DEEPSEEK_SANDBOX_RUNBOOK.md`.

### What this phase does NOT do

  - It does **NOT** authorise live trading.
  - It does **NOT** authorise auto-tuning.
  - It does **NOT** call DeepSeek live (the v0 HTTP provider
    skeleton refuses to contact the network).
  - It does **NOT** ship Operator Briefing live publishing
    (separate later phase AI-5).
  - It does **NOT** modify any runtime knob (`symbol_limit`,
    anomaly thresholds, `candidate_pool`, Regime weights).
  - It does **NOT** retrofit `app/risk/`, `app/execution/`,
    `app/exchanges/`, `app/telegram/`, or `app/config/`.
  - It does **NOT** wire AI output into any trade-decision
    surface; AI output is *commentary substrate* only.
  - It does **NOT** start Phase 12. **Phase 12 remains
    FORBIDDEN.**

### Safety boundary (held end-to-end)

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `llm_outbound_enabled = False`
  - `sandbox_only = True`
  - `allow_trade_decision = False`
  - `allow_runtime_config_change = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - no Binance API key / secret
  - no signed endpoint
  - no private websocket
  - no `listenKey`
  - no real Telegram outbound
  - no DeepSeek trade decision
  - no real DeepSeek HTTP transport
  - **Phase 12 = FORBIDDEN**

### Forbidden modifications (held end-to-end)

  - no edit under `app/risk/**`
  - no edit under `app/execution/**`
  - no edit under `app/exchanges/**`
  - no edit under `app/telegram/**`
  - no edit under `app/config/**`
  - no edit under `app/ai/evidence_bundle.py`,
    `app/ai/claim_contract.py`, or
    `app/ai/reality_check.py`
  - no change to `symbol_limit`
  - no change to anomaly thresholds
  - no change to `candidate_pool`
  - no change to regime weights
  - no `runtime_config_patch` produced
  - no buy / sell / long / short / position_size / leverage /
    stop / target / risk_budget produced

### Tests

`python -m pytest tests/unit/test_deepseek_offline_sandbox.py -q`
ships 94 tests, all PASS;
`python -m pytest tests/unit -q` reports 3015 PASS, 0
failures (was 2921 before this phase; +94 from this phase).

The phase is marked **IN_REVIEW** here. Maintainer-led review
of the implementation PR is the only path to **ACCEPTED**.



---

## Open phase: Phase 11C / Offline Rule Sandbox Replay v0 (IN_REVIEW)

> **Title:** Offline Rule Sandbox Replay v0
> *离线规则沙箱回放 v0*
> **Status:** IN_REVIEW (after the implementation PR is merged the
> phase moves from IN_REVIEW to ACCEPTED only via a separate docs
> closeout PR; this PR alone does NOT mark the phase ACCEPTED).
> **Parent:** Phase 11C umbrella.
> **Trade authority:** **none.**
> **Phase 12:** **FORBIDDEN.**

### Purpose

A strictly offline, deterministic replay layer that scores the
direction-of-effect of hypothetical rule changes against historical
evidence (Block B integrated evidence report, Block C integrated
checkpoint report, AI Integrated Checkpoint report). It closes
roadmap gap #2 ("operator cannot safely probe rule changes against
historical evidence before paper-shadowing them") without granting
any new authority.

### Gate flags (Phase 11C / Offline Rule Sandbox Replay v0)

| flag | value |
| --- | --- |
| `mode` | `paper` |
| `live_trading` | `False` |
| `exchange_live_orders` | `False` |
| `right_tail` | `False` |
| `llm` | `False` (default) |
| `llm_outbound_enabled` | `False` (default) |
| `telegram_outbound_enabled` | `False` |
| `binance_private_api_enabled` | `False` |
| `sandbox_only` | `True` |
| `allow_trade_decision` | `False` |
| `allow_runtime_config_change` | `False` |
| `auto_tuning_allowed` | `False` |
| `trade_authority` | `False` |
| `phase_12_forbidden` | **`True`** |

### Allowed event types (added by this phase, all report/export/replay scope)

- `OFFLINE_RULE_SANDBOX_REPLAY_RUN`
- `OFFLINE_RULE_SANDBOX_SCENARIO_EVALUATED`
- `OFFLINE_RULE_SANDBOX_REPORT_GENERATED`

No trade-action events are added. No event is wired into the runtime
hot path. No database schema or migration is touched.

### Forbidden by this phase (verbatim)

- Do not modify `app/risk/**`, `app/execution/**`,
  `app/exchanges/**`, `app/telegram/**`, or `app/config/**`.
- Do not write back to runtime config.
- Do not modify `symbol_limit`, anomaly thresholds, `candidate_pool`,
  or Regime weights.
- Do not generate `runtime_config_patch`, `threshold_patch`,
  `symbol_limit_patch`, `candidate_pool_patch`,
  `regime_weight_patch`, or `strategy_parameter_patch`.
- Do not output `buy`, `sell`, `long`, `short`, `direction`,
  `entry`, `exit`, `position_size`, `leverage`, `stop`,
  `stop_loss`, `target`, `take_profit`, `risk_budget`, `order`,
  `execution_command`, `signal_to_trade`, `should_buy`,
  `should_short`, `apply_change`, `deploy_change`, or
  `enable_live`.
- Do not call DeepSeek / LLM / network endpoints.
- Do not send Telegram messages.
- Do not touch the Binance private API.
- Do not auto-tune.
- Do not enter Phase 12.

### Allowed transitions

| From | To | Allowed? |
| --- | --- | --- |
| Phase 11C / Offline Rule Sandbox Replay v0 IN_REVIEW | Phase 11C / Offline Rule Sandbox Replay v0 ACCEPTED | Only via a separate docs-closeout PR after maintainer review. |
| Phase 11C / Offline Rule Sandbox Replay v0 IN_REVIEW | Paper Shadow Strategy Validation preparation | After a successful sandbox run (`PROMISING_FOR_PAPER_SHADOW`); transition itself is the next phase's responsibility. |
| any | Phase 12 | **FORBIDDEN.** |

A `recommendation_level` of `PROMISING_FOR_PAPER_SHADOW` does **not**
authorise a paper shadow run on its own — it only marks the scenario
as a candidate for the next phase's preparation work. The Paper
Shadow Strategy Validation phase itself is out of scope for Phase 11C.

### Tests

`python -m pytest tests/unit/test_offline_rule_sandbox_replay.py -q`
ships **19 PASSING** tests covering the full safety contract;
`python -m pytest tests/unit -q` reports **3346 PASSING** tests, 0
failures (no regression vs. the prior post-PR baseline).



---

## Open phase: Phase 11C.1D-B / Paper Shadow Strategy Validation v0 (IN_REVIEW)

> **Title:** Paper Shadow Strategy Validation v0
> *纸面影子策略验证 v0*
> **Status:** IN_REVIEW (after the implementation PR is merged the
> phase moves from IN_REVIEW to ACCEPTED only via a separate docs
> closeout PR; this PR alone does NOT mark the phase ACCEPTED).
> **Parent:** Phase 11C umbrella.
> **Trade authority:** **none.**
> **Phase 12:** **FORBIDDEN.**

### Purpose

A strictly paper-only / report-only / evidence-only cohort
evaluation layer that turns the structured outputs of the Block B
integrated evidence checkpoint, the Block C integrated checkpoint,
and the Offline Rule Sandbox Replay v0 (PR #89) into
``PaperShadowSample`` rows, groups them into cohorts, computes
cohort-level metrics, and emits a paper shadow validation report.
The report tells the operator which discovery patterns /
regime-cluster cohorts have a structural edge on the historical
record, and which look like noise / late chase / fake breakout /
data gap. It closes the next paper-only roadmap gap after PR #89
("operator cannot safely score discovery patterns and
regime-cluster cohorts on the historical record before scoping
forward-test preparation") without granting any new authority.

### Gate flags (Phase 11C.1D-B / Paper Shadow Strategy Validation v0)

| flag | value |
| --- | --- |
| `mode` | `paper` |
| `live_trading` | `False` |
| `exchange_live_orders` | `False` |
| `right_tail` | `False` |
| `llm` | `False` (default) |
| `llm_outbound_enabled` | `False` (default) |
| `telegram_outbound_enabled` | `False` |
| `binance_private_api_enabled` | `False` |
| `sandbox_only` | `True` |
| `allow_trade_decision` | `False` |
| `allow_runtime_config_change` | `False` |
| `auto_tuning_allowed` | `False` |
| `trade_authority` | `False` |
| `phase_12_forbidden` | **`True`** |

### Allowed event types (added by this phase, all report/export/replay scope)

- `PAPER_SHADOW_SAMPLE_CREATED`
- `PAPER_SHADOW_COHORT_EVALUATED`
- `PAPER_SHADOW_REPORT_GENERATED`

No trade-action events are added. No event is wired into the
runtime hot path. No database schema or migration is touched.

### Allowed recommendation levels (closed taxonomy)

```
REVIEW_ONLY
PROMISING_FOR_FORWARD_TEST
INCONCLUSIVE
RISKY
REJECTED_BY_EVIDENCE
```

`APPLY`, `DEPLOY`, `ENABLE_LIVE`, `TRADE`, `BUY`, `SELL`,
`GO_LIVE`, `AUTO_APPLY` are intentionally NOT defined and the
engine refuses to ever emit them.

### Forbidden by this phase (verbatim)

- Do not modify `app/risk/**`, `app/execution/**`,
  `app/exchanges/**`, `app/telegram/**`, or `app/config/**`.
- Do not write back to runtime config.
- Do not modify `symbol_limit`, anomaly thresholds,
  `candidate_pool`, or Regime weights.
- Do not generate `runtime_config_patch`, `threshold_patch`,
  `symbol_limit_patch`, `candidate_pool_patch`,
  `regime_weight_patch`, or `strategy_parameter_patch`.
- Do not output `buy`, `sell`, `long`, `short`, `direction`,
  `entry`, `exit`, `position_size`, `leverage`, `stop`,
  `stop_loss`, `target`, `take_profit`, `risk_budget`, `order`,
  `execution_command`, `signal_to_trade`, `should_buy`,
  `should_short`, `apply_change`, `deploy_change`, or
  `enable_live`.
- Do not call DeepSeek / LLM / network endpoints.
- Do not send Telegram messages.
- Do not touch the Binance private API.
- Do not auto-tune.
- Do not enter Phase 12.

### Allowed transitions

| From | To | Allowed? |
| --- | --- | --- |
| Phase 11C.1D-B IN_REVIEW | Phase 11C.1D-B ACCEPTED | Only via a separate docs-closeout PR after maintainer review. |
| Phase 11C.1D-B IN_REVIEW | Risk / Execution / Capital Safety Matrix preparation | After a successful paper shadow run with at least one `PROMISING_FOR_FORWARD_TEST` cohort; transition itself is the next phase's responsibility. |
| Phase 11C.1D-B IN_REVIEW | Strict walk-forward preparation | After a successful paper shadow run with at least one `PROMISING_FOR_FORWARD_TEST` cohort; transition itself is the next phase's responsibility. |
| any | Phase 12 | **FORBIDDEN.** |

A `recommendation_level` of `PROMISING_FOR_FORWARD_TEST` does
**not** authorise a forward-test run on its own — it only marks
the cohort as a candidate for the next phase's preparation work.
The forward-test phase itself is out of scope for Phase 11C.1D-B.

### Tests

`python -m pytest tests/unit/test_paper_shadow_strategy_validation.py -q`
ships **22 PASSING** tests covering the full safety contract for
this phase;
`python -m pytest tests/unit -q` reports **3368 PASSING** tests, 0
failures (was 3346 before this phase; +22 from this phase).


---

## Open phase: Phase 11C.1D-C / Risk / Execution / Capital Safety Matrix v0 (IN_REVIEW)

> **Title:** Risk / Execution / Capital Safety Matrix v0
> *风险 / 执行 / 资金 / 数据降级 / AI 降级 安全矩阵 v0*
> **Status:** IN_REVIEW (after the implementation PR is merged the
> phase moves from IN_REVIEW to ACCEPTED only via a separate docs
> closeout PR; this PR alone does NOT mark the phase ACCEPTED).
> **Parent:** Phase 11C umbrella.
> **Trade authority:** **none.**
> **Phase 12:** **FORBIDDEN.**

### Purpose

A strictly paper / report / evidence-only safety verification
engine that turns the documented safety boundary of the AMA-RT
V1.4 system into a deterministic, auditable matrix. The matrix
takes a closed taxonomy of adverse-condition scenarios (stop
failures, ghost / orphan / missing-remote positions, reconciliation
mismatches, data degradations, WebSocket staleness, REST 429 / 418
throttling, Telegram export failures, capital rebase / external
deposit / profit withdrawal, AI degradation / DeepSeek timeout /
Reality-Check failure / forbidden-field stripped, kill-all
audit-only, pause-resume required) and verifies that every
scenario, when evaluated, produces the *minimum required defensive
safety actions*: pauses new opens when required, rejects unsafe
actions, requires operator review or operator resume when
required, degrades to report-only when telemetry is degraded,
blocks Telegram outbound, AI trade authority, runtime config
changes, and live orders unconditionally, keeps the paper ledger
when the live path is unsafe, and records audit events for every
adverse scenario. The output is one descriptive
``risk_execution_capital_safety_matrix_report.json`` (plus its
Markdown twin) that an auditor can review.

### Gate flags (Phase 11C.1D-C / Risk / Execution / Capital Safety Matrix v0)

| flag | value |
| --- | --- |
| `mode` | `paper` |
| `live_trading` | `False` |
| `exchange_live_orders` | `False` |
| `right_tail` | `False` |
| `llm` | `False` (default) |
| `llm_outbound_enabled` | `False` (default) |
| `telegram_outbound_enabled` | `False` |
| `binance_private_api_enabled` | `False` |
| `sandbox_only` | `True` |
| `allow_trade_decision` | `False` |
| `allow_runtime_config_change` | `False` |
| `auto_tuning_allowed` | `False` |
| `trade_authority` | `False` |
| `phase_12_forbidden` | **`True`** |

### Allowed event types (added by this phase, all report / export / audit scope)

- `SAFETY_MATRIX_SCENARIO_EVALUATED`
- `SAFETY_MATRIX_REPORT_GENERATED`
- `SAFETY_MATRIX_BLOCKER_DETECTED`

No trade-action events are added. No event is wired into the
runtime hot path. No database schema or migration is touched.

### Allowed scenario types (closed taxonomy)

```
STOP_FAILED
STOP_UNCONFIRMED
GHOST_POSITION
ORPHAN_STOP
MISSING_REMOTE_POSITION
RECONCILIATION_MISMATCH
DATA_DEGRADED
WS_STALE
REST_429
REST_418
TELEGRAM_EXPORT_FAILURE
TELEGRAM_OUTBOUND_BLOCKED
PAUSE_RESUME_REQUIRED
KILL_ALL_AUDIT_ONLY
CAPITAL_REBASE_IN_PROGRESS
EXTERNAL_DEPOSIT
PROFIT_WITHDRAWAL
LLM_DEGRADED
DEEPSEEK_TIMEOUT
AI_REALITY_CHECK_FAILED
AI_FORBIDDEN_FIELD_STRIPPED
```

### Allowed expected actions (closed taxonomy)

```
PAUSE_NEW_OPENS
REJECT_UNSAFE_ACTION
REQUIRE_OPERATOR_REVIEW
REQUIRE_OPERATOR_RESUME
DEGRADE_TO_REPORT_ONLY
RECORD_AUDIT_EVENT
BLOCK_TELEGRAM_OUTBOUND
BLOCK_AI_TRADE_AUTHORITY
BLOCK_RUNTIME_CONFIG_CHANGE
BLOCK_LIVE_ORDER
PAPER_LEDGER_ONLY
NO_ACTION_REQUIRED
```

`APPLY`, `DEPLOY`, `ENABLE_LIVE`, `GO_LIVE`, `AUTO_APPLY`, `BUY`,
`SELL`, `OPEN_POSITION`, `CLOSE_POSITION`, `PLACE_ORDER`,
`SUBMIT_ORDER` are intentionally NOT defined and the engine
refuses to ever emit them.

### Allowed result statuses (closed taxonomy)

```
PASS
WARN
FAIL
INSUFFICIENT_EVIDENCE
```

`ACCEPTED`, `TRADE`, `BUY`, `SELL`, `GO_LIVE`, `ENABLE_LIVE`,
`APPLY`, `DEPLOY` are intentionally NOT in the result-status
taxonomy.

### Forbidden by this phase (verbatim)

- Do not modify `app/risk/**`, `app/execution/**`,
  `app/exchanges/**`, `app/telegram/**`, or `app/config/**`.
- Do not add Binance signed endpoints, `listenKey`, or private
  WebSockets.
- Do not enable live orders.
- Do not send real Telegram messages.
- Do not let Telegram commands bypass the Risk Engine.
- Do not let AI / DeepSeek output a trade action.
- Do not let AI / DeepSeek modify config / risk / execution.
- Do not modify `symbol_limit`, anomaly thresholds,
  `candidate_pool`, or Regime weights.
- Do not generate `runtime_config_patch`, `threshold_patch`,
  `symbol_limit_patch`, `candidate_pool_patch`,
  `regime_weight_patch`, or `strategy_parameter_patch`.
- Do not output `buy`, `sell`, `long`, `short`, `direction`,
  `entry`, `exit`, `position_size`, `leverage`, `stop`,
  `stop_loss`, `target`, `take_profit`, `risk_budget`, `order`,
  `execution_command`, `signal_to_trade`, `should_buy`,
  `should_short`, `apply_change`, `deploy_change`,
  `enable_live`, `live_ready`, `trading_approved`.
- Do not call DeepSeek / LLM / network endpoints.
- Do not auto-tune.
- Do not enter Phase 12.

### Next-allowed-phase decision rule

```
if failed_count == 0 and len(p0_failures) == 0 and len(p1_failures) == 0
        and total_scenarios > 0:
    next_allowed_phase = Strict Blind Walk-forward design checkpoint
                         (paper / read-only; requires human-owner-
                         supplied strict forward-only anti-lookahead
                         blind-test design)
else:
    next_allowed_phase = Safety Matrix remediation required
                         (paper / read-only; remediate P0 / P1
                         blockers and re-run)
```

A successful Safety Matrix run only authorises the *Strict Blind
Walk-forward design checkpoint*. It does **NOT** authorise *Blind
Walk-forward implementation*. **Before Blind Walk-forward
implementation can begin, the human owner MUST provide a finalized
strict forward-only anti-lookahead blind-test design.** This phase
does not, and cannot, generate that design.

### Allowed transitions

| From | To | Allowed? |
| --- | --- | --- |
| Phase 11C.1D-C IN_REVIEW | Phase 11C.1D-C ACCEPTED | Only via a separate docs-closeout PR after maintainer review. |
| Phase 11C.1D-C IN_REVIEW | Strict Blind Walk-forward design checkpoint | After a successful Safety Matrix run with zero P0 / P1 blockers AND human-owner-supplied strict forward-only anti-lookahead blind-test design; transition itself is the next phase's responsibility. |
| Phase 11C.1D-C IN_REVIEW | Blind Walk-forward implementation | **FORBIDDEN by this phase alone.** Requires the design checkpoint to have completed AND the human owner to have signed off on the design. |
| any | Phase 12 | **FORBIDDEN.** |

### Tests

`python -m pytest tests/unit/test_risk_execution_capital_safety_matrix.py -q`
ships **32 PASSING** tests covering all 20 brief-mandated scenarios
plus extras (scenario taxonomy coverage, SAFETY_CONTRACT shape,
scenario / result input validation, empty-scenarios
INSUFFICIENT_EVIDENCE status, P0 failure flips overall status and
next_allowed_phase, runner file output, byte-identical re-run with
a fixed clock, runner rejects unsupported scenario_set values,
result-status closed-enum sweep, expected-action vocabulary
excludes trade verbs);
`python -m pytest tests/unit -q` reports **3400 PASSING** tests, 0
failures (was 3368 before this phase; +32 from this phase).



## Open phase: Phase 11C.1D-D / Strict Blind Walk-forward Sim-Live Constitution (IN_REVIEW)

> **Title:** Strict Blind Walk-forward Sim-Live Constitution
> *Strict Forward-only Historical Sim-Live Blind Walk-forward Design Baseline / 盲测设计宪法 / 严格前向 Sim-Live 盲测基线*
> **Status:** IN_REVIEW (after this docs-only PR is merged the
> phase moves from IN_REVIEW to ACCEPTED only via a separate
> docs-closeout PR; this PR alone does NOT mark the phase
> ACCEPTED).
> **Type:** **docs-only constitution.** No runtime code, no
> configuration, no tests, no scripts, no data files are
> introduced or modified by this PR.
> **Parent:** Phase 11C umbrella.
> **Trade authority:** **none.**
> **Phase 12:** **FORBIDDEN.**

### Purpose

The human-owner-supplied **Strict Blind Walk-forward design
checkpoint** that the Phase 11C.1D-C *Risk / Execution /
Capital Safety Matrix v0* `next_allowed_phase` rule explicitly
required before any *Blind Walk-forward implementation* may
begin. Phase 11C.1D-D ships that checkpoint as a **docs-only
constitution** (`docs/PHASE_11C_1D_D_STRICT_BLIND_WALK_FORWARD_SIM_LIVE_CONSTITUTION.md`)
covering §1 Purpose through §20 Final Governance Rule plus the
owner-review enhancements §A *Explicit leakage test suite*, §B
*Feature Store as-of rule*, §C *Hyperparameter / rule search
budget*, §D *Mandatory final untouched holdout*, §E *Data
revision / late arrival policy*, §F *Run invalidation rules*.

The constitution defines AMA-RT V1.4 blind testing as a
**strict forward-only historical sim-live**, not an ordinary
backtest. At simulated time `T`, the system MAY only access
records whose `available_at <= T`. Future top-mover labels,
completed tail labels, post-discovery outcomes, future MFE /
MAE, severe missed-tail labels, final window PnL, future
drawdown, future funding-rate changes, future regime labels,
future AI briefings, future replay summaries, and future
reflection summaries MAY ONLY be used for scoring / audit
**after** the blind window has closed; they MUST NOT enter
any decision surface inside the window. Training MAY use only
already-closed historical windows. Before a blind window
opens, the runtime code, configuration, rule set, feature
schema, data manifest, universe manifest, fee / slippage /
latency / outage models, and AI offline state MUST be frozen
and content-hashed. The blind window MUST NOT auto-tune. Any
look-ahead / drift / leakage MUST mark the run
`INVALIDATED_LOOKAHEAD_OR_DRIFT`.

### Gate flags (Phase 11C.1D-D / Strict Blind Walk-forward Sim-Live Constitution)

The blind walk-forward phase introduces a **separate
sim-live namespace** so that no dangerous live flag is
reused, even by accident, to authorise simulation-only
behaviour. The sim-live flags are **additive** on top of the
project-wide safety boundary; they cannot subtract from it.

Live-trading safety boundary (held; no change introduced by
this constitution):

| flag | value |
| --- | --- |
| `mode` | `paper` |
| `live_trading` | `False` |
| `exchange_live_orders` | `False` |
| `right_tail` | `False` |
| `llm` | `False` (default) |
| `llm_outbound_enabled` | `False` (default) |
| `telegram_outbound_enabled` | `False` |
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
| `telegram_live_command_authority` | `False` |
| `ai_trade_authority` | `False` |
| `auto_tuning_inside_blind_window` | `False` |
| `phase_12_forbidden` | **`True`** |

Sim-live namespace (designed by this constitution; the
flags become *implementable* by PR94 → PR100, **not** by
this docs-only PR):

| flag | value |
| --- | --- |
| `mode` | `historical_blind_sim_live` |
| `historical_replay_enabled` | `True` |
| `simulation_clock_enabled` | `True` |
| `time_wall_guard_enabled` | `True` |
| `mock_exchange_enabled` | `True` |
| `paper_shadow_execution_enabled` | `True` |
| `simulated_order_lifecycle_enabled` | `True` |
| `simulated_position_lifecycle_enabled` | `True` |
| `simulated_capital_flow_enabled` | `True` |
| `telegram_sandbox_outbox_enabled` | `True` |
| `ai_offline_briefing_enabled` | `True` |

A sim-live flag MAY NOT flip a live-trading flag under any
condition. Setting `historical_replay_enabled=True` does NOT
flip `live_trading`. Setting `mock_exchange_enabled=True` does
NOT flip `exchange_live_orders`. Setting
`telegram_sandbox_outbox_enabled=True` does NOT flip
`telegram_live_command_authority`. Setting
`ai_offline_briefing_enabled=True` does NOT flip
`ai_trade_authority`.

### Forbidden by this phase (verbatim, docs-only)

This is a **docs-only** PR. It MUST NOT:

- modify `app/**`,
- modify `scripts/**`,
- modify `tests/**`,
- modify `configs/**`,
- modify `data/**`,
- modify `requirements.txt` or `pyproject.toml` or `.env*`,
- ship a SimulationClock implementation,
- ship a Time-Wall Guard implementation,
- ship a Historical Market Store implementation,
- ship a ReplayFeedProvider implementation,
- ship a MockExchange implementation,
- ship a Pessimistic Fill Model implementation,
- ship a Simulated Capital Flow implementation,
- ship a Telegram Sandbox Outbox implementation,
- ship a Blind Walk-forward Runner implementation,
- modify the Risk Engine, Execution FSM, Exchange gateway,
  Telegram outbound, runtime config, or any DeepSeek / LLM
  hot-path code,
- enable live orders,
- connect to Binance private API (signed endpoints,
  `listenKey`, private WebSocket, account / order / position /
  leverage / margin endpoints),
- send real Telegram messages,
- let Telegram commands bypass the Risk Engine,
- let AI / DeepSeek output a trade action,
- let AI / DeepSeek modify config / risk / execution / strategy,
- generate `runtime_config_patch`, `threshold_patch`,
  `symbol_limit_patch`, `candidate_pool_patch`,
  `regime_weight_patch`, or `strategy_parameter_patch`,
- output `buy`, `sell`, `long`, `short`, `direction`,
  `entry`, `exit`, `position_size`, `leverage`, `stop`,
  `stop_loss`, `target`, `take_profit`, `risk_budget`,
  `order`, `execution_command`, `signal_to_trade`,
  `should_buy`, `should_short`, `apply_change`,
  `deploy_change`, `enable_live`, `live_ready`,
  `trading_approved`,
- auto-tune anything,
- enter Phase 12.

The constitution itself, when later implemented (PR94 →
PR100), MUST also forbid the same items inside the blind
walk-forward runtime; that forbidden list is restated in §F
*Run invalidation rules*.

### Required outputs of a (future) blind walk-forward run

Defined by §16 of the constitution. Implementation belongs
to later PRs (PR94 → PR100). Required artefacts:

```
Blind Run Manifest
Trade Ledger
Equity Timeseries
Discovery Quality Ledger
Failure Ledger
Telegram Sandbox Transcript
AI Operator Briefing
```

### Acceptance criteria for a (future) blind walk-forward implementation

Defined by §17 of the constitution. A blind walk-forward
implementation is valid only if every condition holds; a
single violation invalidates the run under §F. Verbatim
acceptance criteria:

- SimulationClock used by every simulation-sensitive
  component.
- No-lookahead guard rejects future data.
- Every read obeys `available_at <= simulated_time`.
- Outcome labels unavailable during blind window.
- Training artefacts frozen before blind window.
- Blind window cannot auto-tune.
- Market universe reconstructed as-of historical time.
- Execution FSM routes only to MockExchange.
- No real Binance private endpoint reachable.
- No real order can be placed.
- Telegram sandbox-only.
- AI offline-only and no trading authority.
- Trade ledger generated.
- Equity timeseries generated.
- Discovery quality ledger generated.
- Failure ledger generated.
- Replay / Reflection / Export evidence generated.
- Phase 12 remains forbidden.

### Run invalidation status (closed taxonomy)

Defined by §F of the constitution:

```
INVALIDATED_LOOKAHEAD_OR_DRIFT
```

A run MUST carry `INVALIDATED_LOOKAHEAD_OR_DRIFT` if any of
the following occurs: configuration drift, rule-hash drift,
feature-schema drift, data-manifest drift,
universe-manifest drift, future-record access, tail-label
leakage, post-discovery outcome leakage, replay / reflection
summary leakage, AI output used as truth / label / strategy
sample, manual sample deletion, validation / test tuning,
missing failure ledger, unlogged runtime override.

`INVALIDATED_LOOKAHEAD_OR_DRIFT` is **not** a runtime knob;
it is a closed-status outcome that can only be removed by
re-running the entire window with a fresh frozen artefact
set. Once recorded, it is permanent evidence.

### Required leakage test suite (for later implementation PRs only)

Defined by §A of the constitution. Required test names
(this PR does NOT add tests; the names below are normative
for later implementation PRs):

- `test_available_at_future_record_rejected`
- `test_unclosed_candle_high_low_not_visible`
- `test_future_tail_label_unavailable_in_blind_window`
- `test_post_discovery_outcome_unavailable_before_window_close`
- `test_ai_briefing_unavailable_as_truth`
- `test_replay_reflection_summary_unavailable_during_blind_window`
- `test_config_drift_invalidates_window`

### Recommended engineering route

Defined by §19 of the constitution. Each step is its own PR
with its own gate, brief, forbidden list, and acceptance
evidence. Acceptance of one step **does not** authorise the
next step to skip its gate. Skipping is forbidden.

| step | scope |
| --- | --- |
| **PR93** | **Strict Blind Walk-forward Sim-Live Constitution** (this docs-only PR). |
| PR94 | SimulationClock + Time-Wall Guard. |
| PR95 | Historical Market Store v0. |
| PR96 | ReplayFeedProvider. |
| PR97 | MockExchange + Pessimistic Fill Model v0. |
| PR98 | Simulated Capital Flow + Trade Ledger. |
| PR99 | Telegram Sandbox Outbox. |
| PR100 | Blind Walk-forward Runner v0. |

### Next-allowed-phase decision rule

```
Successful PR93 acceptance only authorises:
    next_allowed_phase = PR94 — SimulationClock + Time-Wall Guard
                         (paper / docs-and-code; the SimulationClock and
                         the Time-Wall Guard are the *first*
                         implementation step of the blind walk-forward
                         stack and MUST be merged before any subsequent
                         step in the engineering route opens).

Successful PR93 acceptance does NOT authorise:
    PR95 Historical Market Store v0
    PR96 ReplayFeedProvider
    PR97 MockExchange + Pessimistic Fill Model v0
    PR98 Simulated Capital Flow + Trade Ledger
    PR99 Telegram Sandbox Outbox
    PR100 Blind Walk-forward Runner v0
    Live trading
    Auto-tuning
    The DeepSeek hot path
    Telegram live outbound
    Phase 12
```

Each subsequent step (PR95 → PR100) MUST open its own gate
explicitly. Skipping a step is forbidden.

### Allowed transitions

| From | To | Allowed? |
| --- | --- | --- |
| Phase 11C.1D-D IN_REVIEW | Phase 11C.1D-D ACCEPTED | Only via a separate docs-closeout PR after maintainer review. |
| Phase 11C.1D-D IN_REVIEW | PR94 — SimulationClock + Time-Wall Guard | After a successful PR93 docs-only acceptance; PR94 itself opens its own gate. |
| Phase 11C.1D-D IN_REVIEW | PR95 — Historical Market Store v0 | **FORBIDDEN by this phase alone.** Requires successful PR94 acceptance first. |
| Phase 11C.1D-D IN_REVIEW | PR96 — ReplayFeedProvider | **FORBIDDEN by this phase alone.** Requires successful PR95 acceptance first. |
| Phase 11C.1D-D IN_REVIEW | PR97 — MockExchange + Pessimistic Fill Model | **FORBIDDEN by this phase alone.** Requires successful PR96 acceptance first. |
| Phase 11C.1D-D IN_REVIEW | PR98 — Simulated Capital Flow + Trade Ledger | **FORBIDDEN by this phase alone.** Requires successful PR97 acceptance first. |
| Phase 11C.1D-D IN_REVIEW | PR99 — Telegram Sandbox Outbox | **FORBIDDEN by this phase alone.** Requires successful PR98 acceptance first. |
| Phase 11C.1D-D IN_REVIEW | PR100 — Blind Walk-forward Runner v0 | **FORBIDDEN by this phase alone.** Requires successful PR99 acceptance first. |
| Phase 11C.1D-D IN_REVIEW | Blind Walk-forward implementation | **FORBIDDEN by this phase alone.** A complete blind walk-forward run requires PR94 → PR100 to have been accepted in order. |
| any | Phase 12 | **FORBIDDEN.** |

### Tests

This is a **docs-only** PR. It does NOT add tests. The
required leakage test suite (§A) is normative for later
implementation PRs only. The full `tests/unit` suite is
unchanged by this PR.

### Files shipped

- `docs/PHASE_11C_1D_D_STRICT_BLIND_WALK_FORWARD_SIM_LIVE_CONSTITUTION.md`
  (the constitution itself; §1–§20 plus owner-review
  enhancements §A–§F).
- `docs/PROJECT_STATUS.md` (current-phase entry prepended;
  prior 11C.1D-C entry preserved as *Prior status* below
  the new entry).
- `docs/PHASE_GATE.md` (this section appended; Phase 12
  row in the *Open / Reserved phases* table unchanged).
- `docs/CHANGELOG.md` (docs-only entry recording that no
  runtime behaviour changed).

No file under `app/`, `scripts/`, `tests/`, `configs/`,
`data/`, no `requirements.txt`, no `pyproject.toml`, and no
`.env*` is touched by this PR.

### Inheritance

Phase 11C.1D-D inherits, verbatim, every Phase 1, Phase
11C, Phase 11C.1A, Phase 11C.1B, Phase 11C.1C-A, Phase
11C.1C-B, Phase 11C.1C-C-A, Phase 11C.1C-C-B-A, Phase
11C.1C-C-B-B-A, Phase 11C.1C-C-B-B-B-A, Phase
11C.1C-C-B-B-B-B, Phase 11C.1C-C-B-B-B-C, Phase
11C.1C-C-B-B-B-D, Phase 11C.1C-C-B-B-B-D-A, Phase
11C.1C-C-B-B-B-D-B, Phase 11C.1C-C-B-B-B-D-B.1, Phase
11C.1C-C-B-B-B-D-C-A, Phase 11C.1C-C-B-B-B-D-C-B, Phase
11C.1C-C-B-B-B-D-D, Phase 11C.1C-C-B-B-B-D-E, Phase
11C.1C-C-B-B-B-E-A, Phase 11C.1C-C-B-B-B-E-B, Phase
11C.1C-C-B-B-B-E-C, Phase AI-1, Phase AI-2, Phase AI-3,
Phase AI-4, Phase AI-5, Phase AI-6, Phase AI-CHECKPOINT,
Phase 11C / Offline Rule Sandbox Replay, Phase 11C.1D-B
*Paper Shadow Strategy Validation*, and Phase 11C.1D-C
*Risk / Execution / Capital Safety Matrix* forbidden item.

The Risk Engine remains the single trade-decision gate.
Phase 12 remains **FORBIDDEN**.



## Open phase: Phase 11C.1D-D-A / SimulationClock + Time-Wall Guard (PR94, IN_REVIEW)

> **Title:** SimulationClock + Time-Wall Guard
> *(Strict forward-only historical sim-live time substrate /
> 严格前向 Sim-Live 模拟时钟与时间墙守卫 v0)*
>
> **Status:** IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).
> **Type:** Implementation PR (paper / report / evidence-only
> infrastructure).
> **Parent:** Phase 11C.1D-D *Strict Blind Walk-forward Sim-Live
> Constitution* (PR93, merged).
>
> Phase 11C.1D-D-A ships the **first** anti-future-lookahead
> infrastructure block of the strict blind walk-forward stack
> defined by PR93. PR93 §19's engineering route explicitly
> authorises ONLY this PR (PR94) to begin the next paper-only
> step. PR94 introduces a small, deterministic, pure-Python
> time substrate. It introduces NO runtime hot-path wiring, NO
> new event types, NO schema migration, NO I/O, NO network,
> and NO authority over the Risk Engine or the Execution FSM.

### Scope (Phase 11C.1D-D-A / PR94)

  - `app/sim/__init__.py` — package init re-exporting the
    PR94 public surface.
  - `app/sim/simulation_clock.py` — :class:`SimulationClock`
    (strict forward-only simulated UTC clock; the **only**
    source of market-state decision time inside a strict
    blind walk-forward run; never consults the wall-clock;
    forward-only by default; rewinds require an explicit
    test-only flag); :class:`HistoricalRecordTime` (the
    four-timestamp record-time helper carrying `event_time`,
    `available_at`, `ingested_at`, `source`, plus optional
    `record_id` / `symbol` / `interval`); the
    `ensure_utc_aware` and `parse_interval_seconds` helpers.
  - `app/sim/time_wall_guard.py` — :class:`TimeWallGuard`
    (the `available_at <= simulated_time` enforcement layer;
    `can_read` / `assert_can_read` / `validate_no_lookahead` /
    `filter_available` / `reject_future_records` /
    `make_ingested_at_used_as_availability_violation` /
    `make_outcome_label_violation` /
    `make_unclosed_candle_field_access_violation`);
    :class:`NoLookaheadViolation` (audit-only descriptive
    violation object with a closed reason taxonomy
    `FUTURE_AVAILABLE_AT` / `MISSING_AVAILABLE_AT` /
    `INGESTED_AT_USED_AS_AVAILABILITY` /
    `UNCLOSED_CANDLE_FIELD_ACCESS` /
    `OUTCOME_LABEL_DURING_BLIND_WINDOW`, and a closed
    severity taxonomy `P0` / `P1`);
    :class:`CandleVisibilityGuard` (the §6 closed-candle
    visibility rule; final OHLCV invisible before close);
    `assert_no_forbidden_fields` (recursive guard against
    trade-action / runtime-config-patch / "live ready" field
    names at any nesting depth).
  - `tests/unit/test_simulation_clock_time_wall_guard.py` —
    the 27-test PR94 safety contract (21 brief-mandated
    scenarios plus 6 defensive extras).
  - `docs/PHASE_11C_1D_D_A_SIMULATION_CLOCK_TIME_WALL_GUARD.md`
    — the design / acceptance brief.
  - `docs/PROJECT_STATUS.md` — current-phase entry prepended
    (prior 11C.1D-D entry preserved as historical context
    below).
  - `docs/PHASE_GATE.md` — this section appended; Phase 12
    row in the *Open / Reserved phases* table unchanged.
  - `docs/CHANGELOG.md` — this PR's entry.

### Boundary (must hold from day one)

| flag | required value |
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

### Explicitly forbidden (inherited verbatim)

  - Do NOT modify `app/risk/**`, `app/execution/**`,
    `app/exchanges/**`, `app/telegram/**`, `app/config/**`.
  - Do NOT implement the Blind Walk-forward Runner (PR100).
  - Do NOT implement the Historical Market Store v0 (PR95).
  - Do NOT implement the ReplayFeedProvider (PR96).
  - Do NOT implement the MockExchange + Pessimistic Fill
    Model (PR97).
  - Do NOT implement the Simulated Capital Flow + Trade
    Ledger (PR98).
  - Do NOT implement the Telegram Sandbox Outbox (PR99).
  - Do NOT enable live orders.
  - Do NOT connect to Binance private API.
  - Do NOT enable any real Telegram outbound.
  - Do NOT call DeepSeek / LLM / any network transport.
  - Do NOT import `app.risk` / `app.execution` /
    `app.exchanges` / `app.telegram` / `app.config`.
  - Do NOT auto-tune anything.
  - Do NOT enter Phase 12.

### Acceptance gate (placeholder; status: IN_REVIEW)

  - PR94 is marked **IN_REVIEW**.
  - Maintainer-led review of the implementation PR is the
    only path to **ACCEPTED**.
  - `python -m pytest tests/unit/test_simulation_clock_time_wall_guard.py -q`
    ships 27 PASSING tests on the PR branch.
  - `python -m pytest tests/unit -q` reports 3427 PASSING
    tests, 0 failures (was 3400 before this PR; +27 from
    this PR).

### Allowed transitions out of Phase 11C.1D-D-A

| From | To | Authorised by |
| --- | --- | --- |
| Phase 11C.1D-D-A IN_REVIEW | Phase 11C.1D-D-A ACCEPTED | Only via a separate docs-closeout PR after maintainer review. |
| Phase 11C.1D-D-A IN_REVIEW | PR95 — Historical Market Store v0 | After a successful PR94 acceptance; PR95 itself opens its own gate. |
| Phase 11C.1D-D-A IN_REVIEW | PR96 — ReplayFeedProvider | **FORBIDDEN by this phase alone.** Requires successful PR95 acceptance first. |
| Phase 11C.1D-D-A IN_REVIEW | PR97 — MockExchange + Pessimistic Fill Model | **FORBIDDEN by this phase alone.** Requires successful PR96 acceptance first. |
| Phase 11C.1D-D-A IN_REVIEW | PR98 — Simulated Capital Flow + Trade Ledger | **FORBIDDEN by this phase alone.** Requires successful PR97 acceptance first. |
| Phase 11C.1D-D-A IN_REVIEW | PR99 — Telegram Sandbox Outbox | **FORBIDDEN by this phase alone.** Requires successful PR98 acceptance first. |
| Phase 11C.1D-D-A IN_REVIEW | PR100 — Blind Walk-forward Runner v0 | **FORBIDDEN by this phase alone.** Requires successful PR99 acceptance first. |
| Phase 11C.1D-D-A IN_REVIEW | Blind Walk-forward implementation | **FORBIDDEN by this phase alone.** A complete blind walk-forward run requires PR94 → PR100 to have been accepted in order. |
| any | Phase 12 | **FORBIDDEN.** |

### Inheritance

Phase 11C.1D-D-A inherits, verbatim, every Phase 1, Phase
11C, Phase 11C.1A, Phase 11C.1B, Phase 11C.1C-A through
Phase 11C.1C-C-B-B-B-E-D, Phase AI-1 through Phase
AI-CHECKPOINT, Phase 11C / Offline Rule Sandbox Replay,
Phase 11C.1D-B *Paper Shadow Strategy Validation*, Phase
11C.1D-C *Risk / Execution / Capital Safety Matrix*, and
Phase 11C.1D-D *Strict Blind Walk-forward Sim-Live
Constitution* forbidden item.

The Risk Engine remains the single trade-decision gate.
Phase 12 remains **FORBIDDEN**.



## Open phase: Phase 11C.1D-D-B / Historical Market Store v0 (PR95, IN_REVIEW)

**Type:** Implementation PR (paper / report / evidence-only
infrastructure). **Runtime effect:** **none on real trading.**
One new module `app/sim/historical_market_store.py`, one new
unit-test module `tests/unit/test_historical_market_store.py`,
and one new phase doc
`docs/PHASE_11C_1D_D_B_HISTORICAL_MARKET_STORE.md`. The
`app/sim/__init__.py` re-exports the new public surface
alongside the PR94 substrate. **No file under `app/risk/`,
`app/execution/`, `app/exchanges/`, `app/telegram/`, or
`app/config/` is touched.** No event type wired into the
runtime hot path. No database schema / migration. The new
module has NO I/O, NO network, NO real data fetch, NO authority
over the Risk Engine, the Execution FSM, or the Capital Flow
Engine.

**What this PR ships.** The **second** anti-future-lookahead
infrastructure block of the strict blind walk-forward stack
defined by Phase 11C.1D-D (PR93, the *Strict Blind Walk-forward
Sim-Live Constitution*). PR93 §19's engineering route
explicitly authorises ONLY this PR (PR95) to begin the next
paper-only step after PR94. PR95 implements the typed
historical-record schema and the in-memory store that all
later (separately gated) PR96..PR100 modules MUST consume so
that the Constitution §5 / §6 / §9 / §10 / §E rules become
machine-enforceable at the data layer.

**Public surface added.**

  - :class:`HistoricalMarketRecordType` — closed taxonomy:
    `KLINE_1M`, `KLINE_5M`, `FUNDING_RATE`, `OPEN_INTEREST`,
    `TICKER_24H`, `EXCHANGE_INFO`, `SYMBOL_STATUS`,
    `LISTING_STATUS`, `DELISTING_STATUS`. `KLINE_TYPES` and
    `SYMBOL_STATUS_TYPES` subsets exposed.
  - :class:`DataQualityFlag` — closed taxonomy: `DATA_GAP`,
    `LATE_ARRIVAL`, `REVISED_RECORD`, `INCOMPLETE_KLINE`,
    `SYMBOL_STATUS_UNKNOWN`, `FUNDING_MISSING`, `OI_MISSING`,
    `TICKER_MISSING`.
  - :class:`SymbolStatus` — closed taxonomy: `TRADING`,
    `BREAK`, `HALT`, `DELISTED`, `SETTLING`, `PRE_TRADING`,
    `UNKNOWN`. `TRADABLE_OR_MONITORABLE` subset exposed
    (`DELISTED` is **explicitly excluded** from the as-of
    universe).
  - :class:`DataCompletenessState` — closed taxonomy: `OK`,
    `DEGRADED`, `INCOMPLETE`, `UNKNOWN`.
  - :class:`HistoricalMarketRecord` — generic non-kline
    record. Required: `record_id`, `record_type`, `event_time`,
    `available_at`. Optional: `symbol`, `ingested_at`, `source`,
    `interval`, `payload`, `data_quality_flags`, `evidence_refs`,
    `revision_time`, `revised_from_record_id`, `late_arrival`.
    `available_at >= event_time` enforced at construction;
    naive datetimes rejected; `payload` runs through
    `assert_no_forbidden_fields` and a JSON-serialisability
    check at construction time.
  - :class:`HistoricalKlineRecord` — 1m / 5m kline (v0
    supports `"1m"` and `"5m"` only). Required: `symbol`,
    `interval`, `open_time`, `open`, `high`, `low`, `close`,
    `volume`, `available_at`. Optional: `close_time` (defaults
    to `open_time + interval`; explicit value must agree),
    `event_time` (defaults to `open_time`), `ingested_at`,
    `source`, `record_id`, `data_quality_flags`,
    `evidence_refs`, `revision_time`, `revised_from_record_id`,
    `late_arrival`. `available_at >= close_time` is enforced at
    construction time (Constitution §6: final OHLCV invisible
    before close); OHLC sanity (`high >= max(open, close)`,
    `low <= min(open, close)`, `volume >= 0`) is enforced at
    construction time.
  - :class:`SymbolStatusRecord` — symbol metadata for the
    as-of universe (Constitution §9). Required: `symbol`,
    `market_type`, `listed_at`, `status`, `available_at`.
    Optional: `delisted_at`, `min_notional`, `tick_size`,
    `step_size`, `contract_type`, `data_completeness_state`
    (default `OK`), `source`, `ingested_at`, `record_id`,
    `event_time` (defaults to `listed_at`; the **only** field
    that may legitimately allow `available_at < listed_at` for
    pre-listing-announcement records, by being set explicitly
    to the announcement time, in which case `available_at >=
    event_time` is still enforced), `data_quality_flags`,
    `evidence_refs`, `revision_time`,
    `revised_from_record_id`, `late_arrival`. `DELISTED` status
    requires `delisted_at` to be set.
  - :class:`HistoricalMarketStore` — in-memory store. Public
    methods: `add_record(record)`, `add_records(records)`,
    `query_records(record_type, *, symbol=None,
    start_time=None, end_time=None, simulated_time)`,
    `query_latest(record_type, symbol, simulated_time)`,
    `query_klines(symbol, interval, *, start_time=None,
    end_time=None, simulated_time)`,
    `query_symbol_status(symbol, simulated_time)`,
    `query_asof_universe(simulated_time)`. Public properties:
    `time_wall_guard`, `candle_visibility_guard`, `violations`,
    `record_count`, `kline_count`, `symbol_status_count`.
    `clear_violations()` resets the audit accumulator.
    `safety_payload()` and `to_dict()` re-pin the project-wide
    safety boundary.

**Strict blind walk-forward semantics.**

  - Every query is gated by :class:`TimeWallGuard`. At
    simulated time `T`, the store returns ONLY records whose
    `available_at <= T`. Future records are NEVER silently
    dropped; every rejection produces a
    :class:`NoLookaheadViolation` audit object accessible via
    `store.violations`. `ingested_at` is NEVER substituted for
    `available_at`.
  - `query_klines` cross-checks
    :meth:`CandleVisibilityGuard.is_candle_closed` after the
    time wall passes. If a kline somehow lands on an unclosed
    candle relative to `simulated_time`, the store mints an
    `UNCLOSED_CANDLE_FIELD_ACCESS` violation and refuses to
    return the record. The candle is closed iff `simulated_time
    >= candle_close_time`; the close instant itself counts as
    closed.
  - `query_asof_universe(simulated_time)` enforces Constitution
    §9: a symbol qualifies iff `listed_at <= simulated_time`
    AND (`delisted_at is None` OR `delisted_at >
    simulated_time`) AND `available_at <= simulated_time` AND
    `status` is in `SymbolStatus.TRADABLE_OR_MONITORABLE`. The
    store NEVER substitutes the *current* symbol list; an empty
    store at any `simulated_time` returns an empty universe.
  - Late-arriving / revised records are first-class. A revised
    record's own `available_at` decides its earliest visibility.
    The original record is NEVER overwritten or removed; both
    remain in the audit trail.
  - All query results are deterministically sorted (by
    `(event_time, available_at, symbol, record_id)` for generic
    records; by `(open_time, available_at, record_id)` for
    klines; by `(symbol, listed_at, record_id)` for the as-of
    universe).

**Hard safety boundary (Phase 11C.1D-D-B / PR95).**

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

The Risk Engine remains the single trade-decision gate.

**No-network / no-LLM / no-Telegram / no-Binance assertions.**
The unit suite AST-walks `app/sim/__init__.py` and
`app/sim/historical_market_store.py` and asserts that they do
**NOT** import `app.risk` / `app.execution` / `app.exchanges` /
`app.telegram` / `app.config`, do **NOT** import any
`deepseek` / `openai` / `anthropic` / `telegram` / `binance` /
`ccxt` / `websocket` / `websockets` / `httpx` / `aiohttp` /
`requests` / `urllib.request` / `http.client` / `grpc` /
`boto3` / `socket` module, and do **NOT** reference any
`requests.get` / `requests.post` / `urllib.request` /
`socket.connect` / `socket.create_connection` identifier.
Importing the `app.sim` package and the new
`app.sim.historical_market_store` module is also asserted at
runtime (via `sys.modules` diffing) to not pull any forbidden
module.

**No-trade-verb public surface assertion.** A dedicated test
asserts that no public method on
:class:`HistoricalMarketStore`, :class:`HistoricalMarketRecord`,
:class:`HistoricalKlineRecord`, or :class:`SymbolStatusRecord`
exposes any of the trade verbs `buy`, `sell`, `place_order`,
`submit_order`, `long`, `short`, `open_position`,
`close_position`, `set_leverage`, `set_stop`, `set_target`,
`apply_change`, `deploy`, `enable_live`.

**Forbidden by this PR (verbatim).**

  - Do not modify `app/risk/**`, `app/execution/**`,
    `app/exchanges/**`, `app/telegram/**`, `app/config/**`.
  - Do not implement the ReplayFeedProvider (PR96).
  - Do not implement the MockExchange + Pessimistic Fill
    Model (PR97).
  - Do not implement the Simulated Capital Flow + Trade
    Ledger (PR98).
  - Do not implement the Telegram Sandbox Outbox (PR99).
  - Do not implement the Blind Walk-forward Runner (PR100).
  - Do not enable live orders.
  - Do not connect to Binance private API.
  - Do not enable any real Telegram outbound.
  - Do not call DeepSeek / LLM / any network transport.
  - Do not auto-tune anything.
  - Do not enter Phase 12.

**Tests.** `python -m pytest
tests/unit/test_historical_market_store.py -q` ships **26
PASSING** tests (covering all 21 brief-mandated scenarios plus
5 defensive extras: closed-taxonomy sweep, kline construction-
time invariants, symbol-status invariants, latest-symbol-
status, deterministic violation IDs); `python -m pytest
tests/unit -q` reports **3453 PASSING** tests, 0 failures (was
3427 before this phase; +26 from this phase).

### Allowed transitions out of Phase 11C.1D-D-B

| From | To | Authorised by |
| --- | --- | --- |
| Phase 11C.1D-D-B IN_REVIEW | Phase 11C.1D-D-B ACCEPTED | Only via a separate docs-closeout PR after maintainer review. |
| Phase 11C.1D-D-B IN_REVIEW | PR96 — ReplayFeedProvider | After a successful PR95 acceptance; PR96 itself opens its own gate. |
| Phase 11C.1D-D-B IN_REVIEW | PR97 — MockExchange + Pessimistic Fill Model | **FORBIDDEN by this phase alone.** Requires successful PR96 acceptance first. |
| Phase 11C.1D-D-B IN_REVIEW | PR98 — Simulated Capital Flow + Trade Ledger | **FORBIDDEN by this phase alone.** Requires successful PR97 acceptance first. |
| Phase 11C.1D-D-B IN_REVIEW | PR99 — Telegram Sandbox Outbox | **FORBIDDEN by this phase alone.** Requires successful PR98 acceptance first. |
| Phase 11C.1D-D-B IN_REVIEW | PR100 — Blind Walk-forward Runner v0 | **FORBIDDEN by this phase alone.** Requires successful PR99 acceptance first. |
| Phase 11C.1D-D-B IN_REVIEW | Blind Walk-forward implementation | **FORBIDDEN by this phase alone.** A complete blind walk-forward run requires PR94 → PR100 to have been accepted in order. |
| any | Phase 12 | **FORBIDDEN.** |

### Inheritance

Phase 11C.1D-D-B inherits, verbatim, every Phase 1, Phase
11C, Phase 11C.1A, Phase 11C.1B, Phase 11C.1C-A through
Phase 11C.1C-C-B-B-B-E-D, Phase AI-1 through Phase
AI-CHECKPOINT, Phase 11C / Offline Rule Sandbox Replay,
Phase 11C.1D-B *Paper Shadow Strategy Validation*, Phase
11C.1D-C *Risk / Execution / Capital Safety Matrix*, Phase
11C.1D-D *Strict Blind Walk-forward Sim-Live Constitution*,
and Phase 11C.1D-D-A *SimulationClock + Time-Wall Guard*
forbidden item.

The Risk Engine remains the single trade-decision gate.
Phase 12 remains **FORBIDDEN**.



## Open phase: Phase 11C.1D-D-C / ReplayFeedProvider v0 (PR96, IN_REVIEW)

**Type:** Implementation PR (paper / report / evidence-only
infrastructure). **Runtime effect:** **none on real trading.**
One new module `app/sim/replay_feed_provider.py`, one new
unit-test module `tests/unit/test_replay_feed_provider.py`,
and one new phase doc
`docs/PHASE_11C_1D_D_C_REPLAY_FEED_PROVIDER.md`. The
`app/sim/__init__.py` re-exports the new public surface
alongside the PR94 + PR95 substrate. **No file under
`app/risk/`, `app/execution/`, `app/exchanges/`,
`app/telegram/`, or `app/config/` is touched.** No PR94 or
PR95 source file is modified — the existing
`app/sim/simulation_clock.py`, `app/sim/time_wall_guard.py`, and
`app/sim/historical_market_store.py` contracts are reused
verbatim. No event type wired into the runtime hot path. No
database schema / migration. The new module has NO I/O, NO
network, NO real data fetch, NO authority over the Risk Engine,
the Execution FSM, or the Capital Flow Engine.

**What this PR ships.** The **third** anti-future-lookahead
infrastructure block of the strict blind walk-forward stack
defined by Phase 11C.1D-D (PR93, the *Strict Blind Walk-forward
Sim-Live Constitution*). PR93 §19's engineering route explicitly
authorises ONLY this PR (PR96) to begin the next paper-only step
after PR95. PR96 implements the deterministic, forward-only feed
substrate that all later (separately gated) PR97..PR100 modules
MUST consume so that the Constitution §5 / §6 / §9 / §10 / §E
rules become machine-enforceable at the feed layer.

**Public surface added.**

  - :class:`ReplayFeedProviderConfig` — frozen replay-window
    config: `start_time`, `end_time`, `step_interval`
    (timedelta / number-of-seconds / interval-string),
    `include_record_types` (default = full Constitution §10 v0
    minimum: `KLINE_1M`, `KLINE_5M`, `FUNDING_RATE`,
    `OPEN_INTEREST`, `TICKER_24H`, `EXCHANGE_INFO`,
    `SYMBOL_STATUS`, `LISTING_STATUS`, `DELISTING_STATUS`),
    optional `symbols` filter, `include_asof_universe`
    (default `True`), `allow_reemit` (default `False`),
    `strict_time_wall` (default `True`),
    `strict_candle_visibility` (default `True`). Naive
    datetimes rejected; `end_time >= start_time` enforced;
    `step_interval > 0` enforced; `include_record_types`
    rejects unknown / empty / duplicate values.
  - :class:`ReplayFeedCursor` — forward-only cursor:
    `start_time`, `end_time`, `step_interval`, `current_time`,
    `emitted_record_ids`, `replay_complete`. Cannot move
    backward, cannot fall below `start_time`, cannot exceed
    `end_time`. Reaches `replay_complete=True` when the cursor
    hits `end_time`.
  - :class:`ReplayFeedDiagnostics` — cumulative counters:
    `total_records_considered`, `emitted_record_count`,
    `future_records_rejected_count`,
    `missing_available_at_count`,
    `unclosed_candle_violation_count`,
    `duplicate_record_skipped_count`, `data_gap_flags` (closed
    `DataQualityFlag.*` taxonomy), and the preserved
    :class:`NoLookaheadViolation` audit list.
    `record_violation(v)` classifies by reason and bumps the
    matching counter; `record_data_quality_flag(f)` enforces the
    closed taxonomy; `snapshot()` returns a deep copy used by
    every :class:`ReplayFeedBatch`.
  - :class:`ReplayFeedBatch` — frozen, JSON-serialisable
    per-tick batch. Fields: `batch_id`, `simulated_time`,
    `records` (deterministic catch-all union sorted by
    `(event_time, available_at, symbol, record_id)`),
    `klines_1m`, `klines_5m`, `funding_rates`, `open_interest`,
    `ticker_24h`, `symbol_status`, `asof_universe` (snapshot,
    NEVER deduped), `diagnostics` (snapshot of cumulative),
    `violations` (per-batch slice of `store.violations`),
    `replay_complete`, plus hard-pinned
    `phase_12_forbidden=True`, `auto_tuning_allowed=False`,
    `trade_authority=False`. Construction refuses any attempt to
    flip the safety flags.
  - :class:`ReplayFeedProvider` — deterministic forward-only feed
    provider. Public methods: `next_batch()` (advance clock by
    `config.step_interval`), `advance_and_get_batch(delta)`
    (advance clock by `delta`; `delta` may be `timedelta` /
    `int|float` seconds / interval string),
    `batch_at(simulated_time)` (advance clock to
    `simulated_time` which MUST be `>= cursor.current_time`),
    `get_asof_universe()` (also forward-only),
    `get_diagnostics()` (returns a snapshot), `reset()`
    (test-only; requires `monotonic_forward_only=False` on the
    clock), `safety_payload()`, `to_dict()`. Public properties
    `store`, `clock`, `config`, `cursor`, `diagnostics`,
    `time_wall_guard`, `candle_visibility_guard`,
    `replay_complete`, plus the defensive tripwires
    `sandbox_only`, `live_trading`, `exchange_live_orders`,
    `binance_private_api_enabled`, `telegram_outbound_enabled`,
    `ai_trade_authority`, `trade_authority`,
    `auto_tuning_allowed`, `phase_12_forbidden`.
    `next_batch()` raises `StopIteration` after
    `replay_complete=True`.

**Strict blind walk-forward semantics.**

  - Every emitted record obeys
    `available_at <= simulated_time`, delegated to PR95
    :meth:`HistoricalMarketStore.query_records`, which
    delegates to PR94
    :meth:`TimeWallGuard.validate_no_lookahead`. Future
    records produce :class:`NoLookaheadViolation` audit
    objects accumulated on `store.violations`; PR96 reads the
    per-batch slice and (a) records each via
    :meth:`ReplayFeedDiagnostics.record_violation` and (b)
    exposes the slice as :pyattr:`ReplayFeedBatch.violations`.
    `ingested_at` is NEVER substituted for `available_at`.
  - Closed-candle visibility is enforced by construction in
    PR95 (`HistoricalKlineRecord.available_at >= close_time`)
    and re-checked at query time via
    :meth:`CandleVisibilityGuard.is_candle_closed` when
    `strict_candle_visibility=True`. If a kline somehow lands
    on an unclosed candle relative to `simulated_time`, PR96
    mints an `UNCLOSED_CANDLE_FIELD_ACCESS` violation via
    :meth:`TimeWallGuard.make_unclosed_candle_field_access_violation`
    and refuses to emit the batch.
  - The as-of universe is delegated to
    :meth:`HistoricalMarketStore.query_asof_universe`
    (Constitution §9: `listed_at <= T` AND
    (`delisted_at is None` OR `delisted_at > T`) AND
    `available_at <= T` AND `status` is in
    `SymbolStatus.TRADABLE_OR_MONITORABLE`). The provider
    NEVER consults the *current* symbol list; an empty store
    at any `simulated_time` returns an empty universe.
  - All batch contents are deterministically sorted (records by
    `(event_time, available_at, symbol, record_id)`; per-type
    lists by the same key; as-of universe by `(symbol,
    listed_at, record_id)`; `batch_id` is the deterministic
    `"replay_batch_{counter:06d}"` string). Two providers fed
    identical (store, clock, config) produce byte-identical
    batch sequences.
  - All record / batch / cursor / diagnostics / config /
    provider `to_dict()` outputs are JSON-serialisable.

**Hard safety boundary (Phase 11C.1D-D-C / PR96).**

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

The Risk Engine remains the single trade-decision gate.

**No-network / no-LLM / no-Telegram / no-Binance assertions.**
The unit suite AST-walks `app/sim/__init__.py` and
`app/sim/replay_feed_provider.py` and asserts that they do
**NOT** import `app.risk` / `app.execution` / `app.exchanges` /
`app.telegram` / `app.config`, do **NOT** import any
`deepseek` / `openai` / `anthropic` / `telegram` / `binance` /
`ccxt` / `websocket` / `websockets` / `httpx` / `aiohttp` /
`requests` / `urllib.request` / `http.client` / `grpc` /
`boto3` / `socket` module, and do **NOT** reference any
`requests.get` / `requests.post` / `urllib.request` /
`socket.connect` / `socket.create_connection` identifier.
Importing the `app.sim` package and the new
`app.sim.replay_feed_provider` module is also asserted at
runtime (via `sys.modules` diffing) to not pull any forbidden
module.

**No-trade-verb public surface assertion.** A dedicated test
asserts that no public method on
:class:`ReplayFeedProvider`, :class:`ReplayFeedBatch`,
:class:`ReplayFeedCursor`, :class:`ReplayFeedDiagnostics`, or
:class:`ReplayFeedProviderConfig` exposes any of the trade
verbs `buy`, `sell`, `place_order`, `submit_order`, `long`,
`short`, `open_position`, `close_position`, `set_leverage`,
`set_stop`, `set_target`, `apply_change`, `deploy`,
`enable_live`.

**Forbidden by this PR (verbatim).**

  - Do not modify `app/risk/**`, `app/execution/**`,
    `app/exchanges/**`, `app/telegram/**`, `app/config/**`.
  - Do not modify `app/sim/simulation_clock.py`,
    `app/sim/time_wall_guard.py`, or
    `app/sim/historical_market_store.py` (PR94 + PR95 contracts
    are reused verbatim).
  - Do not implement the MockExchange + Pessimistic Fill
    Model (PR97).
  - Do not implement the Simulated Capital Flow + Trade
    Ledger (PR98).
  - Do not implement the Telegram Sandbox Outbox (PR99).
  - Do not implement the Blind Walk-forward Runner (PR100).
  - Do not enable live orders.
  - Do not connect to Binance private API.
  - Do not enable any real Telegram outbound.
  - Do not call DeepSeek / LLM / any network transport.
  - Do not auto-tune anything.
  - Do not enter Phase 12.

**Tests.** `python -m pytest
tests/unit/test_replay_feed_provider.py -q` ships **26
PASSING** tests (covering all 21 brief-mandated scenarios plus
5 defensive extras: config validation sweep,
`replay_complete` + `StopIteration`, symbol filter, `reset()`
requires non-monotonic clock, `data_quality_flags`
propagation); `python -m pytest tests/unit -q` reports
**3479 PASSING** tests, 0 failures (was 3453 before this
phase; +26 from this phase).

### Allowed transitions out of Phase 11C.1D-D-C

| From | To | Authorised by |
| --- | --- | --- |
| Phase 11C.1D-D-C IN_REVIEW | Phase 11C.1D-D-C ACCEPTED | Only via a separate docs-closeout PR after maintainer review. |
| Phase 11C.1D-D-C IN_REVIEW | PR97 — MockExchange + Pessimistic Fill Model v0 | After a successful PR96 acceptance; PR97 itself opens its own gate. |
| Phase 11C.1D-D-C IN_REVIEW | PR98 — Simulated Capital Flow + Trade Ledger | **FORBIDDEN by this phase alone.** Requires successful PR97 acceptance first. |
| Phase 11C.1D-D-C IN_REVIEW | PR99 — Telegram Sandbox Outbox | **FORBIDDEN by this phase alone.** Requires successful PR98 acceptance first. |
| Phase 11C.1D-D-C IN_REVIEW | PR100 — Blind Walk-forward Runner v0 | **FORBIDDEN by this phase alone.** Requires successful PR99 acceptance first. |
| Phase 11C.1D-D-C IN_REVIEW | Blind Walk-forward implementation | **FORBIDDEN by this phase alone.** A complete blind walk-forward run requires PR94 → PR100 to have been accepted in order. |
| any | Phase 12 | **FORBIDDEN.** |

### Inheritance

Phase 11C.1D-D-C inherits, verbatim, every Phase 1, Phase
11C, Phase 11C.1A, Phase 11C.1B, Phase 11C.1C-A through
Phase 11C.1C-C-B-B-B-E-D, Phase AI-1 through Phase
AI-CHECKPOINT, Phase 11C / Offline Rule Sandbox Replay,
Phase 11C.1D-B *Paper Shadow Strategy Validation*, Phase
11C.1D-C *Risk / Execution / Capital Safety Matrix*, Phase
11C.1D-D *Strict Blind Walk-forward Sim-Live Constitution*,
Phase 11C.1D-D-A *SimulationClock + Time-Wall Guard*, and
Phase 11C.1D-D-B *Historical Market Store v0* forbidden item.

The Risk Engine remains the single trade-decision gate.
Phase 12 remains **FORBIDDEN**.


## Open phase: Phase 11C.1D-D-D / MockExchange + Pessimistic Fill Model v0 (PR97, IN_REVIEW)

**Status:** IN_REVIEW (after this implementation PR; not
`ACCEPTED` until maintainer review).

**Type:** **Implementation PR** (paper / report / evidence-only
infrastructure).

**Phase identifier:**
`Phase 11C.1D-D-D / PR97 / MockExchange + Pessimistic Fill Model v0`.

**Parent:** Phase 11C.1D-D *Strict Blind Walk-forward Sim-Live
Constitution* (PR93, merged), Phase 11C.1D-D-A
*SimulationClock + Time-Wall Guard* (PR94, merged), Phase
11C.1D-D-B *Historical Market Store v0* (PR95, merged), and
Phase 11C.1D-D-C *ReplayFeedProvider v0* (PR96, merged).
Phase 11C.1D-D-D ships the **fourth** anti-future-lookahead
infrastructure block of the strict blind walk-forward stack.
The constitution's PR93 §19 engineering route explicitly
authorises ONLY this PR (PR97) to begin the next paper-only
step. PR97 introduces a small, deterministic, pure-Python
in-memory simulated exchange and a conservative fill model
that consume only PR96 :class:`ReplayFeedBatch` / PR95
:class:`HistoricalKlineRecord` visible market data.

### Scope (Phase 11C.1D-D-D / PR97)

Authorised:

  - the public surface listed in §0 of
    `docs/PHASE_11C_1D_D_D_MOCK_EXCHANGE_PESSIMISTIC_FILL_MODEL.md`
    (`MockOrderType`, `MockOrderSide`, `MockOrderStatus`,
    `AmbiguousIntrabarPolicy`, `LimitTouchFillPolicy`,
    `FillReason`, `ConservativeAssumption`, `MockOrder`,
    `MockFill`, `MockExchangeConfig`, `FillModelDecision`,
    `PessimisticFillModel`, `OrderRequest`,
    `MockExchangeDiagnostics`, `MockExchange`),
  - the matching unit-test module
    `tests/unit/test_mock_exchange_pessimistic_fill_model.py`
    (the 25-test PR97 safety contract: 22 brief-mandated
    scenarios plus 3 defensive extras),
  - the docs trio
    (`docs/PHASE_11C_1D_D_D_MOCK_EXCHANGE_PESSIMISTIC_FILL_MODEL.md`,
    `docs/PROJECT_STATUS.md` current-phase block,
    `docs/PHASE_GATE.md` this section,
    `docs/CHANGELOG.md` entry).

Files explicitly NOT touched:

  - `app/risk/**`, `app/execution/**`, `app/exchanges/**`,
    `app/telegram/**`, `app/config/**`,
  - `app/sim/simulation_clock.py`,
    `app/sim/time_wall_guard.py`,
    `app/sim/historical_market_store.py`,
    `app/sim/replay_feed_provider.py` (PR94 + PR95 + PR96
    contracts are reused verbatim; not modified),
  - `app/safety/**`, `app/ai/**`, `app/replay/**`,
    `app/reflection/**`, `app/paper_shadow/**`,
    `app/sandbox/**`, `app/state_machine/**`,
    `app/scanner/**`, `app/regime/**`,
    `app/market_data/**`, `app/market_data_public/**`,
    `app/universe/**`, `app/liquidity/**`,
    `app/manipulation/**`, `app/monitoring/**`,
    `app/database/**`, `app/exports/**`,
    `app/incidents/**`, `app/learning/**`,
    `app/llm/**`, `app/paper_run/**`,
    `app/reconciliation/**`, `app/confirmation/**`,
    `app/capital/**`, `app/core/**`, `app/main.py`,
  - `scripts/**`, `configs/**`, `data/**`,
    `requirements.txt`, `pyproject.toml`, `.env*`.

### Forbidden by this phase

  - Do NOT modify `app/risk/**`, `app/execution/**`,
    `app/exchanges/**`, `app/telegram/**`, `app/config/**`.
  - Do NOT modify the PR94 / PR95 / PR96 sources.
  - Do NOT implement the Simulated Capital Flow + Trade
    Ledger (PR98).
  - Do NOT implement the Telegram Sandbox Outbox (PR99).
  - Do NOT implement the Blind Walk-forward Runner (PR100).
  - Do NOT enable live orders.
  - Do NOT connect to Binance private API.
  - Do NOT add any signed endpoint.
  - Do NOT add any private websocket / listenKey.
  - Do NOT advertise a real exchange order id, an api key,
    an api secret, or a signed-endpoint reference.
  - Do NOT enable any real Telegram outbound.
  - Do NOT call DeepSeek / LLM / any network transport.
  - Do NOT auto-tune anything.
  - Do NOT enter Phase 12.

### Acceptance criteria

  - PR97 is marked **IN_REVIEW**.
  - Promotion to `ACCEPTED` requires a separate docs-closeout
    PR after maintainer review. **Phase 12 remains
    FORBIDDEN.**
  - All 25 tests in
    `tests/unit/test_mock_exchange_pessimistic_fill_model.py`
    pass; the full suite reports **3504 PASSING** tests, 0
    failures (was 3479 before this phase; +25 from this
    phase).

**Hard safety boundary (Phase 11C.1D-D-D / PR97).**

| flag | value |
| --- | --- |
| `mode` | `paper` |
| `sandbox_only` | `True` |
| `simulated_only` | `True` |
| `no_live_order` | `True` |
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

### Allowed transitions out of Phase 11C.1D-D-D

| From | To | Authorised by |
| --- | --- | --- |
| Phase 11C.1D-D-D IN_REVIEW | Phase 11C.1D-D-D ACCEPTED | Only via a separate docs-closeout PR after maintainer review. |
| Phase 11C.1D-D-D IN_REVIEW | PR98 — Simulated Capital Flow + Trade Ledger v0 | After a successful PR97 acceptance; PR98 itself opens its own gate. |
| Phase 11C.1D-D-D IN_REVIEW | PR99 — Telegram Sandbox Outbox | **FORBIDDEN by this phase alone.** Requires successful PR98 acceptance first. |
| Phase 11C.1D-D-D IN_REVIEW | PR100 — Blind Walk-forward Runner v0 | **FORBIDDEN by this phase alone.** Requires successful PR99 acceptance first. |
| Phase 11C.1D-D-D IN_REVIEW | Blind Walk-forward implementation | **FORBIDDEN by this phase alone.** A complete blind walk-forward run requires PR94 → PR100 to have been accepted in order. |
| any | Phase 12 | **FORBIDDEN.** |

### Inheritance

Phase 11C.1D-D-D inherits, verbatim, every Phase 1, Phase
11C, Phase 11C.1A, Phase 11C.1B, Phase 11C.1C-A through
Phase 11C.1C-C-B-B-B-E-D, Phase AI-1 through Phase
AI-CHECKPOINT, Phase 11C / Offline Rule Sandbox Replay,
Phase 11C.1D-B *Paper Shadow Strategy Validation*, Phase
11C.1D-C *Risk / Execution / Capital Safety Matrix*, Phase
11C.1D-D *Strict Blind Walk-forward Sim-Live Constitution*,
Phase 11C.1D-D-A *SimulationClock + Time-Wall Guard*, Phase
11C.1D-D-B *Historical Market Store v0*, and Phase
11C.1D-D-C *ReplayFeedProvider v0* forbidden item.

The Risk Engine remains the single trade-decision gate.
Phase 12 remains **FORBIDDEN**.



## Open phase: Phase 11C.1D-D-F / Telegram Sandbox Outbox v0 (PR99, IN_REVIEW)

> **Status:** IN_REVIEW after this implementation PR; not
> ACCEPTED until maintainer review.
> **Phase identity string:**
> `Phase 11C.1D-D-F / PR99 / Telegram Sandbox Outbox v0`.

### Purpose

Phase 11C.1D-D-F ships the **sixth** anti-future-lookahead
infrastructure block of the strict blind walk-forward stack
defined by Phase 11C.1D-D (PR93). PR98's engineering route
explicitly authorises ONLY this PR (PR99) to begin the next
paper-only step. PR99 introduces one small, deterministic,
pure-Python module (`app/sim/telegram_sandbox_outbox.py`) that
exposes a closed-vocabulary, file-only, paper-only Telegram
notification surface for blind-run evidence and operator review.

### Scope (Phase 11C.1D-D-F / PR99)

  - `app/sim/telegram_sandbox_outbox.py` (new module): defines
    `TelegramSandboxMessageType` (closed taxonomy of exactly 13
    values), `TelegramSandboxSeverity` (closed taxonomy: `INFO` /
    `NOTICE` / `WARNING` / `CRITICAL`), the four mandatory
    simulated / no-live transcript labels
    (`SIMULATED_HISTORICAL_BLIND_TEST_LABEL`,
    `NO_LIVE_ORDER_LABEL`, `NO_REAL_CAPITAL_LABEL`,
    `NO_TELEGRAM_COMMAND_AUTHORITY_LABEL`, exposed as
    `MANDATORY_LABELS`), `TelegramSandboxMessage` (frozen, with
    hard-pinned `sandbox_only=True`,
    `no_live_order_assertion=True`,
    `no_real_capital_assertion=True`,
    `no_telegram_command_authority=True`,
    `phase_12_forbidden=True`, `trade_authority=False`,
    `auto_tuning_allowed=False`),
    `TelegramSandboxOutboxConfig` (frozen, with hard-pinned
    `sandbox_only=True`, `telegram_outbound_enabled=False`,
    `telegram_live_command_authority=False`,
    `telegram_production_channel_enabled=False`,
    `command_authority=False`), and `TelegramSandboxOutbox`
    (paper-only / file-only writer with `append_message` /
    `append_messages` / `render_message` / `write_jsonl` /
    `write_markdown_transcript` / `list_messages` / `reset` /
    `safety_payload` / `to_dict`).
  - `app/sim/__init__.py` (extended): re-exports the new public
    surface alongside PR94 / PR95 / PR96 / PR97 / PR98.
  - `tests/unit/test_telegram_sandbox_outbox.py` (new): the
    23-test PR99 safety contract — 21 brief-mandated tests plus 2
    defensive extras (closed-taxonomy + phase-name-string
    presence; `reset()` clears the in-memory list but does NOT
    truncate any on-disk artefact).
  - `docs/PHASE_11C_1D_D_F_TELEGRAM_SANDBOX_OUTBOX.md` (new): the
    phase design / acceptance doc.
  - `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
    `docs/CHANGELOG.md` (updated).

### Out-of-scope (Phase 11C.1D-D-F)

  - **Blind Walk-forward Runner** (PR100). Forbidden by this
    phase alone.
  - Any change under `app/risk/`, `app/execution/`,
    `app/exchanges/`, `app/telegram/`, `app/config/`, or other
    runtime hot-path packages. The existing Phase 10D Telegram
    fake / refusal boundary in `app/telegram/` is **NOT** reused
    by PR99; PR99 has its own separate sandbox path that NEVER
    touches the real outbound transport.
  - Any modification of the existing PR94 / PR95 / PR96 / PR97 /
    PR98 sources.
  - Any real Telegram outbound, real Telegram bot token, real
    production / live Telegram channel, or Telegram command
    authority.
  - Any real account / signed endpoint / private websocket /
    listenKey access.
  - Any LLM, DeepSeek, Telegram, or Binance network call.
  - Any auto-tuning of any parameter or rule.
  - Any entry into Phase 12.

### Hard safety boundary (Phase 11C.1D-D-F / PR99)

| flag | value |
| --- | --- |
| `mode` | `paper` |
| `sandbox_only` | `True` |
| `simulated_only` | `True` |
| `no_live_order` | `True` |
| `no_live_order_assertion` | `True` |
| `no_real_capital_assertion` | `True` |
| `no_telegram_command_authority` | `True` |
| `live_trading` | `False` |
| `live_capital_enabled` | `False` |
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
| `telegram_production_channel_enabled` | `False` |
| `ai_trade_authority` | `False` |
| `trade_authority` | `False` |
| `auto_tuning_allowed` | `False` |
| `phase_12_forbidden` | **`True`** |

### Allowed transitions out of Phase 11C.1D-D-F

| From | To | Authorised by |
| --- | --- | --- |
| Phase 11C.1D-D-F IN_REVIEW | Phase 11C.1D-D-F ACCEPTED | Only via a separate docs-closeout PR after maintainer review. |
| Phase 11C.1D-D-F IN_REVIEW | PR100 — Blind Walk-forward Runner v0 | After a successful PR99 acceptance; PR100 itself opens its own gate. |
| Phase 11C.1D-D-F IN_REVIEW | Blind Walk-forward implementation | **FORBIDDEN by this phase alone.** A complete blind walk-forward run requires PR94 → PR100 to have been accepted in order. |
| any | Phase 12 | **FORBIDDEN.** |

### Inheritance

Phase 11C.1D-D-F inherits, verbatim, every Phase 1, Phase 11C,
Phase 11C.1A, Phase 11C.1B, Phase 11C.1C-A through Phase
11C.1C-C-B-B-B-E-D, Phase AI-1 through Phase AI-CHECKPOINT, Phase
11C / Offline Rule Sandbox Replay, Phase 11C.1D-B *Paper Shadow
Strategy Validation*, Phase 11C.1D-C *Risk / Execution / Capital
Safety Matrix*, Phase 11C.1D-D *Strict Blind Walk-forward Sim-Live
Constitution*, Phase 11C.1D-D-A *SimulationClock + Time-Wall
Guard*, Phase 11C.1D-D-B *Historical Market Store v0*, Phase
11C.1D-D-C *ReplayFeedProvider v0*, Phase 11C.1D-D-D *MockExchange
+ Pessimistic Fill Model v0*, and Phase 11C.1D-D-E *Simulated
Capital Flow + Trade Ledger v0* forbidden item.

The Risk Engine remains the single trade-decision gate.
Phase 12 remains **FORBIDDEN**.

## Open phase: Phase 11C.1D-D-E / Simulated Capital Flow + Trade Ledger v0 (PR98, IN_REVIEW)

> **Status:** IN_REVIEW after this implementation PR; not
> ACCEPTED until maintainer review.
> **Phase identity string:**
> `Phase 11C.1D-D-E / PR98 / Simulated Capital Flow + Trade Ledger v0`.

### Purpose

Phase 11C.1D-D-E ships the **fifth** anti-future-lookahead
infrastructure block of the strict blind walk-forward stack defined
by Phase 11C.1D-D (PR93). PR97's engineering route explicitly
authorises ONLY this PR (PR98) to begin the next paper-only step.
PR98 introduces two small, deterministic, pure-Python modules
(`app/sim/simulated_capital_flow.py` and `app/sim/trade_ledger.py`)
that consume the :class:`MockFill` outputs of PR97's
:class:`MockExchange` and produce the simulated capital state, the
simulated position book, the trade ledger, and the equity
timeseries.

### Scope (Phase 11C.1D-D-E / PR98)

  - `app/sim/simulated_capital_flow.py` (new module): defines
    `SimulatedCapitalConfig`, `SimulatedPosition`,
    `SimulatedCapitalState`, `SimulatedCapitalFlowEngine`,
    `PositionSide`, `PositionStatus`, `RiskFreezeReason`,
    `CapitalFrozenError`.
  - `app/sim/trade_ledger.py` (new module): defines
    `TradeLedgerEntry`, `TradeLedger`, `TradeLedgerSummary`,
    `EquityTimeseriesPoint`, `TradeOutcome`, `TradeFailureFlag`.
  - `app/sim/__init__.py` (extended): re-exports the new public
    surface alongside PR94 / PR95 / PR96 / PR97.
  - `tests/unit/test_simulated_capital_flow_trade_ledger.py` (new):
    the 26-test PR98 safety contract — 24 brief-mandated tests
    plus closed-taxonomy enforcement and phase-name-string
    presence.
  - `docs/PHASE_11C_1D_D_E_SIMULATED_CAPITAL_FLOW_TRADE_LEDGER.md`
    (new): the phase design / acceptance doc.
  - `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
    `docs/CHANGELOG.md` (updated).

### Out-of-scope (Phase 11C.1D-D-E)

  - **Telegram Sandbox Outbox** (PR99). Forbidden by this phase
    alone.
  - **Blind Walk-forward Runner** (PR100). Forbidden by this phase
    alone.
  - Any change under `app/risk/`, `app/execution/`,
    `app/exchanges/`, `app/telegram/`, `app/config/`, or other
    runtime hot-path packages.
  - Any modification of the existing PR94 / PR95 / PR96 / PR97
    sources.
  - Any real account / signed endpoint / private websocket /
    listenKey access.
  - Any LLM, DeepSeek, Telegram, or Binance network call.
  - Any auto-tuning of any parameter or rule.
  - Any entry into Phase 12.

### Hard safety boundary (Phase 11C.1D-D-E / PR98)

| flag | value |
| --- | --- |
| `mode` | `paper` |
| `sandbox_only` | `True` |
| `simulated_only` | `True` |
| `no_live_order` | `True` |
| `live_trading` | `False` |
| `live_capital_enabled` | `False` |
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

### Allowed transitions out of Phase 11C.1D-D-E

| From | To | Authorised by |
| --- | --- | --- |
| Phase 11C.1D-D-E IN_REVIEW | Phase 11C.1D-D-E ACCEPTED | Only via a separate docs-closeout PR after maintainer review. |
| Phase 11C.1D-D-E IN_REVIEW | PR99 — Telegram Sandbox Outbox v0 | PR99 has now opened its own gate (Phase 11C.1D-D-F, IN_REVIEW); see the open-phase block above. |
| Phase 11C.1D-D-E IN_REVIEW | PR100 — Blind Walk-forward Runner v0 | **FORBIDDEN by this phase alone.** Requires successful PR99 acceptance first. |
| Phase 11C.1D-D-E IN_REVIEW | Blind Walk-forward implementation | **FORBIDDEN by this phase alone.** A complete blind walk-forward run requires PR94 → PR100 to have been accepted in order. |
| any | Phase 12 | **FORBIDDEN.** |

### Inheritance

Phase 11C.1D-D-E inherits, verbatim, every Phase 1, Phase 11C,
Phase 11C.1A, Phase 11C.1B, Phase 11C.1C-A through Phase
11C.1C-C-B-B-B-E-D, Phase AI-1 through Phase AI-CHECKPOINT, Phase
11C / Offline Rule Sandbox Replay, Phase 11C.1D-B *Paper Shadow
Strategy Validation*, Phase 11C.1D-C *Risk / Execution / Capital
Safety Matrix*, Phase 11C.1D-D *Strict Blind Walk-forward Sim-Live
Constitution*, Phase 11C.1D-D-A *SimulationClock + Time-Wall
Guard*, Phase 11C.1D-D-B *Historical Market Store v0*, Phase
11C.1D-D-C *ReplayFeedProvider v0*, and Phase 11C.1D-D-D
*MockExchange + Pessimistic Fill Model v0* forbidden item.

The Risk Engine remains the single trade-decision gate.
Phase 12 remains **FORBIDDEN**.



## Open phase: Phase 11C.1D-D-G / Blind Walk-forward Runner v0 (PR100, IN_REVIEW)

> **Title:** Blind Walk-forward Runner v0
> **Status:** IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).
> **Type:** implementation PR (paper / report / evidence-only
> infrastructure).
> **Phase 12:** **FORBIDDEN** (no change).

PR100 ships the **seventh** anti-future-lookahead infrastructure
block of the strict blind walk-forward stack defined by Phase
11C.1D-D (PR93). It strings PR94..PR99 substrate (the
SimulationClock + Time-Wall Guard, the Historical Market Store,
the ReplayFeedProvider, the MockExchange + Pessimistic Fill
Model, the Simulated Capital Flow + Trade Ledger, the Telegram
Sandbox Outbox) into the first version of the strict
forward-only historical sim-live blind runner.

The runner implements the `train` / `freeze` / `blind` /
`score` / `experience-update` loop the Constitution requires,
drives a `SimulationClock` from `window.blind_start` to
`window.blind_end`, pulls one batch per step from the
`ReplayFeedProvider`, marks the `SimulatedCapitalFlowEngine`
against the closed 1m candles in each batch, forwards orders
returned by an optional decision callback to the
`MockExchange`, forwards every fill back into the
`SimulatedCapitalFlowEngine` so the trade ledger and equity
time-series stay consistent, writes a paper-only Telegram
sandbox transcript via the `TelegramSandboxOutbox`, records
every `NoLookaheadViolation` and every
`BlindRunInvalidationReason`, and scores **only** after
`window.blind_end` (never inside the blind window).

PR100 outputs every required artefact under
`data/reports/blind_walk_forward/<run_id>/`:
`blind_run_manifest.json`, `trade_ledger.json`,
`equity_timeseries.json`, `discovery_quality_ledger.json`,
`failure_ledger.json`, `telegram_sandbox_transcript.md`,
`blind_walk_forward_report.json`,
`blind_walk_forward_report.md`, `no_lookahead_violations.json`.
Every payload is checked against the project-wide
`FORBIDDEN_OUTPUT_FIELDS` guard. Every payload re-pins the
safety boundary.

### Gate flags (Phase 11C.1D-D-G / PR100)

  - mode = `historical_blind_sim_live`
  - sandbox_only = `True`
  - simulated_only = `True`
  - no_live_order = `True`
  - live_trading = `False`
  - exchange_live_orders = `False`
  - binance_private_api_enabled = `False`
  - signed_endpoint_reachable = `False`
  - private_websocket_reachable = `False`
  - account_endpoint_reachable = `False`
  - order_endpoint_reachable = `False`
  - position_endpoint_reachable = `False`
  - leverage_endpoint_reachable = `False`
  - margin_endpoint_reachable = `False`
  - real_exchange_order_path = `False`
  - real_capital = `False`
  - telegram_outbound_enabled = `False`
  - telegram_live_command_authority = `False`
  - telegram_production_channel_enabled = `False`
  - ai_trade_authority = `False`
  - trade_authority = `False`
  - auto_tuning_inside_blind_window = `False`
  - auto_tuning_allowed = `False`
  - phase_12_forbidden = `True`

### What this PR does NOT authorise

  - Do NOT authorise live trading.
  - Do NOT authorise auto-tuning (no runtime config patch, no
    threshold patch, no symbol limit patch, no candidate pool
    patch, no regime weight patch, no strategy parameter patch).
  - Do NOT authorise real Telegram outbound.
  - Do NOT authorise Telegram production / live channel.
  - Do NOT authorise Telegram command authority.
  - Do NOT authorise the Binance private API.
  - Do NOT authorise small-cap live trading.
  - Do NOT authorise AI / DeepSeek output to enter the trade
    decision chain.
  - Do NOT authorise AI / DeepSeek output to become Truth Layer
    fact, training label, tail label, or strategy validation
    sample.
  - Do NOT authorise Phase 12.

### Allowed transitions

| From                           | To                                                  | Notes                                                                                                  |
| ------------------------------ | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Phase 11C.1D-D-G IN_REVIEW     | Phase 11C.1D-D-G ACCEPTED                           | Only via a separate docs-closeout PR after maintainer review. Acceptance authorises ONLY the next item. |
| Phase 11C.1D-D-G ACCEPTED      | Blind Walk-forward operator evidence run / checkpoint | Paper-only, sandbox-only. NEVER authorises live trading, auto-tuning, real Telegram outbound, real exchange orders, the Binance private API, or Phase 12. |
| any                            | Phase 12                                            | **FORBIDDEN.**                                                                                          |

### Tests

`tests/unit/test_blind_walk_forward_runner.py` ships **31
PASSING tests** covering all 30 brief-mandated scenarios plus
one bonus `INSUFFICIENT_EVIDENCE`-on-empty-run check on the
pure scoring helper. The full unit suite remains green
(`python -m pytest tests/unit -q` — 3584 PASSING).

### Files shipped

  - `app/sim/blind_walk_forward_manifest.py` (NEW)
  - `app/sim/blind_walk_forward_scoring.py` (NEW)
  - `app/sim/blind_walk_forward_runner.py` (NEW)
  - `app/sim/__init__.py` (EXTENDED — re-exports)
  - `scripts/run_blind_walk_forward.py` (NEW)
  - `tests/unit/test_blind_walk_forward_runner.py` (NEW)
  - `docs/PHASE_11C_1D_D_G_BLIND_WALK_FORWARD_RUNNER.md` (NEW)
  - `docs/PROJECT_STATUS.md` (UPDATED)
  - `docs/PHASE_GATE.md` (this section appended)
  - `docs/CHANGELOG.md` (UPDATED)

No file under `app/risk/`, `app/execution/`, `app/exchanges/`,
`app/telegram/`, `app/config/`, `app/safety/`, `app/ai/`,
`app/replay/`, `app/reflection/`, `app/paper_shadow/`,
`app/sandbox/`, `app/state_machine/`, `app/scanner/`,
`app/regime/`, `app/market_data/`, `app/market_data_public/`,
`app/universe/`, `app/liquidity/`, `app/manipulation/`,
`app/monitoring/`, `app/database/`, `app/exports/`,
`app/incidents/`, `app/learning/`, `app/llm/`,
`app/paper_run/`, `app/reconciliation/`, `app/confirmation/`,
`app/capital/`, `app/core/`, `app/main.py` is touched. The
existing PR94..PR99 sources are reused **verbatim** and are
NOT modified by this PR.

### Inheritance

Phase 11C.1D-D-G inherits, verbatim, every Phase 1, Phase
11C, Phase 11C.1A, Phase 11C.1B, Phase 11C.1C-A through
Phase 11C.1C-C-B-B-B-E-D, Phase AI-1 through Phase
AI-CHECKPOINT, Phase 11C / Offline Rule Sandbox Replay,
Phase 11C.1D-B *Paper Shadow Strategy Validation*, Phase
11C.1D-C *Risk / Execution / Capital Safety Matrix*, Phase
11C.1D-D *Strict Blind Walk-forward Sim-Live Constitution*,
Phase 11C.1D-D-A *SimulationClock + Time-Wall Guard*, Phase
11C.1D-D-B *Historical Market Store v0*, Phase 11C.1D-D-C
*ReplayFeedProvider v0*, Phase 11C.1D-D-D *MockExchange +
Pessimistic Fill Model v0*, Phase 11C.1D-D-E *Simulated
Capital Flow + Trade Ledger v0*, and Phase 11C.1D-D-F
*Telegram Sandbox Outbox v0* forbidden item.

The Risk Engine remains the single trade-decision gate.
Phase 12 remains **FORBIDDEN**.


## Open phase: Phase 11C.1D-D-H / Historical Data Ingestion / Backfill v0 (PR101, IN_REVIEW)

> **Title:** Historical Data Ingestion / Backfill v0
> **Status:** IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).
> **Type:** implementation PR (paper / report / evidence-only
> infrastructure).
> **Phase 12:** **FORBIDDEN** (no change).

> **Sub-task PR101-A — Binance Public Kline File Adapter Fix
> (IN_REVIEW).** Bugfix on top of PR101: makes the ingestion
> scanner / parser recognise **real** Binance public futures kline
> daily CSV dumps when `source_type = BINANCE_PUBLIC_KLINE_FILE`.
> Supported layout
> `klines/<SYMBOL>/<INTERVAL>/<SYMBOL>-<INTERVAL>-YYYY-MM-DD.csv`
> (and the `binance_um/` dump prefix) with the 12-column header
> `open_time,open,high,low,close,volume,close_time,quote_volume,
> count,taker_buy_volume,taker_buy_quote_volume,ignore`; the header
> row is skipped (never parsed as data), `open_time` / `close_time`
> millisecond epochs become timezone-aware UTC, `event_time =
> close_time`, `available_at = close_time + lag` (never
> `ingested_at`), and malformed rows are rejected with warnings
> (never fabricated). Scope: `app/sim/historical_data_ingestion.py`
> + `tests/unit/test_historical_data_ingestion.py` + these status
> docs only. **No** `app/risk/`, `app/execution/`, `app/exchanges/`,
> `app/telegram/`, `app/config/`, Blind Runner, `MockExchange`, or
> Capital Flow change. No Binance private API, no live orders, no
> real Telegram, no auto-tuning, no 30D / 60D / 90D / 2Y runner.
> `python -m pytest tests/unit/test_historical_data_ingestion.py -q`
> → 44 passed; full `tests/unit` → 3628 passed. Still
> `historical_blind_sim_live` / paper-only. **Phase 12 remains
> FORBIDDEN.**

PR101 ships the **eighth** anti-future-lookahead infrastructure
block of the strict blind walk-forward stack defined by Phase
11C.1D-D (PR93). It turns **local files** into the PR95 record
types (`HistoricalKlineRecord`, `HistoricalMarketRecord`,
`SymbolStatusRecord`) and produces the data / universe manifests +
coverage / gap audit that later strict forward-only blind
walk-forward runs (the PR100 runner) will consume. It feeds the
PR100 `BlindRunManifest` `data_manifest_hash` /
`universe_manifest_hash`.

PR101 reads **local files only**. It does NOT download data, does
NOT open a network socket, does NOT call the Binance private API /
Telegram / DeepSeek / any LLM, does NOT place a real order, and does
NOT fabricate real market data. Missing input yields
`INSUFFICIENT_EVIDENCE`; a deterministic synthetic dataset is
produced ONLY when `fixture_mode` is explicitly enabled and is
clearly marked synthetic. A coverage report is NEVER presented as a
strategy-effectiveness conclusion. It does NOT implement the
30D / 60D / 90D / 2Y runner.

### Public surface (Phase 11C.1D-D-H / PR101)

  - `HistoricalDataSourceType` — closed taxonomy of **public /
    file** source types.
  - `DataIngestionStatus` — `EVIDENCE_GENERATED` /
    `PARTIAL_EVIDENCE` / `INSUFFICIENT_EVIDENCE` /
    `FAILED_SCHEMA_VALIDATION` / `INVALIDATED_TIME_FIELDS`.
  - `HistoricalDataIngestionConfig`,
    `HistoricalDataIngestionResult`.
  - `HistoricalDataManifest` (deterministic `data_manifest_hash`),
    `UniverseManifest` (as-of universe, `survivorship_bias_guard`).
  - Row parsers + `HistoricalDataIngestion` engine.

### Gate flags (Phase 11C.1D-D-H / PR101)

  - mode = `historical_blind_sim_live`
  - sandbox_only = `True`
  - simulated_only = `True`
  - no_live_order = `True`
  - live_trading = `False`
  - exchange_live_orders = `False`
  - binance_private_api_enabled = `False`
  - signed_endpoint_reachable = `False`
  - private_websocket_reachable = `False`
  - account_endpoint_reachable = `False`
  - order_endpoint_reachable = `False`
  - position_endpoint_reachable = `False`
  - leverage_endpoint_reachable = `False`
  - margin_endpoint_reachable = `False`
  - real_exchange_order_path = `False`
  - real_capital = `False`
  - telegram_outbound_enabled = `False`
  - telegram_live_command_authority = `False`
  - ai_trade_authority = `False`
  - trade_authority = `False`
  - auto_tuning_allowed = `False`
  - phase_12_forbidden = `True`

### What this PR does NOT authorise

  - Do NOT authorise live trading.
  - Do NOT authorise auto-tuning (no runtime config patch, no
    threshold patch, no symbol limit patch, no candidate pool
    patch, no regime weight patch, no strategy parameter patch).
  - Do NOT authorise real Telegram outbound or Telegram command
    authority.
  - Do NOT authorise the Binance private API, a signed endpoint, a
    private websocket, or a listenKey.
  - Do NOT authorise a real exchange order or real capital.
  - Do NOT authorise DeepSeek / LLM calls or any network call path.
  - Do NOT present a coverage report as a strategy-effectiveness
    conclusion.
  - Do NOT authorise the 30D / 60D / 90D / 2Y runner.
  - Do NOT authorise Phase 12.

### Allowed transitions

| From                           | To                                                                       | Notes                                                                                                  |
| ------------------------------ | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| Phase 11C.1D-D-H IN_REVIEW     | Phase 11C.1D-D-H ACCEPTED                                                | Only via a separate docs-closeout PR after maintainer review. Acceptance authorises ONLY the next item. |
| Phase 11C.1D-D-H ACCEPTED      | Historical Data Coverage Checkpoint / short-window no-lookahead trial preparation | Paper-only, sandbox-only. NEVER authorises live trading, auto-tuning, real Telegram outbound, real exchange orders, the Binance private API, the 30D / 60D / 90D / 2Y runner, or Phase 12. |
| any                            | Phase 12                                                                 | **FORBIDDEN.**                                                                                          |

### Tests

`tests/unit/test_historical_data_ingestion.py` ships **30 PASSING
tests** covering all 25 brief-mandated scenarios plus 5 defensive
extras. The full unit suite remains green
(`python -m pytest tests/unit -q` — 3613 PASSING).

### Files shipped

  - `app/sim/historical_data_manifest.py` (NEW)
  - `app/sim/historical_data_ingestion.py` (NEW)
  - `app/sim/__init__.py` (EXTENDED — re-exports)
  - `scripts/run_historical_data_ingestion.py` (NEW)
  - `tests/unit/test_historical_data_ingestion.py` (NEW)
  - `docs/PHASE_11C_1D_D_H_HISTORICAL_DATA_INGESTION_BACKFILL.md` (NEW)
  - `docs/PROJECT_STATUS.md` (UPDATED)
  - `docs/PHASE_GATE.md` (this section appended)
  - `docs/CHANGELOG.md` (UPDATED)

No file under `app/risk/`, `app/execution/`, `app/exchanges/`,
`app/telegram/`, `app/config/` is touched, and no existing
PR94..PR100 `app/sim/` source is modified except
`app/sim/__init__.py` (export wiring only).

### Inheritance

Phase 11C.1D-D-H inherits, verbatim, every prior forbidden item
through Phase 11C.1D-D-G *Blind Walk-forward Runner v0*. The Risk
Engine remains the single trade-decision gate. Phase 12 remains
**FORBIDDEN**.
