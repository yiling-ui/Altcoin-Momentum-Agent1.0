"""Telegram message formatters (Phase 10D - Issue #10 Part 4).

The 10 formatters required by the Issue #10 Part 4 brief, replacing
the Phase 1 placeholders. Each formatter:

  - Is a *pure function* (string in, string out, no IO, no network).
  - Returns a SHORT human-readable line suitable for Telegram. NEVER
    a raw event dump; full payloads belong in `/export_*` documents.
  - Carries a ``mode=PAPER|LIVE_LIMITED|LIVE`` banner so the operator
    can never confuse a paper-mode message with a live-trading audit.
  - Carries an explicit ``live=on/off`` token so the live-trading flag
    is in front of the operator on every message.
  - Routes its output through :func:`app.exports.redaction.redact`
    before returning so accidental credentials in the input dict can
    never reach the wire.

The Phase 1 placeholder shape (``[PHASE1-SKELETON] <name> ...``) is
gone; the new tag is a stable ``[ama-rt:<topic>]`` prefix that
monitoring can grep for.

Phase 10D boundary
------------------

  - No formatter calls a Risk Engine surface.
  - No formatter mutates state.
  - No formatter touches an exchange / LLM / Telegram client.
  - No formatter reads ``os.environ``.
  - No formatter sends a message; that is the AlertDispatcher's job.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.exports.redaction import REDACTED, redact


# Stable topic tags (used by the AlertDispatcher dedupe key + by the
# operator-facing search string).
TAG_SYSTEM_STATUS = "system_status"
TAG_MARKET_REGIME = "market_regime"
TAG_CANDIDATE_SYMBOL = "candidate_symbol"
TAG_STATE_TRANSITION = "state_transition"
TAG_ORDER_EVENT = "order_event"
TAG_RISK_REJECTION = "risk_rejection"
TAG_PROFIT_LOCK = "profit_lock"
TAG_CAPITAL_REBASE = "capital_rebase"
TAG_INCIDENT_ALERT = "incident_alert"
TAG_DAILY_REPORT = "daily_report"

ALL_TAGS = (
    TAG_SYSTEM_STATUS,
    TAG_MARKET_REGIME,
    TAG_CANDIDATE_SYMBOL,
    TAG_STATE_TRANSITION,
    TAG_ORDER_EVENT,
    TAG_RISK_REJECTION,
    TAG_PROFIT_LOCK,
    TAG_CAPITAL_REBASE,
    TAG_INCIDENT_ALERT,
    TAG_DAILY_REPORT,
)


# Issue brief - the six high-priority risk-rejection reasons that the
# /risk_rejection formatter MUST surface verbatim when present in the
# upstream payload.
HIGH_PRIORITY_REJECT_REASONS = (
    "stop_unconfirmed",
    "unknown_position",
    "rebase_in_progress",
    "manipulation_m3",
    "data_degraded",
    "no_exit_channel",
)

# Phase 10D allowed trading modes (Spec §10.2 + Phase 1 lock).
TRADING_MODE_PAPER = "PAPER"
TRADING_MODE_LIVE_LIMITED = "LIVE_LIMITED"
TRADING_MODE_LIVE = "LIVE"
ALLOWED_TRADING_MODES = (
    TRADING_MODE_PAPER,
    TRADING_MODE_LIVE_LIMITED,
    TRADING_MODE_LIVE,
)


def _normalise_trading_mode(value: Any) -> str:
    """Map any incoming trading_mode to the canonical PAPER / LIVE_LIMITED / LIVE."""
    if value is None:
        return TRADING_MODE_PAPER
    if isinstance(value, str):
        upper = value.strip().upper()
        if upper in ALLOWED_TRADING_MODES:
            return upper
        if upper.startswith("LIVE_LIM"):
            return TRADING_MODE_LIVE_LIMITED
        if upper == "LIVE":
            return TRADING_MODE_LIVE
        return TRADING_MODE_PAPER
    return TRADING_MODE_PAPER


def _normalise_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _banner(payload: Mapping[str, Any]) -> str:
    """Return the canonical banner prefix every Phase 10D message carries.

    Format: ``mode=<MODE> live=on|off`` - short enough to fit on the
    first line of every message regardless of topic.
    """
    mode = _normalise_trading_mode(payload.get("trading_mode"))
    live = _normalise_bool(payload.get("live_trading_enabled"))
    return f"mode={mode} live={'on' if live else 'off'}"


def _short(value: Any, *, max_len: int = 80) -> str:
    """Return a short string representation of ``value``.

    Defence-in-depth: long values are truncated to ``max_len`` and
    suffixed with an ellipsis so a maliciously long payload cannot
    push a Telegram message over the size limit.
    """
    if value is None:
        return "-"
    s = str(value)
    s = s.replace("\n", " ").replace("\r", " ").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "\u2026"


def _list(value: Any, *, max_items: int = 6) -> str:
    """Render a list-like value as ``a,b,c`` with truncation."""
    if value is None:
        return "-"
    if isinstance(value, str):
        items = [v.strip() for v in value.split(",") if v.strip()]
    else:
        try:
            items = [str(v) for v in value]
        except TypeError:
            return _short(value)
    if not items:
        return "-"
    if len(items) > max_items:
        items = list(items[:max_items]) + [f"+{len(items) - max_items}"]
    return ",".join(items)


def _redact_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Walk ``payload`` through the Phase 8.5 redactor.

    The redactor returns a new dict with every credential-shaped key
    or value replaced by ``[REDACTED]``. Used by every formatter.
    """
    return redact(dict(payload))


def _line(*, tag: str, banner: str, body: str) -> str:
    """Compose one canonical Phase 10D message: ``[ama-rt:<tag>] <banner> <body>``."""
    return f"[ama-rt:{tag}] {banner} {body}".rstrip()


# ---------------------------------------------------------------------------
# 1. System status
# ---------------------------------------------------------------------------
def format_system_status(payload: Mapping[str, Any]) -> str:
    """``/status`` reply + heartbeat / pause / resume / protection-mode push.

    Expected keys (all optional except ``trading_mode``):

    - ``trading_mode``: PAPER | LIVE_LIMITED | LIVE
    - ``live_trading_enabled``: bool
    - ``status``: e.g. ``running`` / ``paused`` / ``protection_mode``
    - ``new_opens_paused``: bool
    - ``protection_mode_active``: bool
    - ``open_positions``: int
    - ``open_orders``: int
    - ``incidents_open``: int
    - ``health``: ``ok`` / ``degraded``
    - ``app_version`` / ``phase``
    """
    p = _redact_payload(payload)
    banner = _banner(p)
    parts = [
        f"status={_short(p.get('status'), max_len=20)}",
        f"new_opens_paused={_normalise_bool(p.get('new_opens_paused'))}",
        f"protection={_normalise_bool(p.get('protection_mode_active'))}",
        f"open_pos={_short(p.get('open_positions'), max_len=8)}",
        f"open_ord={_short(p.get('open_orders'), max_len=8)}",
        f"incidents={_short(p.get('incidents_open'), max_len=4)}",
        f"health={_short(p.get('health'), max_len=12)}",
    ]
    if "app_version" in p or "phase" in p:
        parts.append(
            f"version={_short(p.get('app_version'), max_len=24)}/{_short(p.get('phase'), max_len=24)}"
        )
    return _line(tag=TAG_SYSTEM_STATUS, banner=banner, body=" ".join(parts))


# ---------------------------------------------------------------------------
# 2. Market regime - REGIME_UPDATED (Spec §15)
# ---------------------------------------------------------------------------
def format_market_regime(payload: Mapping[str, Any]) -> str:
    """REGIME_UPDATED push: alert when the market regime flips.

    Highlights SYSTEMIC_RISK / ALT_RISK_OFF because those forbid every
    new opening (Spec §15.3 + §27.2).
    """
    p = _redact_payload(payload)
    banner = _banner(p)
    regime = _short(p.get("market_regime"), max_len=24)
    risk_perm = _short(p.get("risk_permission"), max_len=24)
    parts = [
        f"regime={regime}",
        f"risk_permission={risk_perm}",
        f"btc_trend={_short(p.get('btc_trend'), max_len=16)}",
        f"btc_vol={_short(p.get('btc_volatility'), max_len=16)}",
        f"alt_liq={_short(p.get('alt_liquidity'), max_len=16)}",
    ]
    # Surface high-severity regimes loud and explicit.
    if regime.upper() == "SYSTEMIC_RISK":
        parts.insert(0, "[!] SYSTEMIC_RISK - new opens forbidden")
    elif regime.upper() == "ALT_RISK_OFF":
        parts.insert(0, "[!] ALT_RISK_OFF - scout-only")
    if "reason_tags" in p:
        parts.append(f"tags={_list(p.get('reason_tags'))}")
    return _line(tag=TAG_MARKET_REGIME, banner=banner, body=" ".join(parts))


# ---------------------------------------------------------------------------
# 3. Candidate symbol - PRE_ANOMALY_DETECTED / ANOMALY_DETECTED
# ---------------------------------------------------------------------------
def format_candidate_symbol(payload: Mapping[str, Any]) -> str:
    """High-grade candidate push (A / S grade + supporting scores)."""
    p = _redact_payload(payload)
    banner = _banner(p)
    grade = _short(p.get("grade"), max_len=4).upper()
    parts = [
        f"sym={_short(p.get('symbol'), max_len=24)}",
        f"grade={grade or '-'}",
        f"pre_anomaly={_short(p.get('pre_anomaly_score'), max_len=12)}",
        f"anomaly={_short(p.get('anomaly_score'), max_len=12)}",
        f"trade_conf={_short(p.get('trade_confirmation_level'), max_len=8)}",
        f"manip={_short(p.get('manipulation_level'), max_len=8)}",
    ]
    if "regime" in p:
        parts.append(f"regime={_short(p.get('regime'), max_len=24)}")
    if "opportunity_id" in p:
        parts.append(f"opp={_short(p.get('opportunity_id'), max_len=40)}")
    if "reason_tags" in p:
        parts.append(f"tags={_list(p.get('reason_tags'))}")
    return _line(tag=TAG_CANDIDATE_SYMBOL, banner=banner, body=" ".join(parts))


# ---------------------------------------------------------------------------
# 4. State transition - STATE_TRANSITION (Spec §26)
# ---------------------------------------------------------------------------
def format_state_transition(payload: Mapping[str, Any]) -> str:
    """OBSERVE -> SCOUT -> CONFIRM -> ATTACK ladder push."""
    p = _redact_payload(payload)
    banner = _banner(p)
    parts = [
        f"sym={_short(p.get('symbol'), max_len=24)}",
        f"{_short(p.get('from'), max_len=24)}->{_short(p.get('to'), max_len=24)}",
        f"trigger={_short(p.get('trigger'), max_len=24)}",
    ]
    if "opportunity_id" in p:
        parts.append(f"opp={_short(p.get('opportunity_id'), max_len=40)}")
    if "reasons" in p:
        parts.append(f"reasons={_list(p.get('reasons'))}")
    if "event_id" in p:
        parts.append(f"event_id={_short(p.get('event_id'), max_len=36)}")
    return _line(tag=TAG_STATE_TRANSITION, banner=banner, body=" ".join(parts))


# ---------------------------------------------------------------------------
# 5. Order event - ORDER_SENT / FILLED / CANCELLED / STOP_*
# ---------------------------------------------------------------------------
def format_order_event(payload: Mapping[str, Any]) -> str:
    """Order / stop / position event push (Spec §30)."""
    p = _redact_payload(payload)
    banner = _banner(p)
    event = _short(p.get("event"), max_len=24)
    parts = [
        f"event={event}",
        f"sym={_short(p.get('symbol'), max_len=24)}",
        f"side={_short(p.get('side'), max_len=8)}",
        f"intent={_short(p.get('intent'), max_len=24)}",
        f"qty={_short(p.get('qty'), max_len=16)}",
    ]
    if "fill_price" in p:
        parts.append(f"fill={_short(p.get('fill_price'), max_len=16)}")
    if "limit_price" in p:
        parts.append(f"limit={_short(p.get('limit_price'), max_len=16)}")
    if "stop_price" in p:
        parts.append(f"stop={_short(p.get('stop_price'), max_len=16)}")
    if "reduce_only" in p:
        parts.append(f"reduce_only={_normalise_bool(p.get('reduce_only'))}")
    if "client_order_id" in p:
        parts.append(f"coid={_short(p.get('client_order_id'), max_len=40)}")
    if "opportunity_id" in p:
        parts.append(f"opp={_short(p.get('opportunity_id'), max_len=40)}")
    if "event_id" in p:
        parts.append(f"event_id={_short(p.get('event_id'), max_len=36)}")
    return _line(tag=TAG_ORDER_EVENT, banner=banner, body=" ".join(parts))


# ---------------------------------------------------------------------------
# 6. Risk rejection - RISK_REJECTED (Spec §27)
# ---------------------------------------------------------------------------
def format_risk_rejection(payload: Mapping[str, Any]) -> str:
    """Risk-engine rejection push.

    The Issue brief mandates that the formatter surface six
    high-priority reasons when present in ``payload['reasons']``:

      stop_unconfirmed / unknown_position / rebase_in_progress /
      manipulation_m3 / data_degraded / no_exit_channel

    Each surfaces with a ``[!]`` warning prefix so the operator never
    misses one. ``stop_unconfirmed`` and ``unknown_position`` are
    severity-CRITICAL (per Phase 1 review-fix) and the dispatcher MUST
    bypass throttle for them.
    """
    p = _redact_payload(payload)
    banner = _banner(p)
    raw_reasons = p.get("reasons") or p.get("reject_reasons") or ()
    if isinstance(raw_reasons, str):
        reasons_list = [r.strip() for r in raw_reasons.split(",") if r.strip()]
    else:
        try:
            reasons_list = [str(r).strip() for r in raw_reasons]
        except TypeError:
            reasons_list = []
    reasons_lower = {r.lower() for r in reasons_list}
    high_priority_present = [
        r for r in HIGH_PRIORITY_REJECT_REASONS if r in reasons_lower
    ]
    parts = [
        f"sym={_short(p.get('symbol'), max_len=24)}",
        f"action={_short(p.get('action'), max_len=24)}",
    ]
    if "regime" in p:
        parts.append(f"regime={_short(p.get('regime'), max_len=24)}")
    if "manipulation_level" in p:
        parts.append(f"manip={_short(p.get('manipulation_level'), max_len=8)}")
    if "trade_confirmation_level" in p:
        parts.append(
            f"trade_conf={_short(p.get('trade_confirmation_level'), max_len=8)}"
        )
    if "account_tier" in p:
        parts.append(f"tier={_short(p.get('account_tier'), max_len=4)}")
    if reasons_list:
        parts.append(f"reasons={_list(reasons_list, max_items=8)}")
    if high_priority_present:
        parts.append("[!] " + ",".join(high_priority_present))
    if "opportunity_id" in p:
        parts.append(f"opp={_short(p.get('opportunity_id'), max_len=40)}")
    if "event_id" in p:
        parts.append(f"event_id={_short(p.get('event_id'), max_len=36)}")
    return _line(tag=TAG_RISK_REJECTION, banner=banner, body=" ".join(parts))


# ---------------------------------------------------------------------------
# 7. Profit lock - LOCK_PROFIT / EXIT_TRIGGERED / POSITION_CLOSED
# ---------------------------------------------------------------------------
def format_profit_lock(payload: Mapping[str, Any]) -> str:
    """Profit-lock / forced-exit / right-tail-amplify summary push."""
    p = _redact_payload(payload)
    banner = _banner(p)
    parts = [
        f"sym={_short(p.get('symbol'), max_len=24)}",
        f"action={_short(p.get('action'), max_len=24)}",
        f"realized_pnl={_short(p.get('realized_pnl'), max_len=16)}",
        f"unrealized_pnl={_short(p.get('unrealized_pnl'), max_len=16)}",
    ]
    if "entry_price" in p:
        parts.append(f"entry={_short(p.get('entry_price'), max_len=16)}")
    if "exit_price" in p:
        parts.append(f"exit={_short(p.get('exit_price'), max_len=16)}")
    if "tail_qty" in p:
        parts.append(f"tail_qty={_short(p.get('tail_qty'), max_len=16)}")
    if "right_tail" in p:
        parts.append(f"right_tail={_normalise_bool(p.get('right_tail'))}")
    if "opportunity_id" in p:
        parts.append(f"opp={_short(p.get('opportunity_id'), max_len=40)}")
    if "event_id" in p:
        parts.append(f"event_id={_short(p.get('event_id'), max_len=36)}")
    return _line(tag=TAG_PROFIT_LOCK, banner=banner, body=" ".join(parts))


# ---------------------------------------------------------------------------
# 8. Capital rebase - PROFIT_HARVEST / CAPITAL_REBASE / RISK_BUDGET_RECALCULATED
# ---------------------------------------------------------------------------
def format_capital_rebase(payload: Mapping[str, Any]) -> str:
    """Capital event push (Spec §28).

    A withdrawal is NOT a loss; the formatter surfaces the
    ``net_trading_pnl`` and the new ``trading_capital`` so the
    operator never confuses a rebase with a draw-down.
    """
    p = _redact_payload(payload)
    banner = _banner(p)
    parts = [
        f"event={_short(p.get('event'), max_len=24)}",
        f"trading_capital={_short(p.get('trading_capital'), max_len=16)}",
        f"exchange_equity={_short(p.get('exchange_equity'), max_len=16)}",
        f"withdrawn_profit={_short(p.get('withdrawn_profit'), max_len=16)}",
        f"lifetime_equity={_short(p.get('lifetime_equity'), max_len=16)}",
        f"net_trading_pnl={_short(p.get('net_trading_pnl'), max_len=16)}",
    ]
    if "withdrawal_type" in p:
        parts.append(f"type={_short(p.get('withdrawal_type'), max_len=24)}")
    if "principal_part" in p:
        parts.append(f"principal_part={_short(p.get('principal_part'), max_len=16)}")
    if "profit_part" in p:
        parts.append(f"profit_part={_short(p.get('profit_part'), max_len=16)}")
    if "rebase_in_progress" in p:
        parts.append(
            f"rebase_in_progress={_normalise_bool(p.get('rebase_in_progress'))}"
        )
    if "event_id" in p:
        parts.append(f"event_id={_short(p.get('event_id'), max_len=36)}")
    return _line(tag=TAG_CAPITAL_REBASE, banner=banner, body=" ".join(parts))


# ---------------------------------------------------------------------------
# 9. Incident alert - INCIDENT_OPENED / PROTECTION_MODE_ENTERED
# ---------------------------------------------------------------------------
def format_incident_alert(payload: Mapping[str, Any]) -> str:
    """Incident push (Spec §38). P0 / P1 bypass throttle in the dispatcher."""
    p = _redact_payload(payload)
    banner = _banner(p)
    level = _short(p.get("level"), max_len=4).upper()
    parts = [
        f"level={level or 'P?'}",
        f"sym={_short(p.get('symbol'), max_len=24)}",
        f"title={_short(p.get('title'), max_len=64)}",
    ]
    if level in {"P0", "P1"}:
        parts.insert(0, f"[!] {level}")
    if "incident_id" in p:
        parts.append(f"incident_id={_short(p.get('incident_id'), max_len=36)}")
    if "protection_mode_active" in p:
        parts.append(
            f"protection={_normalise_bool(p.get('protection_mode_active'))}"
        )
    if "new_opens_paused" in p:
        parts.append(
            f"new_opens_paused={_normalise_bool(p.get('new_opens_paused'))}"
        )
    if "resolution" in p:
        parts.append(f"resolution={_short(p.get('resolution'), max_len=32)}")
    return _line(tag=TAG_INCIDENT_ALERT, banner=banner, body=" ".join(parts))


# ---------------------------------------------------------------------------
# 10. Daily report - end-of-day summary
# ---------------------------------------------------------------------------
def format_daily_report(payload: Mapping[str, Any]) -> str:
    """End-of-day summary push.

    A SHORT summary; the full report ships via ``/export_report
    today`` as a redacted document attachment.
    """
    p = _redact_payload(payload)
    banner = _banner(p)
    parts = [
        f"date={_short(p.get('date'), max_len=20)}",
        f"trades={_short(p.get('trade_count'), max_len=8)}",
        f"approved={_short(p.get('risk_approved_count'), max_len=8)}",
        f"rejected={_short(p.get('risk_rejected_count'), max_len=8)}",
        f"net_pnl={_short(p.get('net_trading_pnl'), max_len=16)}",
        f"incidents={_short(p.get('incidents_count'), max_len=4)}",
        f"protection_mode={_normalise_bool(p.get('protection_mode_active'))}",
    ]
    if "top_reject_reason" in p:
        parts.append(
            f"top_reject={_short(p.get('top_reject_reason'), max_len=32)}"
        )
    if "top_symbol" in p:
        parts.append(f"top_sym={_short(p.get('top_symbol'), max_len=24)}")
    return _line(tag=TAG_DAILY_REPORT, banner=banner, body=" ".join(parts))


# ---------------------------------------------------------------------------
# Public registry so the AlertDispatcher and tests can iterate.
# ---------------------------------------------------------------------------
FORMATTERS: dict[str, Any] = {
    TAG_SYSTEM_STATUS: format_system_status,
    TAG_MARKET_REGIME: format_market_regime,
    TAG_CANDIDATE_SYMBOL: format_candidate_symbol,
    TAG_STATE_TRANSITION: format_state_transition,
    TAG_ORDER_EVENT: format_order_event,
    TAG_RISK_REJECTION: format_risk_rejection,
    TAG_PROFIT_LOCK: format_profit_lock,
    TAG_CAPITAL_REBASE: format_capital_rebase,
    TAG_INCIDENT_ALERT: format_incident_alert,
    TAG_DAILY_REPORT: format_daily_report,
}


__all__ = [
    "format_system_status",
    "format_market_regime",
    "format_candidate_symbol",
    "format_state_transition",
    "format_order_event",
    "format_risk_rejection",
    "format_profit_lock",
    "format_capital_rebase",
    "format_incident_alert",
    "format_daily_report",
    "FORMATTERS",
    "ALL_TAGS",
    "HIGH_PRIORITY_REJECT_REASONS",
    "ALLOWED_TRADING_MODES",
    "TRADING_MODE_PAPER",
    "TRADING_MODE_LIVE_LIMITED",
    "TRADING_MODE_LIVE",
    "TAG_SYSTEM_STATUS",
    "TAG_MARKET_REGIME",
    "TAG_CANDIDATE_SYMBOL",
    "TAG_STATE_TRANSITION",
    "TAG_ORDER_EVENT",
    "TAG_RISK_REJECTION",
    "TAG_PROFIT_LOCK",
    "TAG_CAPITAL_REBASE",
    "TAG_INCIDENT_ALERT",
    "TAG_DAILY_REPORT",
    "REDACTED",
]
