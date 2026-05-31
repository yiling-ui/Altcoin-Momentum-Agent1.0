# AMA-RT Final Full-System Single-Altcoin Live Sandbox Audit (PR117)

> **Status:** `PR117 FULL_SYSTEM_SANDBOX_AUDIT_IN_REVIEW`
> **Default posture:** `live_trading=false`, `exchange_live_orders=false`,
> `trade_authority=false`, `ai_trade_authority=false`,
> **no real order ever sent**, **fake transports only**.

PR117 is the **final, full-blooded sandbox audit** of the AMA-RT V1.4 live
system. It is the last checkpoint before a funded 10U `LIVE_LIMITED`
launch is considered for real-key validation.

---

## 1. Purpose of the final full-system audit

PR110–PR116 each shipped one layer of the live stack (path isolation,
capital profiles, live risk, the execution gateway, the Telegram operator
console, DeepSeek live intelligence, and the 10U launch pack). PR117
proves the layers **work together as one chain** by running the *real*
PR110–PR116 code end to end:

```
fake live market
  -> strategy / opportunity (source=LIVE)
  -> live risk decision
  -> capital profile
  -> right-tail leverage gate (deterministic)
  -> execution gateway (15-point gate)
  -> fake Binance order  (REAL adapter + fake transport)
  -> fills / fees / funding
  -> live order ledger + funding-aware PnL
  -> Telegram operator cards
  -> DeepSeek briefing (explain-only)
  -> kill switch / rollback
  -> deposit / withdrawal / profile mismatch / capital scaling
```

The audit hunts for bugs that only appear when PR110–PR116 are串联
(chained), checks that the strategy reaches the live path, and confirms
the live path stays isolated from blind / replay / sim.

## 2. Why it uses one altcoin sandbox

A single deterministic fake altcoin — `RAVEUSDT_SANDBOX` — lets the audit
drive the **entire** chain through legible, repeatable market shapes (a
RAVE-like right-tail breakout, a fake breakout reversal, funding holds,
bad liquidity, a mid-trade exchange failure) without the noise of a full
universe scan. One coin, the whole pipeline, every time.

## 3. Why it is not blind testing

- It is **not** a unit test, **not** a historical blind test, **not** a
  replay/backtest, and it does **not** re-open the blind route.
- Every intent carries `source=LIVE`. The strategy harness emits a
  deterministic *live-equivalent* plan with **no future labels**
  (`completed_tail_label` / MFE / MAE are absent). There is no look-ahead.
- The fake market is a **live-equivalent** source, deliberately **not** in
  `FORBIDDEN_LIVE_SOURCE_CLASSES`; the blind / replay / sim sources remain
  forbidden (see §4).

## 4. Why blind / replay / sim remain isolated

The audit re-proves the PR110/PR114 isolation boundary holds under the
full chain:

- `OrderSource.SIM | BLIND | REPLAY | PAPER_SHADOW` are blocked at the
  order isolation guard (`LIVE_PATH_BLOCKED`) and at the live-source guard
  (`LIVE_SOURCE_REJECTED`).
- `HistoricalMarketStore`, `MockExchange`, `ReplayFeedProvider`,
  `SimulatedCapitalFlow`, `BlindWalkForwardRunner`,
  `PaperShadowStrategyBridge` can never be a live market/capital source
  (`LiveRuntime.assert_live_market_source` raises).
- A non-LIVE source can never enter the live AI evidence bundle, change
  the runtime mode, or change the capital profile.

## 5. Scenarios covered

| Scenario | What it proves |
|---|---|
| `strategy_lifecycle` | quiet→no entry; weak pump→observe; right-tail→shadow plan; bad liquidity→rejected; reversal→stop/exit; no-stop/no-exit→rejected; leverage from the deterministic gate only; AI/blind cannot influence the plan |
| `execution_lifecycle` | LIVE_SHADOW plan-only; gated LIVE_LIMITED fake fill; partial fill; reject; post-submit timeout (no duplicate, pending reconciliation); exit gross/fee/funding/net |
| `live_risk` | right-tail approved; `real_order_allowed` flips only when fully armed; shadow/source/stop/exit/notional/capital-cap rejects; reads the active profile dynamically |
| `capital_ladder` | every funded profile L1_1U…L8_10M; 10U cap enforced; mismatch never auto-upgrades; operator switch changes caps with no code change; 1M/10M stricter liquidity/slippage |
| `funding_fee_pnl` | deposit≠profit; withdrawal≠loss; commission/funding-fee/funding-income folded into net PnL; harvest/rebase/manual never pollute the curve; performance equity excludes external flows |
| `telegram_operator` | unauthorized rejected; empty allow-list fails closed; `/mode live_limited` only confirms; arming never enables real orders; readable entry/exit/PnL cards; AI briefing is market-intelligence only |
| `ai_guard` | forbidden trade-authority fields stripped+rejected (incl. nested); AI cannot call execution; AI source cannot mutate live state; AI cannot decide leverage; blind AI evidence rejected |
| `blind_isolation` | every non-LIVE source blocked at every live surface |
| `kill_switch` | ready/active semantics; `/kill_all`→`/confirm_kill`; active kill blocks entries; flag-disable blocks; rollback to LIVE_SHADOW; corrupt state fails safe; never falsely claims positions closed |

## 6. How to run the audit

```bash
python scripts/live_full_system_sandbox_audit.py --json
python scripts/live_full_system_sandbox_audit.py --symbol RAVEUSDT_SANDBOX --scenario all --json
python scripts/live_full_system_sandbox_audit.py --scenario strategy_lifecycle --json
python scripts/live_full_system_sandbox_audit.py --scenario execution_lifecycle --json
python scripts/live_full_system_sandbox_audit.py --scenario live_risk --json
python scripts/live_full_system_sandbox_audit.py --scenario capital_ladder --json
python scripts/live_full_system_sandbox_audit.py --scenario funding_fee_pnl --json
python scripts/live_full_system_sandbox_audit.py --scenario telegram_operator --json
python scripts/live_full_system_sandbox_audit.py --scenario ai_guard --json
python scripts/live_full_system_sandbox_audit.py --scenario kill_switch --json
python scripts/live_full_system_sandbox_audit.py --scenario blind_isolation --json
```

The JSON includes: `overall_status`, `scenario_results`, `blockers`,
`warnings`, every `*_chain_ok` flag, `no_real_order_sent`,
`fake_transports_used=true`, `live_trading=false`,
`exchange_live_orders=false`, `trade_authority=false`,
`ai_trade_authority=false`, and `ready_for_real_key_validation`.

## 7. What PASS / WARN / FAIL means

- **PASS** — every blocker check in every requested scenario passed. The
  sandbox proved the full chain behaves correctly.
- **WARN** — no blocker failed, but at least one non-critical (warning)
  check did. Review the warnings; not a hard stop.
- **FAIL** — at least one blocker check failed. The chain has a defect
  that must be fixed before a funded launch. `ready_for_real_key_validation`
  is forced `false`.

A single scenario can be run on its own; chain flags for scenarios that
did not run are treated as not-evaluated (not failed).

## 8. What blocks a real 10U live launch

A real 10U `LIVE_LIMITED` order still requires **all** of the PR113
15-point gate (`runtime_mode=LIVE_LIMITED`, `live_limited_confirmed`,
`exchange_live_orders`, `trade_authority`, private trade enabled by
config, kill switch not active, `source=LIVE`, an approved risk decision
with `real_order_allowed=true`, exchangeInfo validation, profile caps,
stop+exit plan, account capital within cap). PR117 does **not** flip any
of those flags; it only proves the machinery is correct with fakes.

## 9. What still requires real-key validation

The sandbox uses **fake** Binance / Telegram / DeepSeek transports and a
**fake** account. Before funded operation, the operator must still run
`scripts/live_launch_check.py --require-real-keys` with real (non-
placeholder) keys to validate: real Binance public + private-read
connectivity, the real account snapshot, real exchangeInfo for the chosen
symbol, real Telegram outbound to the allow-listed chat, and (optionally)
the real DeepSeek key. PR117 sets `ready_for_real_key_validation=true`
only when the full sandbox chain passes — it is a *go to real-key
validation*, not a *go to live*.

## 10. How capital scales after 10U without a code change

The capital profile ladder (`L1_1U` … `L8_10M`) is a constraint model.
The `LiveRuntime` reads the **active** profile dynamically and exposes its
caps via `LiveProfileCaps`; the execution context sets
`allowed_profile_ids=(active,)`. Growing from 10U → 50U → 1,000U → 10,000U
→ 100,000U → 1,000,000U → 10,000,000U is an **operator** profile switch
(`/profile set <ID>` or `LiveRuntime.set_capital_profile`) — **never**
automatic, and **never** a code change. Escalation is gated on explicit
operator acknowledgement; a profile/equity mismatch raises
`CAPITAL_PROFILE_MISMATCH` and caps usable capital at the active profile
until the operator re-selects. Only a bug, a strategy redesign, a new
exchange, or a new execution style requires a new PR.

---

### Components added by PR117

- `app/live/full_system_audit_models.py` — audit verdict + scenario contracts.
- `app/live/fake_live_market.py` — deterministic 8-shape fake live market.
- `app/live/fake_live_exchange.py` — fake Binance transport/adapter, fee/funding engines, fake account.
- `app/live/fake_live_strategy.py` — minimal `LiveStrategySandboxAdapter` (source=LIVE, no future labels).
- `app/live/fake_live_telegram.py` — fake Telegram transport + sandbox data provider.
- `app/live/fake_live_deepseek.py` — fake DeepSeek transport (clean + forbidden payloads).
- `app/live/full_system_sandbox.py` — the runner that wires the real chain to the fakes.
- `scripts/live_full_system_sandbox_audit.py` — the CLI.
- `tests/unit/test_pr117_full_system_sandbox_audit.py` — the 50-point test suite.
