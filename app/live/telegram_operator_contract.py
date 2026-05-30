"""Telegram Operator Contract (PR110 - Live Foundation v0).

Defines the Telegram operating-desk contract for live preparation:

  - the operator COMMAND contract (/mode, /confirm_live, /capital_profile,
    /risk, /positions, /pnl, /pause, /resume, /kill_all),
  - the LIVE_SHADOW -> LIVE_LIMITED two-step confirmation handshake,
  - the card-type taxonomy + the card field SCHEMA,
  - a deterministic card formatter + an audit-payload builder.

The card schema makes every operator card readable: the *planned*
entry / stop / take-profit / leverage / notional, AND (once a real
execution adapter exists) the *real* entry / exit / pnl / balance /
order ids.

Empty-account (空盘跑 / LIVE_SHADOW) cards:
  - ``real_order=False`` / ``real_capital_changed=False``.
  - ``order_id`` / ``fill_price`` / ``entry_price`` / ... = ``"--"``.
  - the PLANNED fields are fully populated.

Funded (有资金跑 / LIVE_LIMITED) cards:
  - the schema carries the real entry / exit / pnl / balance fields.
  - ``real_order`` only ever becomes True once a real execution adapter
    exists. PR110 has NO such adapter, so
    :data:`LIVE_EXECUTION_ADAPTER_AVAILABLE` is False and ``real_order``
    is forced False on every card.

PR110 boundary: this module formats messages and builds audit payloads
only. It does NOT open a Telegram socket, send a message, place an
order, or flip a Phase 1 safety flag. ``telegram_outbound_enabled``
remains False.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.core.enums import LiveRuntimeMode
from app.exports.redaction import redact

# PR110: no real execution adapter exists. Hard-locks ``real_order`` to
# False on every card regardless of payload.
LIVE_EXECUTION_ADAPTER_AVAILABLE: bool = False

PLACEHOLDER = "--"


# ---------------------------------------------------------------------------
# Operator command contract
# ---------------------------------------------------------------------------
class OperatorCommand:
    """Closed set of Telegram operator commands."""

    MODE = "/mode"
    MODE_SHADOW = "/mode shadow"
    MODE_LIVE_LIMITED = "/mode live_limited"
    CONFIRM_LIVE = "/confirm_live"
    CAPITAL_PROFILE = "/capital_profile"
    CAPITAL_PROFILE_SET = "/capital_profile set"
    RISK = "/risk"
    POSITIONS = "/positions"
    PNL = "/pnl"
    PAUSE = "/pause"
    RESUME = "/resume"
    KILL_ALL = "/kill_all"


OPERATOR_COMMANDS: tuple[str, ...] = (
    OperatorCommand.MODE,
    OperatorCommand.CONFIRM_LIVE,
    OperatorCommand.CAPITAL_PROFILE,
    OperatorCommand.RISK,
    OperatorCommand.POSITIONS,
    OperatorCommand.PNL,
    OperatorCommand.PAUSE,
    OperatorCommand.RESUME,
    OperatorCommand.KILL_ALL,
)

# Commands that change live state and therefore require the operator
# confirmation handshake / are audited as state-changing.
STATE_CHANGING_COMMANDS: frozenset[str] = frozenset(
    {
        OperatorCommand.MODE_LIVE_LIMITED,
        OperatorCommand.CONFIRM_LIVE,
        OperatorCommand.CAPITAL_PROFILE_SET,
        OperatorCommand.KILL_ALL,
    }
)


def parse_operator_command(text: str) -> dict[str, Any]:
    """Parse a raw Telegram command line into ``{command, args, raw}``.

    Deterministic, no IO. Unknown commands are returned with
    ``command=None`` so the caller can reject them. NEVER executes
    anything - parsing only.
    """
    raw = (text or "").strip()
    parts = raw.split()
    if not parts or not parts[0].startswith("/"):
        return {"command": None, "args": [], "raw": raw}
    head = parts[0].lower()
    args = parts[1:]
    command = head if head in {c for c in OPERATOR_COMMANDS} else None
    return {"command": command, "args": args, "raw": raw}


# ---------------------------------------------------------------------------
# Card-type taxonomy
# ---------------------------------------------------------------------------
class OperatorCardType:
    """Closed taxonomy of operator card types."""

    SHADOW_ENTRY_PLAN = "SHADOW_ENTRY_PLAN"
    SHADOW_EXIT_PLAN = "SHADOW_EXIT_PLAN"
    SHADOW_RISK_REJECT = "SHADOW_RISK_REJECT"
    LIVE_ENTRY_SUBMITTED = "LIVE_ENTRY_SUBMITTED"
    LIVE_ENTRY_FILLED = "LIVE_ENTRY_FILLED"
    LIVE_EXIT_SUBMITTED = "LIVE_EXIT_SUBMITTED"
    LIVE_EXIT_FILLED = "LIVE_EXIT_FILLED"
    LIVE_RISK_REJECT = "LIVE_RISK_REJECT"
    LIVE_ACCOUNT_HALTED = "LIVE_ACCOUNT_HALTED"
    LIVE_KILL_SWITCH = "LIVE_KILL_SWITCH"
    LIVE_MODE_CHANGED = "LIVE_MODE_CHANGED"
    CAPITAL_PROFILE_CHANGED = "CAPITAL_PROFILE_CHANGED"
    CAPITAL_EVENT_DETECTED = "CAPITAL_EVENT_DETECTED"


SHADOW_CARD_TYPES: frozenset[str] = frozenset(
    {
        OperatorCardType.SHADOW_ENTRY_PLAN,
        OperatorCardType.SHADOW_EXIT_PLAN,
        OperatorCardType.SHADOW_RISK_REJECT,
    }
)

LIVE_CARD_TYPES: frozenset[str] = frozenset(
    {
        OperatorCardType.LIVE_ENTRY_SUBMITTED,
        OperatorCardType.LIVE_ENTRY_FILLED,
        OperatorCardType.LIVE_EXIT_SUBMITTED,
        OperatorCardType.LIVE_EXIT_FILLED,
        OperatorCardType.LIVE_RISK_REJECT,
        OperatorCardType.LIVE_ACCOUNT_HALTED,
        OperatorCardType.LIVE_KILL_SWITCH,
    }
)

ALL_CARD_TYPES: frozenset[str] = SHADOW_CARD_TYPES | LIVE_CARD_TYPES | frozenset(
    {
        OperatorCardType.LIVE_MODE_CHANGED,
        OperatorCardType.CAPITAL_PROFILE_CHANGED,
        OperatorCardType.CAPITAL_EVENT_DETECTED,
    }
)


# ---------------------------------------------------------------------------
# Card field schema
# ---------------------------------------------------------------------------
COMMON_FIELDS: tuple[str, ...] = (
    "mode_display",
    "runtime_mode",
    "capital_profile_id",
    "symbol",
    "side",
    "candidate_stage",
    "opportunity_score",
    "risk_decision",
    "event_id",
    "opportunity_id",
    "timestamp",
)

PLANNED_FIELDS: tuple[str, ...] = (
    "planned_entry_zone",
    "planned_entry_price",
    "planned_stop_price",
    "planned_take_profit_1",
    "planned_take_profit_2",
    "planned_exit_reason",
    "planned_notional_usdt",
    "planned_leverage",
)

REAL_ORDER_FIELDS: tuple[str, ...] = (
    "order_id",
    "client_order_id",
    "entry_order_id",
    "exit_order_id",
    "fill_price",
    "entry_price",
    "exit_price",
    "quantity",
    "notional_usdt",
    "leverage",
    "fee_usdt",
    "slippage_bps",
    "realized_pnl_usdt",
    "pnl_pct",
    "balance_before",
    "balance_after",
    "equity_after",
)

MODE_DISPLAY: dict[LiveRuntimeMode, str] = {
    LiveRuntimeMode.LIVE_SHADOW: "空盘跑",
    LiveRuntimeMode.LIVE_LIMITED: "有资金跑",
}


def _is_shadow_card(card_type: str, runtime_mode: LiveRuntimeMode | None) -> bool:
    if card_type in SHADOW_CARD_TYPES:
        return True
    if card_type in LIVE_CARD_TYPES:
        return False
    # Status cards follow the runtime mode (default shadow).
    return runtime_mode is None or runtime_mode is LiveRuntimeMode.LIVE_SHADOW


def build_operator_card(
    card_type: str,
    payload: Mapping[str, Any] | None = None,
    *,
    runtime_mode: LiveRuntimeMode | None = None,
) -> dict[str, Any]:
    """Build a fully-populated operator card following the PR110 schema.

    The returned dict ALWAYS contains every common + planned + real
    field key (so the schema is stable and auditable). Empty-account
    (shadow) cards fill the real fields with ``"--"`` and force
    ``real_order=False``; funded cards carry the real fields, but
    ``real_order`` is still forced False in PR110 (no execution adapter).
    """
    if card_type not in ALL_CARD_TYPES:
        raise ValueError(f"unknown operator card_type: {card_type!r}")
    p = dict(payload or {})
    is_shadow = _is_shadow_card(card_type, runtime_mode)
    mode = runtime_mode or (
        LiveRuntimeMode.LIVE_SHADOW if is_shadow else LiveRuntimeMode.LIVE_LIMITED
    )

    card: dict[str, Any] = {"card_type": card_type}

    # Common fields.
    for fld in COMMON_FIELDS:
        if fld == "mode_display":
            card[fld] = MODE_DISPLAY.get(mode, MODE_DISPLAY[LiveRuntimeMode.LIVE_SHADOW])
        elif fld == "runtime_mode":
            card[fld] = mode.value
        else:
            card[fld] = p.get(fld, PLACEHOLDER)

    # Planned fields - ALWAYS populated from the payload (mandatory on
    # shadow cards; informative on live cards).
    for fld in PLANNED_FIELDS:
        card[fld] = p.get(fld, PLACEHOLDER)

    # Real-order fields.
    if is_shadow:
        card["real_order"] = False
        card["real_capital_changed"] = False
        for fld in REAL_ORDER_FIELDS:
            card[fld] = PLACEHOLDER
    else:
        # PR110: real_order can only be True once a live adapter exists.
        card["real_order"] = bool(p.get("real_order", False)) and LIVE_EXECUTION_ADAPTER_AVAILABLE
        card["real_capital_changed"] = (
            bool(p.get("real_capital_changed", False)) and LIVE_EXECUTION_ADAPTER_AVAILABLE
        )
        for fld in REAL_ORDER_FIELDS:
            card[fld] = p.get(fld, PLACEHOLDER)

    # Kill-switch / safety markers visible on every card.
    card["kill_switch_armed"] = bool(p.get("kill_switch_armed", False))
    card["live_trading"] = False
    card["binance_private_api_enabled"] = False
    card["telegram_outbound_enabled"] = False
    return card


def render_operator_card(card: Mapping[str, Any]) -> str:
    """Render a short, redacted one-line display string for a card."""
    c = redact(dict(card))
    parts = [
        f"[ama-rt:live:{c.get('card_type', '?')}]",
        f"mode={c.get('mode_display')}/{c.get('runtime_mode')}",
        f"profile={c.get('capital_profile_id')}",
        f"sym={c.get('symbol')}",
        f"side={c.get('side')}",
        f"plan_entry={c.get('planned_entry_price')}",
        f"plan_stop={c.get('planned_stop_price')}",
        f"plan_tp1={c.get('planned_take_profit_1')}",
        f"plan_lev={c.get('planned_leverage')}",
        f"real_order={c.get('real_order')}",
        f"order_id={c.get('order_id')}",
        f"fill={c.get('fill_price')}",
        f"pnl={c.get('realized_pnl_usdt')}",
        f"bal_after={c.get('balance_after')}",
        f"risk={c.get('risk_decision')}",
        f"kill_switch={c.get('kill_switch_armed')}",
    ]
    return " ".join(parts)


def build_audit_payload(card: Mapping[str, Any]) -> dict[str, Any]:
    """Return a redacted audit payload for a card.

    Defence-in-depth: routes the card through the Phase 8.5 redactor so
    an accidental credential in the payload can never reach an audit
    log, and stamps the PR110 safety markers.
    """
    payload = redact(dict(card))
    payload.update(
        {
            "live_trading": False,
            "exchange_live_orders": False,
            "binance_private_api_enabled": False,
            "telegram_outbound_enabled": False,
            "ai_trade_authority": False,
            "phase_12_forbidden": True,
            "live_execution_adapter_available": LIVE_EXECUTION_ADAPTER_AVAILABLE,
        }
    )
    return payload


__all__ = [
    "LIVE_EXECUTION_ADAPTER_AVAILABLE",
    "PLACEHOLDER",
    "OperatorCommand",
    "OPERATOR_COMMANDS",
    "STATE_CHANGING_COMMANDS",
    "parse_operator_command",
    "OperatorCardType",
    "SHADOW_CARD_TYPES",
    "LIVE_CARD_TYPES",
    "ALL_CARD_TYPES",
    "COMMON_FIELDS",
    "PLANNED_FIELDS",
    "REAL_ORDER_FIELDS",
    "MODE_DISPLAY",
    "build_operator_card",
    "render_operator_card",
    "build_audit_payload",
]
