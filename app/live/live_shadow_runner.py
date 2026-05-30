"""LIVE_SHADOW runner (PR116 - 10U LIVE_LIMITED Launch Pack v0).

The real-market shadow runner (*空盘跑*). One iteration:

  1. read live Binance public + private-read data (account / income),
  2. build a :class:`app.live.capital_state.LiveCapitalState` + the
     funding-aware PnL summary,
  3. enforce the ACTIVE capital profile (caps usable capital; detects a
     profile/equity mismatch) - read dynamically from
     :class:`app.live.live_runtime.LiveRuntime`,
  4. build operator cards (account status / capital-profile status / pnl
     / funding / positions / risk + a LIVE_SHADOW_SUMMARY),
  5. OPTIONALLY build a DeepSeek live-safe AI briefing (intelligence
     only; no trade authority),
  6. OPTIONALLY push the cards to Telegram (only when outbound is enabled
     AND the chat id is authorised).

Hard boundary (the brief): the shadow runner NEVER places a real order.
Every card carries ``real_order=False`` and the result carries
``no_real_order_sent=True``. It NEVER changes capital / mode / profile /
leverage, never grants AI trade authority, and never lets a non-LIVE
source drive it.
"""

from __future__ import annotations

from typing import Any, Callable

from app.core.clock import now_ms
from app.core.enums import LiveRuntimeMode, OrderSource
from app.core.events import Event, EventType
from app.live.ai_live_briefing import LiveAIBriefingGenerator
from app.live.ai_live_evidence import build_live_ai_evidence_bundle
from app.live.api_config import LiveApiConfig
from app.live.binance_income import BinanceIncomeEvent
from app.live.binance_models import BinanceAccountSnapshot
from app.live.capital_state import LiveCapitalState
from app.live.live_capital_service import (
    build_capital_profile_mismatch_payload,
    build_funding_event_summary_payload,
    build_live_account_status_payload,
    build_live_capital_profile_status_payload,
    build_live_pnl_summary_payload,
)
from app.live.live_launch_models import ShadowRunResult, launch_safety_markers
from app.live.live_runtime import LiveRuntime
from app.live.pnl_accounting import build_live_pnl_summary
from app.live.telegram_state import LiveOperatorStateStore

LIVE_SHADOW_RUNNER_MODULE = "live.live_shadow_runner"

# A Telegram card sender: (card) -> True if actually sent. Wired by the
# CLI to the real outbound; tests inject a fake. Used only when outbound
# gating allows it.
TelegramCardSender = Callable[[dict[str, Any]], bool]


class LiveShadowRunner:
    """Runs the LIVE_SHADOW (*空盘跑*) loop. Never places a real order."""

    def __init__(
        self,
        config: LiveApiConfig,
        *,
        runtime: LiveRuntime | None = None,
        state_store: LiveOperatorStateStore | None = None,
        binance_client: Any | None = None,
        briefing_generator: LiveAIBriefingGenerator | None = None,
        telegram_sender: TelegramCardSender | None = None,
        event_repo: Any | None = None,
        clock: Callable[[], int] = now_ms,
    ) -> None:
        self._config = config
        self._store = state_store or LiveOperatorStateStore()
        self._runtime = runtime or LiveRuntime(
            config, state_store=self._store, event_repo=event_repo
        )
        self._binance_client = binance_client
        self._briefing_generator = briefing_generator
        self._telegram_sender = telegram_sender
        self._event_repo = event_repo
        self._clock = clock

    # ------------------------------------------------------------------
    # Single iteration
    # ------------------------------------------------------------------
    def run_once(
        self,
        *,
        send_telegram: bool = False,
        with_ai_briefing: bool = False,
        account_snapshot: BinanceAccountSnapshot | None = None,
        income_events: list[BinanceIncomeEvent] | None = None,
        open_order_count: int = 0,
        daily_loss_usdt: float = 0.0,
        total_loss_usdt: float = 0.0,
        ai_dry_run: bool = False,
    ) -> ShadowRunResult:
        """Run one shadow iteration; never places a real order."""
        active_profile_id = self._runtime.active_capital_profile_id()
        # A shadow run is ALWAYS read-only; the cards are stamped SHADOW.
        runtime_mode = LiveRuntimeMode.LIVE_SHADOW
        warnings: list[str] = []

        # 1. Read account (best-effort; injected snapshot wins).
        if account_snapshot is None and self._binance_client is not None:
            account_snapshot = self._read_account()
        if income_events is None and self._binance_client is not None:
            income_events = self._read_income()
        income_events = income_events or []

        cards: list[dict[str, Any]] = []
        account_equity: float | None = None
        usable_capital: float | None = None
        open_positions = 0

        if account_snapshot is not None:
            capital_state = LiveCapitalState.from_account_snapshot(
                account_snapshot,
                runtime_mode=runtime_mode,
                capital_profile_id=active_profile_id,
                open_order_count=open_order_count,
            )
            profile_state = self._runtime.evaluate_capital_profile(
                capital_state,
                daily_loss_usdt=daily_loss_usdt,
                total_loss_usdt=total_loss_usdt,
            )
            account_equity = profile_state.account_equity_usdt
            usable_capital = profile_state.usable_capital_usdt
            open_positions = capital_state.open_position_count

            pnl = build_live_pnl_summary(
                income_events, account_equity_usdt=account_equity
            )
            cards.append(build_live_account_status_payload(capital_state, profile_state=profile_state))
            cards.append(build_live_capital_profile_status_payload(profile_state))
            cards.append(build_live_pnl_summary_payload(pnl))
            cards.append(build_funding_event_summary_payload(pnl))
            cards.append(self._positions_card(capital_state))
            if profile_state.mismatch.mismatch:
                cards.append(build_capital_profile_mismatch_payload(profile_state))
                warnings.append("capital_profile_mismatch")
        else:
            warnings.append("no_account_snapshot_private_read_unavailable")

        # 5. Optional AI briefing (intelligence-only; never actionable).
        ai_status: str | None = None
        if with_ai_briefing:
            ai_status = self._maybe_build_briefing(
                cards, runtime_mode, active_profile_id, account_equity, dry_run=ai_dry_run
            )

        # Always include a LIVE_SHADOW_SUMMARY card last.
        summary = ShadowRunResult(
            runtime_mode=runtime_mode.value,
            capital_profile_id=active_profile_id.value,
            account_equity_usdt=account_equity,
            usable_live_capital_usdt=usable_capital,
            open_position_count=open_positions,
            cards=(),  # filled below
            telegram_sent_count=0,
            telegram_suppressed_count=0,
            ai_briefing_status=ai_status,
            warnings=tuple(warnings),
        )
        cards.append(summary.telegram_summary_card())

        # 6. Optional Telegram push (only when outbound + chat allowed).
        sent, suppressed = self._maybe_send(cards, send_telegram)

        result = ShadowRunResult(
            runtime_mode=runtime_mode.value,
            capital_profile_id=active_profile_id.value,
            account_equity_usdt=account_equity,
            usable_live_capital_usdt=usable_capital,
            open_position_count=open_positions,
            cards=tuple(cards),
            telegram_sent_count=sent,
            telegram_suppressed_count=suppressed,
            ai_briefing_status=ai_status,
            warnings=tuple(warnings),
        )
        self._emit_run(result)
        return result

    # ------------------------------------------------------------------
    # Reads (best-effort; never crash a shadow run)
    # ------------------------------------------------------------------
    def _read_account(self) -> BinanceAccountSnapshot | None:
        if (
            not self._config.binance.enable_private_read
            or not self._config.binance.has_credentials
            or self._config.binance.api_key.is_placeholder
            or self._config.binance.api_secret.is_placeholder
        ):
            return None
        try:
            return self._binance_client.get_account()
        except Exception:  # pragma: no cover - read failure is non-fatal
            return None

    def _read_income(self) -> list[BinanceIncomeEvent]:
        if (
            not self._config.binance.enable_private_read
            or not self._config.binance.has_credentials
        ):
            return []
        try:
            return self._binance_client.get_income_history(limit=50)
        except Exception:  # pragma: no cover
            return []

    # ------------------------------------------------------------------
    # AI briefing
    # ------------------------------------------------------------------
    def _maybe_build_briefing(
        self,
        cards: list[dict[str, Any]],
        runtime_mode: LiveRuntimeMode,
        profile_id: Any,
        account_equity: float | None,
        *,
        dry_run: bool,
    ) -> str | None:
        gen = self._briefing_generator or LiveAIBriefingGenerator(
            self._config.deepseek, event_repo=self._event_repo
        )
        # Build a live-only evidence bundle from the shadow cards.
        account_card = next(
            (c for c in cards if c.get("payload_type") == "LIVE_ACCOUNT_STATUS"), {}
        )
        pnl_card = next(
            (c for c in cards if c.get("payload_type") == "LIVE_PNL_SUMMARY"), {}
        )
        bundle_result = build_live_ai_evidence_bundle(
            runtime_mode=runtime_mode,
            capital_profile_id=profile_id.value if hasattr(profile_id, "value") else str(profile_id),
            account_status=account_card,
            pnl_summary=pnl_card,
            sources=[OrderSource.LIVE],
            event_repo=self._event_repo,
        )
        if not bundle_result.accepted or bundle_result.bundle is None:
            return "EVIDENCE_REJECTED"
        briefing = gen.generate(bundle_result.bundle, dry_run=dry_run)
        cards.append(
            {
                "card_type": "LIVE_AI_BRIEFING",
                "status": briefing.status,
                "market_summary": briefing.market_summary,
                "evidence_quality": briefing.evidence_quality,
                "ai_trade_authority": False,
                "source_scope": "LIVE_ONLY",
                **launch_safety_markers(),
            }
        )
        return briefing.status

    # ------------------------------------------------------------------
    # Telegram outbound
    # ------------------------------------------------------------------
    def _outbound_allowed(self) -> bool:
        tg = self._config.telegram
        return bool(
            tg.outbound_enabled
            and tg.has_token
            and len(tg.allowed_chat_ids) > 0
            and self._telegram_sender is not None
        )

    def _maybe_send(self, cards: list[dict[str, Any]], send_telegram: bool) -> tuple[int, int]:
        if not send_telegram:
            return 0, 0
        if not self._outbound_allowed():
            return 0, len(cards)
        sent = 0
        suppressed = 0
        for card in cards:
            try:
                ok = bool(self._telegram_sender(card))
            except Exception:  # pragma: no cover - send failure is non-fatal
                ok = False
            if ok:
                sent += 1
            else:
                suppressed += 1
        return sent, suppressed

    # ------------------------------------------------------------------
    # Cards / events
    # ------------------------------------------------------------------
    def _positions_card(self, capital_state: LiveCapitalState) -> dict[str, Any]:
        card = {
            "payload_type": "LIVE_POSITIONS",
            "card_type": "LIVE_POSITIONS",
            "runtime_mode": capital_state.runtime_mode.value,
            "open_position_count": capital_state.open_position_count,
            "positions": [p.to_dict() for p in capital_state.open_positions],
        }
        card.update(launch_safety_markers())
        return card

    def _emit_run(self, result: ShadowRunResult) -> None:
        if self._event_repo is None:
            return
        try:
            self._event_repo.append(
                Event(
                    event_type=EventType.LIVE_SHADOW_ACTIVE,
                    source_module=LIVE_SHADOW_RUNNER_MODULE,
                    payload={
                        "runtime_mode": result.runtime_mode,
                        "capital_profile_id": result.capital_profile_id,
                        "open_position_count": result.open_position_count,
                        "telegram_sent_count": result.telegram_sent_count,
                        "ai_briefing_status": result.ai_briefing_status,
                        **launch_safety_markers(),
                    },
                )
            )
        except Exception:  # pragma: no cover
            pass


__all__ = [
    "LIVE_SHADOW_RUNNER_MODULE",
    "TelegramCardSender",
    "LiveShadowRunner",
]
