"""Phase AI-4 - DeepSeek Offline Sandbox runner.

Reads a frozen Phase AI-1 :class:`AIEvidenceBundle` JSON file
from disk, hands it to the
:class:`DeepSeekOfflineSandboxRunner`, and writes the resulting
:class:`AIIntelligenceOutput` to disk as JSON + Markdown.

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

The runner reads only local files under ``--bundle-path`` and
writes only files under ``--output-dir``. By default the
runner uses :class:`FakeDeepSeekProvider`; outbound is opt-in
via ``--outbound-enabled`` AND ``--enabled``. Even with both
flags set the runner refuses to invoke the
:class:`OptionalDeepSeekHTTPProvider` (which is a refusal-only
skeleton); a future PR will land the real transport behind a
separate Spec §41 Go/No-Go review.

Usage
-----

    python scripts/run_deepseek_offline_sandbox.py \
        --bundle-path data/reports/ai/evidence_bundle.json \
        --task-type MARKET_INTELLIGENCE_SUMMARY \
        --output-dir data/reports/ai/deepseek_sandbox

The runner prints a summary line to stdout and writes:

    <output-dir>/deepseek_sandbox_output.json
    <output-dir>/deepseek_sandbox_output.md

Both files re-pin the project-wide safety invariants
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
#   - app.ai.deepseek_sandbox        (Phase AI-4)
#   - app.ai.intelligence_schema     (Phase AI-4)
#
# The runner MUST NOT import:
#   - app.risk             (forbidden)
#   - app.execution        (forbidden)
#   - app.exchanges        (forbidden)
#   - app.telegram         (forbidden)
#   - app.config           (forbidden)
from app.ai.deepseek_sandbox import (  # noqa: E402
    DeepSeekOfflineSandboxRunner,
    DeepSeekSandboxConfig,
    DeepSeekSandboxInput,
    FakeDeepSeekProvider,
)
from app.ai.intelligence_schema import (  # noqa: E402
    AIIntelligenceOutput,
    AIIntelligenceTaskType,
)


# ---------------------------------------------------------------------------
# Identity / constants
# ---------------------------------------------------------------------------
SOURCE_MODULE: str = "scripts.run_deepseek_offline_sandbox"
SOURCE_PHASE: str = "phase_ai_4"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_deepseek_offline_sandbox",
        description=(
            "Phase AI-4 - DeepSeek Offline Sandbox runner. "
            "Reads a frozen Phase AI-1 evidence bundle JSON and "
            "emits one schema-checked AIIntelligenceOutput. "
            "Sandbox-only. NOT live trading. NOT Phase 12."
        ),
    )
    parser.add_argument(
        "--bundle-path",
        type=Path,
        required=True,
        help=(
            "Path to a serialised Phase AI-1 AIEvidenceBundle "
            "JSON file. The runner consumes it as a frozen "
            "input; it never builds a fresh bundle from runtime "
            "state."
        ),
    )
    parser.add_argument(
        "--task-type",
        type=str,
        default=AIIntelligenceTaskType.MARKET_INTELLIGENCE_SUMMARY.value,
        choices=[t.value for t in AIIntelligenceTaskType],
        help=(
            "Closed task-type vocabulary; default is "
            "MARKET_INTELLIGENCE_SUMMARY."
        ),
    )
    parser.add_argument(
        "--operator-instruction",
        type=str,
        default=(
            "Summarise the evidence bundle as commentary "
            "substrate for the operator. Cite every claim."
        ),
        help=(
            "Operator-supplied free-form instruction (paper / "
            "report / sandbox-only)."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/reports/ai/deepseek_sandbox"),
        help=(
            "Directory the runner writes "
            "deepseek_sandbox_output.json and "
            "deepseek_sandbox_output.md into."
        ),
    )
    parser.add_argument(
        "--enabled",
        action="store_true",
        help=(
            "Master gate; default is False. The sandbox short-"
            "circuits to a degraded result when the gate is "
            "closed."
        ),
    )
    parser.add_argument(
        "--outbound-enabled",
        action="store_true",
        help=(
            "Outbound gate; default is False. Even with the "
            "gate open the runner uses FakeDeepSeekProvider in "
            "v0; OptionalDeepSeekHTTPProvider remains a "
            "refusal-only skeleton."
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="Provider timeout in seconds; must be > 0.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=2048,
        help="Provider max-tokens budget; must be > 0.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="deepseek-chat",
        help="Provider model identifier.",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------
def _render_markdown(output: AIIntelligenceOutput) -> str:
    payload = output.to_dict()
    lines: list[str] = []
    lines.append("# DeepSeek Offline Sandbox v0 - Output Report")
    lines.append("")
    lines.append(
        "> **Status:** paper / report / sandbox-only. **NOT** "
        "live trading. **NOT** trade authority. **NOT** "
        "auto-tuning. **NOT** Phase 12."
    )
    lines.append("")
    lines.append(
        f"- **schema_version:** `{payload['schema_version']}`"
    )
    lines.append(
        f"- **source_phase:** `{payload['source_phase']}`"
    )
    lines.append(
        f"- **bundle_id:** `{payload['bundle_id']}`"
    )
    lines.append(
        f"- **task_type:** `{payload['task_type']}`"
    )
    lines.append(
        f"- **status:** `{payload['status']}`"
    )
    lines.append(
        f"- **authority_level:** `{payload['authority_level']}`"
    )
    lines.append(
        f"- **reality_check_status:** "
        f"`{payload['reality_check_status']}`"
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(payload["summary"])
    lines.append("")
    lines.append("## Claims")
    lines.append("")
    if not payload["claims"]:
        lines.append("_No claims emitted._")
    for claim in payload["claims"]:
        lines.append(f"- **{claim['claim_id']}** ")
        lines.append(f"  - claim_type: `{claim['claim_type']}`")
        lines.append(
            f"  - citation_authority_level: "
            f"`{claim['citation_authority_level']}`"
        )
        lines.append(
            f"  - reality_check_status: "
            f"`{claim['reality_check_status']}`"
        )
        lines.append(
            f"  - reality_check_authority_level: "
            f"`{claim['reality_check_authority_level']}`"
        )
        lines.append(
            f"  - evidence_refs: "
            f"`{', '.join(claim['evidence_refs'])}`"
        )
        lines.append(f"  - claim_text: {claim['claim_text']}")
    lines.append("")
    lines.append("## Audit")
    lines.append("")
    lines.append(
        f"- **forbidden_fields_stripped:** "
        f"`{len(payload['forbidden_fields_stripped'])}` "
        f"(paths: {payload['forbidden_fields_stripped']})"
    )
    lines.append(
        f"- **redacted_secret_count:** "
        f"`{payload['redacted_secret_count']}`"
    )
    lines.append(
        f"- **degraded_reasons:** "
        f"`{payload['degraded_reasons']}`"
    )
    lines.append(
        f"- **warnings:** `{payload['warnings']}`"
    )
    lines.append("")
    lines.append("## Safety boundary (held end-to-end)")
    lines.append("")
    safety = payload["safety_flags"]
    for key, value in safety.items():
        lines.append(f"- `{key}` = `{value}`")
    lines.append(
        f"- `trade_authority` = `{payload['trade_authority']}`"
    )
    lines.append(
        f"- `auto_tuning_allowed` = "
        f"`{payload['auto_tuning_allowed']}`"
    )
    lines.append(
        f"- `phase_12_forbidden` = "
        f"`{payload['phase_12_forbidden']}`"
    )
    lines.append("")
    lines.append(
        "The Risk Engine remains the single trade-decision "
        "gate."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    bundle_path: Path = args.bundle_path
    if not bundle_path.exists():
        print(
            f"ERROR: bundle path does not exist: {bundle_path}",
            file=sys.stderr,
        )
        return 2
    try:
        bundle_payload = json.loads(
            bundle_path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        print(
            f"ERROR: bundle JSON is not parseable: {exc}",
            file=sys.stderr,
        )
        return 2

    if not isinstance(bundle_payload, dict):
        print(
            "ERROR: bundle JSON must be a JSON object at the "
            "top level.",
            file=sys.stderr,
        )
        return 2

    task_type = AIIntelligenceTaskType(args.task_type)

    config = DeepSeekSandboxConfig(
        enabled=bool(args.enabled),
        outbound_enabled=bool(args.outbound_enabled),
        timeout_seconds=float(args.timeout_seconds),
        max_tokens=int(args.max_tokens),
        model=str(args.model),
    )

    sandbox_input = DeepSeekSandboxInput(
        evidence_bundle=bundle_payload,
        task_type=task_type,
        operator_instruction=str(args.operator_instruction),
        allowed_output_schema={},
    )

    # Default to the deterministic in-memory provider; even
    # when ``outbound_enabled=True`` v0 uses the fake provider
    # because the OptionalDeepSeekHTTPProvider skeleton
    # refuses to actually reach the network.
    provider = FakeDeepSeekProvider(
        payload={
            "summary": (
                "Offline sandbox echo. The runner consumed the "
                "frozen evidence bundle and produced commentary "
                "substrate only; no trade authority was granted, "
                "no runtime knob was changed, no live network "
                "call was made."
            ),
            "claims": [],
            "contradictions": [],
            "unsupported_claims": [],
            "risk_tags": [],
        }
    )

    runner = DeepSeekOfflineSandboxRunner(
        config=config,
        provider=provider,
    )
    output = runner.run(sandbox_input)

    # Persist the result.
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = output.to_dict()
    payload["generated_at_utc"] = (
        datetime.now(tz=timezone.utc).isoformat()
    )
    payload["source_module"] = SOURCE_MODULE
    json_path = output_dir / "deepseek_sandbox_output.json"
    md_path = output_dir / "deepseek_sandbox_output.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=False),
        encoding="utf-8",
    )
    md_path.write_text(_render_markdown(output), encoding="utf-8")

    summary_line = (
        "DeepSeek Offline Sandbox v0 run complete: "
        f"status={output.status.value} "
        f"authority_level={output.authority_level.value} "
        f"reality_check_status={output.reality_check_status} "
        f"forbidden_fields_stripped={len(output.forbidden_fields_stripped)} "
        f"redacted_secret_count={output.redacted_secret_count} "
        f"output_json={json_path} "
        f"output_md={md_path}"
    )
    print(summary_line)
    # The runner is paper / report / sandbox-only. A degraded
    # result is still a successful run from the script's POV;
    # we exit 0 unless the input was malformed.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
