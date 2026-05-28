"""Phase AI-5 - AI Operator Briefing / Evidence Compression runner.

Reads a frozen Phase AI-1 :class:`AIEvidenceBundle` JSON, a
serialised Phase AI-4 :class:`AIIntelligenceOutput` JSON, and an
optional Block C Integrated Checkpoint report JSON from disk;
hands them to the
:class:`OperatorBriefingBuilder`; and writes the resulting
operator briefing AND the underlying evidence compression
report to disk as JSON + Markdown.

Boundary
========

The runner is paper / report / sandbox-only. It MUST NOT and
DOES NOT:

  - place an order;
  - close a position;
  - change leverage / position size / stop / target;
  - override the Risk Engine;
  - override the Execution FSM;
  - alter runtime configuration (``symbol_limit`` / candidate-
    pool capacity / anomaly thresholds / Regime weights /
    strategy parameters);
  - send a real Telegram outbound message;
  - import :mod:`app.risk`, :mod:`app.execution`,
    :mod:`app.exchanges`, :mod:`app.telegram`, or
    :mod:`app.config`;
  - import :mod:`openai` / :mod:`anthropic` / :mod:`deepseek`
    / :mod:`httpx` / :mod:`requests` / :mod:`aiohttp` /
    :mod:`urllib3` / :mod:`websocket` / :mod:`websockets` /
    :mod:`grpc` / :mod:`boto3` / :mod:`socket`;
  - read or carry an API secret in any logged / exported /
    serialised payload;
  - emit a forbidden trade-action / runtime-config-patch
    field;
  - open Phase 12.

The runner reads only local files under the supplied
``--evidence-bundle`` / ``--sandbox-output`` /
``--block-c-report`` paths and writes only files under
``--output-dir``. The runner uses the offline Phase AI-5
:class:`OperatorBriefingBuilder`; it never opens a network
socket and never calls DeepSeek.

Usage
-----

    python scripts/run_ai_operator_briefing.py \
        --evidence-bundle path/to/bundle.json \
        --sandbox-output path/to/deepseek_sandbox_output.json \
        --block-c-report \
            data/reports/block_c_integrated_checkpoint/\
            block_c_integrated_checkpoint_report.json \
        --output-dir data/reports/ai/operator_briefing \
        --reference-window 60d

The runner prints a summary line to stdout and writes:

    <output-dir>/operator_briefing.json
    <output-dir>/operator_briefing.md
    <output-dir>/evidence_compression_report.json
    <output-dir>/evidence_compression_report.md

All four files re-pin the project-wide safety invariants
(``mode=paper``, ``live_trading=False``,
``exchange_live_orders=False``, ``llm=False``,
``llm_outbound_enabled=False``, ``sandbox_only=True``,
``trade_authority=False``, ``auto_tuning_allowed=False``,
``phase_12_forbidden=True``).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add project root to path so the runner can be invoked as a script.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Imports from allowed packages only:
#   - app.ai.operator_briefing    (Phase AI-5)
#   - app.ai.evidence_compression (Phase AI-5)
#
# The runner MUST NOT import:
#   - app.risk             (forbidden)
#   - app.execution        (forbidden)
#   - app.exchanges        (forbidden)
#   - app.telegram         (forbidden)
#   - app.config           (forbidden)
from app.ai.evidence_compression import (  # noqa: E402
    render_evidence_compression_report_markdown,
)
from app.ai.operator_briefing import (  # noqa: E402
    OperatorBriefingBuilder,
    render_operator_briefing_markdown,
)


# ---------------------------------------------------------------------------
# Identity / constants
# ---------------------------------------------------------------------------
SOURCE_MODULE: str = "scripts.run_ai_operator_briefing"
SOURCE_PHASE: str = "phase_ai_5"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_ai_operator_briefing",
        description=(
            "Phase AI-5 - AI Operator Briefing / Evidence "
            "Compression runner. Reads a frozen Phase AI-1 "
            "evidence bundle JSON, a Phase AI-4 sandbox output "
            "JSON, and an optional Block C Integrated "
            "Checkpoint report JSON; emits one operator "
            "briefing and one evidence compression report. "
            "Sandbox-only. NOT live trading. NOT trade "
            "authority. NOT auto-tuning. NOT Phase 12."
        ),
    )
    parser.add_argument(
        "--evidence-bundle",
        type=Path,
        required=True,
        help=(
            "Path to a serialised Phase AI-1 AIEvidenceBundle "
            "JSON file. The runner consumes it as a frozen "
            "input."
        ),
    )
    parser.add_argument(
        "--sandbox-output",
        type=Path,
        required=True,
        help=(
            "Path to a serialised Phase AI-4 "
            "AIIntelligenceOutput JSON file (or any "
            "structurally compatible offline / fake "
            "intelligence payload)."
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
            "Path to the Block C Integrated Checkpoint report "
            "JSON file. Optional: when missing the runner "
            "still emits a briefing without the Block C "
            "interpretation."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/reports/ai/operator_briefing"),
        help=(
            "Directory the runner writes operator_briefing."
            "json / .md and evidence_compression_report.json "
            "/ .md into."
        ),
    )
    parser.add_argument(
        "--reference-window",
        type=str,
        default="60d",
        help=(
            "Reference window label surfaced in the briefing. "
            "Defaults to 60d."
        ),
    )
    parser.add_argument(
        "--briefing-id",
        type=str,
        default=None,
        help=(
            "Optional deterministic briefing id. When omitted "
            "the runner constructs one from the evidence "
            "bundle id and the current UTC timestamp."
        ),
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------
def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"path does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"path is not valid JSON: {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(
            f"path JSON must be an object at the top level: {path}"
        )
    return payload


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # Load evidence bundle.
    try:
        bundle_payload = _read_json(args.evidence_bundle)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: evidence bundle: {exc}", file=sys.stderr)
        return 2

    # Load AI-4 sandbox output.
    try:
        ai_output_payload = _read_json(args.sandbox_output)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: sandbox output: {exc}", file=sys.stderr)
        return 2

    # Load Block C report (optional).
    block_c_payload: dict[str, Any] | None
    if args.block_c_report and args.block_c_report.exists():
        try:
            block_c_payload = _read_json(args.block_c_report)
        except (FileNotFoundError, ValueError) as exc:
            print(
                f"WARNING: block_c report unreadable: {exc}; "
                "continuing without it.",
                file=sys.stderr,
            )
            block_c_payload = None
    else:
        block_c_payload = None

    # Construct deterministic briefing identifier when missing.
    bundle_id = str(bundle_payload.get("bundle_id", "<unknown>"))
    created_at = datetime.now(tz=timezone.utc).isoformat()
    briefing_id = (
        str(args.briefing_id).strip()
        if args.briefing_id
        else f"operator_briefing:{bundle_id}:{created_at}"
    )

    builder = OperatorBriefingBuilder()
    source_paths: list[str] = [
        f"file:{args.evidence_bundle}",
        f"file:{args.sandbox_output}",
    ]
    if block_c_payload is not None:
        source_paths.append(f"file:{args.block_c_report}")

    briefing, compression = builder.build(
        briefing_id=briefing_id,
        created_at_utc=created_at,
        evidence_bundle=bundle_payload,
        ai_intelligence_output=ai_output_payload,
        block_c_report=block_c_payload,
        reference_window=str(args.reference_window),
        source_report_paths=source_paths,
    )

    # Persist the result.
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    briefing_payload = briefing.to_dict()
    briefing_payload["generated_at_utc"] = created_at
    briefing_payload["source_module"] = SOURCE_MODULE
    briefing_json_path = output_dir / "operator_briefing.json"
    briefing_md_path = output_dir / "operator_briefing.md"
    briefing_json_path.write_text(
        json.dumps(briefing_payload, indent=2, sort_keys=False),
        encoding="utf-8",
    )
    briefing_md_path.write_text(
        render_operator_briefing_markdown(briefing),
        encoding="utf-8",
    )

    compression_payload = compression.to_dict()
    compression_payload["generated_at_utc"] = created_at
    compression_payload["source_module"] = SOURCE_MODULE
    compression_json_path = (
        output_dir / "evidence_compression_report.json"
    )
    compression_md_path = (
        output_dir / "evidence_compression_report.md"
    )
    compression_json_path.write_text(
        json.dumps(compression_payload, indent=2, sort_keys=False),
        encoding="utf-8",
    )
    compression_md_path.write_text(
        render_evidence_compression_report_markdown(compression),
        encoding="utf-8",
    )

    summary_line = (
        "AI Operator Briefing v0 run complete: "
        f"briefing_id={briefing.briefing_id} "
        f"authority_level={briefing.authority_level.value} "
        f"supported_claims={len(briefing.key_findings)} "
        f"unsupported_claims={len(briefing.unsupported_claims)} "
        f"contradictions={len(briefing.contradictions)} "
        f"data_gaps={len(briefing.data_gaps)} "
        f"operator_review_items={len(briefing.operator_review_items)} "
        f"forbidden_fields_stripped={len(briefing.forbidden_fields_stripped)} "
        f"redacted_secret_count={briefing.redacted_secret_count} "
        f"briefing_json={briefing_json_path} "
        f"briefing_md={briefing_md_path} "
        f"compression_json={compression_json_path} "
        f"compression_md={compression_md_path}"
    )
    print(summary_line)
    # Paper / report / sandbox-only: a degraded result is
    # still a successful run from the script's POV.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
