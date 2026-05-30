"""Live Path Isolation (PR110 - Live Foundation v0).

Hard isolation boundary between the historical / blind / simulated /
paper-shadow code paths and the (not-yet-implemented) live execution
path.

AMA-RT already ships a deep simulation stack: SimulationClock,
HistoricalMarketStore, ReplayFeedProvider, MockExchange,
SimulatedCapitalFlow, Telegram Sandbox Outbox, Blind Walk-forward
Runner, Paper Shadow Strategy Bridge, Core Strategy Sim-Live Bridge.
Every one of those modules is a TEST surface. None of them may ever
reach a real live order gateway.

PR110 enforces this with a single rule:

    Only an order intent whose ``source`` is ``OrderSource.LIVE`` may
    be authorised by :class:`LivePathIsolationGuard`. Every other
    source (``SIM`` / ``BLIND`` / ``REPLAY`` / ``PAPER_SHADOW``) is
    refused with a ``LIVE_PATH_BLOCKED`` event and a
    :class:`LivePathIsolationViolation`.

The ``LIVE`` source is reserved for a future ``LiveExchangeAdapter`` /
``LiveExecutionGateway``. PR110 does NOT implement that adapter; it
only builds the gate and proves the simulation modules cannot pass
through it.

PR110 boundary
--------------
- No real order is ever placed (no live adapter exists).
- No private Binance API is contacted.
- Nothing here flips a Phase 1 safety flag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.clock import now_ms
from app.core.enums import Direction, OrderSource
from app.core.errors import LivePathIsolationViolation
from app.core.events import Event, EventType

# Identifier the guard stamps on its blocked-path audit events.
LIVE_PATH_ISOLATION_MODULE = "live.path_isolation"

# Known simulation / blind / replay / paper-shadow origin class names.
# Used by :func:`classify_source_module` so a misconfigured caller that
# forgets to set ``source`` still gets correctly mapped to a non-LIVE
# source (fail-safe: unknown modules map to SIM, never LIVE).
SIM_SOURCE_MODULES: dict[str, OrderSource] = {
    "MockExchangeClient": OrderSource.SIM,
    "MockExchange": OrderSource.SIM,
    "SimulatedCapitalFlowEngine": OrderSource.SIM,
    "SimulatedCapitalFlow": OrderSource.SIM,
    "HistoricalMarketStore": OrderSource.SIM,
    "SimulationClock": OrderSource.SIM,
    "BlindWalkForwardRunner": OrderSource.BLIND,
    "ReplayFeedProvider": OrderSource.REPLAY,
    "PaperShadowStrategyBridge": OrderSource.PAPER_SHADOW,
    "CoreStrategyBridge": OrderSource.PAPER_SHADOW,
}


def classify_source_module(module_name: str) -> OrderSource:
    """Map a producing module's class name to its :class:`OrderSource`.

    Fail-safe: an unknown module name maps to ``OrderSource.SIM`` (a
    blocked source), never ``LIVE``. A caller can only obtain a ``LIVE``
    source by constructing the intent with ``source=OrderSource.LIVE``
    explicitly - which only a real ``LiveExchangeAdapter`` is permitted
    to do.
    """
    return SIM_SOURCE_MODULES.get(module_name, OrderSource.SIM)


@dataclass(frozen=True)
class LiveOrderIntent:
    """A request to place a real order, carrying its provenance.

    Every order intent in the system MUST carry a ``source``. The
    isolation guard inspects ``source`` (not the contents) to decide
    admissibility, so a simulation module physically cannot smuggle an
    order onto the live path even if every other field looks live.
    """

    source: OrderSource
    source_module: str
    symbol: str
    side: Direction
    quantity: float = 0.0
    notional_usdt: float = 0.0
    client_order_id: str | None = None
    opportunity_id: str | None = None
    timestamp: int = field(default_factory=now_ms)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_module(
        cls,
        *,
        source_module: str,
        symbol: str,
        side: Direction,
        **kwargs: Any,
    ) -> "LiveOrderIntent":
        """Build an intent, inferring ``source`` from the module name.

        Convenience for the simulation modules: they cannot accidentally
        claim ``LIVE`` because :func:`classify_source_module` never maps
        an unknown / simulation module to ``LIVE``.
        """
        return cls(
            source=classify_source_module(source_module),
            source_module=source_module,
            symbol=symbol,
            side=side,
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.value,
            "source_module": self.source_module,
            "symbol": self.symbol,
            "side": self.side.value if isinstance(self.side, Direction) else self.side,
            "quantity": self.quantity,
            "notional_usdt": self.notional_usdt,
            "client_order_id": self.client_order_id,
            "opportunity_id": self.opportunity_id,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class IsolationDecision:
    """Result of submitting an intent to the isolation guard."""

    authorised: bool
    source: OrderSource
    reason: str
    intent: LiveOrderIntent

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorised": self.authorised,
            "source": self.source.value,
            "reason": self.reason,
            "intent": self.intent.to_dict(),
        }


class LivePathIsolationGuard:
    """The single gate that protects the live order path.

    ``authorize`` returns an :class:`IsolationDecision` describing
    whether the intent may continue to the (future) live adapter. The
    ``raise_on_block`` variant raises :class:`LivePathIsolationViolation`
    for callers that want a hard stop. Every blocked attempt emits a
    ``LIVE_PATH_BLOCKED`` event when an event repository is attached.
    """

    def __init__(self, *, event_repo: Any | None = None, enabled: bool = True) -> None:
        self._event_repo = event_repo
        # Isolation is on by default and cannot be silently disabled in
        # a way that lets a non-LIVE source through: even when disabled
        # the guard still blocks non-LIVE sources (the flag only governs
        # whether the guard is *wired in*, never whether it weakens).
        self.enabled = bool(enabled)
        self._blocked_count = 0

    @property
    def blocked_count(self) -> int:
        return self._blocked_count

    def authorize(self, intent: LiveOrderIntent) -> IsolationDecision:
        """Decide whether ``intent`` may reach the live order path.

        Authorised IFF ``intent.source is OrderSource.LIVE``. Any other
        source is blocked, counted, and audited.
        """
        if intent.source is OrderSource.LIVE:
            return IsolationDecision(
                authorised=True,
                source=intent.source,
                reason="live_source_admissible",
                intent=intent,
            )
        self._blocked_count += 1
        reason = f"non_live_source_blocked:{intent.source.value}"
        self._emit_blocked(intent, reason)
        return IsolationDecision(
            authorised=False,
            source=intent.source,
            reason=reason,
            intent=intent,
        )

    def assert_live_path(self, intent: LiveOrderIntent) -> LiveOrderIntent:
        """Authorise or raise.

        Raises :class:`LivePathIsolationViolation` for any non-LIVE
        source. Returns the intent unchanged when admissible.
        """
        decision = self.authorize(intent)
        if not decision.authorised:
            raise LivePathIsolationViolation(
                f"live path isolation blocked an order intent from "
                f"{intent.source_module!r} (source={intent.source.value}); "
                f"only OrderSource.LIVE may reach the live order gateway. "
                f"Blind / replay / sim / paper-shadow modules are isolated "
                f"from live execution by PR110."
            )
        return intent

    def _emit_blocked(self, intent: LiveOrderIntent, reason: str) -> None:
        if self._event_repo is None:
            return
        self._event_repo.append(
            Event(
                event_type=EventType.LIVE_PATH_BLOCKED,
                source_module=LIVE_PATH_ISOLATION_MODULE,
                symbol=intent.symbol,
                payload={
                    "reason": reason,
                    "blocked_source": intent.source.value,
                    "source_module": intent.source_module,
                    "intent": intent.to_dict(),
                    # PR110 safety markers (audit visibility):
                    "live_trading": False,
                    "exchange_live_orders": False,
                    "binance_private_api_enabled": False,
                    "phase_12_forbidden": True,
                },
            )
        )


__all__ = [
    "LIVE_PATH_ISOLATION_MODULE",
    "SIM_SOURCE_MODULES",
    "classify_source_module",
    "LiveOrderIntent",
    "IsolationDecision",
    "LivePathIsolationGuard",
]
