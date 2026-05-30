# AMA-RT DeepSeek Live Intelligence v0 (PR115)

> **PR115 — DeepSeek Live Intelligence v0: Live-safe Operator Briefing +
> Evidence Compression + Risk Explanation.**
> **Status: IN_REVIEW.**
> **Type: AI market-intelligence only. The AI has NO trade authority and
> can NEVER place, size, or direct a trade.**

PR115 connects DeepSeek to the live operator workflow **only** as market
intelligence: it summarises live-approved evidence, compresses it into a
readable operator briefing, explains live risk rejections, summarises
funding / commission / PnL, and can push that briefing to Telegram. It
adds no trading capability of any kind.

> **This is not the 10U live launch.** Real live trading does not begin
> until the launch PR (**PR116**) explicitly clears the stage docs. PR115
> keeps `live_trading=false`, `exchange_live_orders=false`,
> `trade_authority=false`, `ai_trade_authority=false`,
> `runtime_mode=LIVE_SHADOW`, and `phase_12_forbidden=true` by default.

---

## 1. What PR115 is (and is not)

1. PR115 connects DeepSeek to the **live operator briefing only**.
2. The AI has **no trade authority** (`ai_trade_authority=false`, pinned
   on every bundle, briefing, card, and audit payload).
3. The AI **cannot** output direction, position size, leverage, stop,
   take-profit, target, order type, entry/exit price, execute / trade
   decision, or any runtime / strategy / risk-limit config patch.
4. The AI **cannot** use blind / replay / sim / paper-shadow / backtest /
   offline-AI / telegram-sandbox evidence as a live input. Evidence is
   `source_scope=LIVE_ONLY`.
5. The AI **cannot** call the execution gateway. The PR115 modules do not
   import or invoke `LiveExecutionGateway` / `BinanceExecutionAdapter`.
6. The AI briefing **can** be sent to Telegram, but it is **informational
   only** — every card carries `no_order_instruction=true` and
   `recommends_action=false`.
7. Funding / commission / PnL summaries are **explanatory only**; deposits
   and withdrawals stay separate from strategy PnL.
8. The 10U live launch still requires **PR116**.

---

## 2. Data flow

```
live-approved evidence  ->  LiveAIEvidenceBundle (source_scope=LIVE_ONLY)
                              |  (non-live source -> REJECTED + audit)
                              v
                        build_prompt_messages  (market-intelligence-only)
                              |
                              v
                        DeepSeek chat-completion (key in Authorization only)
                              |
                              v
                        sanitize_ai_output  (strip trade-authority fields)
                              |
                              v
                        LiveAIBriefing (ai_trade_authority=false)
                              |
                              v
              CLI  /  Telegram AI card  (informational, redacted)
```

The DeepSeek API key is held as a `SecretValue`, never logged, and only
ever travels in the `Authorization` header handed to the transport.

---

## 3. Live AI evidence bundle

`app/live/ai_live_evidence.py` — `build_live_ai_evidence_bundle(...)`
compresses a `LiveAIEvidenceBundle`. Fields: `evidence_bundle_id`,
`created_at`, `source_scope=LIVE_ONLY`, `runtime_mode`,
`capital_profile_id`, `account_status`, `pnl_summary`, `open_positions`,
`risk_summary`, `recent_order_summary`, `funding_summary`,
`telegram_state`, `api_health_summary`, `market_snapshot_summary`,
`evidence_refs`, `forbidden_sources_detected`, `ai_trade_authority=false`.

**Live-approved evidence only** — Binance public market data, Binance
private read (account / positions / income), `LiveCapitalState`,
`LivePnlSummary`, `LiveRiskDecision`, `LiveExecutionGateway` /
`LiveOrderLedger` summaries, Telegram operator state, capital profile
state, funding attribution result, system health check.

**Forbidden sources** — `SIM`, `BLIND`, `REPLAY`, `PAPER_SHADOW`,
`BACKTEST`, `OFFLINE_AI`, `TELEGRAM_SANDBOX` (plus the simulation /
blind / replay / paper-shadow module class names). An unknown source
**fails safe to forbidden**. Any forbidden source rejects the whole
bundle and emits `LIVE_AI_EVIDENCE_REJECTED_FOR_NONLIVE_SOURCE`.

Evidence content is redacted on construction so no secret can ever reach
the AI prompt.

---

## 4. Prompt contract + output guard

`app/live/ai_live_briefing.py` — the system prompt declares the AI is
`MARKET_INTELLIGENCE_ONLY` and lists everything it must not do (decide
trades / direction / size / leverage / stop / take-profit / target /
order / execution / config patch). The requested output schema is
restricted to the allowed briefing fields; no trade-authority field is
ever requested. If the evidence is insufficient the AI is told to say so.

`app/live/ai_output_guard.py` — `sanitize_ai_output(payload)` strips every
forbidden trade-authority field at any nesting depth (case-insensitive).
Forbidden output fields include: `should_buy`, `should_sell`,
`should_long`, `should_short`, `direction`, `position_size`, `size`,
`leverage`, `stop_price`, `take_profit`, `target_price`, `order_type`,
`entry_price`, `exit_price`, `execute`, `trade_decision`,
`runtime_config_patch`, `strategy_patch`, `risk_limit_patch` (plus the
PR111 trade-authority superset). When a forbidden field is present the
briefing status becomes `REJECTED_FOR_TRADE_AUTHORITY`, the events
`AI_FORBIDDEN_FIELD_STRIPPED` + `DEEPSEEK_OUTPUT_REJECTED_FOR_TRADE_AUTHORITY`
are emitted, and the briefing is never sent as an actionable Telegram
card.

`LiveAIBriefing` schema: `briefing_id`, `status`, `market_summary`,
`account_summary`, `risk_summary`, `pnl_summary`, `funding_summary`,
`position_notes`, `rejection_summary`, `anomaly_notes`, `operator_notes`,
`evidence_quality`, `missing_evidence`, `forbidden_fields_detected`,
`ai_trade_authority=false`, `source_scope=LIVE_ONLY`.

Failure handling never crashes: DeepSeek disabled → `DISABLED`; missing /
placeholder key → `MISSING_SECRET`; HTTP / transport error → `ERROR`
(safe text); insufficient live evidence → `INSUFFICIENT_EVIDENCE`.

---

## 5. Telegram AI commands

`app/live/ai_telegram.py` — `AIBriefingTelegram` adds read-only AI
commands to the operator desk:

| Command | Returns |
| --- | --- |
| `/ai_status` | DeepSeek enabled? key present (masked)? last briefing status? `MARKET_INTELLIGENCE_ONLY`, `ai_trade_authority=false`, `source_scope=LIVE_ONLY`. |
| `/brief` | The latest live-safe briefing. Never creates an order intent. |
| `/explain_risk` | Current risk state + recent rejects. Never recommends an order action. |
| `/explain_position <SYMBOL>` | The open position using live data. Never recommends hold / add / close / open. |
| `/summarize_pnl` | Gross realized PnL, commission, funding, net strategy PnL, deposits/withdrawals (kept separate). Explanatory only. |
| `/summarize_rejections` | Recent risk / execution rejects. Never suggests bypassing any gate (`no_bypass_suggested=true`). |

Every AI card displays the header `[AI Briefing / MARKET_INTELLIGENCE_ONLY]`,
`ai_trade_authority=false`, `source_scope=LIVE_ONLY`, `evidence_quality`,
risk notes, missing evidence, and carries `no_order_instruction=true` /
`recommends_action=false`. A non-LIVE source, a live / state-changing
command, or a trade-authority leak is blocked (`AI_TELEGRAM_BRIEFING_BLOCKED`).

---

## 6. CLI

`scripts/live_ai_briefing.py`:

```
python scripts/live_ai_briefing.py --status-json
python scripts/live_ai_briefing.py --brief --json
python scripts/live_ai_briefing.py --brief --dry-run
python scripts/live_ai_briefing.py --validate-output sample.json
```

The CLI never submits orders, never switches mode, never changes the
profile, never calls the execution gateway, and never uses blind / replay
/ sim evidence. Secrets are masked / redacted. A missing DeepSeek key
returns `MISSING_SECRET` / `DISABLED` rather than crashing. `--dry-run`
builds the briefing locally with no network call.

---

## 7. Audit events

PR115 adds: `LIVE_AI_BRIEFING_REQUESTED`, `LIVE_AI_BRIEFING_GENERATED`,
`LIVE_AI_BRIEFING_FAILED`, `LIVE_AI_EVIDENCE_REJECTED_FOR_NONLIVE_SOURCE`,
`AI_FORBIDDEN_FIELD_STRIPPED`, `AI_TELEGRAM_BRIEFING_SENT`,
`AI_TELEGRAM_BRIEFING_BLOCKED` (and reuses the PR111
`DEEPSEEK_OUTPUT_REJECTED_FOR_TRADE_AUTHORITY`). No payload ever carries
an API key or raw secret.

---

## 8. Safety boundary

PR115 keeps the Phase 1 safety flags locked. By default and at all times:

| Flag | Value |
| --- | --- |
| `live_trading` | `false` |
| `exchange_live_orders` | `false` |
| `trade_authority` | `false` |
| `ai_trade_authority` | `false` |
| `runtime_mode` | `LIVE_SHADOW` |
| `phase_12_forbidden` | `true` |

The AI cannot decide direction / size / leverage / stop / take-profit /
target, cannot open / close / add / hold, cannot call the execution
gateway, cannot change the runtime mode / capital profile / leverage /
stop / take-profit / risk limits, cannot auto-switch to `LIVE_LIMITED`,
cannot use blind / replay / sim evidence as live input, cannot trigger a
Telegram live order command, and cannot output a runtime config patch.
The 10U live launch remains a **PR116** concern.
