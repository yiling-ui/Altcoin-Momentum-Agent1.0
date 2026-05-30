"""Telegram operator command contract (PR114 - Operator Console v0).

The deterministic core of the live operator console. It parses an
operator command, enforces the live-source isolation boundary, mutates
the persisted live state (mode / confirmation / capital profile / kill
switch) through safe handshakes, and returns an operator card + a short
rendered text line.

Command contract (the brief):

  /help                 - command list + current mode.
  /status               - runtime mode + profile + safety flags + API
                          health + open positions + equity.
  /mode                 - show current mode + whether real orders allowed.
  /mode shadow          - switch back to LIVE_SHADOW; disarm LIVE_LIMITED.
  /mode live_limited    - DOES NOT switch; returns a risk summary +
                          confirmation code.
  /confirm_live CODE    - arm LIVE_LIMITED iff the code matches + not
                          expired + the profile allows real orders.
  /positions            - per-position view + funding attribution status.
  /pnl                  - gross / commission / funding / net + flows.
  /risk                 - profile limits + loss state + halts + kill sw.
  /capital              - wallet / available / equity + flows + mismatch.
  /profile              - current + recommended profile.
  /profile set <ID>     - request a profile change (escalation needs ack).
  /pause                - pause NEW entries.
  /resume               - resume scanning (does NOT bypass gates).
  /kill_all             - request kill switch (returns a confirm code).
  /confirm_kill CODE    - arm the kill switch.

HARD boundaries (the brief): a Telegram command can NEVER place a naked
order, bypass the Risk Engine, bypass the Execution Gateway, bypass the
Capital Profile, bypass the kill switch, or be driven by a non-LIVE
source (blind / replay / sim / paper-shadow / backtest / offline-AI /
telegram-sandbox). Arming LIVE_LIMITED never by itself enables real
orders - ``exchange_live_orders`` / ``trade_authority`` / private trade
remain config-gated, and a real order still passes the PR113 gate.

This module performs ONLY local state IO (through the state store). It
NEVER opens a network socket, NEVER places an order, and NEVER flips a
Phase 1 safety flag.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.clock import now_ms
from app.core.enums import LiveRuntimeMode, OrderSource
from app.core.errors import LiveSourceRejected
from app.core.events import Event, EventType
from app.live import telegram_formatters as fmt
from app.live.capital_profile import (
    CAPITAL_PROFILE_ORDER,
    CapitalProfileId,
    get_profile,
)
from app.live.telegram_auth import LiveSourceGuard
from app.live.telegram_state import (
    CapitalProfileStateRecord,
    ConfirmationState,
    KillSwitchState,
    LiveOperatorStateStore,
    RuntimeModeState,
)

TELEGRAM_COMMANDS_MODULE = "live.telegram_commands"

DEFAULT_CONFIRMATION_TTL_MS = 5 * 60 * 1000  # 5 minutes

# State-changing commands (audited + source-isolated).
_STATE_CHANGING: frozenset[str] = frozenset(
    {
        "/mode shadow",
        "/mode live_limited",
        "/confirm_live",
        "/profile set",
        "/pause",
        "/resume",
        "/kill_all",
        "/confirm_kill",
    }
)

# The full operator command list shown by /help.
HELP_COMMANDS: tuple[str, ...] = (
    "/help",
    "/status",
    "/mode",
    "/mode shadow",
    "/mode live_limited",
    "/confirm_live CODE",
    "/positions",
    "/pnl",
    "/risk",
    "/capital",
    "/profile",
    "/profile set <PROFILE_ID>",
    "/pause",
    "/resume",
    "/kill_all",
    "/confirm_kill CODE",
)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ParsedCommand:
    """A parsed operator command (head + canonical key + args)."""

    raw: str
    head: str
    key: str
    args: tuple[str, ...]

    @property
    def is_known(self) -> bool:
        return self.key != ""


_TWO_WORD_HEADS = {"/mode", "/profile"}


def parse_command(text: str) -> ParsedCommand:
    """Parse a raw command line into ``ParsedCommand`` (deterministic, no IO).

    Recognises the multi-word forms ``/mode shadow``, ``/mode live_limited``
    and ``/profile set``. Unknown commands carry ``key=""``.
    """
    raw = (text or "").strip()
    parts = raw.split()
    if not parts or not parts[0].startswith("/"):
        return ParsedCommand(raw=raw, head="", key="", args=())
    head = parts[0].lower()
    rest = parts[1:]

    known_singles = {
        "/help",
        "/status",
        "/positions",
        "/pnl",
        "/risk",
        "/capital",
        "/pause",
        "/resume",
        "/kill_all",
        "/confirm_live",
        "/confirm_kill",
    }

    if head == "/mode":
        if rest and rest[0].lower() in ("shadow", "live_limited"):
            return ParsedCommand(raw=raw, head=head, key=f"/mode {rest[0].lower()}", args=tuple(rest[1:]))
        return ParsedCommand(raw=raw, head=head, key="/mode", args=tuple(rest))
    if head == "/profile":
        if rest and rest[0].lower() == "set":
            return ParsedCommand(raw=raw, head=head, key="/profile set", args=tuple(rest[1:]))
        return ParsedCommand(raw=raw, head=head, key="/profile", args=tuple(rest))
    if head in known_singles:
        return ParsedCommand(raw=raw, head=head, key=head, args=tuple(rest))
    return ParsedCommand(raw=raw, head=head, key="", args=tuple(rest))


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CommandResult:
    """Outcome of handling one operator command."""

    command: str
    ok: bool
    card: dict[str, Any]
    text: str
    reason: str = ""
    state_changed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "ok": self.ok,
            "card": self.card,
            "text": self.text,
            "reason": self.reason,
            "state_changed": self.state_changed,
        }


# ---------------------------------------------------------------------------
# Data provider
# ---------------------------------------------------------------------------
class LiveConsoleDataProvider:
    """Supplies read-only snapshots for the status / pnl / risk / ... cards.

    The default base returns safe, empty snapshots so the console works in
    dry-run / no-account mode. The operator runtime injects a real
    provider that reads from the PR112 live capital service. A provider
    NEVER places an order; it only reads.
    """

    def safety_flags(self) -> dict[str, Any]:
        return {
            "exchange_live_orders": False,
            "trade_authority_flag": False,
            "private_trade_enabled": False,
            "binance_public_status": None,
            "binance_private_read_status": None,
            "telegram_outbound_status": None,
            "deepseek_status": None,
        }

    def account_status(self) -> dict[str, Any]:
        return {}

    def positions(self) -> list[dict[str, Any]]:
        return []

    def pnl(self) -> dict[str, Any]:
        return {}

    def risk(self) -> dict[str, Any]:
        return {}

    def capital(self) -> dict[str, Any]:
        return {}

    def account_equity_usdt(self) -> float | None:
        return None

    def funding_attribution_status(self) -> str | None:
        return None


# ---------------------------------------------------------------------------
# Command handler
# ---------------------------------------------------------------------------
class TelegramCommandHandler:
    """Deterministic operator-command handler (PR114).

    Owns the persisted live state through a :class:`LiveOperatorStateStore`
    and a live-source isolation guard. Construct it once; it loads state on
    init and persists on every mutation.
    """

    def __init__(
        self,
        *,
        state_store: LiveOperatorStateStore,
        data_provider: LiveConsoleDataProvider | None = None,
        source_guard: LiveSourceGuard | None = None,
        event_repo: Any | None = None,
        clock: Callable[[], int] = now_ms,
        confirmation_ttl_ms: int = DEFAULT_CONFIRMATION_TTL_MS,
        kill_switch_callback: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._store = state_store
        self._data = data_provider or LiveConsoleDataProvider()
        self._source_guard = source_guard or LiveSourceGuard(event_repo=event_repo)
        self._event_repo = event_repo
        self._clock = clock
        self._ttl = int(confirmation_ttl_ms)
        # An OPTIONAL callback that, if wired, performs a controlled
        # cancel/exit through the PR113 execution gateway + safety gate.
        # PR114 default is None (kill switch only arms + alerts).
        self._kill_switch_callback = kill_switch_callback
        self._load()

    # -- state load / reload ------------------------------------------
    def _load(self) -> None:
        state = self._store.load()
        self._runtime = state.runtime
        self._confirmation = state.confirmation
        self._profile = state.capital_profile
        self._kill = state.kill_switch
        self._load_warnings = list(state.warnings)

    def reload(self) -> None:
        """Re-read the persisted state (used after a restart)."""
        self._load()

    # -- read-only accessors ------------------------------------------
    @property
    def runtime_mode(self) -> LiveRuntimeMode:
        return self._runtime.runtime_mode

    @property
    def live_limited_armed(self) -> bool:
        return bool(self._runtime.live_limited_armed)

    @property
    def paused(self) -> bool:
        return bool(self._runtime.paused)

    @property
    def capital_profile_id(self) -> CapitalProfileId:
        return self._profile.capital_profile_id

    @property
    def kill_switch_armed(self) -> bool:
        return bool(self._kill.armed)

    @property
    def load_warnings(self) -> list[str]:
        return list(self._load_warnings)

    # -- dispatch ------------------------------------------------------
    def handle(
        self,
        text: str,
        *,
        source: OrderSource | str = OrderSource.LIVE,
        actor: str = "operator",
    ) -> CommandResult:
        """Parse + handle one operator command.

        ``source`` is the provenance of the actor; only ``OrderSource.LIVE``
        may run a STATE-CHANGING command. A non-LIVE source attempting a
        state change is refused with ``LIVE_SOURCE_REJECTED`` (read-only
        commands are still answered).
        """
        cmd = parse_command(text)
        if not cmd.is_known:
            return self._reject(cmd.head or text, "unknown_command")

        # Live-source isolation: only LIVE may mutate live state.
        if cmd.key in _STATE_CHANGING and not self._source_guard.authorize(
            source, action=f"telegram_command:{cmd.key}"
        ):
            return self._source_rejected(cmd.key, source)

        self._emit_received(cmd, actor=actor)

        dispatch: dict[str, Callable[[ParsedCommand], CommandResult]] = {
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            "/mode": self._cmd_mode,
            "/mode shadow": self._cmd_mode_shadow,
            "/mode live_limited": self._cmd_mode_live_limited,
            "/confirm_live": self._cmd_confirm_live,
            "/positions": self._cmd_positions,
            "/pnl": self._cmd_pnl,
            "/risk": self._cmd_risk,
            "/capital": self._cmd_capital,
            "/profile": self._cmd_profile,
            "/profile set": self._cmd_profile_set,
            "/pause": self._cmd_pause,
            "/resume": self._cmd_resume,
            "/kill_all": self._cmd_kill_all,
            "/confirm_kill": self._cmd_confirm_kill,
        }
        handler = dispatch[cmd.key]
        return handler(cmd)

    # -- /help ---------------------------------------------------------
    def _cmd_help(self, cmd: ParsedCommand) -> CommandResult:
        card = fmt.build_help_card(list(HELP_COMMANDS), mode=self._runtime.runtime_mode)
        return self._ok(cmd.key, card)

    # -- /status -------------------------------------------------------
    def _cmd_status(self, cmd: ParsedCommand) -> CommandResult:
        flags = self._data.safety_flags()
        status = {
            "runtime_mode": self._runtime.runtime_mode.value,
            "capital_profile_id": self._profile.capital_profile_id.value,
            "live_limited_armed": self._runtime.live_limited_armed,
            "paused": self._runtime.paused,
            "kill_switch_armed": self._kill.armed,
            "open_position_count": len(self._data.positions()),
            "account_equity_usdt": self._data.account_equity_usdt(),
            "funding_attribution_status": self._data.funding_attribution_status(),
            **flags,
        }
        # Merge any extra fields the provider supplied.
        status.update(self._data.account_status())
        card = fmt.build_status_card(status)
        return self._ok(cmd.key, card)

    # -- /mode ---------------------------------------------------------
    def _cmd_mode(self, cmd: ParsedCommand) -> CommandResult:
        card = fmt.build_mode_status_card(
            self._runtime.runtime_mode,
            real_order_allowed=self._real_order_allowed(),
            live_limited_armed=self._runtime.live_limited_armed,
            paused=self._runtime.paused,
        )
        return self._ok(cmd.key, card)

    def _cmd_mode_shadow(self, cmd: ParsedCommand) -> CommandResult:
        from_mode = self._runtime.runtime_mode
        self._runtime = RuntimeModeState(
            runtime_mode=LiveRuntimeMode.LIVE_SHADOW,
            live_limited_armed=False,
            paused=self._runtime.paused,
            updated_at=self._clock(),
            updated_by="operator",
        )
        # Disarm the confirmation so a future arm needs a fresh handshake.
        self._confirmation = ConfirmationState(
            live_limited_confirmed=False,
        )
        self._store.save_runtime_mode(self._runtime)
        self._store.save_confirmation(self._confirmation)
        self._emit(EventType.LIVE_MODE_CHANGED, {
            "from": from_mode.value,
            "to": LiveRuntimeMode.LIVE_SHADOW.value,
            "real_order_allowed": False,
        })
        card = fmt.build_mode_changed_card(
            from_mode=from_mode,
            to_mode=LiveRuntimeMode.LIVE_SHADOW,
            reason="operator_switch_to_shadow",
            real_order_allowed=False,
        )
        return self._ok(cmd.key, card, state_changed=True)

    def _cmd_mode_live_limited(self, cmd: ParsedCommand) -> CommandResult:
        # NEVER switches directly. Issue a confirmation code + risk summary.
        code = "LIVE-" + uuid.uuid4().hex[:8].upper()
        now = self._clock()
        self._confirmation = ConfirmationState(
            pending_code=code,
            pending_target=LiveRuntimeMode.LIVE_LIMITED.value,
            pending_issued_at=now,
            pending_expires_at=now + self._ttl,
            live_limited_confirmed=self._confirmation.live_limited_confirmed,
            live_limited_confirmed_at=self._confirmation.live_limited_confirmed_at,
            pending_kill_code=self._confirmation.pending_kill_code,
            pending_kill_expires_at=self._confirmation.pending_kill_expires_at,
        )
        self._store.save_confirmation(self._confirmation)

        prof = get_profile(self._profile.capital_profile_id)
        flags = self._data.safety_flags()
        summary = {
            "confirmation_code": code,
            "current_mode": self._runtime.runtime_mode.value,
            "target_mode": LiveRuntimeMode.LIVE_LIMITED.value,
            "capital_profile_id": self._profile.capital_profile_id.value,
            "account_equity_usdt": self._data.account_equity_usdt(),
            "max_account_capital_usdt": prof.max_account_capital_usdt,
            "max_position_notional_usdt": prof.max_position_notional_usdt,
            "max_active_positions": prof.max_active_positions,
            "max_daily_loss_usdt": prof.max_daily_loss_usdt,
            "max_total_loss_usdt": prof.max_total_loss_usdt,
            "max_leverage": prof.max_leverage,
            "exchange_live_orders": flags.get("exchange_live_orders", False),
            "trade_authority_flag": flags.get("trade_authority_flag", False),
            "private_trade_enabled": flags.get("private_trade_enabled", False),
            "kill_switch_armed": self._kill.armed,
            "funding_attribution_status": self._data.funding_attribution_status(),
        }
        self._emit(EventType.LIVE_MODE_SWITCH_REQUESTED, {
            "target_mode": LiveRuntimeMode.LIVE_LIMITED.value,
            "capital_profile_id": self._profile.capital_profile_id.value,
        })
        card = fmt.build_mode_switch_requested_card(summary)
        # Issuing a code is not itself a state change to the runtime mode.
        return self._ok(cmd.key, card, state_changed=False)

    def _cmd_confirm_live(self, cmd: ParsedCommand) -> CommandResult:
        code = cmd.args[0] if cmd.args else ""
        now = self._clock()
        reject: list[str] = []

        if not self._confirmation.pending_code:
            reject.append("no_pending_mode_switch")
        elif code != self._confirmation.pending_code:
            reject.append("confirmation_code_mismatch")
        elif (
            self._confirmation.pending_expires_at is not None
            and now > self._confirmation.pending_expires_at
        ):
            reject.append("confirmation_code_expired")

        prof = get_profile(self._profile.capital_profile_id)
        if not prof.real_orders_allowed:
            reject.append("profile_does_not_allow_real_orders")
        if LiveRuntimeMode.LIVE_LIMITED not in prof.mode_allowed:
            reject.append("profile_does_not_allow_live_limited")
        if self._kill.armed:
            # An ACTIVE kill switch (emergency halt) blocks arming live.
            reject.append("kill_switch_active")

        if reject:
            # Clear the pending code on a failed confirm.
            self._clear_pending_mode()
            self._emit(EventType.LIVE_MODE_SWITCH_REJECTED, {"reject_reasons": reject})
            card = fmt.build_mode_changed_card(
                from_mode=self._runtime.runtime_mode,
                to_mode=self._runtime.runtime_mode,
                reason="confirm_live_rejected:" + ",".join(reject),
                real_order_allowed=False,
            )
            return CommandResult(
                command=cmd.key,
                ok=False,
                card=card,
                text=fmt.render_card(card),
                reason=reject[0],
            )

        # All gates passed: arm LIVE_LIMITED. This does NOT enable real
        # orders - exchange_live_orders / trade_authority / private trade
        # are still config-gated and the PR113 execution gate still runs.
        self._runtime = RuntimeModeState(
            runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
            live_limited_armed=True,
            paused=self._runtime.paused,
            updated_at=now,
            updated_by="operator",
        )
        self._confirmation = ConfirmationState(
            pending_code=None,
            pending_target=None,
            pending_issued_at=None,
            pending_expires_at=None,
            live_limited_confirmed=True,
            live_limited_confirmed_at=now,
            pending_kill_code=self._confirmation.pending_kill_code,
            pending_kill_expires_at=self._confirmation.pending_kill_expires_at,
        )
        self._store.save_runtime_mode(self._runtime)
        self._store.save_confirmation(self._confirmation)
        self._emit(EventType.LIVE_MODE_SWITCH_CONFIRMED, {"by": "operator"})
        self._emit(EventType.LIVE_LIMITED_ARMED, {"by": "operator"})
        self._emit(EventType.LIVE_MODE_CHANGED, {
            "from": LiveRuntimeMode.LIVE_SHADOW.value,
            "to": LiveRuntimeMode.LIVE_LIMITED.value,
            "real_order_allowed": self._real_order_allowed(),
        })
        card = fmt.build_mode_changed_card(
            from_mode=LiveRuntimeMode.LIVE_SHADOW,
            to_mode=LiveRuntimeMode.LIVE_LIMITED,
            reason="live_limited_armed",
            real_order_allowed=self._real_order_allowed(),
        )
        return self._ok(cmd.key, card, state_changed=True)

    # -- /positions ----------------------------------------------------
    def _cmd_positions(self, cmd: ParsedCommand) -> CommandResult:
        card = fmt.build_positions_card(
            self._data.positions(),
            runtime_mode=self._runtime.runtime_mode,
            funding_attribution_status=self._data.funding_attribution_status(),
        )
        return self._ok(cmd.key, card)

    # -- /pnl ----------------------------------------------------------
    def _cmd_pnl(self, cmd: ParsedCommand) -> CommandResult:
        card = fmt.build_pnl_card(self._data.pnl())
        return self._ok(cmd.key, card)

    # -- /risk ---------------------------------------------------------
    def _cmd_risk(self, cmd: ParsedCommand) -> CommandResult:
        risk = dict(self._data.risk())
        prof = get_profile(self._profile.capital_profile_id)
        risk.setdefault("capital_profile_id", self._profile.capital_profile_id.value)
        risk.setdefault("max_account_capital_usdt", prof.max_account_capital_usdt)
        risk.setdefault("max_position_notional_usdt", prof.max_position_notional_usdt)
        risk.setdefault("max_leverage", prof.max_leverage)
        risk.setdefault("kill_switch_state", "ARMED" if self._kill.armed else "READY")
        card = fmt.build_risk_card(risk)
        return self._ok(cmd.key, card)

    # -- /capital ------------------------------------------------------
    def _cmd_capital(self, cmd: ParsedCommand) -> CommandResult:
        card = fmt.build_capital_card(self._data.capital())
        return self._ok(cmd.key, card)

    # -- /profile ------------------------------------------------------
    def _cmd_profile(self, cmd: ParsedCommand) -> CommandResult:
        prof = get_profile(self._profile.capital_profile_id)
        equity = self._data.account_equity_usdt()
        recommended = None
        if equity is not None and equity > 0:
            from app.live.capital_profile import suggest_profile_for_equity

            recommended = suggest_profile_for_equity(equity).value
        card = fmt.build_profile_card(
            {
                "capital_profile_id": self._profile.capital_profile_id.value,
                "recommended_profile_id": recommended,
                "account_equity_usdt": equity,
                "max_account_capital_usdt": prof.max_account_capital_usdt,
            }
        )
        return self._ok(cmd.key, card)

    def _cmd_profile_set(self, cmd: ParsedCommand) -> CommandResult:
        if not cmd.args:
            return self._profile_rejected("<missing>", "profile_id_required")
        raw = cmd.args[0]
        ack = len(cmd.args) > 1 and cmd.args[1].lower() in ("confirm", "ack", "yes")
        try:
            target = CapitalProfileId(raw)
        except ValueError:
            return self._profile_rejected(raw, "profile_not_found")

        current = self._profile.capital_profile_id
        if target == current:
            return self._profile_rejected(target.value, "profile_unchanged")

        is_escalation = _is_escalation(current, target)
        # Cannot AUTOMATICALLY raise risk: a higher-risk profile requires
        # an explicit acknowledgement token (e.g. "/profile set L3.. confirm").
        if is_escalation and not ack:
            self._emit(EventType.PROFILE_CHANGE_REJECTED, {
                "from": current.value,
                "to": target.value,
                "reason": "higher_risk_profile_requires_confirmation",
            })
            return self._profile_rejected(
                target.value, "higher_risk_profile_requires_confirmation"
            )

        # Apply (operator-initiated, explicit). Persist.
        self._profile = CapitalProfileStateRecord(
            capital_profile_id=target,
            updated_at=self._clock(),
            updated_by="operator",
        )
        self._store.save_capital_profile(self._profile)
        self._emit(EventType.CAPITAL_PROFILE_CHANGE_REQUESTED, {
            "from": current.value,
            "to": target.value,
            "is_escalation": is_escalation,
        })
        self._emit(EventType.CAPITAL_PROFILE_CHANGED, {
            "from": current.value,
            "to": target.value,
            "is_escalation": is_escalation,
        })
        card = fmt.build_capital_profile_changed_card(
            from_profile=current.value,
            to_profile=target.value,
            is_escalation=is_escalation,
        )
        return self._ok(cmd.key, card, state_changed=True)

    # -- /pause /resume -----------------------------------------------
    def _cmd_pause(self, cmd: ParsedCommand) -> CommandResult:
        self._runtime = RuntimeModeState(
            runtime_mode=self._runtime.runtime_mode,
            live_limited_armed=self._runtime.live_limited_armed,
            paused=True,
            updated_at=self._clock(),
            updated_by="operator",
        )
        self._store.save_runtime_mode(self._runtime)
        self._emit(EventType.LIVE_PAUSED, {"reason": "operator_pause"})
        card = fmt.build_paused_card(paused=True, reason="operator_pause")
        return self._ok(cmd.key, card, state_changed=True)

    def _cmd_resume(self, cmd: ParsedCommand) -> CommandResult:
        self._runtime = RuntimeModeState(
            runtime_mode=self._runtime.runtime_mode,
            live_limited_armed=self._runtime.live_limited_armed,
            paused=False,
            updated_at=self._clock(),
            updated_by="operator",
        )
        self._store.save_runtime_mode(self._runtime)
        self._emit(EventType.LIVE_RESUMED, {"reason": "operator_resume"})
        card = fmt.build_paused_card(paused=False, reason="operator_resume")
        return self._ok(cmd.key, card, state_changed=True)

    # -- /kill_all /confirm_kill --------------------------------------
    def _cmd_kill_all(self, cmd: ParsedCommand) -> CommandResult:
        code = "KILL-" + uuid.uuid4().hex[:8].upper()
        now = self._clock()
        self._confirmation = ConfirmationState(
            pending_code=self._confirmation.pending_code,
            pending_target=self._confirmation.pending_target,
            pending_issued_at=self._confirmation.pending_issued_at,
            pending_expires_at=self._confirmation.pending_expires_at,
            live_limited_confirmed=self._confirmation.live_limited_confirmed,
            live_limited_confirmed_at=self._confirmation.live_limited_confirmed_at,
            pending_kill_code=code,
            pending_kill_expires_at=now + self._ttl,
        )
        self._store.save_confirmation(self._confirmation)
        self._emit(EventType.LIVE_KILL_SWITCH_ARM_REQUESTED, {"requested_by": "operator"})
        card = fmt.build_kill_switch_card(
            armed=self._kill.armed, arm_requested=True, confirmation_code=code
        )
        return self._ok(cmd.key, card, state_changed=False)

    def _cmd_confirm_kill(self, cmd: ParsedCommand) -> CommandResult:
        code = cmd.args[0] if cmd.args else ""
        now = self._clock()
        reject: list[str] = []
        if not self._confirmation.pending_kill_code:
            reject.append("no_pending_kill_request")
        elif code != self._confirmation.pending_kill_code:
            reject.append("kill_confirmation_code_mismatch")
        elif (
            self._confirmation.pending_kill_expires_at is not None
            and now > self._confirmation.pending_kill_expires_at
        ):
            reject.append("kill_confirmation_code_expired")

        if reject:
            self._clear_pending_kill()
            card = fmt.build_kill_switch_card(
                armed=self._kill.armed, arm_requested=False, reason="confirm_kill_rejected"
            )
            return CommandResult(
                command=cmd.key,
                ok=False,
                card=card,
                text=fmt.render_card(card),
                reason=reject[0],
            )

        # Arm the kill switch (emergency halt). New entries are blocked;
        # the runtime is also paused. A real cancel/exit only runs if a
        # callback was wired (it MUST route through the PR113 gateway).
        self._kill = KillSwitchState(
            armed=True,
            armed_at=now,
            armed_by="operator",
            reason="operator_kill_all",
        )
        self._runtime = RuntimeModeState(
            runtime_mode=self._runtime.runtime_mode,
            live_limited_armed=self._runtime.live_limited_armed,
            paused=True,
            updated_at=now,
            updated_by="operator",
        )
        self._clear_pending_kill()
        self._store.save_kill_switch(self._kill)
        self._store.save_runtime_mode(self._runtime)

        callback_result: dict[str, Any] | None = None
        if self._kill_switch_callback is not None:
            try:
                callback_result = self._kill_switch_callback()
            except Exception:  # pragma: no cover - kill must not crash
                callback_result = {"error": "kill_switch_callback_failed"}

        self._emit(EventType.LIVE_KILL_SWITCH, {
            "armed": True,
            "by": "operator",
            "controlled_action": callback_result,
        })
        card = fmt.build_kill_switch_card(
            armed=True, arm_requested=False, reason="operator_kill_all"
        )
        if callback_result is not None:
            card["controlled_action"] = callback_result
        return self._ok(cmd.key, card, state_changed=True)

    # -- helpers -------------------------------------------------------
    def _real_order_allowed(self) -> bool:
        """Whether a real order COULD be authorised given the current state.

        True only when LIVE_LIMITED is armed AND every config flag the
        execution gate needs is set. The console never sets those flags
        itself; it only reflects them.
        """
        if self._runtime.runtime_mode is not LiveRuntimeMode.LIVE_LIMITED:
            return False
        if not self._runtime.live_limited_armed:
            return False
        if self._kill.armed:
            return False
        flags = self._data.safety_flags()
        return bool(
            flags.get("exchange_live_orders")
            and flags.get("trade_authority_flag")
            and flags.get("private_trade_enabled")
        )

    def _clear_pending_mode(self) -> None:
        self._confirmation = ConfirmationState(
            pending_code=None,
            pending_target=None,
            pending_issued_at=None,
            pending_expires_at=None,
            live_limited_confirmed=self._confirmation.live_limited_confirmed,
            live_limited_confirmed_at=self._confirmation.live_limited_confirmed_at,
            pending_kill_code=self._confirmation.pending_kill_code,
            pending_kill_expires_at=self._confirmation.pending_kill_expires_at,
        )
        self._store.save_confirmation(self._confirmation)

    def _clear_pending_kill(self) -> None:
        self._confirmation = ConfirmationState(
            pending_code=self._confirmation.pending_code,
            pending_target=self._confirmation.pending_target,
            pending_issued_at=self._confirmation.pending_issued_at,
            pending_expires_at=self._confirmation.pending_expires_at,
            live_limited_confirmed=self._confirmation.live_limited_confirmed,
            live_limited_confirmed_at=self._confirmation.live_limited_confirmed_at,
            pending_kill_code=None,
            pending_kill_expires_at=None,
        )
        self._store.save_confirmation(self._confirmation)

    def _ok(self, command: str, card: dict[str, Any], *, state_changed: bool = False) -> CommandResult:
        return CommandResult(
            command=command,
            ok=True,
            card=card,
            text=fmt.render_card(card),
            state_changed=state_changed,
        )

    def _reject(self, command: str, reason: str) -> CommandResult:
        card = fmt.build_help_card(list(HELP_COMMANDS), mode=self._runtime.runtime_mode)
        card["reject_reason"] = reason
        return CommandResult(
            command=command,
            ok=False,
            card=card,
            text=f"[ama-rt:live:UNKNOWN_COMMAND] reason={reason}",
            reason=reason,
        )

    def _profile_rejected(self, to_profile: str, reason: str) -> CommandResult:
        card = fmt.build_profile_change_rejected_card(to_profile=to_profile, reject_reason=reason)
        return CommandResult(
            command="/profile set",
            ok=False,
            card=card,
            text=fmt.render_card(card),
            reason=reason,
        )

    def _source_rejected(self, command: str, source: OrderSource | str) -> CommandResult:
        src = source.value if isinstance(source, OrderSource) else str(source)
        card = {
            "card_type": "LIVE_SOURCE_REJECTED",
            "command": command,
            "rejected_source": src,
            "reason": "only_live_source_may_change_live_state",
            "real_order": False,
            "trade_authority": False,
            "ai_trade_authority": False,
            "exchange_live_orders": False,
            "phase_12_forbidden": True,
        }
        return CommandResult(
            command=command,
            ok=False,
            card=card,
            text=f"[ama-rt:live:LIVE_SOURCE_REJECTED] command={command} source={src}",
            reason="live_source_rejected",
        )

    def _emit_received(self, cmd: ParsedCommand, *, actor: str) -> None:
        self._emit(EventType.TELEGRAM_COMMAND_RECEIVED, {
            "command": cmd.key,
            "actor": actor,
            "state_changing": cmd.key in _STATE_CHANGING,
        })

    def _emit(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_repo is None:
            return
        try:
            self._event_repo.append(
                Event(
                    event_type=event_type,
                    source_module=TELEGRAM_COMMANDS_MODULE,
                    payload={
                        **payload,
                        "runtime_mode": self._runtime.runtime_mode.value,
                        "capital_profile_id": self._profile.capital_profile_id.value,
                        # PR114 safety markers.
                        "trade_authority": False,
                        "ai_trade_authority": False,
                        "exchange_live_orders": False,
                        "phase_12_forbidden": True,
                    },
                )
            )
        except Exception:  # pragma: no cover - audit must never crash a command
            pass


def _is_escalation(current: CapitalProfileId, target: CapitalProfileId) -> bool:
    """True when ``target`` sits higher on the capital ladder than ``current``."""
    try:
        return CAPITAL_PROFILE_ORDER.index(target) > CAPITAL_PROFILE_ORDER.index(current)
    except ValueError:  # pragma: no cover
        return True


__all__ = [
    "TELEGRAM_COMMANDS_MODULE",
    "DEFAULT_CONFIRMATION_TTL_MS",
    "HELP_COMMANDS",
    "ParsedCommand",
    "parse_command",
    "CommandResult",
    "LiveConsoleDataProvider",
    "TelegramCommandHandler",
]
