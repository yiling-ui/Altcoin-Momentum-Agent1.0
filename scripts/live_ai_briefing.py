"""Live AI briefing CLI (PR115 - DeepSeek Live Intelligence v0).

Generates / inspects live-safe DeepSeek operator briefings. The AI is
MARKET_INTELLIGENCE_ONLY: it summarises live-approved evidence, compresses
it, explains live risk, and can be pushed to Telegram - but it has NO
trade authority.

USAGE
-----

    python scripts/live_ai_briefing.py --status-json
    python scripts/live_ai_briefing.py --brief --json
    python scripts/live_ai_briefing.py --brief --dry-run
    python scripts/live_ai_briefing.py --validate-output sample.json

SAFETY (enforced by this CLI)
-----------------------------

  1. It NEVER submits / cancels / modifies an order.
  2. It NEVER switches runtime mode or changes the capital profile.
  3. It NEVER calls the execution gateway.
  4. It NEVER uses blind / replay / sim evidence (LIVE_ONLY scope).
  5. Secrets are always masked / redacted; no key / token is printed.
  6. If the DeepSeek key is missing / disabled it returns
     MISSING_SECRET / DISABLED - it never crashes.

EXIT CODES
----------

  0 = OK
  1 = WARN (disabled / missing secret / insufficient evidence / rejected)
  2 = FAIL (could not read / parse a --validate-output file)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.exports.redaction import redact  # noqa: E402
from app.live.ai_live_briefing import LiveAIBriefingGenerator  # noqa: E402
from app.live.ai_live_evidence import build_live_ai_evidence_bundle  # noqa: E402
from app.live.ai_output_guard import BriefingStatus, sanitize_ai_output  # noqa: E402
from app.live.api_config import LiveApiConfig  # noqa: E402
from app.live.telegram_state import LiveOperatorStateStore  # noqa: E402

# Statuses that map to a WARN (non-zero) exit.
_WARN_STATUSES = frozenset(
    {
        BriefingStatus.DISABLED,
        BriefingStatus.MISSING_SECRET,
        BriefingStatus.ERROR,
        BriefingStatus.INSUFFICIENT_EVIDENCE,
        BriefingStatus.REJECTED_FOR_TRADE_AUTHORITY,
    }
)

# The Phase 8.5 redactor masks any key whose name contains a sensitive
# substring (e.g. ``auth`` in ``ai_trade_authority``). These constant
# safety markers must stay VISIBLE so the operator can actually SEE that
# the unsafe flags are False; they are re-stamped AFTER redaction. The
# values are fixed booleans / labels, never credentials.
_VISIBLE_SAFETY_MARKERS = {
    "ai_trade_authority": False,
    "trade_authority": False,
    "exchange_live_orders": False,
    "live_trading": False,
    "authority": "MARKET_INTELLIGENCE_ONLY",
    "source_scope": "LIVE_ONLY",
    "phase_12_forbidden": True,
}


def _safe_visible(report: dict) -> dict:
    """Redact dynamic content, then re-stamp the visible safety markers."""
    safe = redact(report)
    for key, value in _VISIBLE_SAFETY_MARKERS.items():
        if key in report:
            safe[key] = value
    return safe


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="live_ai_briefing",
        description=(
            "AMA-RT PR115 live AI briefing. MARKET_INTELLIGENCE_ONLY; the AI "
            "has no trade authority and uses LIVE-only evidence."
        ),
    )
    parser.add_argument(
        "--status-json",
        action="store_true",
        help="Print the redacted AI/DeepSeek status snapshot and exit.",
    )
    parser.add_argument(
        "--brief",
        action="store_true",
        help="Generate a live-safe operator briefing.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the briefing locally (no DeepSeek call / no network).",
    )
    parser.add_argument(
        "--validate-output",
        default=None,
        metavar="FILE",
        help="Validate a sample AI output JSON file against the output guard.",
    )
    parser.add_argument(
        "--state-dir",
        default=None,
        help="Override the live-state directory (default data/live_state).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    return parser


def _build_generator(config: LiveApiConfig) -> LiveAIBriefingGenerator:
    return LiveAIBriefingGenerator(config.deepseek)


def _build_evidence_result(config: LiveApiConfig, state_dir: str | None):
    """Build a LIVE-only evidence bundle from locally available state.

    The CLI performs NO network read; it compresses the runtime mode +
    capital profile + persisted telegram operator state. Account / PnL /
    positions are left empty (surfaced as missing evidence).
    """
    store = LiveOperatorStateStore(state_dir) if state_dir else LiveOperatorStateStore()
    state = store.load()
    telegram_state = {
        "runtime_mode": state.runtime.runtime_mode.value,
        "live_limited_armed": state.runtime.live_limited_armed,
        "paused": state.runtime.paused,
        "kill_switch_armed": state.kill_switch.armed,
        "capital_profile_id": state.capital_profile.capital_profile_id.value,
    }
    return build_live_ai_evidence_bundle(
        runtime_mode=state.runtime.runtime_mode,
        capital_profile_id=state.capital_profile.capital_profile_id.value,
        telegram_state=telegram_state,
        sources=["LIVE", "TELEGRAM_OPERATOR", "CAPITAL_PROFILE"],
    )


def build_status_report(config: LiveApiConfig) -> dict:
    """Build the redacted AI status report (also used by --status-json)."""
    generator = _build_generator(config)
    snapshot = generator.status()
    return _safe_visible(snapshot)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    config = LiveApiConfig.from_env()
    exit_code = 0

    # --validate-output FILE.
    if args.validate_output:
        path = Path(args.validate_output)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("sample output must be a JSON object")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            out = {"error": f"could_not_read_sample:{str(exc)[:120]}", "ai_trade_authority": False}
            print(json.dumps(redact(out), indent=2, sort_keys=True))
            return 2
        guard = sanitize_ai_output(raw)
        report = _safe_visible(guard.to_dict())
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1 if guard.had_forbidden_fields else 0

    # --status-json.
    if args.status_json:
        report = build_status_report(config)
        print(json.dumps(report, indent=2, sort_keys=True))
        if not report.get("deepseek_enabled") or not report.get("deepseek_key_present"):
            exit_code = 1
        return exit_code

    # --brief.
    if args.brief:
        generator = _build_generator(config)
        ev = _build_evidence_result(config, args.state_dir)
        if not ev.accepted or ev.bundle is None:
            out = {
                "error": "non_live_evidence_rejected",
                "forbidden_sources_detected": list(ev.forbidden_sources_detected),
                "ai_trade_authority": False,
                "source_scope": "LIVE_ONLY",
            }
            print(json.dumps(_safe_visible(out), indent=2, sort_keys=True))
            return 1
        briefing = generator.generate(ev.bundle, dry_run=bool(args.dry_run))
        report = _safe_visible(briefing.to_dict())
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(
                f"[AI Briefing / MARKET_INTELLIGENCE_ONLY] status={briefing.status} "
                f"evidence_quality={briefing.evidence_quality} "
                f"ai_trade_authority=False source_scope=LIVE_ONLY"
            )
            if briefing.operator_notes:
                print(f"operator_notes: {briefing.operator_notes}")
        if briefing.status in _WARN_STATUSES:
            exit_code = 1
        return exit_code

    # Default: print the status snapshot.
    report = build_status_report(config)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
