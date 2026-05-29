"""Telegram Sandbox Outbox v0 for Phase 11C.1D-D-F (PR99 - Telegram
Sandbox Outbox v0).

Strict blind walk-forward simulated Telegram outbox. This module is
the **sixth** anti-future-lookahead infrastructure block of the
strict blind walk-forward stack defined by Phase 11C.1D-D (the
*Strict Blind Walk-forward Sim-Live Constitution*, PR93). It builds
strictly on top of the PR94 / PR95 / PR96 / PR97 / PR98 substrate
and is consumed by the (still-FORBIDDEN-by-this-phase) PR100 Blind
Walk-forward Runner.

Constitution §13: the Telegram Sandbox Outbox is a **paper-only,
file-only** notification surface. It NEVER opens a network socket,
NEVER calls the Telegram Bot API, NEVER reads a Telegram production
token, NEVER targets a production / live channel, NEVER accepts an
inbound command, NEVER carries Telegram command authority, NEVER
authorises a runtime-config patch, NEVER touches the Risk Engine,
the Execution FSM, the real exchange gateway, or any runtime config.
The outbox writes only deterministic local JSONL / Markdown
transcript files for operator review and blind-run evidence.

Hard safety boundary (Phase 11C.1D-D-F / PR99):

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

This module MUST NOT and CANNOT:

  - import app.risk / app.execution / app.exchanges / app.telegram /
    app.config
  - call DeepSeek / LLM / Telegram Bot API / Binance private API /
    any network
  - read a Telegram production token
  - send a real Telegram message
  - target a production / live Telegram channel
  - accept an inbound Telegram command
  - emit any runtime_config_patch / threshold_patch /
    symbol_limit_patch / candidate_pool_patch / regime_weight_patch /
    strategy_parameter_patch / signal_to_trade / should_buy /
    should_short / apply_change / deploy_change / enable_live /
    live_ready / trading_approved
  - emit a real exchange order id, a real account id, an api key,
    an api secret, a Telegram bot token, a production channel id, or
    a signed-endpoint reference
  - authorise live trading or auto-tuning
  - enter Phase 12

PR99 acceptance authorises ONLY PR100 (*Blind Walk-forward Runner v0*)
to begin its own gate. PR99 does NOT implement, and does NOT
authorise:

  - the Blind Walk-forward Runner (PR100),
  - Phase 12.

The Risk Engine remains the single trade-decision gate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Tuple

from app.sim.simulation_clock import ensure_utc_aware
from app.sim.time_wall_guard import assert_no_forbidden_fields


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

PHASE_NAME: str = (
    "Phase 11C.1D-D-F / PR99 / Telegram Sandbox Outbox v0"
)


# ---------------------------------------------------------------------------
# Mandatory simulated / no-live labels rendered on every transcript
# entry. These four labels MUST be present in the rendered Markdown
# output of every TelegramSandboxMessage. They are NEVER trade
# instructions, NEVER runtime patches, NEVER Telegram command
# authority signals.
# ---------------------------------------------------------------------------

SIMULATED_HISTORICAL_BLIND_TEST_LABEL: str = "[SIMULATED HISTORICAL BLIND TEST]"
NO_LIVE_ORDER_LABEL: str = "[NO LIVE ORDER]"
NO_REAL_CAPITAL_LABEL: str = "[NO REAL CAPITAL]"
NO_TELEGRAM_COMMAND_AUTHORITY_LABEL: str = "[NO TELEGRAM COMMAND AUTHORITY]"

MANDATORY_LABELS: Tuple[str, ...] = (
    SIMULATED_HISTORICAL_BLIND_TEST_LABEL,
    NO_LIVE_ORDER_LABEL,
    NO_REAL_CAPITAL_LABEL,
    NO_TELEGRAM_COMMAND_AUTHORITY_LABEL,
)


# ---------------------------------------------------------------------------
# Default sandbox output paths. Tests MUST use a temp directory and
# NEVER write to these defaults.
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT_JSONL_PATH: str = "data/reports/telegram_sandbox_outbox.jsonl"
DEFAULT_OUTPUT_MARKDOWN_PATH: str = "data/reports/telegram_sandbox_messages.md"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safety_payload() -> Dict[str, Any]:
    """Project-wide safety boundary, re-pinned on every serialisation
    boundary so that no payload can ever be misread as authorising
    live Telegram outbound, live trading, auto-tuning, Telegram
    command authority, or Phase 12.
    """
    return {
        "phase": PHASE_NAME,
        "mode": "paper",
        "sandbox_only": True,
        "simulated_only": True,
        "no_live_order": True,
        "no_live_order_assertion": True,
        "no_real_capital_assertion": True,
        "no_telegram_command_authority": True,
        "live_trading": False,
        "live_capital_enabled": False,
        "exchange_live_orders": False,
        "binance_private_api_enabled": False,
        "signed_endpoint_reachable": False,
        "private_websocket_reachable": False,
        "account_endpoint_reachable": False,
        "order_endpoint_reachable": False,
        "position_endpoint_reachable": False,
        "leverage_endpoint_reachable": False,
        "margin_endpoint_reachable": False,
        "real_exchange_order_path": False,
        "real_capital": False,
        "telegram_outbound_enabled": False,
        "telegram_live_command_authority": False,
        "telegram_production_channel_enabled": False,
        "ai_trade_authority": False,
        "trade_authority": False,
        "auto_tuning_allowed": False,
        "phase_12_forbidden": True,
        # Defensive non-trade markers:
        "is_telegram_sandbox_payload": True,
        "is_real_telegram_outbound": False,
        "is_runtime_patch": False,
    }


# Forbidden keys that MUST NEVER appear (recursively) in any payload
# produced by this module. This is in addition to the project-wide
# :data:`app.sim.time_wall_guard.FORBIDDEN_OUTPUT_FIELDS` set.
_OUTBOX_FORBIDDEN_KEYS: FrozenSet[str] = frozenset(
    {
        "telegram_bot_token",
        "bot_token",
        "production_channel_id",
        "live_channel_id",
        "production_channel",
        "live_channel",
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
)


def _assert_no_outbox_forbidden_keys(
    payload: Any, _path: str = "$"
) -> None:
    """Recursively assert no outbox-forbidden field name appears in
    ``payload``. Raises :class:`ValueError` on the first violation.
    """
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            if isinstance(k, str) and k in _OUTBOX_FORBIDDEN_KEYS:
                raise ValueError(
                    f"telegram-sandbox-forbidden field {k!r} "
                    f"present at {_path}"
                )
            _assert_no_outbox_forbidden_keys(v, f"{_path}.{k}")
    elif isinstance(payload, (list, tuple)):
        for i, v in enumerate(payload):
            _assert_no_outbox_forbidden_keys(v, f"{_path}[{i}]")


def _check_str_tuple(
    values: Iterable[Any], field_name: str
) -> Tuple[str, ...]:
    out: List[str] = []
    for v in values:
        if not isinstance(v, str):
            raise TypeError(
                f"{field_name} entries must be strings, got "
                f"{type(v)!r}"
            )
        out.append(v)
    return tuple(out)


def _ensure_path_str(value: Any, name: str) -> str:
    if isinstance(value, Path):
        return str(value)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string or Path")
    return value


# ---------------------------------------------------------------------------
# Closed taxonomies
# ---------------------------------------------------------------------------


class TelegramSandboxMessageType:
    """Closed taxonomy of Telegram sandbox message types.

    Each value is a paper-only descriptor of the **kind** of
    sandbox notification being recorded. None of these values is a
    trade instruction, a runtime patch, or a Telegram command
    authority signal. The values intentionally re-use operational
    vocabulary (``ENTRY``, ``EXIT``, ``REJECTION``, ``FORCED_EXIT``)
    so the transcript reads like an operator briefing; the values
    appear only as JSON / Markdown **values**, never as field
    **names**, so the project-wide
    :data:`app.sim.time_wall_guard.FORBIDDEN_OUTPUT_FIELDS` guard
    remains untouched.
    """

    SIMULATED_ENTRY_ALERT: str = "SIMULATED_ENTRY_ALERT"
    SIMULATED_EXIT_ALERT: str = "SIMULATED_EXIT_ALERT"
    RISK_REJECTION: str = "RISK_REJECTION"
    FORCED_EXIT: str = "FORCED_EXIT"
    STALE_FEED: str = "STALE_FEED"
    OUTAGE: str = "OUTAGE"
    DATA_GAP: str = "DATA_GAP"
    RIGHT_TAIL_CAPTURED: str = "RIGHT_TAIL_CAPTURED"
    SEVERE_MISSED_TAIL: str = "SEVERE_MISSED_TAIL"
    EQUITY_SUMMARY: str = "EQUITY_SUMMARY"
    FAILURE_LEDGER_SUMMARY: str = "FAILURE_LEDGER_SUMMARY"
    MONTHLY_BLIND_TEST_SUMMARY: str = "MONTHLY_BLIND_TEST_SUMMARY"
    AI_OPERATOR_BRIEFING_READY: str = "AI_OPERATOR_BRIEFING_READY"

    ALLOWED: FrozenSet[str] = frozenset(
        {
            SIMULATED_ENTRY_ALERT,
            SIMULATED_EXIT_ALERT,
            RISK_REJECTION,
            FORCED_EXIT,
            STALE_FEED,
            OUTAGE,
            DATA_GAP,
            RIGHT_TAIL_CAPTURED,
            SEVERE_MISSED_TAIL,
            EQUITY_SUMMARY,
            FAILURE_LEDGER_SUMMARY,
            MONTHLY_BLIND_TEST_SUMMARY,
            AI_OPERATOR_BRIEFING_READY,
        }
    )


class TelegramSandboxSeverity:
    """Closed taxonomy of Telegram sandbox message severities.

    Descriptive only. NEVER a runtime config patch, NEVER an order
    severity, NEVER a Risk Engine override.
    """

    INFO: str = "INFO"
    NOTICE: str = "NOTICE"
    WARNING: str = "WARNING"
    CRITICAL: str = "CRITICAL"

    ALLOWED: FrozenSet[str] = frozenset({INFO, NOTICE, WARNING, CRITICAL})


# ---------------------------------------------------------------------------
# TelegramSandboxMessage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TelegramSandboxMessage:
    """A single deterministic Telegram sandbox message.

    The message is **immutable** and **JSON-serialisable** via
    :meth:`to_dict` / :meth:`to_json`. The hard-pinned safety markers
    cannot be flipped through the dataclass constructor. The message
    NEVER carries a real Telegram bot token, a real production / live
    channel id, an api key, an api secret, a real account id, or a
    signed-endpoint reference. The message NEVER carries a runtime
    config patch, an apply / deploy / enable-live flag, or any
    Telegram command authority signal.
    """

    message_id: str
    timestamp_simulated: datetime
    message_type: str
    title: str
    body: str
    severity: str = TelegramSandboxSeverity.INFO
    symbol: Optional[str] = None
    evidence_refs: Tuple[str, ...] = ()
    # Hard-pinned safety markers:
    sandbox_only: bool = True
    no_live_order_assertion: bool = True
    no_real_capital_assertion: bool = True
    no_telegram_command_authority: bool = True
    phase_12_forbidden: bool = True
    trade_authority: bool = False
    auto_tuning_allowed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.message_id, str) or not self.message_id:
            raise ValueError("message_id must be a non-empty string")
        ts = ensure_utc_aware(
            self.timestamp_simulated, "timestamp_simulated"
        )
        if self.message_type not in TelegramSandboxMessageType.ALLOWED:
            raise ValueError(
                f"message_type must be one of "
                f"{sorted(TelegramSandboxMessageType.ALLOWED)}, got "
                f"{self.message_type!r}"
            )
        if self.severity not in TelegramSandboxSeverity.ALLOWED:
            raise ValueError(
                f"severity must be one of "
                f"{sorted(TelegramSandboxSeverity.ALLOWED)}, got "
                f"{self.severity!r}"
            )
        if not isinstance(self.title, str) or not self.title:
            raise ValueError("title must be a non-empty string")
        if not isinstance(self.body, str) or not self.body:
            raise ValueError("body must be a non-empty string")
        if self.symbol is not None and (
            not isinstance(self.symbol, str) or not self.symbol
        ):
            raise ValueError(
                "symbol must be a non-empty string or None"
            )
        refs = _check_str_tuple(self.evidence_refs, "evidence_refs")
        if self.sandbox_only is not True:
            raise ValueError("sandbox_only must be True")
        if self.no_live_order_assertion is not True:
            raise ValueError("no_live_order_assertion must be True")
        if self.no_real_capital_assertion is not True:
            raise ValueError("no_real_capital_assertion must be True")
        if self.no_telegram_command_authority is not True:
            raise ValueError(
                "no_telegram_command_authority must be True"
            )
        if self.phase_12_forbidden is not True:
            raise ValueError("phase_12_forbidden must be True")
        if self.trade_authority is not False:
            raise ValueError("trade_authority must be False")
        if self.auto_tuning_allowed is not False:
            raise ValueError("auto_tuning_allowed must be False")
        object.__setattr__(self, "timestamp_simulated", ts)
        object.__setattr__(self, "evidence_refs", refs)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "message_id": self.message_id,
            "timestamp_simulated": self.timestamp_simulated.isoformat(),
            "message_type": self.message_type,
            "severity": self.severity,
            "symbol": self.symbol,
            "title": self.title,
            "body": self.body,
            "evidence_refs": list(self.evidence_refs),
            "is_telegram_sandbox_message": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        _assert_no_outbox_forbidden_keys(out)
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


# ---------------------------------------------------------------------------
# TelegramSandboxOutboxConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TelegramSandboxOutboxConfig:
    """Frozen configuration for a :class:`TelegramSandboxOutbox`.

    The frozen container guarantees downstream callers cannot mutate
    output paths, append-mode, evidence-ref inclusion, or any of the
    hard-pinned safety markers at runtime.
    """

    output_jsonl_path: str = DEFAULT_OUTPUT_JSONL_PATH
    output_markdown_path: str = DEFAULT_OUTPUT_MARKDOWN_PATH
    append_mode: bool = False
    include_evidence_refs: bool = True
    max_message_body_chars: Optional[int] = None
    # Hard-pinned safety markers:
    sandbox_only: bool = True
    telegram_outbound_enabled: bool = False
    telegram_live_command_authority: bool = False
    telegram_production_channel_enabled: bool = False
    command_authority: bool = False

    def __post_init__(self) -> None:
        jsonl = _ensure_path_str(
            self.output_jsonl_path, "output_jsonl_path"
        )
        md = _ensure_path_str(
            self.output_markdown_path, "output_markdown_path"
        )
        if not isinstance(self.append_mode, bool):
            raise TypeError("append_mode must be bool")
        if not isinstance(self.include_evidence_refs, bool):
            raise TypeError("include_evidence_refs must be bool")
        if self.max_message_body_chars is not None:
            if (
                not isinstance(self.max_message_body_chars, int)
                or isinstance(self.max_message_body_chars, bool)
            ):
                raise TypeError(
                    "max_message_body_chars must be int or None"
                )
            if self.max_message_body_chars <= 0:
                raise ValueError(
                    "max_message_body_chars must be > 0 or None"
                )
        if self.sandbox_only is not True:
            raise ValueError("sandbox_only must be True")
        if self.telegram_outbound_enabled is not False:
            raise ValueError(
                "telegram_outbound_enabled must be False"
            )
        if self.telegram_live_command_authority is not False:
            raise ValueError(
                "telegram_live_command_authority must be False"
            )
        if self.telegram_production_channel_enabled is not False:
            raise ValueError(
                "telegram_production_channel_enabled must be False"
            )
        if self.command_authority is not False:
            raise ValueError("command_authority must be False")
        object.__setattr__(self, "output_jsonl_path", jsonl)
        object.__setattr__(self, "output_markdown_path", md)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "output_jsonl_path": self.output_jsonl_path,
            "output_markdown_path": self.output_markdown_path,
            "append_mode": bool(self.append_mode),
            "include_evidence_refs": bool(self.include_evidence_refs),
            "max_message_body_chars": (
                int(self.max_message_body_chars)
                if self.max_message_body_chars is not None
                else None
            ),
            "command_authority": False,
            "is_telegram_sandbox_outbox_config": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        _assert_no_outbox_forbidden_keys(out)
        return out


# ---------------------------------------------------------------------------
# TelegramSandboxOutbox
# ---------------------------------------------------------------------------


class TelegramSandboxOutbox:
    """Paper-only / file-only Telegram sandbox outbox.

    The outbox writes every notification only to local JSONL +
    Markdown transcript files for operator review and blind-run
    evidence. It NEVER opens a network socket, NEVER calls the
    Telegram Bot API, NEVER reads a Telegram production token, NEVER
    targets a production / live channel, NEVER accepts an inbound
    command, NEVER carries Telegram command authority, NEVER
    authorises a runtime-config patch, NEVER touches the Risk
    Engine, the Execution FSM, the real exchange gateway, or any
    runtime config.

    Public API:

      * :meth:`append_message` — append a single
        :class:`TelegramSandboxMessage`.
      * :meth:`append_messages` — bulk-append.
      * :meth:`render_message` — return the deterministic Markdown
        rendering of a single message (with the four mandatory
        labels).
      * :meth:`write_jsonl` — write every appended message as one
        JSON object per line (deterministic, ``sort_keys=True``).
      * :meth:`write_markdown_transcript` — write the full Markdown
        transcript (header + per-message section) for operator
        review.
      * :meth:`list_messages` — return the appended messages as a
        deterministic tuple.
      * :meth:`reset` — clear the in-memory message list (does NOT
        truncate any on-disk file).
      * :meth:`safety_payload` — return the paper-only safety
        boundary payload.
      * :meth:`to_dict` — return the deterministic outbox snapshot.
    """

    def __init__(
        self,
        config: Optional[TelegramSandboxOutboxConfig] = None,
    ) -> None:
        if config is None:
            config = TelegramSandboxOutboxConfig()
        if not isinstance(config, TelegramSandboxOutboxConfig):
            raise TypeError(
                f"config must be TelegramSandboxOutboxConfig, got "
                f"{type(config)!r}"
            )
        self._config: TelegramSandboxOutboxConfig = config
        self._messages: List[TelegramSandboxMessage] = []

    # ------------------------------------------------------------------
    # Defensive tripwires (exposed as properties on every instance)
    # ------------------------------------------------------------------

    @property
    def config(self) -> TelegramSandboxOutboxConfig:
        return self._config

    @property
    def sandbox_only(self) -> bool:
        return True

    @property
    def telegram_outbound_enabled(self) -> bool:
        return False

    @property
    def telegram_live_command_authority(self) -> bool:
        return False

    @property
    def telegram_production_channel_enabled(self) -> bool:
        return False

    @property
    def no_live_order_assertion(self) -> bool:
        return True

    @property
    def no_real_capital_assertion(self) -> bool:
        return True

    @property
    def no_telegram_command_authority(self) -> bool:
        return True

    @property
    def phase_12_forbidden(self) -> bool:
        return True

    @property
    def trade_authority(self) -> bool:
        return False

    @property
    def auto_tuning_allowed(self) -> bool:
        return False

    @property
    def message_count(self) -> int:
        return len(self._messages)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def append_message(
        self, message: TelegramSandboxMessage
    ) -> TelegramSandboxMessage:
        """Append a single :class:`TelegramSandboxMessage`.

        Defensively rechecks every hard-pinned safety marker. Returns
        the appended message unchanged.
        """
        if not isinstance(message, TelegramSandboxMessage):
            raise TypeError(
                f"message must be TelegramSandboxMessage, got "
                f"{type(message)!r}"
            )
        if message.sandbox_only is not True:
            raise ValueError("message.sandbox_only must be True")
        if message.no_live_order_assertion is not True:
            raise ValueError(
                "message.no_live_order_assertion must be True"
            )
        if message.no_real_capital_assertion is not True:
            raise ValueError(
                "message.no_real_capital_assertion must be True"
            )
        if message.no_telegram_command_authority is not True:
            raise ValueError(
                "message.no_telegram_command_authority must be True"
            )
        if message.phase_12_forbidden is not True:
            raise ValueError("message.phase_12_forbidden must be True")
        if message.trade_authority is not False:
            raise ValueError("message.trade_authority must be False")
        if message.auto_tuning_allowed is not False:
            raise ValueError(
                "message.auto_tuning_allowed must be False"
            )
        # Recursively validate that the message's serialised payload
        # carries neither a project-wide forbidden field nor an
        # outbox-specific forbidden field.
        payload = message.to_dict()
        assert_no_forbidden_fields(payload)
        _assert_no_outbox_forbidden_keys(payload)
        self._messages.append(message)
        return message

    def append_messages(
        self, messages: Iterable[TelegramSandboxMessage]
    ) -> Tuple[TelegramSandboxMessage, ...]:
        out: List[TelegramSandboxMessage] = []
        for m in messages:
            out.append(self.append_message(m))
        return tuple(out)

    def list_messages(self) -> Tuple[TelegramSandboxMessage, ...]:
        return tuple(self._messages)

    def reset(self) -> None:
        """Clear the in-memory message list. Does NOT truncate any
        on-disk JSONL / Markdown file.
        """
        self._messages = []

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _truncated_body(self, body: str) -> str:
        cap = self._config.max_message_body_chars
        if cap is None or len(body) <= cap:
            return body
        return body[:cap]

    def render_message(self, message: TelegramSandboxMessage) -> str:
        """Return the deterministic Markdown rendering of a single
        :class:`TelegramSandboxMessage`. The rendering MUST contain
        all four mandatory simulated / no-live labels.
        """
        if not isinstance(message, TelegramSandboxMessage):
            raise TypeError(
                f"message must be TelegramSandboxMessage, got "
                f"{type(message)!r}"
            )
        body = self._truncated_body(message.body)
        lines: List[str] = []
        # Mandatory labels (always first, always all four).
        lines.append(SIMULATED_HISTORICAL_BLIND_TEST_LABEL)
        lines.append(NO_LIVE_ORDER_LABEL)
        lines.append(NO_REAL_CAPITAL_LABEL)
        lines.append(NO_TELEGRAM_COMMAND_AUTHORITY_LABEL)
        lines.append("")
        lines.append(f"## {message.title}")
        lines.append("")
        lines.append(f"- message_id: `{message.message_id}`")
        lines.append(f"- message_type: `{message.message_type}`")
        lines.append(f"- severity: `{message.severity}`")
        lines.append(
            f"- timestamp_simulated: "
            f"`{message.timestamp_simulated.isoformat()}`"
        )
        if message.symbol is not None:
            lines.append(f"- symbol: `{message.symbol}`")
        lines.append("")
        lines.append("body:")
        lines.append("")
        lines.append(body)
        if (
            self._config.include_evidence_refs
            and message.evidence_refs
        ):
            lines.append("")
            lines.append("evidence_refs:")
            for ref in message.evidence_refs:
                lines.append(f"- {ref}")
        lines.append("")
        # Re-pin the boundary at the end of the rendering as a
        # human-visible footer.
        lines.append("---")
        lines.append(
            "sandbox_only=true; "
            "telegram_outbound_enabled=false; "
            "telegram_live_command_authority=false; "
            "telegram_production_channel_enabled=false; "
            "no_live_order_assertion=true; "
            "no_real_capital_assertion=true; "
            "no_telegram_command_authority=true; "
            "phase_12_forbidden=true; "
            "auto_tuning_allowed=false; "
            "trade_authority=false."
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # On-disk writers (deterministic, paper-only, no network)
    # ------------------------------------------------------------------

    def _payload_for_message(
        self, message: TelegramSandboxMessage
    ) -> Dict[str, Any]:
        payload = message.to_dict()
        if not self._config.include_evidence_refs:
            payload["evidence_refs"] = []
        cap = self._config.max_message_body_chars
        if cap is not None and len(payload["body"]) > cap:
            payload["body"] = payload["body"][:cap]
        assert_no_forbidden_fields(payload)
        _assert_no_outbox_forbidden_keys(payload)
        return payload

    def write_jsonl(self, path: Optional[str] = None) -> str:
        """Write the appended messages as JSONL, one JSON object per
        line. Returns the absolute path written. The output is
        deterministic (``sort_keys=True``) and contains NO
        Telegram bot token, NO production / live channel id, and NO
        api key / api secret / signed-endpoint reference.
        """
        target = path if path is not None else self._config.output_jsonl_path
        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if self._config.append_mode else "w"
        with target_path.open(mode, encoding="utf-8") as fh:
            for m in self._messages:
                payload = self._payload_for_message(m)
                fh.write(json.dumps(payload, sort_keys=True))
                fh.write("\n")
        return str(target_path)

    def write_markdown_transcript(
        self, path: Optional[str] = None
    ) -> str:
        """Write the full Markdown transcript (header + per-message
        section) for operator review. Returns the absolute path
        written. The transcript is deterministic and contains all
        four mandatory simulated / no-live labels at the top of every
        message section.
        """
        target = (
            path if path is not None else self._config.output_markdown_path
        )
        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if self._config.append_mode else "w"
        header_lines: List[str] = []
        header_lines.append(
            "# Telegram Sandbox Transcript "
            "(Phase 11C.1D-D-F / PR99)"
        )
        header_lines.append("")
        header_lines.append(SIMULATED_HISTORICAL_BLIND_TEST_LABEL)
        header_lines.append(NO_LIVE_ORDER_LABEL)
        header_lines.append(NO_REAL_CAPITAL_LABEL)
        header_lines.append(NO_TELEGRAM_COMMAND_AUTHORITY_LABEL)
        header_lines.append("")
        header_lines.append(
            "Paper-only blind walk-forward Telegram sandbox transcript. "
            "No real Telegram outbound. No production / live channel. "
            "No Telegram command authority. No live trading. No real "
            "capital. No auto-tuning. Phase 12 = FORBIDDEN."
        )
        header_lines.append("")
        header_lines.append(f"- phase: `{PHASE_NAME}`")
        header_lines.append(f"- message_count: {len(self._messages)}")
        header_lines.append("- sandbox_only: `true`")
        header_lines.append("- telegram_outbound_enabled: `false`")
        header_lines.append(
            "- telegram_live_command_authority: `false`"
        )
        header_lines.append(
            "- telegram_production_channel_enabled: `false`"
        )
        header_lines.append("- no_live_order_assertion: `true`")
        header_lines.append("- no_real_capital_assertion: `true`")
        header_lines.append("- no_telegram_command_authority: `true`")
        header_lines.append("- phase_12_forbidden: `true`")
        header_lines.append("- auto_tuning_allowed: `false`")
        header_lines.append("- trade_authority: `false`")
        header_lines.append("")
        with target_path.open(mode, encoding="utf-8") as fh:
            if not self._config.append_mode:
                fh.write("\n".join(header_lines))
                fh.write("\n")
            for m in self._messages:
                fh.write(self.render_message(m))
                fh.write("\n\n")
        return str(target_path)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def safety_payload(self) -> Dict[str, Any]:
        out = _safety_payload()
        assert_no_forbidden_fields(out)
        _assert_no_outbox_forbidden_keys(out)
        return out

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "config": self._config.to_dict(),
            "message_count": len(self._messages),
            "messages": [
                self._payload_for_message(m) for m in self._messages
            ],
            "is_telegram_sandbox_outbox": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        _assert_no_outbox_forbidden_keys(out)
        return out


__all__ = [
    "PHASE_NAME",
    "DEFAULT_OUTPUT_JSONL_PATH",
    "DEFAULT_OUTPUT_MARKDOWN_PATH",
    "MANDATORY_LABELS",
    "NO_LIVE_ORDER_LABEL",
    "NO_REAL_CAPITAL_LABEL",
    "NO_TELEGRAM_COMMAND_AUTHORITY_LABEL",
    "SIMULATED_HISTORICAL_BLIND_TEST_LABEL",
    "TelegramSandboxMessage",
    "TelegramSandboxMessageType",
    "TelegramSandboxOutbox",
    "TelegramSandboxOutboxConfig",
    "TelegramSandboxSeverity",
]
