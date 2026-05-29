"""TimeWallGuard + NoLookaheadViolation + CandleVisibilityGuard.

Strict blind walk-forward time-wall enforcement (Phase 11C.1D-D-A,
PR94 - SimulationClock + Time-Wall Guard).

Constitution §5 (the Strict Blind Walk-forward Sim-Live Constitution,
PR93): at simulated time ``T``, the system MAY only read records
whose ``available_at <= T``. Any read of a record whose
``available_at > T`` MUST be rejected and logged as a
``NO_LOOKAHEAD_VIOLATION``. ``ingested_at`` is NOT a substitute for
``available_at``.

Constitution §6: a 1m / 5m / longer-period candle's final OHLCV is
fully visible only after that candle has closed. Without tick / trade
data, intra-bar paths are ambiguous and cannot be inferred.

Constitution §7: outcome labels (future top-mover labels, completed
tail labels, post-discovery outcome metrics, future MFE / MAE,
severe missed-tail labels, final window PnL, future drawdown, future
funding-rate changes, future regime labels, future AI briefings,
future replay summaries, future reflection summaries) MAY ONLY be
used after the blind window has closed.

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
  - call DeepSeek / LLM / Telegram / Binance private API / any
    network
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

This module is the audit / rejection substrate. It does NOT
implement the Blind Walk-forward Runner, the Historical Market
Store, the ReplayFeedProvider, the MockExchange, the Simulated
Capital Flow, or the Telegram Sandbox Outbox.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
)

from app.sim.simulation_clock import (
    HistoricalRecordTime,
    ensure_utc_aware,
    parse_interval_seconds,
)


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

PHASE_NAME: str = (
    "Phase 11C.1D-D-A / PR94 / SimulationClock + Time-Wall Guard"
)


# ---------------------------------------------------------------------------
# Forbidden field names that must NEVER appear in any output payload
# ---------------------------------------------------------------------------

FORBIDDEN_OUTPUT_FIELDS: frozenset = frozenset(
    {
        # Direction / side.
        "buy",
        "sell",
        "long",
        "short",
        "direction",
        # Order plumbing.
        "entry",
        "exit",
        "order",
        "execution_command",
        # Sizing / risk.
        "position_size",
        "leverage",
        "stop",
        "stop_loss",
        "target",
        "take_profit",
        "risk_budget",
        # Runtime tuning patches.
        "runtime_config_patch",
        "symbol_limit_patch",
        "threshold_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
        "strategy_parameter_patch",
        # Trade-authority signals.
        "signal_to_trade",
        "should_buy",
        "should_short",
        "apply_change",
        "deploy_change",
        "enable_live",
        "live_ready",
        "trading_approved",
    }
)


def assert_no_forbidden_fields(payload: Any, _path: str = "$") -> None:
    """Recursively assert no forbidden field name appears in ``payload``.

    Raises :class:`ValueError` on the first violation. Used as a
    defensive check on every output payload before serialisation.
    """
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            if isinstance(k, str) and k in FORBIDDEN_OUTPUT_FIELDS:
                raise ValueError(
                    f"forbidden field {k!r} present at {_path}"
                )
            assert_no_forbidden_fields(v, f"{_path}.{k}")
    elif isinstance(payload, (list, tuple)):
        for i, v in enumerate(payload):
            assert_no_forbidden_fields(v, f"{_path}[{i}]")
    # Scalars: nothing to check (the check is on field NAMES, not values).


# ---------------------------------------------------------------------------
# Closed taxonomy of no-lookahead violation reasons
# ---------------------------------------------------------------------------


class NoLookaheadViolationReason:
    """Closed enum of no-lookahead violation reasons.

    Constitution §5 / §6 / §7 / §F. Descriptive only; never a runtime
    knob. Adding a new reason is a docs / brief / new-PR concern.
    """

    FUTURE_AVAILABLE_AT: str = "FUTURE_AVAILABLE_AT"
    MISSING_AVAILABLE_AT: str = "MISSING_AVAILABLE_AT"
    INGESTED_AT_USED_AS_AVAILABILITY: str = (
        "INGESTED_AT_USED_AS_AVAILABILITY"
    )
    UNCLOSED_CANDLE_FIELD_ACCESS: str = "UNCLOSED_CANDLE_FIELD_ACCESS"
    OUTCOME_LABEL_DURING_BLIND_WINDOW: str = (
        "OUTCOME_LABEL_DURING_BLIND_WINDOW"
    )

    ALLOWED: frozenset = frozenset(
        {
            FUTURE_AVAILABLE_AT,
            MISSING_AVAILABLE_AT,
            INGESTED_AT_USED_AS_AVAILABILITY,
            UNCLOSED_CANDLE_FIELD_ACCESS,
            OUTCOME_LABEL_DURING_BLIND_WINDOW,
        }
    )


class NoLookaheadViolationSeverity:
    """Closed enum of no-lookahead violation severities."""

    P0: str = "P0"
    P1: str = "P1"

    ALLOWED: frozenset = frozenset({P0, P1})


# ---------------------------------------------------------------------------
# NoLookaheadViolation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NoLookaheadViolation:
    """A no-lookahead violation. Audit-only / descriptive.

    Constitution §5 / §F: violations of the time-wall MUST be visible
    and auditable. The Time-Wall Guard records one
    :class:`NoLookaheadViolation` per rejected read; the violation is
    descriptive substrate that downstream (separately gated) PR95..PR100
    modules will consume to invalidate runs under §F.

    A NoLookaheadViolation is NOT a trade. It is NOT a runtime patch.
    It NEVER carries direction, sizing, leverage, stop, target, or
    risk-budget fields. It NEVER authorises live trading,
    auto-tuning, or Phase 12.
    """

    violation_id: str
    reason: str
    simulated_time: datetime
    record_id: Optional[str] = None
    symbol: Optional[str] = None
    event_time: Optional[datetime] = None
    available_at: Optional[datetime] = None
    source: Optional[str] = None
    severity: str = NoLookaheadViolationSeverity.P0
    detail: Optional[str] = None
    # Hard-pinned safety flags surfaced on every violation record:
    phase_12_forbidden: bool = True
    auto_tuning_allowed: bool = False
    trade_authority: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.violation_id, str) or not self.violation_id:
            raise ValueError("violation_id must be a non-empty string")
        if self.reason not in NoLookaheadViolationReason.ALLOWED:
            raise ValueError(
                f"reason must be one of "
                f"{sorted(NoLookaheadViolationReason.ALLOWED)}, got "
                f"{self.reason!r}"
            )
        if self.severity not in NoLookaheadViolationSeverity.ALLOWED:
            raise ValueError(
                f"severity must be one of "
                f"{sorted(NoLookaheadViolationSeverity.ALLOWED)}, got "
                f"{self.severity!r}"
            )
        st = ensure_utc_aware(self.simulated_time, "simulated_time")
        object.__setattr__(self, "simulated_time", st)
        if self.event_time is not None:
            object.__setattr__(
                self,
                "event_time",
                ensure_utc_aware(self.event_time, "event_time"),
            )
        if self.available_at is not None:
            object.__setattr__(
                self,
                "available_at",
                ensure_utc_aware(self.available_at, "available_at"),
            )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "phase": PHASE_NAME,
            "violation_id": self.violation_id,
            "reason": self.reason,
            "severity": self.severity,
            "simulated_time": self.simulated_time.isoformat(),
            "record_id": self.record_id,
            "symbol": self.symbol,
            "event_time": (
                self.event_time.isoformat()
                if self.event_time is not None
                else None
            ),
            "available_at": (
                self.available_at.isoformat()
                if self.available_at is not None
                else None
            ),
            "source": self.source,
            "detail": self.detail,
            # Hard-pinned safety flags:
            "phase_12_forbidden": True,
            "auto_tuning_allowed": False,
            "trade_authority": False,
            # Defensive non-trade markers (visible to reviewers):
            "is_no_lookahead_violation": True,
            "is_trade": False,
            "is_runtime_patch": False,
        }
        # Defensive: refuse to emit a forbidden field smuggled by a
        # caller via a hostile dataclass subclass / field override.
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# Internal: record-time extraction
# ---------------------------------------------------------------------------


def _maybe_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return ensure_utc_aware(value, "record_time")
    raise TypeError(
        f"record time fields must be datetime or None, got "
        f"{type(value)!r}"
    )


def _extract_record_time(
    record: Any,
) -> Tuple[
    Optional[datetime],
    Optional[datetime],
    Optional[datetime],
    Optional[str],
    Optional[str],
    Optional[str],
]:
    """Return ``(event_time, available_at, ingested_at, record_id,
    symbol, source)`` for a record. Missing fields are None.

    Accepted shapes: :class:`HistoricalRecordTime`, or a
    :class:`Mapping` carrying ``event_time`` / ``available_at`` /
    ``ingested_at`` / ``record_id`` / ``symbol`` / ``source`` keys.
    """
    if isinstance(record, HistoricalRecordTime):
        return (
            record.event_time,
            record.available_at,
            record.ingested_at,
            record.record_id,
            record.symbol,
            record.source,
        )
    if isinstance(record, Mapping):
        return (
            _maybe_dt(record.get("event_time")),
            _maybe_dt(record.get("available_at")),
            _maybe_dt(record.get("ingested_at")),
            record.get("record_id"),
            record.get("symbol"),
            record.get("source"),
        )
    raise TypeError(
        f"record must be HistoricalRecordTime or Mapping, got "
        f"{type(record)!r}"
    )


# ---------------------------------------------------------------------------
# TimeWallGuard
# ---------------------------------------------------------------------------


class TimeWallGuard:
    """Strict blind walk-forward time-wall enforcement.

    Rule: at simulated time ``T``, only records whose
    ``available_at <= T`` are visible. Records whose
    ``available_at > T`` MUST be rejected and audited. Records with
    no ``available_at`` are also rejected (we cannot prove they were
    visible at ``T``).

    The guard is pure / deterministic and never opens any network. It
    has no knowledge of trade direction, sizing, leverage, stops, or
    targets - it ONLY enforces time-wall visibility.
    """

    def __init__(self) -> None:
        # Defensive tripwires: the guard cannot accidentally advertise
        # capabilities it must never have.
        self.sandbox_only: bool = True
        self.live_trading: bool = False
        self.exchange_live_orders: bool = False
        self.binance_private_api_enabled: bool = False
        self.telegram_outbound_enabled: bool = False
        self.ai_trade_authority: bool = False
        self.trade_authority: bool = False
        self.auto_tuning_allowed: bool = False
        self.phase_12_forbidden: bool = True
        self._violation_counter: int = 0

    # ----- public API -----

    def can_read(
        self,
        record: Any,
        simulated_time: datetime,
    ) -> bool:
        """Return True iff the record may be read at ``simulated_time``.

        A record may be read iff its ``available_at`` is present AND
        ``available_at <= simulated_time``.
        """
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        _, available_at, _, _, _, _ = _extract_record_time(record)
        if available_at is None:
            return False
        return available_at <= sim

    def assert_can_read(
        self,
        record: Any,
        simulated_time: datetime,
    ) -> NoLookaheadViolation:
        """Raise :class:`ValueError` if the record cannot be read.

        On rejection the constructed :class:`NoLookaheadViolation` is
        attached to the exception via ``args``; callers that prefer
        the violation object should use :meth:`validate_no_lookahead`
        instead.
        """
        violation = self.validate_no_lookahead(record, simulated_time)
        if violation is not None:
            raise ValueError(
                f"NO_LOOKAHEAD_VIOLATION: {violation.reason} "
                f"(record_id={violation.record_id!r}, "
                f"symbol={violation.symbol!r}, "
                f"available_at={violation.available_at}, "
                f"simulated_time={violation.simulated_time})"
            )
        return None  # type: ignore[return-value]

    def filter_available(
        self,
        records: Iterable[Any],
        simulated_time: datetime,
    ) -> Tuple[List[Any], List[NoLookaheadViolation]]:
        """Filter ``records`` into ``(allowed, violations)``.

        ``allowed`` contains records whose ``available_at <= T``.
        ``violations`` contains a :class:`NoLookaheadViolation` for
        every rejected record (future ``available_at`` OR missing
        ``available_at``). Records are NEVER silently dropped - every
        rejected record produces an auditable violation object.
        """
        allowed: List[Any] = []
        violations: List[NoLookaheadViolation] = []
        for record in records:
            v = self.validate_no_lookahead(record, simulated_time)
            if v is None:
                allowed.append(record)
            else:
                violations.append(v)
        return allowed, violations

    def reject_future_records(
        self,
        records: Iterable[Any],
        simulated_time: datetime,
    ) -> List[NoLookaheadViolation]:
        """Return one :class:`NoLookaheadViolation` per rejected record."""
        return self.filter_available(records, simulated_time)[1]

    def validate_no_lookahead(
        self,
        record: Any,
        simulated_time: datetime,
    ) -> Optional[NoLookaheadViolation]:
        """Return a :class:`NoLookaheadViolation` if the record cannot
        be read at ``simulated_time``, else ``None``.
        """
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        et, avail, _ingested, rid, sym, src = _extract_record_time(record)

        # MISSING_AVAILABLE_AT.
        if avail is None:
            return self._make_violation(
                reason=NoLookaheadViolationReason.MISSING_AVAILABLE_AT,
                simulated_time=sim,
                record_id=rid,
                symbol=sym,
                event_time=et,
                available_at=None,
                source=src,
                detail=(
                    "record carries no available_at; cannot prove the "
                    "record was visible at the simulated time"
                ),
            )
        # FUTURE_AVAILABLE_AT.
        if avail > sim:
            return self._make_violation(
                reason=NoLookaheadViolationReason.FUTURE_AVAILABLE_AT,
                simulated_time=sim,
                record_id=rid,
                symbol=sym,
                event_time=et,
                available_at=avail,
                source=src,
                detail=(
                    f"available_at={avail.isoformat()} > simulated_time"
                    f"={sim.isoformat()}; record is in the future and "
                    "MUST NOT be read inside the blind window"
                ),
            )

        return None

    def make_ingested_at_used_as_availability_violation(
        self,
        record: Any,
        simulated_time: datetime,
    ) -> NoLookaheadViolation:
        """Construct a violation flagging ``ingested_at`` substituted
        for ``available_at``.

        Constitution §5: ``ingested_at`` is NOT a substitute for
        ``available_at``. A record whose ``ingested_at <= T`` but
        whose ``available_at > T`` is still future data and MUST be
        rejected. Callers (downstream PR95..PR100) MUST use this
        helper to record the audit event when they detect the
        substitution.
        """
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        et, avail, _ingested, rid, sym, src = _extract_record_time(
            record
        )
        return self._make_violation(
            reason=(
                NoLookaheadViolationReason
                .INGESTED_AT_USED_AS_AVAILABILITY
            ),
            simulated_time=sim,
            record_id=rid,
            symbol=sym,
            event_time=et,
            available_at=avail,
            source=src,
            detail=(
                "ingested_at is NOT a valid substitute for "
                "available_at; rejected as future data"
            ),
        )

    def make_outcome_label_violation(
        self,
        *,
        simulated_time: datetime,
        label: str,
        record_id: Optional[str] = None,
        symbol: Optional[str] = None,
        event_time: Optional[datetime] = None,
        available_at: Optional[datetime] = None,
        source: Optional[str] = None,
    ) -> NoLookaheadViolation:
        """Construct a violation for an outcome label read inside a
        blind window.

        Constitution §7: outcome labels MAY ONLY be used after the
        blind window has closed. Reading any of the closed-list labels
        inside the window is a NO_LOOKAHEAD_VIOLATION.
        """
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        if not isinstance(label, str) or not label:
            raise ValueError("label must be a non-empty string")
        return self._make_violation(
            reason=(
                NoLookaheadViolationReason
                .OUTCOME_LABEL_DURING_BLIND_WINDOW
            ),
            simulated_time=sim,
            record_id=record_id,
            symbol=symbol,
            event_time=event_time,
            available_at=available_at,
            source=source,
            detail=(
                f"outcome label {label!r} accessed inside the blind "
                "window; outcome labels are only valid after the "
                "window has closed (Constitution §7)"
            ),
        )

    def make_unclosed_candle_field_access_violation(
        self,
        *,
        simulated_time: datetime,
        field_name: str,
        candle_open_time: datetime,
        interval: str,
        record_id: Optional[str] = None,
        symbol: Optional[str] = None,
        source: Optional[str] = None,
    ) -> NoLookaheadViolation:
        """Construct a violation for a final OHLCV field access on an
        unclosed candle.

        Constitution §6: a 1m / 5m / longer-period candle's final
        OHLCV (``high`` / ``low`` / ``close`` / ``volume``) is
        invisible until the candle has closed.
        """
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        ot = ensure_utc_aware(candle_open_time, "candle_open_time")
        seconds = parse_interval_seconds(interval)
        close_time = ot + timedelta(seconds=seconds)
        return self._make_violation(
            reason=(
                NoLookaheadViolationReason.UNCLOSED_CANDLE_FIELD_ACCESS
            ),
            simulated_time=sim,
            record_id=record_id,
            symbol=symbol,
            event_time=ot,
            available_at=close_time,
            source=source,
            detail=(
                f"unclosed-candle final field {field_name!r} accessed "
                f"at simulated_time={sim.isoformat()} but candle "
                f"closes at {close_time.isoformat()} (open_time="
                f"{ot.isoformat()}, interval={interval!r}); final "
                "OHLCV is invisible before close (Constitution §6)"
            ),
        )

    # ----- internal helpers -----

    def _next_violation_id(self) -> str:
        self._violation_counter += 1
        return f"nlv_{self._violation_counter:06d}"

    def _make_violation(
        self,
        *,
        reason: str,
        simulated_time: datetime,
        record_id: Optional[str],
        symbol: Optional[str],
        event_time: Optional[datetime],
        available_at: Optional[datetime],
        source: Optional[str],
        detail: Optional[str],
    ) -> NoLookaheadViolation:
        return NoLookaheadViolation(
            violation_id=self._next_violation_id(),
            reason=reason,
            simulated_time=simulated_time,
            record_id=record_id,
            symbol=symbol,
            event_time=event_time,
            available_at=available_at,
            source=source,
            detail=detail,
        )


# ---------------------------------------------------------------------------
# CandleVisibilityGuard
# ---------------------------------------------------------------------------


# Final OHLCV fields that REQUIRE the candle to be closed before they
# may be read.
_FINAL_CANDLE_FIELDS: frozenset = frozenset(
    {"high", "low", "close", "volume"}
)


# Open / partial-metadata fields that MAY be read while the candle is
# still open (provided the candle is treated as partial).
_PARTIAL_VIEW_FIELDS: frozenset = frozenset(
    {
        "open_time",
        "open",
        "interval",
        "symbol",
        "is_partial",
        "source",
        "available_at",
        "event_time",
    }
)


class CandleVisibilityGuard:
    """Closed-candle visibility enforcement.

    Constitution §6: a 1m / 5m / longer-period candle's final OHLCV
    is fully visible only after that candle has closed. Unfinished
    candles MUST NOT have their ``high``, ``low``, ``close``, or
    ``volume`` read. Without tick / trade data, intra-bar paths are
    ambiguous and cannot be inferred.

    A 1m candle that opens at ``T_open`` closes at
    ``T_open + 60 seconds``. The candle is considered closed when
    ``simulated_time >= T_close``.
    """

    FINAL_FIELDS: frozenset = _FINAL_CANDLE_FIELDS
    PARTIAL_VIEW_FIELDS: frozenset = _PARTIAL_VIEW_FIELDS

    def __init__(self) -> None:
        # Defensive tripwires (mirrors TimeWallGuard).
        self.sandbox_only: bool = True
        self.live_trading: bool = False
        self.phase_12_forbidden: bool = True
        self.auto_tuning_allowed: bool = False
        self.trade_authority: bool = False

    # ----- public API -----

    @classmethod
    def candle_close_time(
        cls,
        open_time: datetime,
        interval: str,
    ) -> datetime:
        """Return the candle close time given its open time + interval.

        Close time is conventionally the start of the next candle
        (``open_time + interval_seconds``).
        """
        ot = ensure_utc_aware(open_time, "open_time")
        seconds = parse_interval_seconds(interval)
        return ot + timedelta(seconds=seconds)

    @classmethod
    def is_candle_closed(
        cls,
        candle_open_time: datetime,
        interval: str,
        simulated_time: datetime,
    ) -> bool:
        """Return True iff the candle is closed at ``simulated_time``.

        A candle is closed when ``simulated_time >= candle_close_time``.
        A simulated-time tick exactly at the close instant counts as
        closed.
        """
        close_time = cls.candle_close_time(candle_open_time, interval)
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        return sim >= close_time

    def assert_candle_fields_visible(
        self,
        candle: Mapping[str, Any],
        simulated_time: datetime,
    ) -> None:
        """Raise :class:`ValueError` if any final OHLCV field is read
        on a candle whose close time is in the future at
        ``simulated_time``.

        The candle MUST carry ``open_time`` (UTC-aware) and
        ``interval``; otherwise we cannot compute the close time and
        we conservatively refuse.
        """
        if not isinstance(candle, Mapping):
            raise TypeError(
                f"candle must be a Mapping, got {type(candle)!r}"
            )
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        ot = _maybe_dt(candle.get("open_time"))
        interval = candle.get("interval")
        if ot is None or not isinstance(interval, str):
            raise ValueError(
                "candle must carry timezone-aware open_time and "
                "interval to be checked for closed-candle visibility"
            )
        if self.is_candle_closed(ot, interval, sim):
            return
        # Candle is still open. Refuse any final-field access.
        for k in self.FINAL_FIELDS:
            if k in candle and candle[k] is not None:
                close_time = self.candle_close_time(ot, interval)
                raise ValueError(
                    f"UNCLOSED_CANDLE_FIELD_ACCESS: cannot read "
                    f"final OHLCV field {k!r} before candle close "
                    f"at open_time={ot.isoformat()} interval="
                    f"{interval!r} close_time="
                    f"{close_time.isoformat()} simulated_time="
                    f"{sim.isoformat()}"
                )

    def visible_candle_fields(
        self,
        candle: Mapping[str, Any],
        simulated_time: datetime,
    ) -> Dict[str, Any]:
        """Return a copy of ``candle`` with final OHLCV fields stripped
        if the candle is still open.

        If the candle is closed: full payload is returned.
        If the candle is unclosed: only :data:`PARTIAL_VIEW_FIELDS`
        are kept; final OHLCV (``high`` / ``low`` / ``close`` /
        ``volume``) are stripped.
        """
        if not isinstance(candle, Mapping):
            raise TypeError(
                f"candle must be a Mapping, got {type(candle)!r}"
            )
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        ot = _maybe_dt(candle.get("open_time"))
        interval = candle.get("interval")
        if ot is None or not isinstance(interval, str):
            raise ValueError(
                "candle must carry timezone-aware open_time and "
                "interval to compute visible fields"
            )
        if self.is_candle_closed(ot, interval, sim):
            return dict(candle)
        return {
            k: v
            for k, v in candle.items()
            if k in self.PARTIAL_VIEW_FIELDS
        }


__all__ = [
    "PHASE_NAME",
    "FORBIDDEN_OUTPUT_FIELDS",
    "assert_no_forbidden_fields",
    "NoLookaheadViolation",
    "NoLookaheadViolationReason",
    "NoLookaheadViolationSeverity",
    "TimeWallGuard",
    "CandleVisibilityGuard",
]
