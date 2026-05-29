#!/usr/bin/env python3
"""Runner for Phase 11C.1D-C / Risk / Execution / Capital Safety
Matrix v0.

Strictly paper / report / evidence-only. Builds a deterministic set
of adverse-condition scenarios, evaluates each through the Safety
Matrix engine, writes a JSON + Markdown report. Never opens the
network, never modifies runtime config, never places an order, never
sends Telegram outbound, never calls DeepSeek / LLM, never imports
the real Risk Engine / Execution FSM / Exchange gateway / Telegram /
runtime config.

Hard safety boundary:
  - mode = paper
  - sandbox_only = True
  - writes_runtime_config = False
  - auto_tuning_allowed = False
  - trade_authority = False
  - live_trading = False
  - exchange_live_orders = False
  - right_tail = False
  - llm = False
  - llm_outbound_enabled = False
  - telegram_outbound_enabled = False
  - binance_private_api_enabled = False
  - allow_trade_decision = False
  - allow_runtime_config_change = False
  - phase_12_forbidden = True

This script MUST NOT:
  - import app.risk / app.execution / app.exchanges / app.telegram /
    app.config
  - call any LLM / DeepSeek / Telegram / Binance private API /
    network endpoint
  - write back to runtime config
  - emit buy / sell / long / short / direction / entry / exit /
    position_size / leverage / stop / target / risk_budget
  - emit runtime_config_patch / threshold_patch / symbol_limit_patch
    / candidate_pool_patch / regime_weight_patch /
    strategy_parameter_patch / signal_to_trade / should_buy /
    should_short / apply_change / deploy_change / enable_live /
    live_ready / trading_approved
  - authorize live trading or hot-path execution
  - enter Phase 12

Usage:
  python scripts/run_risk_execution_capital_safety_matrix.py \\
      --output-dir data/reports/safety_matrix \\
      --reference-window 60d \\
      --scenario-set default
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Make ``app`` importable when run from a checkout root.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# IMPORTANT: only safety imports. No risk / execution / exchanges /
# telegram / config imports are permitted in this runner. No LLM /
# DeepSeek / network imports are permitted either.
from app.safety.risk_execution_capital_matrix import (  # noqa: E402
    NEXT_ALLOWED_PHASE_NO_BLOCKERS,
    NEXT_ALLOWED_PHASE_WITH_BLOCKERS,
    PHASE_NAME,
    SafetyMatrixEngine,
    SafetyMatrixEvent,
    SafetyMatrixResultStatus,
    SafetyMatrixScenario,
    assert_no_forbidden_fields,
    default_scenario_set,
    render_report_markdown,
)


def _emit_event(
    events: List[Dict[str, Any]], event_type: str, **fields: Any
) -> None:
    """Append a structured report / export / audit event.

    No trade-action events are emitted. The safety flags are pinned at
    the event boundary as well so any consumer reading the events log
    sees them attached to every record.
    """
    if event_type not in SafetyMatrixEvent.ALLOWED:
        raise ValueError(
            f"event_type {event_type!r} is not in the allowed set "
            f"{sorted(SafetyMatrixEvent.ALLOWED)}"
        )
    rec: Dict[str, Any] = {
        "event_type": event_type,
        "phase": PHASE_NAME,
        "sandbox_only": True,
        "writes_runtime_config": False,
        "auto_tuning_allowed": False,
        "trade_authority": False,
        "phase_12_forbidden": True,
        "live_order_blocked": True,
        "runtime_config_unchanged": True,
        "ai_trade_authority_blocked": True,
        "telegram_outbound_blocked": True,
    }
    rec.update(fields)
    assert_no_forbidden_fields(rec)
    events.append(rec)


def _select_scenarios(scenario_set: str) -> List[SafetyMatrixScenario]:
    """Build the scenario set requested on the CLI.

    Currently only ``default`` is supported. Adding new scenario sets
    is a deliberately scoped follow-up and is NOT permitted in this
    phase.
    """
    if scenario_set != "default":
        raise ValueError(
            f"unsupported scenario_set {scenario_set!r}; "
            f"the only allowed value in Phase 11C.1D-C is 'default'"
        )
    return list(default_scenario_set())


def run(
    *,
    output_dir: str,
    reference_window: str,
    scenario_set: str = "default",
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Execute the safety matrix run.

    Returns the report payload dict (also written to disk under
    ``output_dir``).
    """
    scenarios = _select_scenarios(scenario_set)

    events: List[Dict[str, Any]] = []
    engine = SafetyMatrixEngine()
    report = engine.build_report(
        reference_window=reference_window,
        scenarios=scenarios,
        now_utc=now_utc,
    )
    for r in report.scenario_results:
        _emit_event(
            events,
            SafetyMatrixEvent.SAFETY_MATRIX_SCENARIO_EVALUATED,
            scenario_id=r.scenario_id,
            scenario_type=r.scenario_type,
            severity=r.severity,
            status=r.status,
            passed=r.passed,
            requires_operator_review=r.requires_operator_review,
            requires_operator_resume=r.requires_operator_resume,
        )
        if r.status == SafetyMatrixResultStatus.FAIL:
            _emit_event(
                events,
                SafetyMatrixEvent.SAFETY_MATRIX_BLOCKER_DETECTED,
                scenario_id=r.scenario_id,
                scenario_type=r.scenario_type,
                severity=r.severity,
                failed_reasons=list(r.failed_reasons),
            )
    _emit_event(
        events,
        SafetyMatrixEvent.SAFETY_MATRIX_REPORT_GENERATED,
        report_id=report.report_id,
        total_scenarios=report.total_scenarios,
        passed_count=report.passed_count,
        failed_count=report.failed_count,
        warning_count=report.warning_count,
        next_allowed_phase=report.next_allowed_phase,
    )

    payload = report.to_dict()
    payload["events"] = events
    payload["scenario_set"] = scenario_set

    # Final defensive guard: refuse to serialize a payload with any
    # forbidden field name anywhere.
    assert_no_forbidden_fields(payload)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = (
        out_dir / "risk_execution_capital_safety_matrix_report.json"
    )
    md_path = out_dir / "risk_execution_capital_safety_matrix_report.md"
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, default=str)
        fh.write("\n")
    md_path.write_text(render_report_markdown(report), encoding="utf-8")

    return payload


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Phase 11C.1D-C / Risk / Execution / Capital Safety "
            "Matrix v0 runner"
        ),
    )
    p.add_argument(
        "--output-dir",
        default="data/reports/safety_matrix",
    )
    p.add_argument(
        "--reference-window",
        default="60d",
    )
    p.add_argument(
        "--scenario-set",
        default="default",
        choices=("default",),
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_argparser().parse_args(argv)
    payload = run(
        output_dir=args.output_dir,
        reference_window=args.reference_window,
        scenario_set=args.scenario_set,
    )
    # Print a tiny human-readable summary line; never trade-related.
    print(
        json.dumps(
            {
                "report_id": payload.get("report_id"),
                "phase": payload.get("phase"),
                "status": payload.get("status"),
                "total_scenarios": payload.get("total_scenarios"),
                "passed_count": payload.get("passed_count"),
                "failed_count": payload.get("failed_count"),
                "warning_count": payload.get("warning_count"),
                "p0_failures": payload.get("p0_failures", []),
                "p1_failures": payload.get("p1_failures", []),
                "next_allowed_phase": payload.get("next_allowed_phase"),
                "next_allowed_phase_no_blockers": (
                    NEXT_ALLOWED_PHASE_NO_BLOCKERS
                ),
                "next_allowed_phase_with_blockers": (
                    NEXT_ALLOWED_PHASE_WITH_BLOCKERS
                ),
                "phase_12_forbidden": payload.get(
                    "phase_12_forbidden"
                ),
                "auto_tuning_allowed": payload.get(
                    "auto_tuning_allowed"
                ),
                "trade_authority": payload.get("trade_authority"),
                "exchange_live_orders": payload.get(
                    "exchange_live_orders"
                ),
                "binance_private_api_enabled": payload.get(
                    "binance_private_api_enabled"
                ),
                "telegram_outbound_enabled": payload.get(
                    "telegram_outbound_enabled"
                ),
                "writes_runtime_config": payload.get(
                    "writes_runtime_config"
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
