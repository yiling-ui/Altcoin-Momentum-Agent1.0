"""Unit tests for Phase 11C.1D-D-F / PR99 / Telegram Sandbox Outbox
v0.

These tests are the safety contract for this PR. If any of them
fails the module is not safe to merge.

Hard safety boundary covered by these tests:

  - mode = paper
  - sandbox_only = True
  - simulated_only = True
  - no_live_order = True
  - no_live_order_assertion = True
  - no_real_capital_assertion = True
  - no_telegram_command_authority = True
  - live_trading = False
  - live_capital_enabled = False
  - exchange_live_orders = False
  - binance_private_api_enabled = False
  - signed_endpoint_reachable = False
  - private_websocket_reachable = False
  - account_endpoint_reachable = False
  - order_endpoint_reachable = False
  - position_endpoint_reachable = False
  - leverage_endpoint_reachable = False
  - margin_endpoint_reachable = False
  - real_exchange_order_path = False
  - real_capital = False
  - telegram_outbound_enabled = False
  - telegram_live_command_authority = False
  - telegram_production_channel_enabled = False
  - ai_trade_authority = False
  - trade_authority = False
  - auto_tuning_allowed = False
  - phase_12_forbidden = True

The tests also assert that the new module:

  - does NOT import app.risk / app.execution / app.exchanges /
    app.telegram / app.config
  - does NOT pull any DeepSeek / LLM / Telegram / Binance / network
    transport
  - emits no forbidden trade / runtime-config / live-ready field
  - emits no Telegram bot token / production channel id / api key /
    api secret / real account id / real exchange order id /
    signed-endpoint reference
  - is deterministic
"""

from __future__ import annotations

import ast
import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Mapping

import pytest

from app.sim import (
    FORBIDDEN_OUTPUT_FIELDS,
    NO_LIVE_ORDER_LABEL,
    NO_REAL_CAPITAL_LABEL,
    NO_TELEGRAM_COMMAND_AUTHORITY_LABEL,
    SIMULATED_HISTORICAL_BLIND_TEST_LABEL,
    TELEGRAM_SANDBOX_MANDATORY_LABELS,
    TELEGRAM_SANDBOX_OUTBOX_PHASE_NAME,
    TelegramSandboxMessage,
    TelegramSandboxMessageType,
    TelegramSandboxOutbox,
    TelegramSandboxOutboxConfig,
    TelegramSandboxSeverity,
    assert_no_forbidden_fields,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _walk_keys(payload: Any):
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(payload, (list, tuple)):
        for v in payload:
            yield from _walk_keys(v)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _collect_imported_modules(source_text: str):
    tree = ast.parse(source_text)
    mods: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
    return mods


def _collect_code_identifiers(source_text: str):
    tree = ast.parse(source_text)
    out: set = set()

    def attr_chain(n):
        parts: List[str] = []
        while isinstance(n, ast.Attribute):
            parts.append(n.attr)
            n = n.value
        if isinstance(n, ast.Name):
            parts.append(n.id)
            return ".".join(reversed(parts))
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            chain = attr_chain(node)
            if chain:
                out.add(chain)
    return out


def _make_message(
    *,
    message_id: str = "tg_sandbox_msg_00000001",
    timestamp_simulated: datetime = None,
    message_type: str = TelegramSandboxMessageType.SIMULATED_ENTRY_ALERT,
    title: str = "Simulated entry alert",
    body: str = "Simulated paper entry on BTCUSDT (paper-only).",
    severity: str = TelegramSandboxSeverity.INFO,
    symbol: str = "BTCUSDT",
    evidence_refs=("ev:replay#1", "ev:fill#1"),
) -> TelegramSandboxMessage:
    if timestamp_simulated is None:
        timestamp_simulated = _T0
    return TelegramSandboxMessage(
        message_id=message_id,
        timestamp_simulated=timestamp_simulated,
        message_type=message_type,
        title=title,
        body=body,
        severity=severity,
        symbol=symbol,
        evidence_refs=evidence_refs,
    )


def _make_outbox(tmp_path: Path, **cfg_kwargs) -> TelegramSandboxOutbox:
    cfg_kwargs.setdefault(
        "output_jsonl_path",
        str(tmp_path / "telegram_sandbox_outbox.jsonl"),
    )
    cfg_kwargs.setdefault(
        "output_markdown_path",
        str(tmp_path / "telegram_sandbox_messages.md"),
    )
    return TelegramSandboxOutbox(
        config=TelegramSandboxOutboxConfig(**cfg_kwargs)
    )


# ---------------------------------------------------------------------------
# 1. builds sandbox message with required assertions
# ---------------------------------------------------------------------------


def test_builds_sandbox_message_with_required_assertions():
    msg = _make_message()
    assert isinstance(msg, TelegramSandboxMessage)
    assert msg.message_id == "tg_sandbox_msg_00000001"
    assert msg.timestamp_simulated == _T0
    assert (
        msg.message_type
        == TelegramSandboxMessageType.SIMULATED_ENTRY_ALERT
    )
    assert msg.severity == TelegramSandboxSeverity.INFO
    assert msg.symbol == "BTCUSDT"
    assert msg.title == "Simulated entry alert"
    assert msg.body
    assert msg.evidence_refs == ("ev:replay#1", "ev:fill#1")
    # Hard-pinned safety markers are present and correct.
    assert msg.sandbox_only is True
    assert msg.no_live_order_assertion is True
    assert msg.no_real_capital_assertion is True
    assert msg.no_telegram_command_authority is True
    assert msg.phase_12_forbidden is True
    assert msg.trade_authority is False
    assert msg.auto_tuning_allowed is False
    # Construction refuses any attempt to flip the safety flags.
    with pytest.raises(ValueError):
        TelegramSandboxMessage(
            message_id="x",
            timestamp_simulated=_T0,
            message_type=TelegramSandboxMessageType.SIMULATED_ENTRY_ALERT,
            title="t",
            body="b",
            sandbox_only=False,
        )
    with pytest.raises(ValueError):
        TelegramSandboxMessage(
            message_id="x",
            timestamp_simulated=_T0,
            message_type=TelegramSandboxMessageType.SIMULATED_ENTRY_ALERT,
            title="t",
            body="b",
            no_live_order_assertion=False,
        )
    with pytest.raises(ValueError):
        TelegramSandboxMessage(
            message_id="x",
            timestamp_simulated=_T0,
            message_type=TelegramSandboxMessageType.SIMULATED_ENTRY_ALERT,
            title="t",
            body="b",
            no_real_capital_assertion=False,
        )
    with pytest.raises(ValueError):
        TelegramSandboxMessage(
            message_id="x",
            timestamp_simulated=_T0,
            message_type=TelegramSandboxMessageType.SIMULATED_ENTRY_ALERT,
            title="t",
            body="b",
            no_telegram_command_authority=False,
        )
    with pytest.raises(ValueError):
        TelegramSandboxMessage(
            message_id="x",
            timestamp_simulated=_T0,
            message_type=TelegramSandboxMessageType.SIMULATED_ENTRY_ALERT,
            title="t",
            body="b",
            trade_authority=True,
        )
    with pytest.raises(ValueError):
        TelegramSandboxMessage(
            message_id="x",
            timestamp_simulated=_T0,
            message_type=TelegramSandboxMessageType.SIMULATED_ENTRY_ALERT,
            title="t",
            body="b",
            auto_tuning_allowed=True,
        )
    with pytest.raises(ValueError):
        TelegramSandboxMessage(
            message_id="x",
            timestamp_simulated=_T0,
            message_type=TelegramSandboxMessageType.SIMULATED_ENTRY_ALERT,
            title="t",
            body="b",
            phase_12_forbidden=False,
        )
    # Unknown message_type / severity are refused.
    with pytest.raises(ValueError):
        TelegramSandboxMessage(
            message_id="x",
            timestamp_simulated=_T0,
            message_type="MARS_LANDED",
            title="t",
            body="b",
        )
    with pytest.raises(ValueError):
        TelegramSandboxMessage(
            message_id="x",
            timestamp_simulated=_T0,
            message_type=TelegramSandboxMessageType.SIMULATED_ENTRY_ALERT,
            title="t",
            body="b",
            severity="JACKPOT",
        )
    # Naive timestamp is rejected (PR94 ensure_utc_aware).
    with pytest.raises(ValueError):
        TelegramSandboxMessage(
            message_id="x",
            timestamp_simulated=datetime(2026, 1, 1, 12, 0, 0),
            message_type=TelegramSandboxMessageType.SIMULATED_ENTRY_ALERT,
            title="t",
            body="b",
        )


# ---------------------------------------------------------------------------
# 2. rendered message contains all four mandatory labels
# ---------------------------------------------------------------------------


def test_rendered_message_contains_all_four_mandatory_labels(tmp_path):
    outbox = _make_outbox(tmp_path)
    msg = _make_message()
    rendered = outbox.render_message(msg)
    assert SIMULATED_HISTORICAL_BLIND_TEST_LABEL in rendered
    assert NO_LIVE_ORDER_LABEL in rendered
    assert NO_REAL_CAPITAL_LABEL in rendered
    assert NO_TELEGRAM_COMMAND_AUTHORITY_LABEL in rendered
    for lbl in TELEGRAM_SANDBOX_MANDATORY_LABELS:
        assert lbl in rendered
    # Defensive: every mandatory label appears at least once on its
    # own line (so a reviewer cannot miss it).
    for lbl in TELEGRAM_SANDBOX_MANDATORY_LABELS:
        assert any(
            line.strip() == lbl for line in rendered.splitlines()
        ), f"label {lbl!r} not rendered on its own line"


# ---------------------------------------------------------------------------
# 3. append_message writes JSONL to temp file
# ---------------------------------------------------------------------------


def test_append_message_writes_jsonl_to_temp_file(tmp_path):
    outbox = _make_outbox(tmp_path)
    msg1 = _make_message(
        message_id="tg_sandbox_msg_00000001",
        message_type=TelegramSandboxMessageType.SIMULATED_ENTRY_ALERT,
    )
    msg2 = _make_message(
        message_id="tg_sandbox_msg_00000002",
        message_type=TelegramSandboxMessageType.SIMULATED_EXIT_ALERT,
        timestamp_simulated=_T0 + timedelta(minutes=5),
        body="Simulated paper exit on BTCUSDT (paper-only).",
        title="Simulated exit alert",
    )
    outbox.append_message(msg1)
    outbox.append_message(msg2)
    written = outbox.write_jsonl()
    p = Path(written)
    assert p.exists()
    # Real data/reports/ MUST NOT be touched.
    assert "data/reports" not in str(p) or str(p).startswith(str(tmp_path))
    text = p.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert len(lines) == 2
    parsed = [json.loads(ln) for ln in lines]
    assert parsed[0]["message_id"] == "tg_sandbox_msg_00000001"
    assert parsed[1]["message_id"] == "tg_sandbox_msg_00000002"
    for d in parsed:
        assert d["sandbox_only"] is True
        assert d["telegram_outbound_enabled"] is False
        assert d["telegram_live_command_authority"] is False
        assert d["telegram_production_channel_enabled"] is False
        assert d["phase_12_forbidden"] is True
        assert d["auto_tuning_allowed"] is False
        assert d["trade_authority"] is False


# ---------------------------------------------------------------------------
# 4. markdown transcript generated to temp file
# ---------------------------------------------------------------------------


def test_markdown_transcript_generated_to_temp_file(tmp_path):
    outbox = _make_outbox(tmp_path)
    outbox.append_message(_make_message())
    outbox.append_message(
        _make_message(
            message_id="tg_sandbox_msg_00000002",
            message_type=TelegramSandboxMessageType.RISK_REJECTION,
            severity=TelegramSandboxSeverity.WARNING,
            title="Simulated risk rejection",
            body=(
                "Simulated paper risk rejection on ETHUSDT "
                "(paper-only review)."
            ),
            symbol="ETHUSDT",
            evidence_refs=("ev:risk_decision#1",),
        )
    )
    written = outbox.write_markdown_transcript()
    p = Path(written)
    assert p.exists()
    md = p.read_text(encoding="utf-8")
    # Header markers.
    assert "Telegram Sandbox Transcript" in md
    assert "Phase 11C.1D-D-F / PR99" in md
    # All four mandatory labels appear in the transcript (header
    # AND every per-message section). Each must appear at least
    # once for every appended message + once in the header.
    expected_label_count = 1 + len(outbox.list_messages())
    for lbl in TELEGRAM_SANDBOX_MANDATORY_LABELS:
        count = md.count(lbl)
        assert count >= expected_label_count, (
            f"label {lbl!r} appeared {count} times, expected "
            f">= {expected_label_count}"
        )
    # Tripwire markers in the header.
    assert "telegram_outbound_enabled" in md
    assert "telegram_live_command_authority" in md
    assert "telegram_production_channel_enabled" in md
    assert "phase_12_forbidden" in md
    # No forbidden field NAMES appear as JSON-style keys in the
    # markdown.
    for forbidden in FORBIDDEN_OUTPUT_FIELDS:
        assert f'"{forbidden}"' not in md
    # No Telegram-bot-token / production-channel-id field names
    # appear at all.
    for forbidden in (
        "telegram_bot_token",
        "bot_token",
        "production_channel_id",
        "live_channel_id",
        "api_key",
        "api_secret",
        "real_order_id",
        "exchange_order_id",
        "real_account_id",
    ):
        assert forbidden not in md, (
            f"forbidden token-like field {forbidden!r} present in "
            f"markdown transcript"
        )


# ---------------------------------------------------------------------------
# 5. evidence_refs preserved
# ---------------------------------------------------------------------------


def test_evidence_refs_preserved(tmp_path):
    outbox = _make_outbox(tmp_path)
    msg = _make_message(
        evidence_refs=("ev:replay#42", "ev:fill#7", "ev:capital_state#1"),
    )
    outbox.append_message(msg)
    # In-memory list keeps refs.
    listed = outbox.list_messages()
    assert listed[0].evidence_refs == (
        "ev:replay#42",
        "ev:fill#7",
        "ev:capital_state#1",
    )
    # JSONL preserves refs.
    written = outbox.write_jsonl()
    parsed = json.loads(Path(written).read_text(encoding="utf-8").strip())
    assert parsed["evidence_refs"] == [
        "ev:replay#42",
        "ev:fill#7",
        "ev:capital_state#1",
    ]
    # Markdown transcript preserves refs.
    md_path = outbox.write_markdown_transcript()
    md = Path(md_path).read_text(encoding="utf-8")
    for ref in ("ev:replay#42", "ev:fill#7", "ev:capital_state#1"):
        assert ref in md
    # Disabling include_evidence_refs strips them from JSONL but the
    # in-memory message is unchanged.
    outbox2 = _make_outbox(tmp_path, include_evidence_refs=False)
    outbox2.append_message(msg)
    written2 = outbox2.write_jsonl(
        path=str(tmp_path / "no_refs.jsonl")
    )
    parsed2 = json.loads(
        Path(written2).read_text(encoding="utf-8").strip()
    )
    assert parsed2["evidence_refs"] == []
    assert outbox2.list_messages()[0].evidence_refs == (
        "ev:replay#42",
        "ev:fill#7",
        "ev:capital_state#1",
    )


# ---------------------------------------------------------------------------
# 6. simulated entry alert remains simulated-only
# ---------------------------------------------------------------------------


def test_simulated_entry_alert_remains_simulated_only(tmp_path):
    outbox = _make_outbox(tmp_path)
    msg = _make_message(
        message_type=TelegramSandboxMessageType.SIMULATED_ENTRY_ALERT,
    )
    outbox.append_message(msg)
    payload = msg.to_dict()
    rendered = outbox.render_message(msg)
    assert payload["message_type"] == "SIMULATED_ENTRY_ALERT"
    assert payload["sandbox_only"] is True
    assert payload["simulated_only"] is True
    assert payload["no_live_order"] is True
    assert payload["no_live_order_assertion"] is True
    assert payload["no_real_capital_assertion"] is True
    assert payload["no_telegram_command_authority"] is True
    assert payload["telegram_outbound_enabled"] is False
    assert payload["telegram_live_command_authority"] is False
    assert payload["telegram_production_channel_enabled"] is False
    assert payload["live_trading"] is False
    assert payload["live_capital_enabled"] is False
    assert payload["real_capital"] is False
    assert payload["trade_authority"] is False
    # The rendering carries the four mandatory labels.
    for lbl in TELEGRAM_SANDBOX_MANDATORY_LABELS:
        assert lbl in rendered


# ---------------------------------------------------------------------------
# 7. risk rejection message remains review-only
# ---------------------------------------------------------------------------


def test_risk_rejection_message_remains_review_only(tmp_path):
    outbox = _make_outbox(tmp_path)
    msg = _make_message(
        message_id="tg_sandbox_msg_risk_00001",
        message_type=TelegramSandboxMessageType.RISK_REJECTION,
        severity=TelegramSandboxSeverity.NOTICE,
        title="Simulated risk rejection",
        body=(
            "Simulated risk rejection: insufficient simulated "
            "capital to open a paper position."
        ),
        evidence_refs=("ev:risk_decision#42",),
    )
    outbox.append_message(msg)
    payload = msg.to_dict()
    assert payload["message_type"] == "RISK_REJECTION"
    # A RISK_REJECTION message MUST never authorise any change to
    # the Risk Engine, and MUST never carry trade authority.
    assert payload["trade_authority"] is False
    assert payload["ai_trade_authority"] is False
    assert payload["auto_tuning_allowed"] is False
    assert payload["sandbox_only"] is True
    assert payload["telegram_live_command_authority"] is False
    # No runtime config patch field smuggled into a RISK_REJECTION
    # payload.
    keys = set(_walk_keys(payload))
    forbidden_patches = {
        "runtime_config_patch",
        "symbol_limit_patch",
        "threshold_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
        "strategy_parameter_patch",
        "apply_change",
        "deploy_change",
        "enable_live",
        "live_ready",
        "trading_approved",
    }
    assert keys.isdisjoint(forbidden_patches)


# ---------------------------------------------------------------------------
# 8. forced exit message remains simulated-only
# ---------------------------------------------------------------------------


def test_forced_exit_message_remains_simulated_only(tmp_path):
    outbox = _make_outbox(tmp_path)
    msg = _make_message(
        message_id="tg_sandbox_msg_forced_00001",
        message_type=TelegramSandboxMessageType.FORCED_EXIT,
        severity=TelegramSandboxSeverity.CRITICAL,
        title="Simulated forced exit",
        body=(
            "Simulated forced exit on ETHUSDT under paper "
            "liquidation stress (paper-only)."
        ),
        symbol="ETHUSDT",
        evidence_refs=("ev:forced_exit#1",),
    )
    outbox.append_message(msg)
    payload = msg.to_dict()
    assert payload["message_type"] == "FORCED_EXIT"
    assert payload["sandbox_only"] is True
    assert payload["simulated_only"] is True
    assert payload["no_live_order"] is True
    assert payload["live_trading"] is False
    assert payload["exchange_live_orders"] is False
    assert payload["binance_private_api_enabled"] is False
    assert payload["real_capital"] is False
    assert payload["trade_authority"] is False
    assert payload["telegram_outbound_enabled"] is False


# ---------------------------------------------------------------------------
# 9. equity summary message has no trade authority
# ---------------------------------------------------------------------------


def test_equity_summary_message_has_no_trade_authority(tmp_path):
    outbox = _make_outbox(tmp_path)
    msg = _make_message(
        message_id="tg_sandbox_msg_equity_00001",
        message_type=TelegramSandboxMessageType.EQUITY_SUMMARY,
        title="Simulated equity summary",
        body=(
            "Simulated equity summary: paper equity 9_998.32 USDT; "
            "0 active simulated positions."
        ),
        symbol=None,
        evidence_refs=(
            "ev:equity_timeseries#0001",
            "ev:trade_ledger_summary#0001",
        ),
    )
    outbox.append_message(msg)
    payload = msg.to_dict()
    assert payload["message_type"] == "EQUITY_SUMMARY"
    assert payload["trade_authority"] is False
    assert payload["ai_trade_authority"] is False
    assert payload["auto_tuning_allowed"] is False
    assert payload["telegram_live_command_authority"] is False


# ---------------------------------------------------------------------------
# 10. AI briefing ready message has no AI trade authority
# ---------------------------------------------------------------------------


def test_ai_briefing_ready_message_has_no_ai_trade_authority(tmp_path):
    outbox = _make_outbox(tmp_path)
    msg = _make_message(
        message_id="tg_sandbox_msg_ai_briefing_00001",
        message_type=TelegramSandboxMessageType.AI_OPERATOR_BRIEFING_READY,
        title="AI operator briefing ready",
        body=(
            "AI operator briefing prepared from offline / sandbox "
            "evidence (paper-only review; no AI trade authority)."
        ),
        symbol=None,
        evidence_refs=("ev:ai_briefing#0001",),
    )
    outbox.append_message(msg)
    payload = msg.to_dict()
    rendered = outbox.render_message(msg)
    assert payload["message_type"] == "AI_OPERATOR_BRIEFING_READY"
    assert payload["ai_trade_authority"] is False
    assert payload["trade_authority"] is False
    assert payload["auto_tuning_allowed"] is False
    assert payload["telegram_live_command_authority"] is False
    # The four mandatory labels are still rendered for an AI
    # briefing message.
    for lbl in TELEGRAM_SANDBOX_MANDATORY_LABELS:
        assert lbl in rendered


# ---------------------------------------------------------------------------
# 11. telegram_outbound_enabled=false in every payload
# ---------------------------------------------------------------------------


def test_telegram_outbound_enabled_false_in_every_payload(tmp_path):
    outbox = _make_outbox(tmp_path)
    msg = _make_message()
    outbox.append_message(msg)
    payloads = [
        msg.to_dict(),
        outbox.config.to_dict(),
        outbox.to_dict(),
        outbox.safety_payload(),
    ]
    for d in payloads:
        assert d["telegram_outbound_enabled"] is False
    assert outbox.telegram_outbound_enabled is False
    assert outbox.config.telegram_outbound_enabled is False


# ---------------------------------------------------------------------------
# 12. telegram_live_command_authority=false in every payload
# ---------------------------------------------------------------------------


def test_telegram_live_command_authority_false_in_every_payload(tmp_path):
    outbox = _make_outbox(tmp_path)
    msg = _make_message()
    outbox.append_message(msg)
    payloads = [
        msg.to_dict(),
        outbox.config.to_dict(),
        outbox.to_dict(),
        outbox.safety_payload(),
    ]
    for d in payloads:
        assert d["telegram_live_command_authority"] is False
        assert d["no_telegram_command_authority"] is True
    assert outbox.telegram_live_command_authority is False
    assert outbox.config.telegram_live_command_authority is False
    # Construction refuses any attempt to flip the command
    # authority.
    with pytest.raises(ValueError):
        TelegramSandboxOutboxConfig(
            telegram_live_command_authority=True,
        )
    with pytest.raises(ValueError):
        TelegramSandboxOutboxConfig(command_authority=True)


# ---------------------------------------------------------------------------
# 13. production_channel_enabled=false in every payload
# ---------------------------------------------------------------------------


def test_production_channel_enabled_false_in_every_payload(tmp_path):
    outbox = _make_outbox(tmp_path)
    msg = _make_message()
    outbox.append_message(msg)
    payloads = [
        msg.to_dict(),
        outbox.config.to_dict(),
        outbox.to_dict(),
        outbox.safety_payload(),
    ]
    for d in payloads:
        assert d["telegram_production_channel_enabled"] is False
    assert outbox.telegram_production_channel_enabled is False
    assert outbox.config.telegram_production_channel_enabled is False
    with pytest.raises(ValueError):
        TelegramSandboxOutboxConfig(
            telegram_production_channel_enabled=True,
        )


# ---------------------------------------------------------------------------
# 14. phase_12_forbidden=true in every payload
# ---------------------------------------------------------------------------


def test_phase_12_forbidden_true_in_every_payload(tmp_path):
    outbox = _make_outbox(tmp_path)
    msg = _make_message()
    outbox.append_message(msg)
    payloads = [
        msg.to_dict(),
        outbox.config.to_dict(),
        outbox.to_dict(),
        outbox.safety_payload(),
    ]
    for d in payloads:
        assert d["phase_12_forbidden"] is True
    assert outbox.phase_12_forbidden is True


# ---------------------------------------------------------------------------
# 15. auto_tuning_allowed=false in every payload
# ---------------------------------------------------------------------------


def test_auto_tuning_allowed_false_in_every_payload(tmp_path):
    outbox = _make_outbox(tmp_path)
    msg = _make_message()
    outbox.append_message(msg)
    payloads = [
        msg.to_dict(),
        outbox.config.to_dict(),
        outbox.to_dict(),
        outbox.safety_payload(),
    ]
    for d in payloads:
        assert d["auto_tuning_allowed"] is False
    assert outbox.auto_tuning_allowed is False


# ---------------------------------------------------------------------------
# 16. trade_authority=false in every payload
# ---------------------------------------------------------------------------


def test_trade_authority_false_in_every_payload(tmp_path):
    outbox = _make_outbox(tmp_path)
    msg = _make_message()
    outbox.append_message(msg)
    payloads = [
        msg.to_dict(),
        outbox.config.to_dict(),
        outbox.to_dict(),
        outbox.safety_payload(),
    ]
    for d in payloads:
        assert d["trade_authority"] is False
        assert d["ai_trade_authority"] is False
    assert outbox.trade_authority is False


# ---------------------------------------------------------------------------
# 17. no token / production channel fields in serialized outputs
# ---------------------------------------------------------------------------


def test_no_token_or_production_channel_fields_in_serialised_outputs(
    tmp_path,
):
    outbox = _make_outbox(tmp_path)
    outbox.append_message(_make_message())
    outbox.append_message(
        _make_message(
            message_id="tg_sandbox_msg_00000002",
            message_type=TelegramSandboxMessageType.RISK_REJECTION,
            severity=TelegramSandboxSeverity.WARNING,
            title="Simulated risk rejection",
            body="Simulated paper risk rejection on ETHUSDT.",
            symbol="ETHUSDT",
            evidence_refs=("ev:risk_decision#9",),
        )
    )
    # NOTE: bare "production_channel" / "live_channel" are
    # intentionally NOT in this list, because they would substring-
    # match the legitimate hard-pinned safety marker
    # ``telegram_production_channel_enabled``. We only forbid the
    # ``_id`` variants (the actual leak vectors).
    forbidden_token_fields = (
        "telegram_bot_token",
        "bot_token",
        "production_channel_id",
        "live_channel_id",
        "api_key",
        "api_secret",
        "real_order_id",
        "exchange_order_id",
        "real_account_id",
        "binance_signed",
        "private_websocket_url",
        "signed_endpoint_url",
        "listen_key",
        "listenkey",
        "signed_request",
    )
    payloads = [
        outbox.config.to_dict(),
        outbox.to_dict(),
        outbox.safety_payload(),
        *[m.to_dict() for m in outbox.list_messages()],
    ]
    for d in payloads:
        keys = set(_walk_keys(d))
        for forbidden in forbidden_token_fields:
            assert forbidden not in keys, (
                f"forbidden token-like field {forbidden!r} present"
            )
        # Defensive tripwires also checked.
        assert d["telegram_outbound_enabled"] is False
        assert d["telegram_live_command_authority"] is False
        assert d["telegram_production_channel_enabled"] is False
        assert d["binance_private_api_enabled"] is False
        assert d["signed_endpoint_reachable"] is False
        assert d["private_websocket_reachable"] is False
        assert d["account_endpoint_reachable"] is False
        assert d["order_endpoint_reachable"] is False
        assert d["position_endpoint_reachable"] is False
        assert d["leverage_endpoint_reachable"] is False
        assert d["margin_endpoint_reachable"] is False
        assert d["real_exchange_order_path"] is False
    # The on-disk JSONL + Markdown carry no token-like field names.
    jsonl = Path(outbox.write_jsonl()).read_text(encoding="utf-8")
    md = Path(outbox.write_markdown_transcript()).read_text(
        encoding="utf-8"
    )
    for forbidden in forbidden_token_fields:
        assert forbidden not in jsonl, (
            f"forbidden field {forbidden!r} smuggled into JSONL"
        )
        assert forbidden not in md, (
            f"forbidden field {forbidden!r} smuggled into Markdown"
        )
    # Public surface exposes no Telegram / network verbs.
    forbidden_verbs = {
        "send_message",
        "send_document",
        "send_telegram",
        "open_telegram",
        "open_websocket",
        "open_http",
        "post",
        "get",
        "connect",
        "place_order",
        "place_real_order",
        "sign_request",
        "sign",
        "private_websocket",
        "listen_key",
        "set_leverage",
        "apply_change",
        "deploy",
        "enable_live",
        "fetch_account",
        "fetch_position",
        "fetch_balance",
    }
    for inst in (outbox, outbox.config):
        public = {n for n in dir(inst) if not n.startswith("_")}
        assert public.isdisjoint(forbidden_verbs), (
            f"{inst!r} exposes forbidden verbs: "
            f"{public & forbidden_verbs}"
        )


# ---------------------------------------------------------------------------
# 18. forbidden fields absent from serialized outputs
# ---------------------------------------------------------------------------


def test_forbidden_fields_absent_from_serialised_outputs(tmp_path):
    outbox = _make_outbox(tmp_path)
    outbox.append_message(_make_message())
    outbox.append_message(
        _make_message(
            message_id="tg_sandbox_msg_00000002",
            message_type=TelegramSandboxMessageType.SIMULATED_EXIT_ALERT,
            timestamp_simulated=_T0 + timedelta(minutes=1),
            title="Simulated exit alert",
            body="Simulated paper exit on BTCUSDT (paper-only).",
        )
    )
    outbox.append_message(
        _make_message(
            message_id="tg_sandbox_msg_00000003",
            message_type=TelegramSandboxMessageType.AI_OPERATOR_BRIEFING_READY,
            timestamp_simulated=_T0 + timedelta(minutes=2),
            title="AI operator briefing ready",
            body="AI operator briefing prepared (paper-only review).",
            symbol=None,
        )
    )
    payloads = [
        outbox.config.to_dict(),
        outbox.to_dict(),
        outbox.safety_payload(),
        *[m.to_dict() for m in outbox.list_messages()],
    ]
    explicit = {
        "runtime_config_patch",
        "symbol_limit_patch",
        "threshold_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
        "strategy_parameter_patch",
        "apply_change",
        "deploy_change",
        "enable_live",
        "live_ready",
        "trading_approved",
        "real_order_id",
        "exchange_order_id",
        "real_account_id",
        "api_key",
        "api_secret",
        "telegram_bot_token",
        "bot_token",
        "production_channel_id",
        "live_channel_id",
    }
    for p in payloads:
        assert_no_forbidden_fields(p)
        keys = set(_walk_keys(p))
        assert keys.isdisjoint(FORBIDDEN_OUTPUT_FIELDS), (
            f"forbidden field present: "
            f"{keys & FORBIDDEN_OUTPUT_FIELDS}"
        )
        for forbidden in explicit:
            assert forbidden not in keys, (
                f"forbidden field {forbidden!r} smuggled into payload"
            )
    # Markdown transcript has no JSON-style forbidden keys.
    md = Path(outbox.write_markdown_transcript()).read_text(
        encoding="utf-8"
    )
    for forbidden in FORBIDDEN_OUTPUT_FIELDS:
        assert f'"{forbidden}"' not in md
    # JSONL also clean.
    jsonl_text = Path(outbox.write_jsonl()).read_text(encoding="utf-8")
    for line in jsonl_text.splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        assert_no_forbidden_fields(d)
        keys = set(_walk_keys(d))
        assert keys.isdisjoint(FORBIDDEN_OUTPUT_FIELDS)
        for forbidden in explicit:
            assert forbidden not in keys


# ---------------------------------------------------------------------------
# 19. module does not import app.risk / app.execution / app.exchanges /
#     app.telegram / app.config
# ---------------------------------------------------------------------------


def test_no_forbidden_app_imports_in_modules():
    root = _project_root()
    paths = [
        root / "app" / "sim" / "__init__.py",
        root / "app" / "sim" / "telegram_sandbox_outbox.py",
    ]
    forbidden_prefixes = (
        "app.risk",
        "app.execution",
        "app.exchanges",
        "app.telegram",
        "app.config",
    )
    for path in paths:
        src = path.read_text(encoding="utf-8")
        imported = _collect_imported_modules(src)
        for mod in imported:
            for bad in forbidden_prefixes:
                assert not mod.startswith(bad), (
                    f"{path} imports forbidden module {mod!r}"
                )
        idents = _collect_code_identifiers(src)
        for ident in idents:
            for bad in forbidden_prefixes:
                assert not ident.startswith(bad), (
                    f"{path} references forbidden identifier "
                    f"{ident!r}"
                )
    # Importing the new module does not pull any forbidden module.
    before = set(sys.modules)
    importlib.import_module("app.sim")
    importlib.import_module("app.sim.telegram_sandbox_outbox")
    new = set(sys.modules) - before
    for nm in new:
        for bad in forbidden_prefixes:
            assert not nm.startswith(bad), (
                f"importing app.sim.telegram_sandbox_outbox pulled "
                f"forbidden module {nm}"
            )


# ---------------------------------------------------------------------------
# 20. no Telegram Bot API / DeepSeek / LLM / network call path
# ---------------------------------------------------------------------------


def test_no_telegram_bot_api_deepseek_llm_or_network_path():
    root = _project_root()
    path = root / "app" / "sim" / "telegram_sandbox_outbox.py"
    forbidden_module_prefixes = (
        "deepseek",
        "openai",
        "anthropic",
        "telegram",
        "telegram_bot",
        "python_telegram_bot",
        "telebot",
        "aiogram",
        "binance",
        "ccxt",
        "websocket",
        "websockets",
        "httpx",
        "aiohttp",
        "requests",
        "urllib.request",
        "http.client",
        "grpc",
        "boto3",
        "socket",
    )
    forbidden_identifier_prefixes = (
        "deepseek",
        "openai",
        "anthropic",
        # NOTE: bare "telegram" is intentionally NOT in this list,
        # because every legitimate sandbox class name (e.g.
        # ``TelegramSandboxMessage``) starts with ``Telegram``. We
        # forbid the more specific *bot-API* / library prefixes
        # below. The combined "no-import" check on
        # ``forbidden_module_prefixes`` already prevents importing a
        # real ``telegram`` library.
        "telegram_bot",
        "telegrambot",
        "telegram_api",
        "telegram_send",
        "telegram_webhook",
        "binance",
        "ccxt",
        "websocket",
        "httpx",
        "aiohttp",
        "requests.get",
        "requests.post",
        "urllib.request",
        "socket.connect",
        "socket.create_connection",
        "http.client.HTTPConnection",
        "http.client.HTTPSConnection",
    )
    src = path.read_text(encoding="utf-8")
    imported = _collect_imported_modules(src)
    for mod in imported:
        low = mod.lower()
        for bad in forbidden_module_prefixes:
            assert not low.startswith(bad), (
                f"{path} imports forbidden module {mod!r}"
            )
    idents = _collect_code_identifiers(src)
    for ident in idents:
        low = ident.lower()
        for bad in forbidden_identifier_prefixes:
            assert not low.startswith(bad), (
                f"{path} references forbidden code identifier "
                f"{ident!r}"
            )
    # No Telegram Bot API URL substring smuggled into the source.
    src_low = src.lower()
    for needle in (
        "api.telegram.org",
        "telegram.bot",
        "sendmessage",
        "senddocument",
        "getupdates",
        "set_webhook",
        "setwebhook",
    ):
        assert needle not in src_low, (
            f"forbidden Telegram-api-like substring {needle!r} "
            f"present in module source"
        )
    # Importing the new module does not pull any forbidden module.
    pre = set(sys.modules)
    importlib.import_module("app.sim.telegram_sandbox_outbox")
    new = set(sys.modules) - pre
    for nm in new:
        low = nm.lower()
        for bad in forbidden_module_prefixes:
            assert not low.startswith(bad), (
                f"unexpected import: {nm}"
            )


# ---------------------------------------------------------------------------
# 21. deterministic output
# ---------------------------------------------------------------------------


def test_deterministic_output_across_two_independent_runs(tmp_path):
    def run(target_dir: Path) -> tuple:
        outbox = TelegramSandboxOutbox(
            config=TelegramSandboxOutboxConfig(
                output_jsonl_path=str(
                    target_dir / "telegram_sandbox_outbox.jsonl"
                ),
                output_markdown_path=str(
                    target_dir / "telegram_sandbox_messages.md"
                ),
            )
        )
        outbox.append_message(
            _make_message(
                message_id="tg_sandbox_msg_00000001",
                timestamp_simulated=_T0,
                message_type=TelegramSandboxMessageType.SIMULATED_ENTRY_ALERT,
                title="Simulated entry alert",
                body="Simulated paper entry on BTCUSDT (paper-only).",
                evidence_refs=("ev:replay#1", "ev:fill#1"),
            )
        )
        outbox.append_message(
            _make_message(
                message_id="tg_sandbox_msg_00000002",
                timestamp_simulated=_T0 + timedelta(minutes=5),
                message_type=TelegramSandboxMessageType.RISK_REJECTION,
                severity=TelegramSandboxSeverity.WARNING,
                title="Simulated risk rejection",
                body="Simulated paper risk rejection on ETHUSDT.",
                symbol="ETHUSDT",
                evidence_refs=("ev:risk_decision#1",),
            )
        )
        outbox.append_message(
            _make_message(
                message_id="tg_sandbox_msg_00000003",
                timestamp_simulated=_T0 + timedelta(minutes=10),
                message_type=TelegramSandboxMessageType.EQUITY_SUMMARY,
                severity=TelegramSandboxSeverity.NOTICE,
                title="Simulated equity summary",
                body="Simulated paper equity summary at +10min.",
                symbol=None,
                evidence_refs=(
                    "ev:equity_timeseries#0001",
                    "ev:trade_ledger_summary#0001",
                ),
            )
        )
        jsonl_path = outbox.write_jsonl()
        md_path = outbox.write_markdown_transcript()
        return (
            Path(jsonl_path).read_text(encoding="utf-8"),
            Path(md_path).read_text(encoding="utf-8"),
            outbox.to_dict(),
        )

    a_jsonl, a_md, a_dict = run(tmp_path / "a")
    b_jsonl, b_md, b_dict = run(tmp_path / "b")
    assert a_jsonl == b_jsonl
    assert a_md == b_md
    # to_dict is deterministic too, *modulo* the configured output
    # paths (which are intentionally different here so the two runs
    # cannot trample each other). Strip those before the comparison.
    def _strip_paths(d):
        d = json.loads(json.dumps(d))
        d["config"]["output_jsonl_path"] = "<stripped>"
        d["config"]["output_markdown_path"] = "<stripped>"
        return d

    assert json.dumps(_strip_paths(a_dict), sort_keys=True) == json.dumps(
        _strip_paths(b_dict), sort_keys=True
    )


# ---------------------------------------------------------------------------
# Extra: closed-taxonomy enforcement and phase-name string presence
# ---------------------------------------------------------------------------


def test_closed_taxonomy_and_phase_name_string():
    assert "PR99" in TELEGRAM_SANDBOX_OUTBOX_PHASE_NAME
    assert "11C.1D-D-F" in TELEGRAM_SANDBOX_OUTBOX_PHASE_NAME
    assert isinstance(TelegramSandboxMessageType.ALLOWED, frozenset)
    assert isinstance(TelegramSandboxSeverity.ALLOWED, frozenset)
    # 13 brief-mandated message types.
    expected_types = {
        "SIMULATED_ENTRY_ALERT",
        "SIMULATED_EXIT_ALERT",
        "RISK_REJECTION",
        "FORCED_EXIT",
        "STALE_FEED",
        "OUTAGE",
        "DATA_GAP",
        "RIGHT_TAIL_CAPTURED",
        "SEVERE_MISSED_TAIL",
        "EQUITY_SUMMARY",
        "FAILURE_LEDGER_SUMMARY",
        "MONTHLY_BLIND_TEST_SUMMARY",
        "AI_OPERATOR_BRIEFING_READY",
    }
    assert TelegramSandboxMessageType.ALLOWED == expected_types
    assert TelegramSandboxSeverity.ALLOWED == {
        "INFO",
        "NOTICE",
        "WARNING",
        "CRITICAL",
    }
    # Mandatory labels exposed and exactly four.
    assert len(TELEGRAM_SANDBOX_MANDATORY_LABELS) == 4
    assert SIMULATED_HISTORICAL_BLIND_TEST_LABEL in TELEGRAM_SANDBOX_MANDATORY_LABELS
    assert NO_LIVE_ORDER_LABEL in TELEGRAM_SANDBOX_MANDATORY_LABELS
    assert NO_REAL_CAPITAL_LABEL in TELEGRAM_SANDBOX_MANDATORY_LABELS
    assert (
        NO_TELEGRAM_COMMAND_AUTHORITY_LABEL
        in TELEGRAM_SANDBOX_MANDATORY_LABELS
    )


# ---------------------------------------------------------------------------
# Extra: reset clears in-memory list but preserves on-disk artefacts
# ---------------------------------------------------------------------------


def test_reset_clears_in_memory_list_only(tmp_path):
    outbox = _make_outbox(tmp_path)
    outbox.append_message(_make_message())
    written = outbox.write_jsonl()
    assert Path(written).exists()
    outbox.reset()
    assert outbox.list_messages() == ()
    assert outbox.message_count == 0
    # On-disk file from before reset is untouched (reset is
    # in-memory only).
    assert Path(written).exists()
    text = Path(written).read_text(encoding="utf-8").strip()
    assert text  # non-empty
