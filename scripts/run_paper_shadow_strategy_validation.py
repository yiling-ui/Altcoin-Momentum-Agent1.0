#!/usr/bin/env python3
"""Runner for Phase 11C.1D-B / Paper Shadow Strategy Validation v0.

Strictly paper-only / report-only / evidence-only. Reads historical
evidence reports (Block B integrated evidence, Block C integrated
checkpoint, Offline Rule Sandbox Replay), assembles
``PaperShadowSample`` rows, groups them into cohorts, computes
cohort-level metrics, and writes a JSON + Markdown report.

Hard safety boundary:
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
  - phase_12_forbidden = True

This script MUST NOT:
  - import app.risk / app.execution / app.exchanges / app.telegram /
    app.config
  - call any LLM / DeepSeek / Telegram / Binance private API /
    network endpoint
  - write back to runtime config
  - emit buy / sell / long / short / direction / entry / exit /
    position_size / leverage / stop / target / risk_budget
  - emit runtime_config_patch / threshold_patch / symbol_limit_patch /
    candidate_pool_patch / regime_weight_patch /
    strategy_parameter_patch
  - authorize live trading or hot-path execution
  - enter Phase 12

Usage:
  python scripts/run_paper_shadow_strategy_validation.py \\
      --block-b-report data/reports/block_b_integrated_evidence/block_b_integrated_evidence_report.json \\
      --block-c-report data/reports/block_c_integrated_checkpoint/block_c_integrated_checkpoint_report.json \\
      --rule-sandbox-report data/reports/rule_sandbox/offline_rule_sandbox_report.json \\
      --output-dir data/reports/paper_shadow_strategy_validation \\
      --reference-window 60d
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

# Make ``app`` importable when run from a checkout root.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# IMPORTANT: only paper_shadow imports. No risk / execution / exchanges /
# telegram / config imports are permitted in this runner. No LLM /
# DeepSeek / network imports are permitted either.
from app.paper_shadow.strategy_validation import (  # noqa: E402
    NEXT_ALLOWED_PHASE,
    PHASE_NAME,
    PaperShadowEvent,
    PaperShadowStrategyValidationEngine,
    assert_no_forbidden_fields,
    build_samples_from_reports,
    example_fixture_samples,
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


def _emit_event(
    events: List[Dict[str, Any]], event_type: str, **fields: Any
) -> None:
    """Append a structured report/export/replay event.

    No trade-action events are emitted. The safety flags are pinned at
    the event boundary as well so any consumer reading the events log
    sees them attached to every record.
    """
    if event_type not in PaperShadowEvent.ALLOWED:
        raise ValueError(
            f"event_type {event_type!r} is not in the allowed set "
            f"{sorted(PaperShadowEvent.ALLOWED)}"
        )
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
    rule_sandbox_report_path: Optional[str],
    output_dir: str,
    reference_window: str,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Execute the paper shadow validation run.

    Returns the report payload dict (also written to disk under
    ``output_dir``).
    """
    block_b = _load_json(block_b_report_path)
    block_c = _load_json(block_c_report_path)
    rule_sandbox = _load_json(rule_sandbox_report_path)

    samples = build_samples_from_reports(
        block_b_report=block_b,
        block_c_report=block_c,
        rule_sandbox_report=rule_sandbox,
        reference_window=reference_window,
    )

    # If no operator-supplied samples are available, fall back to a
    # deterministic example fixture. Every fixture sample is marked
    # ``source=example_fixture`` and never claims to be real paper
    # evidence.
    used_example_fixture = False
    if not samples:
        samples = example_fixture_samples(reference_window=reference_window)
        used_example_fixture = True

    events: List[Dict[str, Any]] = []
    for s in samples:
        _emit_event(
            events,
            PaperShadowEvent.PAPER_SHADOW_SAMPLE_CREATED,
            sample_id=s.sample_id,
            symbol=s.symbol,
            source=s.source,
            cohort_id=s.cohort_key.cohort_id(),
        )

    engine = PaperShadowStrategyValidationEngine()
    report = engine.build_report(
        reference_window=reference_window,
        samples=samples,
        now_utc=now_utc,
    )

    for e in report.cohort_evaluations:
        _emit_event(
            events,
            PaperShadowEvent.PAPER_SHADOW_COHORT_EVALUATED,
            cohort_id=e.cohort_id,
            sample_count=e.sample_count,
            recommendation_level=e.recommendation_level,
            confidence_bucket=e.confidence_bucket,
            quality_bucket=e.quality_bucket,
        )
    _emit_event(
        events,
        PaperShadowEvent.PAPER_SHADOW_REPORT_GENERATED,
        report_id=report.report_id,
        total_samples=report.total_samples,
        evaluated_cohort_count=report.evaluated_cohort_count,
    )

    payload = report.to_dict()
    payload["events"] = events
    payload["used_example_fixture"] = used_example_fixture
    payload["block_b_report_present"] = block_b is not None
    payload["block_c_report_present"] = block_c is not None
    payload["rule_sandbox_report_present"] = rule_sandbox is not None
    payload["next_allowed_phase"] = NEXT_ALLOWED_PHASE

    # Final defensive guard: refuse to serialize a payload with any
    # forbidden field name anywhere.
    assert_no_forbidden_fields(payload)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "paper_shadow_strategy_validation_report.json"
    md_path = out_dir / "paper_shadow_strategy_validation_report.md"
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, default=str)
        fh.write("\n")
    md_path.write_text(render_report_markdown(report), encoding="utf-8")

    return payload


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Phase 11C.1D-B / Paper Shadow Strategy Validation v0 "
            "runner"
        ),
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
        "--rule-sandbox-report",
        default=(
            "data/reports/rule_sandbox/offline_rule_sandbox_report.json"
        ),
    )
    p.add_argument(
        "--output-dir",
        default="data/reports/paper_shadow_strategy_validation",
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
        rule_sandbox_report_path=args.rule_sandbox_report,
        output_dir=args.output_dir,
        reference_window=args.reference_window,
    )
    # Print a tiny human-readable summary line; never trade-related.
    print(
        json.dumps(
            {
                "report_id": payload.get("report_id"),
                "phase": payload.get("phase"),
                "status": payload.get("status"),
                "total_samples": payload.get("total_samples"),
                "evaluated_cohort_count": payload.get(
                    "evaluated_cohort_count"
                ),
                "promising_cohorts": payload.get(
                    "promising_cohorts", []
                ),
                "risky_cohorts": payload.get("risky_cohorts", []),
                "rejected_cohorts": payload.get(
                    "rejected_cohorts", []
                ),
                "inconclusive_cohorts": payload.get(
                    "inconclusive_cohorts", []
                ),
                "review_only_cohorts": payload.get(
                    "review_only_cohorts", []
                ),
                "used_example_fixture": payload.get(
                    "used_example_fixture"
                ),
                "next_allowed_phase": payload.get("next_allowed_phase"),
                "phase_12_forbidden": payload.get("phase_12_forbidden"),
                "writes_runtime_config": payload.get(
                    "writes_runtime_config"
                ),
                "auto_tuning_allowed": payload.get(
                    "auto_tuning_allowed"
                ),
                "trade_authority": payload.get("trade_authority"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
