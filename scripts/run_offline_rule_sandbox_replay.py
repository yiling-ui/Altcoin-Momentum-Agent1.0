#!/usr/bin/env python3
"""Runner for Phase 11C / Offline Rule Sandbox Replay v0.

Strictly offline. Reads historical evidence reports, evaluates one or more
hypothetical scenarios, and writes a JSON+Markdown report.

Hard safety boundary:
  - sandbox_only = True
  - writes_runtime_config = False
  - auto_tuning_allowed = False
  - trade_authority = False
  - phase_12_forbidden = True
  - This script MUST NOT import app.risk / app.execution / app.exchanges
    / app.telegram / app.config.
  - This script MUST NOT call any LLM / DeepSeek / network endpoint.
  - This script MUST NOT write back to runtime config.

Usage:
  python scripts/run_offline_rule_sandbox_replay.py \\
      --block-b-report data/reports/block_b_integrated_evidence/block_b_integrated_evidence_report.json \\
      --block-c-report data/reports/block_c_integrated_checkpoint/block_c_integrated_checkpoint_report.json \\
      --ai-checkpoint data/reports/ai/integrated_checkpoint/ai_integrated_checkpoint_report.json \\
      --scenario-file data/reports/rule_sandbox/scenario.json \\
      --output-dir data/reports/rule_sandbox \\
      --reference-window 60d
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

# Make `app` importable when run from a checkout root.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# IMPORTANT: only sandbox imports. No risk / execution / exchanges / telegram
# / config imports are permitted in this runner.
from app.sandbox.offline_rule_sandbox import (  # noqa: E402
    NEXT_ALLOWED_PHASE,
    PHASE_NAME,
    OfflineRuleSandboxEngine,
    OfflineRuleSandboxScenario,
    SandboxEvent,
    assert_no_forbidden_fields,
    build_input_from_reports,
    example_fixture_scenario,
    parse_scenario_dict,
    render_report_markdown,
)


def _load_json(path: Optional[str]) -> Optional[Mapping[str, Any]]:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    with p.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, Mapping):
        return None
    return data


def _load_or_generate_scenarios(
    scenario_file: Optional[str], reference_window: str
) -> List[OfflineRuleSandboxScenario]:
    if scenario_file and Path(scenario_file).is_file():
        with Path(scenario_file).open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if isinstance(payload, list):
            return [parse_scenario_dict(s) for s in payload]
        if isinstance(payload, Mapping) and "scenarios" in payload:
            return [parse_scenario_dict(s) for s in payload["scenarios"]]
        if isinstance(payload, Mapping):
            return [parse_scenario_dict(payload)]
    # Fallback: deterministic example fixture, marked as such.
    return [example_fixture_scenario(reference_window=reference_window)]


def _emit_event(events: List[Dict[str, Any]], event_type: str, **fields: Any) -> None:
    """Append a structured replay/report event. No trade-action events."""
    rec: Dict[str, Any] = {
        "event_type": event_type,
        "phase": PHASE_NAME,
        "sandbox_only": True,
        "writes_runtime_config": False,
        "auto_tuning_allowed": False,
        "trade_authority": False,
        "phase_12_forbidden": True,
    }
    rec.update(fields)
    assert_no_forbidden_fields(rec)
    events.append(rec)


def run(
    *,
    block_b_report_path: Optional[str],
    block_c_report_path: Optional[str],
    ai_checkpoint_path: Optional[str],
    scenario_file: Optional[str],
    output_dir: str,
    reference_window: str,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Execute the offline replay run. Returns the report payload dict."""
    block_b = _load_json(block_b_report_path)
    block_c = _load_json(block_c_report_path)
    ai_chk = _load_json(ai_checkpoint_path)

    scenarios = _load_or_generate_scenarios(scenario_file, reference_window)

    events: List[Dict[str, Any]] = []
    _emit_event(
        events,
        SandboxEvent.OFFLINE_RULE_SANDBOX_REPLAY_RUN,
        scenario_count=len(scenarios),
        reference_window=reference_window,
        block_b_report_present=block_b is not None,
        block_c_report_present=block_c is not None,
        ai_checkpoint_report_present=ai_chk is not None,
    )

    engine = OfflineRuleSandboxEngine()
    sandbox_inputs = [
        build_input_from_reports(
            scenario=s,
            block_b_report=block_b,
            block_c_report=block_c,
            ai_checkpoint_report=ai_chk,
        )
        for s in scenarios
    ]
    report = engine.build_report(
        reference_window=reference_window,
        sandbox_inputs=sandbox_inputs,
        now_utc=now_utc,
    )
    for r in report.scenario_results:
        _emit_event(
            events,
            SandboxEvent.OFFLINE_RULE_SANDBOX_SCENARIO_EVALUATED,
            scenario_id=r.scenario_id,
            status=r.status,
            recommendation_level=r.recommendation_level,
        )
    _emit_event(
        events,
        SandboxEvent.OFFLINE_RULE_SANDBOX_REPORT_GENERATED,
        report_id=report.report_id,
    )

    payload = report.to_dict()
    payload["events"] = events
    payload["next_allowed_phase"] = NEXT_ALLOWED_PHASE

    # Final defensive guard: refuse to serialize a payload with any
    # forbidden field name anywhere.
    assert_no_forbidden_fields(payload)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "offline_rule_sandbox_report.json"
    md_path = out_dir / "offline_rule_sandbox_report.md"
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, default=str)
        fh.write("\n")
    md_path.write_text(render_report_markdown(report), encoding="utf-8")

    return payload


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Phase 11C / Offline Rule Sandbox Replay v0 runner",
    )
    p.add_argument(
        "--block-b-report",
        default=(
            "data/reports/block_b_integrated_evidence/"
            "block_b_integrated_evidence_report.json"
        ),
    )
    p.add_argument(
        "--block-c-report",
        default=(
            "data/reports/block_c_integrated_checkpoint/"
            "block_c_integrated_checkpoint_report.json"
        ),
    )
    p.add_argument(
        "--ai-checkpoint",
        default=(
            "data/reports/ai/integrated_checkpoint/"
            "ai_integrated_checkpoint_report.json"
        ),
    )
    p.add_argument(
        "--scenario-file",
        default="data/reports/rule_sandbox/scenario.json",
    )
    p.add_argument(
        "--output-dir",
        default="data/reports/rule_sandbox",
    )
    p.add_argument(
        "--reference-window",
        default="60d",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_argparser().parse_args(argv)
    payload = run(
        block_b_report_path=args.block_b_report,
        block_c_report_path=args.block_c_report,
        ai_checkpoint_path=args.ai_checkpoint,
        scenario_file=args.scenario_file,
        output_dir=args.output_dir,
        reference_window=args.reference_window,
    )
    # Print a tiny human-readable summary line; never trade-related.
    print(
        json.dumps(
            {
                "report_id": payload.get("report_id"),
                "phase": payload.get("phase"),
                "scenario_count": len(payload.get("scenario_results", [])),
                "best_review_candidates": payload.get(
                    "best_review_candidates", []
                ),
                "rejected_scenarios": payload.get("rejected_scenarios", []),
                "next_allowed_phase": payload.get("next_allowed_phase"),
                "phase_12_forbidden": payload.get("phase_12_forbidden"),
                "writes_runtime_config": payload.get(
                    "writes_runtime_config"
                ),
                "auto_tuning_allowed": payload.get("auto_tuning_allowed"),
                "trade_authority": payload.get("trade_authority"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
