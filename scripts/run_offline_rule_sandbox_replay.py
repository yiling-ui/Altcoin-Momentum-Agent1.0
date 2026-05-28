"""Phase 11C - Offline Rule Sandbox Replay v0 runner.

Loads frozen historical evidence from local files (the Block B
integrated evidence checkpoint, the Block C integrated
checkpoint, the AI integrated checkpoint, and operator-supplied
discovery-quality / outcome / reject / severe-miss / replay /
reflection summaries) plus a scenario file describing one or more
hypothetical rule changes, runs the
:class:`OfflineRuleSandboxEngine` deterministically, and writes
one ``offline_rule_sandbox_report.json`` plus its Markdown twin to
the output directory.

Boundary
========

The runner is paper / report / sandbox-only. It MUST NOT and
DOES NOT:

  - place a real or paper trade,
  - close or modify a position,
  - change ``symbol_limit`` / candidate-pool capacity / anomaly
    thresholds / Regime weights / strategy parameters,
  - write back any runtime configuration,
  - call an LLM, DeepSeek, Telegram outbound transport, or any
    private exchange API,
  - import :mod:`app.risk`, :mod:`app.execution`,
    :mod:`app.exchanges`, :mod:`app.telegram`, :mod:`app.config`,
  - import :mod:`openai`, :mod:`anthropic`, :mod:`deepseek`,
    :mod:`httpx`, :mod:`requests`, :mod:`aiohttp`, :mod:`urllib3`,
    :mod:`websocket`, :mod:`websockets`, :mod:`grpc`,
    :mod:`boto3`, :mod:`socket`,
  - generate a ``runtime_config_patch`` /
    ``threshold_patch`` / ``symbol_limit_patch`` /
    ``candidate_pool_patch`` / ``regime_weight_patch`` /
    ``strategy_parameter_patch``,
  - emit any direction / sizing / leverage / stop / target /
    risk-budget / order / "should buy" / "should short" /
    "apply" / "deploy" / "enable_live" field,
  - open Phase 12.

The Risk Engine remains the single trade-decision gate.

Inputs
------

  - ``--block-b-report``    data/reports/block_b_integrated_evidence/
                            block_b_integrated_evidence_report.json
  - ``--block-c-report``    data/reports/block_c_integrated_checkpoint/
                            block_c_integrated_checkpoint_report.json
  - ``--ai-checkpoint``     data/reports/ai/integrated_checkpoint/
                            ai_integrated_checkpoint_report.json
  - ``--baseline-discovery-quality`` (optional)
                            JSON file carrying the baseline
                            discovery-quality counters / rates.
  - ``--post-discovery-outcomes`` (optional)
                            JSON file carrying the post-discovery
                            outcome roll-up.
  - ``--reject-attributions`` (optional)
                            JSON file carrying the
                            reject-to-outcome attribution roll-up.
  - ``--severe-miss-triage`` (optional)
                            JSON file carrying the severe missed
                            tail triage roll-up.
  - ``--replay-summary`` (optional)
                            JSON file carrying the replay summary.
  - ``--reflection-summary`` (optional)
                            JSON file carrying the reflection
                            summary.
  - ``--scenario-file`` (optional)
                            JSON file carrying one scenario
                            object **or** a list of scenarios.
                            When absent, the runner generates a
                            deterministic example scenario marked
                            ``source=example_fixture``.
  - ``--output-dir``        data/reports/rule_sandbox
  - ``--reference-window``  60d (descriptive only)

Outputs
-------

  - ``<output-dir>/offline_rule_sandbox_report.json``
  - ``<output-dir>/offline_rule_sandbox_report.md``

Both files re-pin the project-wide safety invariants at the
serialisation boundary.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add project root to path so the runner can be invoked as a
# script.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Imports from allowed packages only:
#   - app.sandbox.offline_rule_sandbox (Phase 11C Offline Rule
#     Sandbox Replay v0)
#
# The runner MUST NOT import:
#   - app.risk        (forbidden)
#   - app.execution   (forbidden)
#   - app.exchanges   (forbidden)
#   - app.telegram    (forbidden)
#   - app.config      (forbidden by brief)
from app.sandbox.offline_rule_sandbox import (  # noqa: E402
    FORBIDDEN_SANDBOX_PAYLOAD_KEYS,
    HypotheticalRuleChange,
    NEXT_PHASE_NEEDS_MORE_EVIDENCE,
    NEXT_PHASE_NEEDS_OPERATOR_REVIEW,
    NEXT_PHASE_PAPER_SHADOW_PREP,
    OfflineRuleSandboxEngine,
    OfflineRuleSandboxInput,
    OfflineRuleSandboxReport,
    OfflineRuleSandboxScenario,
    RECOMMENDATION_LEVELS,
    SANDBOX_EVENT_REPLAY_RUN,
    SANDBOX_EVENT_REPORT_GENERATED,
    SANDBOX_EVENT_SCENARIO_EVALUATED,
    SANDBOX_REPORT_SCHEMA_VERSION,
    SANDBOX_SOURCE_PHASE,
    build_example_scenario,
    safety_flags_dict,
)


SOURCE_MODULE: str = "scripts.run_offline_rule_sandbox_replay"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SandboxRunResult:
    """In-memory result of one runner invocation.

    Paper / report / sandbox-only. No trade-authority field.
    """

    output_report_path: Path
    output_summary_path: Path
    payload: Mapping[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path | None) -> Any | None:
    """Return the parsed JSON value at ``path``, or ``None`` if
    the file is missing / empty / unreadable / not parseable.
    """

    if path is None:
        return None
    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _read_json_object(path: Path | None) -> dict[str, Any] | None:
    obj = _read_json(path)
    if isinstance(obj, dict):
        return obj
    return None


def _coerce_str_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(
            str(item) for item in value if item is not None
        )
    if isinstance(value, str):
        text = value.strip()
        return (text,) if text else ()
    return (str(value),)


def _build_hypothetical_rule_change(
    raw: Mapping[str, Any]
) -> HypotheticalRuleChange:
    rule_name = str(raw.get("rule_name") or "").strip() or (
        "generic_rule"
    )
    change_type = str(
        raw.get("change_type") or "no_change"
    ).strip() or "no_change"
    return HypotheticalRuleChange(
        rule_name=rule_name,
        baseline_value=raw.get("baseline_value"),
        sandbox_value=raw.get("sandbox_value"),
        change_type=change_type,
        rationale=str(raw.get("rationale") or ""),
        evidence_refs=_coerce_str_tuple(
            raw.get("evidence_refs")
        ),
    )


def _build_scenario_from_dict(
    raw: Mapping[str, Any], *, default_reference_window: str
) -> OfflineRuleSandboxScenario:
    rule_changes_raw = raw.get("hypothetical_rule_changes") or []
    if not isinstance(rule_changes_raw, (list, tuple)):
        rule_changes_raw = []
    rule_changes = tuple(
        _build_hypothetical_rule_change(item)
        for item in rule_changes_raw
        if isinstance(item, Mapping)
    )
    scenario_id = (
        str(raw.get("scenario_id") or "").strip()
        or "operator_scenario"
    )
    name = str(raw.get("name") or scenario_id)
    reference_window = str(
        raw.get("reference_window")
        or default_reference_window
    )
    baseline_label = str(
        raw.get("baseline_label") or "operator_baseline"
    )
    return OfflineRuleSandboxScenario(
        scenario_id=scenario_id,
        name=name,
        reference_window=reference_window,
        baseline_label=baseline_label,
        hypothetical_rule_changes=rule_changes,
        cohort_filters=_coerce_str_tuple(
            raw.get("cohort_filters")
        ),
        source_reports=_coerce_str_tuple(
            raw.get("source_reports")
        ),
        evidence_refs=_coerce_str_tuple(
            raw.get("evidence_refs")
        ),
        source=str(raw.get("source") or "operator_supplied"),
    )


def _load_scenarios(
    *,
    scenario_file: Path | None,
    reference_window: str,
) -> tuple[
    tuple[OfflineRuleSandboxScenario, ...], str
]:
    """Return ``(scenarios, source)`` where ``source`` is one of
    ``operator_supplied`` / ``example_fixture``.
    """

    raw = _read_json(scenario_file)
    if raw is None:
        # Fall back to the deterministic example scenario.
        return (
            (
                build_example_scenario(
                    reference_window=reference_window
                ),
            ),
            "example_fixture",
        )

    if isinstance(raw, list):
        scenarios = tuple(
            _build_scenario_from_dict(
                item,
                default_reference_window=reference_window,
            )
            for item in raw
            if isinstance(item, Mapping)
        )
        if not scenarios:
            return (
                (
                    build_example_scenario(
                        reference_window=reference_window
                    ),
                ),
                "example_fixture",
            )
        return scenarios, "operator_supplied"

    if isinstance(raw, Mapping):
        # Two possible shapes: a single scenario dict, or a
        # report-shaped dict with a top-level ``scenarios`` list.
        if isinstance(raw.get("scenarios"), list):
            scenarios = tuple(
                _build_scenario_from_dict(
                    item,
                    default_reference_window=reference_window,
                )
                for item in raw["scenarios"]
                if isinstance(item, Mapping)
            )
            if not scenarios:
                return (
                    (
                        build_example_scenario(
                            reference_window=reference_window
                        ),
                    ),
                    "example_fixture",
                )
            return scenarios, "operator_supplied"
        return (
            (
                _build_scenario_from_dict(
                    raw,
                    default_reference_window=reference_window,
                ),
            ),
            "operator_supplied",
        )

    return (
        (
            build_example_scenario(
                reference_window=reference_window
            ),
        ),
        "example_fixture",
    )


def _resolve_baseline_payload(
    *,
    baseline_path: Path | None,
    block_b_report: Mapping[str, Any] | None,
    block_c_report: Mapping[str, Any] | None,
    ai_checkpoint: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    """Return the discovery-quality baseline payload.

    Priority order:

      1. ``--baseline-discovery-quality`` (when present and a
         dict).
      2. The ``baseline`` / ``baseline_metrics`` /
         ``baseline_discovery_quality`` sub-tree of the AI
         integrated checkpoint payload.
      3. The ``baseline`` / ``baseline_metrics`` /
         ``baseline_discovery_quality`` sub-tree of the Block C
         integrated checkpoint payload.
      4. The ``baseline`` / ``baseline_metrics`` /
         ``baseline_discovery_quality`` sub-tree of the Block B
         integrated evidence checkpoint payload.
      5. ``{}`` (and the engine emits a data-gap warning).
    """

    candidate = _read_json_object(baseline_path)
    if candidate is not None:
        return candidate

    for source in (
        ai_checkpoint,
        block_c_report,
        block_b_report,
    ):
        if not isinstance(source, Mapping):
            continue
        for key in (
            "baseline_discovery_quality",
            "baseline_metrics",
            "baseline",
        ):
            value = source.get(key)
            if isinstance(value, Mapping) and value:
                return dict(value)
    return {}


def _resolve_summary_payload(
    *,
    summary_path: Path | None,
    fallback: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    candidate = _read_json_object(summary_path)
    if candidate is not None:
        return candidate
    if isinstance(fallback, Mapping):
        return dict(fallback)
    return {}


def _format_markdown_summary(
    payload: Mapping[str, Any],
) -> str:
    lines: list[str] = []
    lines.append(
        "# Phase 11C Offline Rule Sandbox Replay v0"
    )
    lines.append("")
    lines.append(
        "Paper / report / sandbox-only. **NOT** live "
        "trading. **NOT** auto-tuning. **NOT** runtime "
        "config writeback. **NOT** Phase 12."
    )
    lines.append("")
    lines.append(f"- report_id: {payload.get('report_id')}")
    lines.append(
        f"- generated_at_utc: {payload.get('generated_at_utc')}"
    )
    lines.append(
        f"- reference_window: {payload.get('reference_window')}"
    )
    lines.append(
        f"- next_allowed_phase: "
        f"{payload.get('next_allowed_phase')}"
    )
    lines.append(
        f"- phase_12_forbidden: "
        f"{payload.get('phase_12_forbidden')}"
    )
    lines.append(
        f"- auto_tuning_allowed: "
        f"{payload.get('auto_tuning_allowed')}"
    )
    lines.append(
        f"- writes_runtime_config: "
        f"{payload.get('writes_runtime_config')}"
    )
    lines.append(
        f"- trade_authority: "
        f"{payload.get('trade_authority')}"
    )
    lines.append("")
    lines.append("## Recommendation levels (CLOSED vocabulary)")
    for level in payload.get("recommendation_levels") or []:
        lines.append(f"- {level}")
    lines.append("")
    lines.append("## Scenarios evaluated")
    lines.append("")
    for result in payload.get("scenario_results") or []:
        lines.append(
            f"### {result.get('scenario_id')}"
        )
        lines.append("")
        lines.append(f"- status: {result.get('status')}")
        lines.append(
            f"- recommendation_level: "
            f"{result.get('recommendation_level')}"
        )
        lines.append(
            "- baseline_metrics: "
            f"{json.dumps(result.get('baseline_metrics'))}"
        )
        lines.append(
            "- sandbox_metrics: "
            f"{json.dumps(result.get('sandbox_metrics'))}"
        )
        lines.append(
            "- delta_metrics: "
            f"{json.dumps(result.get('delta_metrics'))}"
        )
        if result.get("likely_benefits"):
            lines.append("- likely_benefits:")
            for item in result["likely_benefits"]:
                lines.append(f"  - {item}")
        if result.get("likely_risks"):
            lines.append("- likely_risks:")
            for item in result["likely_risks"]:
                lines.append(f"  - {item}")
        if result.get("overfit_warnings"):
            lines.append("- overfit_warnings:")
            for item in result["overfit_warnings"]:
                lines.append(f"  - {item}")
        if result.get("data_gap_warnings"):
            lines.append("- data_gap_warnings:")
            for item in result["data_gap_warnings"]:
                lines.append(f"  - {item}")
        if result.get("notes"):
            lines.append("- notes:")
            for item in result["notes"]:
                lines.append(f"  - {item}")
        lines.append("")
    lines.append("## Best review candidates")
    for sc in payload.get("best_review_candidates") or []:
        lines.append(f"- {sc}")
    if not (payload.get("best_review_candidates") or []):
        lines.append("- (none)")
    lines.append("")
    lines.append("## Rejected scenarios")
    for sc in payload.get("rejected_scenarios") or []:
        lines.append(f"- {sc}")
    if not (payload.get("rejected_scenarios") or []):
        lines.append("- (none)")
    lines.append("")
    lines.append("## Known gaps")
    for gap in payload.get("known_gaps") or []:
        lines.append(f"- {gap}")
    if not (payload.get("known_gaps") or []):
        lines.append("- (none)")
    lines.append("")
    lines.append("## Safety boundary")
    lines.append("")
    lines.append(
        "- Sandbox does NOT authorise live trading."
    )
    lines.append(
        "- Sandbox does NOT write back runtime config."
    )
    lines.append("- Sandbox does NOT auto-tune.")
    lines.append(
        "- Sandbox does NOT call Risk / Execution / "
        "Exchange / Telegram / LLM / DeepSeek."
    )
    lines.append(
        "- Sandbox NEVER emits direction / sizing / "
        "leverage / stop / target / risk-budget / order / "
        "runtime_config_patch / signal_to_trade fields."
    )
    lines.append(
        "- A successful sandbox scenario only allows "
        "Paper Shadow Strategy Validation preparation; it "
        "does NOT open Phase 12."
    )
    lines.append(
        "- Phase 12 remains FORBIDDEN. The Risk Engine "
        "remains the single trade-decision gate."
    )
    lines.append("")
    safety = payload.get("safety_flags") or {}
    if isinstance(safety, Mapping):
        lines.append("## Safety flags (re-pinned)")
        lines.append("")
        for k, v in sorted(safety.items()):
            lines.append(f"- `{k}` = `{v}`")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def run_sandbox(
    *,
    block_b_report: Path | None,
    block_c_report: Path | None,
    ai_checkpoint: Path | None,
    baseline_discovery_quality: Path | None,
    post_discovery_outcomes: Path | None,
    reject_attributions: Path | None,
    severe_miss_triage: Path | None,
    replay_summary: Path | None,
    reflection_summary: Path | None,
    scenario_file: Path | None,
    output_dir: Path,
    reference_window: str,
) -> SandboxRunResult:
    """Run the offline rule sandbox once and persist the report.

    The runner is read-only / write-only; it never connects to
    the network.
    """

    output_dir = Path(output_dir)
    output_report_path = (
        output_dir / "offline_rule_sandbox_report.json"
    )
    output_summary_path = (
        output_dir / "offline_rule_sandbox_report.md"
    )

    # Optional descriptive inputs.
    block_b_payload = _read_json_object(block_b_report)
    block_c_payload = _read_json_object(block_c_report)
    ai_checkpoint_payload = _read_json_object(ai_checkpoint)

    baseline_payload = _resolve_baseline_payload(
        baseline_path=baseline_discovery_quality,
        block_b_report=block_b_payload,
        block_c_report=block_c_payload,
        ai_checkpoint=ai_checkpoint_payload,
    )
    post_discovery_payload = _resolve_summary_payload(
        summary_path=post_discovery_outcomes,
    )
    reject_attribution_payload = _resolve_summary_payload(
        summary_path=reject_attributions,
    )
    severe_miss_payload = _resolve_summary_payload(
        summary_path=severe_miss_triage,
    )
    replay_summary_payload = _resolve_summary_payload(
        summary_path=replay_summary,
    )
    reflection_summary_payload = _resolve_summary_payload(
        summary_path=reflection_summary,
    )

    scenarios, scenario_source = _load_scenarios(
        scenario_file=scenario_file,
        reference_window=reference_window,
    )

    sandbox_inputs = tuple(
        OfflineRuleSandboxInput(
            scenario=scenario,
            baseline_discovery_quality=baseline_payload,
            post_discovery_outcomes=post_discovery_payload,
            reject_attributions=reject_attribution_payload,
            severe_miss_triage=severe_miss_payload,
            replay_summary=replay_summary_payload,
            reflection_summary=reflection_summary_payload,
            evidence_refs=tuple(scenario.evidence_refs),
        )
        for scenario in scenarios
    )

    engine = OfflineRuleSandboxEngine()
    report_id = (
        f"offline_rule_sandbox_{reference_window}_"
        f"{len(sandbox_inputs)}_scenarios"
    )
    inputs_summary: dict[str, Any] = {
        "block_b_report_path": (
            str(block_b_report)
            if block_b_report is not None
            else None
        ),
        "block_c_report_path": (
            str(block_c_report)
            if block_c_report is not None
            else None
        ),
        "ai_checkpoint_path": (
            str(ai_checkpoint)
            if ai_checkpoint is not None
            else None
        ),
        "baseline_discovery_quality_path": (
            str(baseline_discovery_quality)
            if baseline_discovery_quality is not None
            else None
        ),
        "post_discovery_outcomes_path": (
            str(post_discovery_outcomes)
            if post_discovery_outcomes is not None
            else None
        ),
        "reject_attributions_path": (
            str(reject_attributions)
            if reject_attributions is not None
            else None
        ),
        "severe_miss_triage_path": (
            str(severe_miss_triage)
            if severe_miss_triage is not None
            else None
        ),
        "replay_summary_path": (
            str(replay_summary)
            if replay_summary is not None
            else None
        ),
        "reflection_summary_path": (
            str(reflection_summary)
            if reflection_summary is not None
            else None
        ),
        "scenario_file_path": (
            str(scenario_file)
            if scenario_file is not None
            else None
        ),
        "scenario_source": scenario_source,
        "block_b_report_loaded": block_b_payload is not None,
        "block_c_report_loaded": block_c_payload is not None,
        "ai_checkpoint_loaded": (
            ai_checkpoint_payload is not None
        ),
        "baseline_payload_loaded": bool(baseline_payload),
        "post_discovery_payload_loaded": bool(
            post_discovery_payload
        ),
        "reject_attribution_payload_loaded": bool(
            reject_attribution_payload
        ),
        "severe_miss_payload_loaded": bool(
            severe_miss_payload
        ),
        "replay_summary_payload_loaded": bool(
            replay_summary_payload
        ),
        "reflection_summary_payload_loaded": bool(
            reflection_summary_payload
        ),
    }

    report = engine.build_report(
        report_id=report_id,
        reference_window=reference_window,
        sandbox_inputs=sandbox_inputs,
        inputs_summary=inputs_summary,
        generated_at_utc=_now_utc_iso(),
    )

    payload = report.to_dict()
    payload["source_module"] = SOURCE_MODULE
    payload["scenario_source"] = scenario_source

    # The runner is the canonical record of the three event
    # names defined for this slice. Embed them as descriptive
    # strings so an export can carry them forward without
    # mutating ``app.core.events.EventType``.
    payload["events_emitted"] = [
        {
            "event_name": SANDBOX_EVENT_REPLAY_RUN,
            "count": 1,
            "is_report_only": True,
        },
        {
            "event_name": SANDBOX_EVENT_SCENARIO_EVALUATED,
            "count": len(report.scenario_results),
            "is_report_only": True,
        },
        {
            "event_name": SANDBOX_EVENT_REPORT_GENERATED,
            "count": 1,
            "is_report_only": True,
        },
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    output_report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    output_summary_path.write_text(
        _format_markdown_summary(payload),
        encoding="utf-8",
    )

    return SandboxRunResult(
        output_report_path=output_report_path,
        output_summary_path=output_summary_path,
        payload=payload,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_args(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_offline_rule_sandbox_replay",
        description=(
            "Phase 11C - Offline Rule Sandbox Replay v0. Paper "
            "/ report / sandbox-only. Phase 12 remains "
            "FORBIDDEN. The Risk Engine remains the single "
            "trade-decision gate."
        ),
    )
    parser.add_argument(
        "--block-b-report",
        type=Path,
        default=Path(
            "data/reports/block_b_integrated_evidence/"
            "block_b_integrated_evidence_report.json"
        ),
        help=(
            "Path to the Block B integrated evidence "
            "checkpoint JSON file (descriptive only)."
        ),
    )
    parser.add_argument(
        "--block-c-report",
        type=Path,
        default=Path(
            "data/reports/block_c_integrated_checkpoint/"
            "block_c_integrated_checkpoint_report.json"
        ),
        help=(
            "Path to the Block C integrated checkpoint JSON "
            "file (descriptive only)."
        ),
    )
    parser.add_argument(
        "--ai-checkpoint",
        type=Path,
        default=Path(
            "data/reports/ai/integrated_checkpoint/"
            "ai_integrated_checkpoint_report.json"
        ),
        help=(
            "Path to the AI integrated checkpoint JSON file "
            "(descriptive only)."
        ),
    )
    parser.add_argument(
        "--baseline-discovery-quality",
        type=Path,
        default=None,
        help=(
            "Optional path to a baseline discovery-quality "
            "JSON file (overrides the baseline pulled from the "
            "AI / Block C / Block B checkpoint payloads)."
        ),
    )
    parser.add_argument(
        "--post-discovery-outcomes",
        type=Path,
        default=None,
        help=(
            "Optional path to a post-discovery outcome "
            "summary JSON file."
        ),
    )
    parser.add_argument(
        "--reject-attributions",
        type=Path,
        default=None,
        help=(
            "Optional path to a reject-to-outcome attribution "
            "summary JSON file."
        ),
    )
    parser.add_argument(
        "--severe-miss-triage",
        type=Path,
        default=None,
        help=(
            "Optional path to a severe missed tail triage "
            "summary JSON file."
        ),
    )
    parser.add_argument(
        "--replay-summary",
        type=Path,
        default=None,
        help=(
            "Optional path to a replay summary JSON file."
        ),
    )
    parser.add_argument(
        "--reflection-summary",
        type=Path,
        default=None,
        help=(
            "Optional path to a reflection summary JSON file."
        ),
    )
    parser.add_argument(
        "--scenario-file",
        type=Path,
        default=Path(
            "data/reports/rule_sandbox/scenario.json"
        ),
        help=(
            "Path to a scenario JSON file. Accepts a single "
            "scenario object, a list of scenarios, or a "
            "report-shaped object with a ``scenarios`` list. "
            "When absent the runner generates a deterministic "
            "example scenario marked "
            "source=example_fixture."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/reports/rule_sandbox"),
        help=(
            "Where the sandbox report + markdown are written."
        ),
    )
    parser.add_argument(
        "--reference-window",
        type=str,
        default="60d",
        help="Audit-window label (descriptive only).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = run_sandbox(
            block_b_report=args.block_b_report,
            block_c_report=args.block_c_report,
            ai_checkpoint=args.ai_checkpoint,
            baseline_discovery_quality=(
                args.baseline_discovery_quality
            ),
            post_discovery_outcomes=(
                args.post_discovery_outcomes
            ),
            reject_attributions=args.reject_attributions,
            severe_miss_triage=args.severe_miss_triage,
            replay_summary=args.replay_summary,
            reflection_summary=args.reflection_summary,
            scenario_file=args.scenario_file,
            output_dir=args.output_dir,
            reference_window=args.reference_window,
        )
    except ValueError as exc:
        sys.stderr.write(
            "offline_rule_sandbox: forbidden key in "
            f"payload: {exc}\n"
        )
        return 2
    sys.stdout.write(
        json.dumps(
            {
                "report_id": result.payload.get(
                    "report_id"
                ),
                "next_allowed_phase": result.payload.get(
                    "next_allowed_phase"
                ),
                "scenario_count": len(
                    result.payload.get("scenarios") or []
                ),
                "best_review_candidates": result.payload.get(
                    "best_review_candidates"
                ),
                "rejected_scenarios": result.payload.get(
                    "rejected_scenarios"
                ),
                "output_report": str(
                    result.output_report_path
                ),
                "output_summary": str(
                    result.output_summary_path
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    sys.stdout.write("\n")
    return 0


__all__ = [
    "FORBIDDEN_SANDBOX_PAYLOAD_KEYS",
    "NEXT_PHASE_NEEDS_MORE_EVIDENCE",
    "NEXT_PHASE_NEEDS_OPERATOR_REVIEW",
    "NEXT_PHASE_PAPER_SHADOW_PREP",
    "RECOMMENDATION_LEVELS",
    "SANDBOX_EVENT_REPLAY_RUN",
    "SANDBOX_EVENT_REPORT_GENERATED",
    "SANDBOX_EVENT_SCENARIO_EVALUATED",
    "SANDBOX_REPORT_SCHEMA_VERSION",
    "SANDBOX_SOURCE_PHASE",
    "SOURCE_MODULE",
    "SandboxRunResult",
    "main",
    "run_sandbox",
    "safety_flags_dict",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
