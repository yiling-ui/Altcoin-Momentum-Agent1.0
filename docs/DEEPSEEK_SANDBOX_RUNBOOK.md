# DeepSeek Offline Sandbox v0 - Operator Runbook

> **Scope:** paper / report / sandbox-only. **NOT** live
> trading. **NOT** trade authority. **NOT** auto-tuning.
> **NOT** the DeepSeek hot path. **NOT** Phase 12. The Risk
> Engine remains the single trade-decision gate.

This runbook describes how an operator runs the Phase AI-4
DeepSeek Offline Sandbox v0 against a frozen Phase AI-1
:class:`AIEvidenceBundle` and inspects the resulting
:class:`AIIntelligenceOutput`. Every step is offline,
deterministic, and read-only.

## 1. Prerequisites

  - A serialised Phase AI-1 evidence bundle JSON file. The
    file is the output of
    `AIEvidenceBundle.to_dict()` -> `json.dumps(...)`. The
    operator typically picks the bundle that the upstream
    pipeline produced for the day's review window.
  - Python 3.12 or 3.13 (matching the project's `pytest`
    matrix) plus `requirements.txt` already installed.
  - The repository checkout at HEAD on `main` (Phase AI-3
    merged via PR #84).

The runbook does NOT require:

  - a DeepSeek API key (the v0 transport is refusal-only);
  - a Binance API key / secret (the runner never reads
    private state);
  - a Telegram bot token (real Telegram outbound remains
    gated by Spec §41);
  - network access (the runner is offline-only in v0).

## 2. Quick start

The runner short-circuits to a degraded result when the
master gate is closed (the default), so a smoke-run with
both gates open is the simplest way to verify the toolchain:

```
python scripts/run_deepseek_offline_sandbox.py \
    --bundle-path data/reports/ai/evidence_bundle.json \
    --task-type MARKET_INTELLIGENCE_SUMMARY \
    --operator-instruction "Summarise the bundle as commentary substrate." \
    --output-dir data/reports/ai/deepseek_sandbox \
    --enabled \
    --outbound-enabled
```

The runner prints one summary line to stdout and writes:

  - `<output-dir>/deepseek_sandbox_output.json`
  - `<output-dir>/deepseek_sandbox_output.md`

Both files re-pin the project-wide safety invariants on
every emission.

## 3. CLI reference

```
python scripts/run_deepseek_offline_sandbox.py [-h]
    --bundle-path BUNDLE_PATH
    [--task-type {OPERATOR_BRIEFING_DRAFT,MARKET_INTELLIGENCE_SUMMARY,
                  EVIDENCE_COMPRESSION,REPLAY_REFLECTION_SUMMARY,
                  CONTRADICTION_SUMMARY,EVIDENCE_QUALITY_ASSESSMENT,
                  COVERAGE_AUDIT_INTERPRETATION,
                  POST_DISCOVERY_OUTCOME_SUMMARY,
                  REJECT_TO_OUTCOME_SUMMARY,SEVERE_MISS_SUMMARY}]
    [--operator-instruction OPERATOR_INSTRUCTION]
    [--output-dir OUTPUT_DIR]
    [--enabled]
    [--outbound-enabled]
    [--timeout-seconds TIMEOUT_SECONDS]
    [--max-tokens MAX_TOKENS]
    [--model MODEL]
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--bundle-path` | required | Path to a serialised Phase AI-1 :class:`AIEvidenceBundle` JSON. |
| `--task-type` | `MARKET_INTELLIGENCE_SUMMARY` | Closed task-type vocabulary. |
| `--operator-instruction` | "Summarise the evidence bundle as commentary substrate for the operator. Cite every claim." | Operator-supplied free-form instruction. |
| `--output-dir` | `data/reports/ai/deepseek_sandbox` | Where the JSON + Markdown output is written. |
| `--enabled` | `False` (master gate closed) | Master gate. When closed the runner short-circuits to a degraded result. |
| `--outbound-enabled` | `False` (outbound gate closed) | Outbound gate. When closed the runner uses :class:`FakeDeepSeekProvider` regardless of what was configured. |
| `--timeout-seconds` | `30.0` | Provider timeout budget. |
| `--max-tokens` | `2048` | Provider max-tokens budget. |
| `--model` | `deepseek-chat` | Provider model id. |

## 4. Reading the output

`deepseek_sandbox_output.json` is the canonical output. The
top-level keys are:

| Key | Meaning |
| --- | --- |
| `schema_version` | `v0`. |
| `source_phase` | `phase_ai_4`. |
| `source_module` | `ai_intelligence_output`. |
| `bundle_id` | The Phase AI-1 bundle id the run consumed. |
| `task_type` | The task type the run executed. |
| `summary` | Free-form commentary; redacted. |
| `claims` | List of cited claims with citation + reality-check verdicts. |
| `contradictions` | Claim ids the Reality Check Layer flagged. |
| `unsupported_claims` | Claim ids without sufficient evidence. |
| `risk_tags` | Descriptive tags only - never trade actions. |
| `evidence_refs` | Deduplicated union of every claim's `evidence_refs`. |
| `reality_check_status` | Aggregated Reality Check status. |
| `authority_level` | One of `COMMENTARY_ONLY` / `SUPPORTED_INTELLIGENCE` / `DEGRADED_NO_EVIDENCE` / `DEGRADED_REALITY_CHECK` / `REJECTED`. |
| `status` | One of `OK` / `DEGRADED_*` / `REJECTED_*`. |
| `forbidden_fields_stripped` | Audit trail: paths the runner stripped. |
| `redacted_secret_count` | Count of credential-shaped keys redacted. |
| `warnings`, `degraded_reasons` | Audit trail. |
| `safety_flags` | Project-wide invariants re-pinned at emission. |
| `forbidden_fields` | Reference list of forbidden trade-action / runtime-config-patch field names. |

## 5. Status interpretation

  - `OK + SUPPORTED_INTELLIGENCE` - the model produced cited
    claims that survived Reality Check. **Commentary
    substrate** for the operator only.
  - `OK + COMMENTARY_ONLY` - the model produced a summary
    plus claims that are descriptive only. Still commentary;
    no trade authority.
  - `DEGRADED_OUTBOUND_DISABLED` - either the master gate
    or the provider configuration prevented an outbound
    call. The runner returned a degraded but well-formed
    output. **Expected** when the gates are closed.
  - `DEGRADED_PROVIDER_ERROR` - the provider raised a
    timeout / 429 / 5xx / unexpected error. The runner
    returned a degraded output instead of crashing.
  - `DEGRADED_MISSING_EVIDENCE` - one or more claims lacked
    `evidence_refs`. The audit trail names the specific
    claim ids in `unsupported_claims`.
  - `DEGRADED_REALITY_CHECK` - one or more claims failed
    Reality Check (contradicted, narrative pollution,
    lookahead violation, insufficient evidence). The audit
    trail names the specific claim ids in
    `contradictions` / `unsupported_claims`.
  - `REJECTED_FORBIDDEN_FIELDS` - the model emitted a
    forbidden trade-action / runtime-config-patch field.
    The runner stripped them and rejected the output. The
    paths are recorded in `forbidden_fields_stripped`.
  - `REJECTED_INVALID_INPUT` - the input contained a
    forbidden / credential-shaped key, an unknown task type,
    or a non-mapping bundle. The runner refused to call the
    provider.

## 6. Safety boundary checklist

After every run the operator MUST verify:

  - `safety_flags.mode == "paper"`
  - `safety_flags.live_trading == false`
  - `safety_flags.exchange_live_orders == false`
  - `safety_flags.right_tail == false`
  - `safety_flags.llm == false`
  - `safety_flags.llm_outbound_enabled == false`
  - `safety_flags.sandbox_only == true`
  - `safety_flags.telegram_outbound_enabled == false`
  - `safety_flags.binance_private_api_enabled == false`
  - `trade_authority == false`
  - `auto_tuning_allowed == false`
  - `phase_12_forbidden == true`

A run output that violates any of the invariants above is a
**hard regression** and must be reported, not consumed.

## 7. What the run does NOT do

The run NEVER:

  - places an order;
  - changes leverage / position size / stop / target;
  - sends a real Telegram outbound message;
  - reads a private exchange API key / secret;
  - reads private account state;
  - calls the real DeepSeek HTTP transport (refusal-only
    skeleton);
  - changes `symbol_limit`, anomaly thresholds, candidate-
    pool capacity, Regime weights, or any other runtime
    knob;
  - feeds its own output back into a future training label,
    a future runtime fact, or a future briefing prompt;
  - opens Phase 12.

## 8. Re-running for evidence preservation

Each run is deterministic given the same bundle, the same
config, and the same provider. A second run with identical
inputs produces an identical
`deepseek_sandbox_output.json` modulo the
`generated_at_utc` timestamp the script attaches at write
time. The deterministic guarantee is asserted by the
`test_same_input_same_output_is_deterministic` unit test.

## 9. Triage

| Symptom | Likely cause | Remedy |
| --- | --- | --- |
| `status=DEGRADED_OUTBOUND_DISABLED`, `warnings=["sandbox_disabled"]` | Master gate closed (`--enabled` not passed). | Pass `--enabled` if you want a non-degraded run; otherwise this is the safe default. |
| `status=DEGRADED_OUTBOUND_DISABLED`, `warnings=["outbound_enabled_but_no_provider"]` | `--outbound-enabled` was passed but no provider was configured. | The default script wires :class:`FakeDeepSeekProvider`; if you replaced it with `OptionalDeepSeekHTTPProvider` it refuses by design. |
| `status=DEGRADED_PROVIDER_ERROR` | Provider raised. | Inspect `degraded_reasons` for the typed error. The runner never crashes; the result is still well-formed. |
| `status=DEGRADED_MISSING_EVIDENCE` | A claim lacked `evidence_refs`. | Inspect `unsupported_claims` for the offending claim ids. |
| `status=DEGRADED_REALITY_CHECK` | A claim failed Reality Check. | Inspect `contradictions` / `unsupported_claims`. The bundle's `market_facts` / `outcome_facts` will explain why. |
| `status=REJECTED_FORBIDDEN_FIELDS` | Model emitted a forbidden field. | Inspect `forbidden_fields_stripped`. The model output is rejected; do NOT attempt to re-enable the field. |
| `status=REJECTED_INVALID_INPUT` | Input contained a forbidden / credential-shaped key, or an unknown task type. | Inspect `warnings` for the specific reason. Re-prepare the bundle without the offending key; the input guard is intentional. |

## 10. Boundary reminder

The DeepSeek Offline Sandbox v0 is the AI Layer's *first*
outbound-capable runtime artefact, but it is a
**sandbox-only** artefact. A successful run does not
authorise live trading, does not authorise auto-tuning, does
not authorise Operator Briefing live publishing, does not
authorise the real DeepSeek HTTP transport, and does not
open Phase 12. The Risk Engine remains the single
trade-decision gate.
