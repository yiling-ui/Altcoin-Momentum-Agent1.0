# Phase 11C — Offline Rule Sandbox Replay v0

> **Status:** IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).
>
> Paper / report / sandbox-only. **NOT** live trading. **NOT**
> auto-tuning. **NOT** runtime-config writeback. **NOT** the
> AI Layer's involvement in the Risk Engine / Execution FSM /
> Strategy Engine / Runtime Config. **NOT** Phase 12. **Phase
> 12 remains FORBIDDEN.** The Risk Engine remains the single
> trade-decision gate.

## Purpose

Phase 11C ships an **offline rule sandbox replay layer** that
lets an operator safely answer hypothetical questions about how
a rule change would have moved **discovery quality** over a
frozen historical reference window:

  - If we lowered the `early_tail_score_threshold`, would the
    severe-miss rate drop?
  - If we tightened the candidate-score cutoff, would the
    late-chase rate rise?
  - If we relaxed a reject rule, would the false-negative
    reject rate fall?
  - If a rule change brings more fake breakouts, is it worth
    advancing?

The sandbox NEVER trades. It NEVER calls Risk, Execution, the
Exchange Gateway, Telegram outbound, an LLM, or DeepSeek. It
NEVER imports `app.risk`, `app.execution`, `app.exchanges`,
`app.telegram`, `app.config`, or any HTTP / WebSocket / network
library. It NEVER writes back runtime configuration. It NEVER
auto-tunes. It NEVER opens Phase 12.

## Relation to roadmap gap #2

The AMA-RT roadmap calls out the absence of a safe rule-change
exploration loop as the second gap blocking the next paper-only
step. The Risk Engine, the Execution FSM, the Exchange Gateway,
and the Strategy Engine all hold the trade-authority line; the
Block A / Block B / Block C integrated checkpoints prove the
data line; the AI-1 → AI-6 chain plus the AI Integrated
Checkpoint prove the read-only intelligence line. What was
missing was a **paper-only counterfactual layer** the operator
could use to ask "what if?" without touching any of those
gates.

This phase fills that gap with the smallest possible
implementation — one Python module, one runner, one test
module, and one design document. It does **not** automate the
answer. It does **not** decide which rules to relax or
tighten. It does **not** propose a runtime-config patch.

## Allowed inputs

The runner reads only local files. Every input is optional;
when an input is missing, the engine falls back to a
conservative default and surfaces a `data_gap_warning` instead
of fabricating evidence.

| CLI flag                            | Description                                                    |
| ----------------------------------- | -------------------------------------------------------------- |
| `--block-b-report`                  | Block B integrated evidence checkpoint JSON (descriptive only) |
| `--block-c-report`                  | Block C integrated checkpoint JSON (descriptive only)          |
| `--ai-checkpoint`                   | AI integrated checkpoint JSON (descriptive only)               |
| `--baseline-discovery-quality`      | Baseline discovery-quality counters / rates                    |
| `--post-discovery-outcomes`         | Post-discovery outcome roll-up                                 |
| `--reject-attributions`             | Reject-to-outcome attribution roll-up                          |
| `--severe-miss-triage`              | Severe missed tail triage roll-up                              |
| `--replay-summary`                  | Replay summary                                                 |
| `--reflection-summary`              | Reflection summary                                             |
| `--scenario-file`                   | Operator-supplied scenario JSON                                |
| `--output-dir`                      | Output directory (writes JSON + Markdown)                      |
| `--reference-window`                | Audit-window label (descriptive only; default `60d`)           |

If `--scenario-file` is missing or unparseable, the runner
generates a deterministic example scenario marked
`source=example_fixture`. That example **MUST NOT** be
treated as an operator-approved scenario; the `source` field
is the contract.

## Allowed outputs

The runner writes only:

  - `<output-dir>/offline_rule_sandbox_report.json`
  - `<output-dir>/offline_rule_sandbox_report.md`

Both files re-pin the project-wide safety invariants at the
serialisation boundary:

```json
{
  "phase_12_forbidden": true,
  "auto_tuning_allowed": false,
  "writes_runtime_config": false,
  "trade_authority": false,
  "sandbox_only": true,
  "ai_output_can_be_truth": false,
  "ai_output_can_be_training_label": false,
  "ai_output_can_be_tail_label": false,
  "ai_output_can_be_strategy_sample": false,
  "safety_flags": {
    "mode": "paper",
    "live_trading": false,
    "exchange_live_orders": false,
    "right_tail": false,
    "llm": false,
    "llm_outbound_enabled": false,
    "sandbox_only": true,
    "allow_trade_decision": false,
    "allow_runtime_config_change": false,
    "auto_tuning_allowed": false,
    "telegram_outbound_enabled": false,
    "binance_private_api_enabled": false
  }
}
```

The recursive `_assert_no_forbidden_keys` guard refuses to
serialise any payload that carries one of the
`FORBIDDEN_SANDBOX_PAYLOAD_KEYS` at any nesting depth. This
includes every direction / sizing / leverage / stop / target /
risk-budget / order / runtime-config-patch / "signal-to-trade"
/ "should buy/short" / "apply" / "deploy" / "enable_live"
alias plus the defensive aliases `trading_approved`,
`live_ready`, `live_trading_allowed`, `phase_12_allowed`.

## Scenario schema

```json
{
  "scenario_id": "operator_scn_loosen_early_tail",
  "name": "loosen early_tail_score_threshold by 10%",
  "reference_window": "60d",
  "baseline_label": "phase_11c_baseline_60d",
  "hypothetical_rule_changes": [
    {
      "rule_name": "early_tail_score_threshold",
      "baseline_value": 0.5,
      "sandbox_value": 0.45,
      "change_type": "loosen",
      "rationale": "test severe-miss recall direction",
      "evidence_refs": [
        "report:discovery_quality_scorecard",
        "report:severe_missed_tail_triage"
      ]
    }
  ],
  "cohort_filters": [],
  "source_reports": [
    "discovery_quality_scorecard",
    "severe_missed_tail_triage",
    "post_discovery_outcome_metrics",
    "reject_to_outcome_attribution"
  ],
  "evidence_refs": [
    "report:block_c_integrated_checkpoint",
    "report:ai_integrated_checkpoint"
  ],
  "source": "operator_supplied"
}
```

`change_type` is restricted to a closed vocabulary of
`loosen` / `tighten` / `no_change`. The fields are deliberately
named `baseline_value` / `sandbox_value` / `rationale` /
`evidence_refs` and **NOT** `runtime_config_patch` /
`threshold_patch`; this is a hypothesis, not a patch the
runtime will apply. Every `HypotheticalRuleChange` is hard-
pinned with `is_runtime_patch=False`,
`writes_runtime_config=False`, `auto_tuning_allowed=False`.

A scenario file may be:

  - one scenario object,
  - a JSON list of scenario objects,
  - or a report-shaped object with a top-level `scenarios`
    list.

## Result schema

Each scenario produces one `OfflineRuleSandboxResult`:

```json
{
  "schema_version": "phase_11c.offline_rule_sandbox_result.v1",
  "scenario_id": "operator_scn_loosen_early_tail",
  "status": "EVALUATED",
  "baseline_metrics": { "...": "..." },
  "sandbox_metrics": { "...": "..." },
  "delta_metrics": {
    "coverage_rate_delta": 0.02,
    "usable_discovery_rate_delta": 0.008,
    "severe_miss_rate_delta": -0.01,
    "false_negative_reject_rate_delta": -0.012,
    "late_chase_rate_delta": 0.014,
    "fake_breakout_rate_delta": 0.012,
    "data_gap_rate_delta": 0.006,
    "median_mfe_delta": -0.004,
    "median_mae_delta": 0.008
  },
  "likely_benefits": ["coverage_rate_improves_by_0.02", "..."],
  "likely_risks": ["late_chase_rate_worsens_by_0.014", "..."],
  "overfit_warnings": [],
  "data_gap_warnings": [],
  "recommendation_level": "PROMISING_FOR_PAPER_SHADOW",
  "notes": []
}
```

Per-scenario status is one of:

  - `EVALUATED` — the engine projected at least one rule
    change against a non-empty baseline.
  - `INCONCLUSIVE` — no rule change could be projected
    (e.g. every change was `no_change`).
  - `INSUFFICIENT_EVIDENCE` — neither baseline metrics nor
    rule changes were usable.

## Recommendation levels (CLOSED)

The recommendation_level is restricted to a closed vocabulary:

| Level                          | Meaning                                                                 |
| ------------------------------ | ----------------------------------------------------------------------- |
| `REVIEW_ONLY`                  | Engine projected the change. Operator review required.                  |
| `INCONCLUSIVE`                 | Engine could not project the change (no-op / no baseline).              |
| `PROMISING_FOR_PAPER_SHADOW`   | Coverage / usable-discovery improved, no major risk side-effect.        |
| `RISKY`                        | Overfit warning OR no evidence ref; review with caution.                |
| `REJECTED_BY_EVIDENCE`         | Severe-miss / fake-breakout / late-chase delta past the risky threshold.|

The vocabulary intentionally **does NOT** include `APPLY`,
`DEPLOY`, `ENABLE_LIVE`, `TRADE`, `BUY`, or `SELL`. Every
output payload re-asserts this via the
`recommendation_levels` list and the recursive forbidden-key
guard.

A `PROMISING_FOR_PAPER_SHADOW` recommendation only authorises
the **next allowed paper / read-only step** — Paper Shadow
Strategy Validation preparation. It does **NOT** authorise
runtime change. It does **NOT** authorise a real or paper
trade. It does **NOT** authorise auto-tuning. It does **NOT**
open Phase 12.

## Why this is **not** auto-tuning

Auto-tuning is the act of an automated layer choosing a
runtime parameter and applying it. The Offline Rule Sandbox
Replay engine:

  - never chooses a parameter — the operator supplies the
    `hypothetical_rule_changes` list,
  - never applies anything — every payload pins
    `auto_tuning_allowed=False`,
  - never reads back — the engine has no I/O surface besides
    JSON files the operator hands it,
  - never proposes a `runtime_config_patch` / `threshold_patch`
    / `symbol_limit_patch` / `candidate_pool_patch` /
    `regime_weight_patch` / `strategy_parameter_patch` —
    these names are in the
    `FORBIDDEN_SANDBOX_PAYLOAD_KEYS` set and the recursive
    guard refuses to emit any payload that carries them.

## Why this does **not** write runtime config

The engine has no writer surface for `app.config` or any
runtime settings store. It refuses to import `app.config`. The
runner refuses to import `app.config`. Every emitted payload
pins `writes_runtime_config=False`, and the
`HypotheticalRuleChange` dataclass additionally pins
`is_runtime_patch=False` so a downstream consumer cannot
misread it as a patch.

## Why this does **not** authorise live trading

  - The runner refuses to import `app.risk`, `app.execution`,
    `app.exchanges`, `app.telegram`, `app.config`.
  - The engine and module never import `openai`, `anthropic`,
    `deepseek`, `httpx`, `requests`, `aiohttp`, `urllib3`,
    `websocket`, `websockets`, `grpc`, `boto3`, or `socket`.
  - Every emitted payload pins `trade_authority=False`,
    `live_trading=False`, `exchange_live_orders=False`,
    `binance_private_api_enabled=False`,
    `right_tail=False`.
  - The recommendation_level vocabulary excludes `TRADE`,
    `BUY`, `SELL`, `ENABLE_LIVE`, `APPLY`, `DEPLOY`.
  - The Risk Engine remains the single trade-decision gate.

## Why this does **not** enter Phase 12

  - Every emitted payload pins `phase_12_forbidden=True`.
  - The next-allowed-phase rollup vocabulary is restricted to
    Paper Shadow Strategy Validation preparation, operator
    review, or "needs more evidence" — none of these names is
    Phase 12.
  - The recursive guard refuses to emit any payload that
    carries a `phase_12_allowed` alias.

## Successor allowed by this phase

A successful sandbox scenario (`recommendation_level =
PROMISING_FOR_PAPER_SHADOW`) only authorises the **Paper
Shadow Strategy Validation preparation** work. It does **NOT**
authorise:

  - live trading,
  - paper trading the candidate rule change directly,
  - DeepSeek hot-path execution,
  - Telegram live outbound,
  - any runtime-config writeback,
  - any auto-tuning,
  - Phase 12.

When `recommendation_level` is `INCONCLUSIVE`,
`REVIEW_ONLY`, `RISKY`, or `REJECTED_BY_EVIDENCE`, the
operator must address the surfaced gaps / risks before the
scenario is re-runnable.

## Files shipped by this phase

  - `app/sandbox/__init__.py`
  - `app/sandbox/offline_rule_sandbox.py`
  - `scripts/run_offline_rule_sandbox_replay.py`
  - `tests/unit/test_offline_rule_sandbox_replay.py`
  - `docs/PHASE_11C_OFFLINE_RULE_SANDBOX_REPLAY.md`

This phase **does not** touch `app/risk/**`, `app/execution/**`,
`app/exchanges/**`, `app/telegram/**`, `app/config/**`,
`app/core/events.py`, `app/database/**`, `app/llm/**`, or
`app/ai/**`. Three new event names
(`OFFLINE_RULE_SANDBOX_REPLAY_RUN`,
`OFFLINE_RULE_SANDBOX_SCENARIO_EVALUATED`,
`OFFLINE_RULE_SANDBOX_REPORT_GENERATED`) are emitted as
descriptive string labels inside the report payload only;
they are **not** wired into `app.core.events.EventType` and
they never cross the runtime hot path.

## Tests

```bash
python -m pytest tests/unit/test_offline_rule_sandbox_replay.py -q
```

The brief's fifteen numbered checks are covered by individual
tests in `tests/unit/test_offline_rule_sandbox_replay.py`,
including:

  - builds scenario without writing runtime config,
  - hypothetical rule change is **not** a runtime patch,
  - delta metrics are deterministic across two runs,
  - missing evidence yields `INSUFFICIENT_EVIDENCE` /
    `INCONCLUSIVE`,
  - data-gap warnings preserved,
  - `recommendation_level` never `APPLY` / `DEPLOY` / `TRADE`,
  - `auto_tuning_allowed=False`,
  - `writes_runtime_config=False`,
  - `trade_authority=False`,
  - `phase_12_forbidden=True`,
  - forbidden fields absent at every nesting depth,
  - runner does not import `app.risk` / `app.execution` /
    `app.exchanges` / `app.telegram` / `app.config`,
  - no DeepSeek / LLM / network call path (and a belt-and-
    braces `socket.socket` monkeypatch test exercising the
    full runner path),
  - JSON output serialisable,
  - deterministic output across two runs.

## Safety boundary held

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `llm_outbound_enabled = False`
  - `sandbox_only = True`
  - `allow_trade_decision = False`
  - `allow_runtime_config_change = False`
  - `auto_tuning_allowed = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - `phase_12_forbidden = True`
  - `trade_authority = False`
  - `writes_runtime_config = False`
  - `ai_output_can_be_truth = False`
  - `ai_output_can_be_training_label = False`
  - `ai_output_can_be_tail_label = False`
  - `ai_output_can_be_strategy_sample = False`

The Risk Engine remains the single trade-decision gate.
**Phase 12 remains FORBIDDEN.**
