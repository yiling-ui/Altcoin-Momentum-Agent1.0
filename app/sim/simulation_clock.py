"""SimulationClock + HistoricalRecordTime helper for Phase 11C.1D-D-A
(PR94 - SimulationClock + Time-Wall Guard).

Strict forward-only historical sim-live time substrate. This module is
the **first** anti-future-lookahead infrastructure block of the strict
blind walk-forward stack defined by Phase 11C.1D-D (the *Strict Blind
Walk-forward Sim-Live Constitution*, PR93).

Hard safety boundary (Phase 11C.1D-D-A / PR94):

  - mode = paper
  - sandbox_only = True
  - live_trading = False
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
  - ai_trade_authority = False
  - trade_authority = False
  - auto_tuning_allowed = False
  - phase_12_forbidden = True

This module MUST NOT and CANNOT:

  - import app.risk / app.execution / app.exchanges / app.telegram /
    app.config
  - call DeepSeek / LLM / Telegram / Binance private API / any network
  - place an order
  - emit buy / sell / long / short / direction / entry / exit /
    position_size / leverage / stop / stop_loss / target /
    take_profit / risk_budget / order / execution_command
  - emit any runtime_config_patch / threshold_patch /
    symbol_limit_patch / candidate_pool_patch / regime_weight_patch /
    strategy_parameter_patch / signal_to_trade / should_buy /
    should_short / apply_change / deploy_change / enable_live /
    live_ready / trading_approved
  - authorize live trading or auto-tuning
  - enter Phase 12

This module is the foundation for time-wall enforcement that all
later (separately gated) PR95..PR100 modules MUST consume. It does
NOT implement:

  - the Blind Walk-forward Runner (PR100),
  - the Historical Market Store v0 (PR95),
  - the ReplayFeedProvider (PR96),
  - the MockExchange + Pessimistic Fill Model (PR97),
  - the Simulated Capital Flow + Trade Ledger (PR98),
  - the Telegram Sandbox Outbox (PR99).

PR94 acceptance authorises ONLY PR95 (*Historical Market Store v0*)
to begin its own gate. It does NOT authorise live trading,
auto-tuning, the DeepSeek hot path, Telegram live outbound, or
Phase 12. Phase 12 remains FORBIDDEN.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

PHASE_NAME: str = (
    "Phase 11C.1D-D-A / PR94 / SimulationClock + Time-Wall Guard"
)


# ---------------------------------------------------------------------------
# Allowed candle intervals for the v0 closed-candle visibility rule
# ---------------------------------------------------------------------------

# These mirror the §6 candle-visibility rule of the Strict Blind
# Walk-forward Sim-Live Constitution. Longer intervals follow the same
# rule by composition. The mapping is a Python module-level constant -
# it is NOT loaded from runtime config, NOT loaded from an LLM, NOT
# exposed via CLI flags, and NOT rewritten by the engine.
_INTERVAL_TO_SECONDS: Dict[str, int] = {
    "1m": 60,
    "3m": 3 * 60,
    "5m": 5 * 60,
    "15m": 15 * 60,
    "30m": 30 * 60,
    "1h": 60 * 60,
    "2h": 2 * 60 * 60,
    "4h": 4 * 60 * 60,
    "6h": 6 * 60 * 60,
    "8h": 8 * 60 * 60,
    "12h": 12 * 60 * 60,
    "1d": 24 * 60 * 60,
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def ensure_utc_aware(dt: datetime, name: str) -> datetime:
    """Return a timezone-aware UTC datetime or raise.

    Naive datetimes are forbidden as market-state decision time. Any
    non-UTC offset is normalised to UTC via ``astimezone(UTC)``.
    """
    if not isinstance(dt, datetime):
        raise TypeError(f"{name} must be a datetime, got {type(dt)!r}")
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(
            f"{name} must be timezone-aware UTC; naive datetimes are "
            f"forbidden as market-state decision time"
        )
    if dt.utcoffset() != timedelta(0):
        return dt.astimezone(timezone.utc)
    return dt


def parse_interval_seconds(interval: str) -> int:
    """Return the duration (seconds) of a candle interval string.

    Accepted: ``"1m"``, ``"3m"``, ``"5m"``, ``"15m"``, ``"30m"``,
    ``"1h"``, ``"2h"``, ``"4h"``, ``"6h"``, ``"8h"``, ``"12h"``,
    ``"1d"``.
    """
    if not isinstance(interval, str):
        raise TypeError(
            f"interval must be a string, got {type(interval)!r}"
        )
    if interval not in _INTERVAL_TO_SECONDS:
        raise ValueError(
            f"unsupported interval {interval!r}; allowed: "
            f"{sorted(_INTERVAL_TO_SECONDS)}"
        )
    return _INTERVAL_TO_SECONDS[interval]


def _coerce_to_timedelta(
    delta: Union[timedelta, int, float, str],
) -> timedelta:
    if isinstance(delta, timedelta):
        return delta
    if isinstance(delta, bool):
        # bool is a subclass of int; refuse it.
        raise TypeError(
            f"step delta must be timedelta / number / interval string, "
            f"got bool"
        )
    if isinstance(delta, (int, float)):
        return timedelta(seconds=float(delta))
    if isinstance(delta, str):
        return timedelta(seconds=parse_interval_seconds(delta))
    raise TypeError(
        f"step delta must be timedelta / number / interval string, "
        f"got {type(delta)!r}"
    )


# ---------------------------------------------------------------------------
# SimulationClock
# ---------------------------------------------------------------------------


class SimulationClock:
    """Strict forward-only simulated UTC clock.

    The SimulationClock is the ONLY source of market-state decision
    time inside a strict blind walk-forward run. Modules that consume
    it MUST NOT call ``datetime.now()`` / ``datetime.utcnow()`` /
    ``time.time()`` / ``time.monotonic()`` / ``pandas.Timestamp.now()``
    as a substitute.

    The wall-clock may still be used by callers for non-decision
    diagnostic metadata (file write timestamps, log rotation, etc.),
    but this clock NEVER consults the wall-clock. The SimulationClock
    is therefore deterministic and reproducible.

    Forward-only by default. Rewinds require constructing a clock with
    ``monotonic_forward_only=False`` (test-only flag).
    """

    def __init__(
        self,
        start_time_utc: datetime,
        end_time_utc: Optional[datetime] = None,
        monotonic_forward_only: bool = True,
    ) -> None:
        start = ensure_utc_aware(start_time_utc, "start_time_utc")
        end = (
            ensure_utc_aware(end_time_utc, "end_time_utc")
            if end_time_utc is not None
            else None
        )
        if end is not None and end < start:
            raise ValueError(
                "end_time_utc must be >= start_time_utc"
            )
        self.start_time_utc: datetime = start
        self.current_time_utc: datetime = start
        self.end_time_utc: Optional[datetime] = end
        self.monotonic_forward_only: bool = bool(monotonic_forward_only)

    # ----- public API -----

    def now(self) -> datetime:
        """Return the current simulated time. Always UTC-aware."""
        return self.current_time_utc

    def step(
        self,
        delta: Union[timedelta, int, float, str],
    ) -> datetime:
        """Advance the simulated clock by ``delta``.

        ``delta`` may be a :class:`datetime.timedelta`, a number of
        seconds (int or float), or an interval string such as
        ``"1m"`` / ``"5m"`` / ``"1h"``.

        Raises:
            ValueError: if the resulting time would move backward and
                ``monotonic_forward_only`` is True (the default).
            ValueError: if the resulting time would exceed
                ``end_time_utc``.
        """
        td = _coerce_to_timedelta(delta)
        if self.monotonic_forward_only and td < timedelta(0):
            raise ValueError(
                "SimulationClock cannot move backward when "
                "monotonic_forward_only=True"
            )
        proposed = self.current_time_utc + td
        if (
            self.end_time_utc is not None
            and proposed > self.end_time_utc
        ):
            raise ValueError(
                "SimulationClock.step would exceed end_time_utc"
            )
        if proposed < self.start_time_utc:
            # Defensive: never let current_time_utc fall below start.
            raise ValueError(
                "SimulationClock.step would precede start_time_utc"
            )
        self.current_time_utc = proposed
        return self.current_time_utc

    def set_time(self, new_time: datetime) -> datetime:
        """Set the simulated time explicitly to ``new_time``.

        Forward-only by default; rewinds require a clock built with
        ``monotonic_forward_only=False`` (test-only flag).
        """
        new_time = ensure_utc_aware(new_time, "new_time")
        if (
            self.monotonic_forward_only
            and new_time < self.current_time_utc
        ):
            raise ValueError(
                "SimulationClock cannot move backward when "
                "monotonic_forward_only=True"
            )
        if new_time < self.start_time_utc:
            raise ValueError(
                "SimulationClock.set_time precedes start_time_utc"
            )
        if (
            self.end_time_utc is not None
            and new_time > self.end_time_utc
        ):
            raise ValueError(
                "SimulationClock.set_time would exceed end_time_utc"
            )
        self.current_time_utc = new_time
        return self.current_time_utc

    def assert_within_bounds(self) -> None:
        """Assert ``start_time_utc <= current_time_utc <= end_time_utc``.

        Raises ``ValueError`` if the current time has somehow drifted
        outside of the configured bounds.
        """
        if self.current_time_utc < self.start_time_utc:
            raise ValueError(
                "SimulationClock current_time_utc < start_time_utc"
            )
        if (
            self.end_time_utc is not None
            and self.current_time_utc > self.end_time_utc
        ):
            raise ValueError(
                "SimulationClock current_time_utc > end_time_utc"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the clock state. Always carries the safety boundary."""
        return {
            "phase": PHASE_NAME,
            "start_time_utc": self.start_time_utc.isoformat(),
            "current_time_utc": self.current_time_utc.isoformat(),
            "end_time_utc": (
                self.end_time_utc.isoformat()
                if self.end_time_utc is not None
                else None
            ),
            "monotonic_forward_only": self.monotonic_forward_only,
            # Hard-pinned safety flags surfaced on every clock dump:
            "mode": "paper",
            "sandbox_only": True,
            "live_trading": False,
            "exchange_live_orders": False,
            "binance_private_api_enabled": False,
            "telegram_outbound_enabled": False,
            "ai_trade_authority": False,
            "trade_authority": False,
            "auto_tuning_allowed": False,
            "phase_12_forbidden": True,
            # Defensive non-trade markers (visible to reviewers):
            "is_simulation_clock": True,
            "is_trade": False,
            "is_runtime_patch": False,
        }


# ---------------------------------------------------------------------------
# HistoricalRecordTime
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoricalRecordTime:
    """Time model for a single historical record.

    Constitution §5: every historical record MUST distinguish four
    timestamps:

      * ``event_time`` - when the underlying market event actually
        occurred,
      * ``available_at`` - the earliest time at which a sim-live
        consumer could legitimately have observed the record (e.g.
        candle close time + exchange publication latency),
      * ``ingested_at`` - when the record entered the historical
        store,
      * ``source`` - which provider / endpoint produced the record.

    ``ingested_at`` MUST NOT be substituted for ``available_at``. A
    record whose ``ingested_at <= T`` but whose ``available_at > T``
    is still future data and MUST be rejected by the Time-Wall Guard.
    """

    event_time: datetime
    available_at: datetime
    ingested_at: Optional[datetime] = None
    source: Optional[str] = None
    record_id: Optional[str] = None
    symbol: Optional[str] = None
    interval: Optional[str] = None

    def __post_init__(self) -> None:
        ev = ensure_utc_aware(self.event_time, "event_time")
        avail = ensure_utc_aware(self.available_at, "available_at")
        ing = (
            ensure_utc_aware(self.ingested_at, "ingested_at")
            if self.ingested_at is not None
            else None
        )
        # available_at must be >= event_time: a record cannot be
        # available before its event happened.
        if avail < ev:
            raise ValueError(
                "available_at must be >= event_time (a record cannot "
                "be available before its event_time)"
            )
        if self.interval is not None:
            # If interval is supplied, it must be a known interval.
            parse_interval_seconds(self.interval)
        object.__setattr__(self, "event_time", ev)
        object.__setattr__(self, "available_at", avail)
        if ing is not None:
            object.__setattr__(self, "ingested_at", ing)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_time": self.event_time.isoformat(),
            "available_at": self.available_at.isoformat(),
            "ingested_at": (
                self.ingested_at.isoformat()
                if self.ingested_at is not None
                else None
            ),
            "source": self.source,
            "record_id": self.record_id,
            "symbol": self.symbol,
            "interval": self.interval,
            # Hard-pinned defensive markers:
            "phase": PHASE_NAME,
            "phase_12_forbidden": True,
            "auto_tuning_allowed": False,
            "trade_authority": False,
            "is_historical_record_time": True,
            "is_trade": False,
            "is_runtime_patch": False,
        }


__all__ = [
    "PHASE_NAME",
    "SimulationClock",
    "HistoricalRecordTime",
    "ensure_utc_aware",
    "parse_interval_seconds",
]
