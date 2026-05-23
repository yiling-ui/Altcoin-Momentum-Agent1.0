"""Phase 11C.1C-C-A - MFE / MAE Label Queue Runtime & Tail Outcome
Tracking.

The Phase 11C.1C-A ``LABEL_QUEUE_ENQUEUED`` event is the *contract* a
future MFE / MAE / Tail-label processor consumes; this module ships
that processor.

Goal
----

Validate Phase 11C.1C-B's ``early_tail_score`` /
``opportunity_score`` / ``strategy_mode`` decisions by labelling
*forward-looking outcomes* on every candidate the WS-radar chain
admits. The labels feed the future Strategy Validation Lab and let
Reflection answer the question: "did the runtime catch the demon
coin early enough?".

Phase 11C.1C-C-A boundary
-------------------------

This runtime:

  - records candidate outcome labels only;
  - NEVER opens, closes, or reasons about a real position;
  - NEVER reads a private API / signed endpoint / private WS /
    listenKey / account / order / position / leverage / margin
    endpoint;
  - NEVER infers live position PnL;
  - NEVER calls an LLM / Telegram outbound / DeepSeek trade-decision
    endpoint;
  - NEVER opens a path into Phase 12 / Strategy Validation Lab /
    AI Learning;
  - emits every event through :class:`EventRepository` only;
  - tags every event with a ``schema_version`` field so old events
    without the runtime sub-block remain replayable verbatim.

The runtime is the single owner of the in-process MFE / MAE state.
The :class:`WSRadarChainDriver` calls :meth:`LabelQueueRuntime.observe`
once per candidate per chain pass; the runner calls
:meth:`LabelQueueRuntime.tick` periodically to expire stale records.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from loguru import logger

from app.adaptive.models import AdaptiveCandidateContext
from app.core.clock import now_ms
from app.core.events import Event, EventType
from app.database.repositories import EventRepository


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: Schema version stamp written onto every Phase 11C.1C-C-A event
#: payload. A future PR that changes the payload shape MUST bump this
#: label and update :data:`KNOWN_LABEL_TRACKING_SCHEMA_VERSIONS` so
#: Replay can detect the change explicitly.
LABEL_TRACKING_SCHEMA_VERSION: str = "phase_11c_1c_c_a.label_tracking.v1"
KNOWN_LABEL_TRACKING_SCHEMA_VERSIONS: tuple[str, ...] = (
    LABEL_TRACKING_SCHEMA_VERSION,
)

#: Allowed values for :attr:`LabelTrackingRecord.status`.
LABEL_TRACKING_STATUSES: tuple[str, ...] = (
    "pending",
    "completed",
    "expired",
    "unresolved",
)

#: Allowed rule-based tail labels.
TAIL_LABELS: tuple[str, ...] = (
    "strong_tail",
    "moderate_tail",
    "weak_tail",
    "fake_breakout",
    "late_chase_failure",
    "dumped",
    "unresolved",
)

#: Default tracking-window seconds map. Order matters: the runtime
#: iterates the dict in insertion order, so "5m" fires first.
DEFAULT_TRACKING_WINDOW_SECONDS: dict[str, int] = {
    "5m": 5 * 60,
    "15m": 15 * 60,
    "30m": 30 * 60,
    "1h": 60 * 60,
    "4h": 4 * 60 * 60,
}

#: Window selected as the *primary* tail-label driver. When this
#: window completes, the record's overall ``status`` flips to
#: ``completed`` and the record's ``final_tail_label`` is set.
DEFAULT_PRIMARY_WINDOW: str = "5m"


# ---------------------------------------------------------------------------
# Configuration (every threshold is configurable, NOT hard-coded)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LabelQueueRuntimeConfig:
    """Tunable thresholds for the Phase 11C.1C-C-A runtime.

    Brief mandates: every threshold MUST be configurable. The defaults
    below are conservative and designed for a 4h paper run; the
    runner / tests can override any of them at construction time.
    """

    enabled: bool = True
    max_pending_records: int = 500
    grace_period_seconds: int = 5 * 60  # 5 min after the last window
    window_seconds_map: Mapping[str, int] = field(
        default_factory=lambda: dict(DEFAULT_TRACKING_WINDOW_SECONDS)
    )
    primary_window_for_tail_label: str = DEFAULT_PRIMARY_WINDOW

    # ---- Tail-label thresholds (paper / virtual; rule-based only) -----
    # ``strong_tail`` requires ``reached_5r`` AND the per-window MAE
    # did NOT breach this adverse threshold first.
    strong_tail_min_r_multiple: float = 5.0
    strong_tail_max_mae_pct: float = -0.04  # -4%

    # ``moderate_tail`` requires ``reached_3r`` and not ``reached_5r``.
    moderate_tail_min_r_multiple: float = 3.0

    # ``weak_tail`` requires ``reached_2r`` and not ``reached_3r``.
    weak_tail_min_r_multiple: float = 2.0

    # ``fake_breakout``: an early positive move that gets reversed.
    fake_breakout_min_mfe_pct: float = 0.03  # at least +3% MFE
    fake_breakout_min_drawdown_after_mfe_pct: float = -0.02  # MAE post-MFE <= -2%
    fake_breakout_max_final_pct: float = 0.005  # final return <= +0.5%

    # ``late_chase_failure``: high late_chase_risk + poor forward MFE.
    late_chase_failure_min_late_chase_risk: float = 60.0
    late_chase_failure_max_mfe_pct: float = 0.005  # < +0.5% upside

    # ``dumped``: severe adverse return with no meaningful upside.
    dumped_min_mae_drop_pct: float = -0.05  # MAE <= -5%
    dumped_max_mfe_pct: float = 0.01  # MFE < +1%

    # ``stopped_before_tail``: the candidate's MAE breached this
    # before any R milestone landed. Independent of dumped because
    # it is a *paper-stop* proxy (no real stop is sent).
    stopped_before_tail_pct: float = -0.04  # -4%

    # ``missed_tail``: the candidate's MFE in this window was at
    # least this big AND its strategy_mode was ``observe`` /
    # ``reject`` AND the stage was ``late`` / ``blowoff`` / ``dumped``.
    missed_tail_min_mfe_pct: float = 0.05  # +5%

    @staticmethod
    def from_mapping(mapping: Mapping[str, Any] | None) -> "LabelQueueRuntimeConfig":
        """Build a config from a YAML-style mapping. Unknown keys are
        ignored so a future YAML schema can ship new fields without
        breaking the runtime at boot."""
        if not mapping:
            return LabelQueueRuntimeConfig()
        kwargs: dict[str, Any] = {}
        for f in (
            "enabled",
            "max_pending_records",
            "grace_period_seconds",
            "primary_window_for_tail_label",
            "strong_tail_min_r_multiple",
            "strong_tail_max_mae_pct",
            "moderate_tail_min_r_multiple",
            "weak_tail_min_r_multiple",
            "fake_breakout_min_mfe_pct",
            "fake_breakout_min_drawdown_after_mfe_pct",
            "fake_breakout_max_final_pct",
            "late_chase_failure_min_late_chase_risk",
            "late_chase_failure_max_mfe_pct",
            "dumped_min_mae_drop_pct",
            "dumped_max_mfe_pct",
            "stopped_before_tail_pct",
            "missed_tail_min_mfe_pct",
        ):
            if f in mapping and mapping[f] is not None:
                kwargs[f] = mapping[f]
        if "window_seconds_map" in mapping and mapping["window_seconds_map"]:
            ws = {
                str(k): int(v)
                for k, v in dict(mapping["window_seconds_map"]).items()
                if int(v) > 0
            }
            if ws:
                kwargs["window_seconds_map"] = ws
        return LabelQueueRuntimeConfig(**kwargs)

    @staticmethod
    def from_settings_section(section: Any) -> "LabelQueueRuntimeConfig":
        """Build a config from a :class:`LabelQueueRuntimeSection`
        (Pydantic model). Pulled out to avoid a hard dependency on
        the Pydantic schema in this module.
        """
        if section is None:
            return LabelQueueRuntimeConfig()
        if hasattr(section, "model_dump"):
            return LabelQueueRuntimeConfig.from_mapping(section.model_dump())
        if isinstance(section, Mapping):
            return LabelQueueRuntimeConfig.from_mapping(section)
        # Fallback: treat as an opaque object with attribute access.
        attrs: dict[str, Any] = {}
        for f in (
            "enabled",
            "max_pending_records",
            "grace_period_seconds",
            "primary_window_for_tail_label",
            "window_seconds_map",
            "strong_tail_min_r_multiple",
            "strong_tail_max_mae_pct",
            "moderate_tail_min_r_multiple",
            "weak_tail_min_r_multiple",
            "fake_breakout_min_mfe_pct",
            "fake_breakout_min_drawdown_after_mfe_pct",
            "fake_breakout_max_final_pct",
            "late_chase_failure_min_late_chase_risk",
            "late_chase_failure_max_mfe_pct",
            "dumped_min_mae_drop_pct",
            "dumped_max_mfe_pct",
            "stopped_before_tail_pct",
            "missed_tail_min_mfe_pct",
        ):
            if hasattr(section, f):
                attrs[f] = getattr(section, f)
        return LabelQueueRuntimeConfig.from_mapping(attrs)


# ---------------------------------------------------------------------------
# Mutable record / window state (intentionally NOT frozen)
# ---------------------------------------------------------------------------
@dataclass
class TrackingWindowState:
    """One MFE / MAE / R-multiple tracking window for one record.

    The runtime updates these fields in place as fresh prices arrive.
    The window's ``window_start_ts`` is anchored to the candidate's
    ``candidate_first_seen_ts`` so MFE / MAE measure the *upside /
    downside since first-seen* (Phase 11C.1C-C-A brief contract).
    """

    window_name: str
    window_seconds: int
    window_start_ts: int  # ms
    window_end_ts: int  # ms
    start_price: float
    latest_price: float = 0.0
    mfe_pct: float = 0.0
    mae_pct: float = 0.0
    mfe_price: float = 0.0
    mae_price: float = 0.0
    max_future_return: float = 0.0
    max_adverse_return: float = 0.0
    time_to_mfe: int = 0  # ms relative to candidate_first_seen_ts
    time_to_mae: int = 0  # ms relative to candidate_first_seen_ts
    reached_2r: bool = False
    reached_3r: bool = False
    reached_5r: bool = False
    reached_10r: bool = False
    stopped_before_tail: bool = False
    missed_tail: bool = False
    fake_breakout: bool = False
    tail_label: str = ""
    completed: bool = False
    no_virtual_risk_unit: bool = False
    last_observation_ts: int = 0

    def to_payload(self) -> dict[str, Any]:
        return {
            "window_name": str(self.window_name),
            "window_seconds": int(self.window_seconds),
            "window_start_ts": int(self.window_start_ts),
            "window_end_ts": int(self.window_end_ts),
            "start_price": float(self.start_price),
            "latest_price": float(self.latest_price),
            "mfe_pct": float(self.mfe_pct),
            "mae_pct": float(self.mae_pct),
            "mfe_price": float(self.mfe_price),
            "mae_price": float(self.mae_price),
            "max_future_return": float(self.max_future_return),
            "max_adverse_return": float(self.max_adverse_return),
            "time_to_mfe": int(self.time_to_mfe),
            "time_to_mae": int(self.time_to_mae),
            "reached_2r": bool(self.reached_2r),
            "reached_3r": bool(self.reached_3r),
            "reached_5r": bool(self.reached_5r),
            "reached_10r": bool(self.reached_10r),
            "stopped_before_tail": bool(self.stopped_before_tail),
            "missed_tail": bool(self.missed_tail),
            "fake_breakout": bool(self.fake_breakout),
            "tail_label": str(self.tail_label or ""),
            "completed": bool(self.completed),
            "no_virtual_risk_unit": bool(self.no_virtual_risk_unit),
            "last_observation_ts": int(self.last_observation_ts),
        }


@dataclass
class LabelTrackingRecord:
    """One Phase 11C.1C-C-A label-tracking record per opportunity.

    Mutable on purpose: the runtime updates ``current_price`` and
    each :class:`TrackingWindowState` in place on every fresh tick.

    Idempotency: the runtime registers at most one ACTIVE record per
    ``opportunity_id`` (or, when missing, per
    ``(symbol, candidate_first_seen_ts, first_seen_price)``).
    """

    tracking_id: str
    opportunity_id: str
    scan_batch_id: str
    symbol: str
    candidate_first_seen_ts: int
    first_seen_price: float
    current_price: float
    tracking_started_ts: int
    source_event_id: str
    early_tail_score: float
    opportunity_score: float
    strategy_mode: str
    candidate_stage: str
    late_chase_risk: float
    freshness_score: float
    distance_from_first_seen: float
    distance_to_24h_high: float
    virtual_risk_unit_pct: float | None
    tracking_windows: list[TrackingWindowState]
    status: str = "pending"
    final_tail_label: str | None = None
    last_update_ts: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        return {
            "tracking_id": str(self.tracking_id),
            "opportunity_id": str(self.opportunity_id),
            "scan_batch_id": str(self.scan_batch_id),
            "symbol": str(self.symbol),
            "candidate_first_seen_ts": int(self.candidate_first_seen_ts),
            "first_seen_price": float(self.first_seen_price),
            "current_price": float(self.current_price),
            "tracking_started_ts": int(self.tracking_started_ts),
            "source_event_id": str(self.source_event_id),
            "early_tail_score": float(self.early_tail_score),
            "opportunity_score": float(self.opportunity_score),
            "strategy_mode": str(self.strategy_mode),
            "candidate_stage": str(self.candidate_stage),
            "late_chase_risk": float(self.late_chase_risk),
            "freshness_score": float(self.freshness_score),
            "distance_from_first_seen": float(self.distance_from_first_seen),
            "distance_to_24h_high": float(self.distance_to_24h_high),
            "virtual_risk_unit_pct": (
                float(self.virtual_risk_unit_pct)
                if self.virtual_risk_unit_pct is not None
                else None
            ),
            "tracking_windows": [
                w.to_payload() for w in self.tracking_windows
            ],
            "tracking_window_names": [w.window_name for w in self.tracking_windows],
            "status": str(self.status),
            "final_tail_label": (
                str(self.final_tail_label)
                if self.final_tail_label is not None
                else None
            ),
            "last_update_ts": int(self.last_update_ts),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def compute_pct_return(*, baseline_price: float, observed_price: float) -> float:
    """Return ``(observed - baseline) / baseline`` or 0.0 on bad data."""
    bp = float(baseline_price or 0.0)
    op = float(observed_price or 0.0)
    if bp <= 0.0:
        return 0.0
    return (op - bp) / bp


def update_window_with_price(
    *,
    window: TrackingWindowState,
    candidate_first_seen_ts: int,
    first_seen_price: float,
    ts_ms: int,
    price: float,
    virtual_risk_unit_pct: float | None,
    config: LabelQueueRuntimeConfig,
) -> bool:
    """Update one window with a new price observation.

    Returns ``True`` iff the window's MFE / MAE / R-flags advanced
    (the runtime uses the return value to decide whether to emit
    ``LABEL_WINDOW_UPDATED``).
    """
    if window.completed:
        return False
    if int(ts_ms) > int(window.window_end_ts):
        # The window already passed; do not overwrite frozen stats.
        return False
    if price <= 0.0:
        return False

    window.latest_price = float(price)
    window.last_observation_ts = int(ts_ms)
    pct = compute_pct_return(
        baseline_price=first_seen_price, observed_price=price
    )
    advanced = False

    # MFE: new high?
    if price > window.mfe_price:
        window.mfe_price = float(price)
        window.mfe_pct = float(pct)
        window.max_future_return = float(pct)
        window.time_to_mfe = max(
            0, int(ts_ms) - int(candidate_first_seen_ts)
        )
        advanced = True

    # MAE: new low?
    if window.mae_price <= 0.0 or price < window.mae_price:
        window.mae_price = float(price)
        window.mae_pct = float(pct)
        window.max_adverse_return = float(pct)
        window.time_to_mae = max(
            0, int(ts_ms) - int(candidate_first_seen_ts)
        )
        advanced = True

    # R-multiple flags: only when virtual_risk_unit_pct is provided.
    if virtual_risk_unit_pct is None or virtual_risk_unit_pct <= 0.0:
        window.no_virtual_risk_unit = True
    else:
        ru = float(virtual_risk_unit_pct)
        prev_2r = window.reached_2r
        prev_3r = window.reached_3r
        prev_5r = window.reached_5r
        prev_10r = window.reached_10r
        if window.mfe_pct >= 2.0 * ru:
            window.reached_2r = True
        if window.mfe_pct >= 3.0 * ru:
            window.reached_3r = True
        if window.mfe_pct >= 5.0 * ru:
            window.reached_5r = True
        if window.mfe_pct >= 10.0 * ru:
            window.reached_10r = True
        if (
            window.reached_2r != prev_2r
            or window.reached_3r != prev_3r
            or window.reached_5r != prev_5r
            or window.reached_10r != prev_10r
        ):
            advanced = True

    # ``stopped_before_tail`` proxy: MAE breached the configured
    # adverse threshold while no R milestone landed yet.
    if (
        window.mae_pct <= float(config.stopped_before_tail_pct)
        and not window.reached_2r
        and not window.stopped_before_tail
    ):
        window.stopped_before_tail = True
        advanced = True

    return advanced


def assign_tail_label_for_window(
    *,
    window: TrackingWindowState,
    record: LabelTrackingRecord,
    config: LabelQueueRuntimeConfig,
) -> tuple[str, bool, bool]:
    """Return ``(tail_label, missed_tail, fake_breakout)`` for one
    completed window.

    Rule-based; no LLM. The rules deliberately consult the original
    candidate's stage / strategy_mode / late_chase_risk so the label
    *measures the runtime's discovery quality* rather than the
    market alone.
    """
    final_pct = compute_pct_return(
        baseline_price=record.first_seen_price,
        observed_price=window.latest_price,
    )
    mfe = float(window.mfe_pct)
    mae = float(window.mae_pct)

    missed_tail = False
    fake_breakout = False

    # ---- Rule 1: strong / moderate / weak tail (R-multiple ladder) ----
    has_r = (
        record.virtual_risk_unit_pct is not None
        and float(record.virtual_risk_unit_pct) > 0.0
    )
    label = ""
    if has_r:
        if (
            window.reached_5r
            and mae > float(config.strong_tail_max_mae_pct)
            and not window.stopped_before_tail
        ):
            label = "strong_tail"
        elif window.reached_3r and not window.reached_5r:
            label = "moderate_tail"
        elif window.reached_2r and not window.reached_3r:
            label = "weak_tail"

    # ---- Rule 2: fake_breakout ----
    if not label:
        if (
            mfe >= float(config.fake_breakout_min_mfe_pct)
            and final_pct <= float(config.fake_breakout_max_final_pct)
            and (
                mae - mfe
                <= float(config.fake_breakout_min_drawdown_after_mfe_pct)
            )
        ):
            label = "fake_breakout"
            fake_breakout = True

    # ---- Rule 3: late_chase_failure ----
    if not label:
        if (
            float(record.late_chase_risk)
            >= float(config.late_chase_failure_min_late_chase_risk)
            and mfe <= float(config.late_chase_failure_max_mfe_pct)
        ):
            label = "late_chase_failure"

    # ---- Rule 4: dumped ----
    if not label:
        if (
            mae <= float(config.dumped_min_mae_drop_pct)
            and mfe < float(config.dumped_max_mfe_pct)
        ):
            label = "dumped"

    # ---- Rule 5: missed_tail (independent flag) ----
    # A window with a meaningful upside the chain refused to follow.
    observe_or_reject = record.strategy_mode in {"observe", "reject"}
    late_or_blowoff = record.candidate_stage in {"late", "blowoff", "dumped"}
    if (
        mfe >= float(config.missed_tail_min_mfe_pct)
        and observe_or_reject
        and late_or_blowoff
    ):
        missed_tail = True

    # Default: unresolved.
    if not label:
        label = "unresolved"
        # Add a hint when no R is available so consumers can audit.
        if not has_r:
            window.no_virtual_risk_unit = True

    if label not in TAIL_LABELS:
        label = "unresolved"

    return label, missed_tail, fake_breakout


# ---------------------------------------------------------------------------
# LabelQueueRuntime
# ---------------------------------------------------------------------------
class LabelQueueRuntime:
    """Phase 11C.1C-C-A MFE / MAE label tracking runtime.

    Wires into the WS-radar event chain:

      - :meth:`observe` is called once per candidate per chain pass;
        creates the record on first call (idempotent), updates
        prices on subsequent calls;
      - :meth:`tick` is called periodically by the runner to expire
        stale records;
      - :meth:`metrics_payload` returns the daily-report aggregates;
      - every event flows through :class:`EventRepository` only.

    The runtime never opens a socket, never reads ``os.environ``,
    never imports an exchange / Telegram / LLM library, never
    mutates settings, and never authorises a real trade. The entire
    surface is paper / virtual.
    """

    SOURCE_MODULE = "adaptive.label_runtime"
    SOURCE_PHASE = "phase_11c_1c_c_a_mfe_mae_label_queue_runtime"

    def __init__(
        self,
        *,
        event_repo: EventRepository,
        config: LabelQueueRuntimeConfig | None = None,
        clock_ms_fn=None,
    ) -> None:
        self._event_repo = event_repo
        self._config = config or LabelQueueRuntimeConfig()
        self._clock_ms_fn = clock_ms_fn or now_ms
        self._records: dict[str, LabelTrackingRecord] = {}  # tracking_id -> rec
        # Idempotency indexes.
        self._index_by_opp: dict[str, str] = {}
        self._index_by_fallback: dict[tuple[str, int, float], str] = {}

        # Counters surfaced to the daily report.
        self._tracking_started_count = 0
        self._window_updated_count = 0
        self._window_completed_count = 0
        self._tail_label_assigned_count = 0
        self._missed_tail_detected_count = 0
        self._fake_breakout_detected_count = 0
        self._records_dropped_capacity = 0

    # ------------------------------------------------------------------
    @property
    def config(self) -> LabelQueueRuntimeConfig:
        return self._config

    @property
    def records(self) -> tuple[LabelTrackingRecord, ...]:
        """Snapshot view of every record. The tuple is a fresh shallow
        copy so callers cannot mutate the internal dict order."""
        return tuple(self._records.values())

    @property
    def tracking_started_count(self) -> int:
        return self._tracking_started_count

    @property
    def window_updated_count(self) -> int:
        return self._window_updated_count

    @property
    def window_completed_count(self) -> int:
        return self._window_completed_count

    @property
    def tail_label_assigned_count(self) -> int:
        return self._tail_label_assigned_count

    @property
    def missed_tail_detected_count(self) -> int:
        return self._missed_tail_detected_count

    @property
    def fake_breakout_detected_count(self) -> int:
        return self._fake_breakout_detected_count

    # ------------------------------------------------------------------
    def observe(
        self,
        *,
        adaptive: AdaptiveCandidateContext,
        source_event_id: str,
        current_price: float | None = None,
        ts_ms: int | None = None,
        virtual_risk_unit_pct: float | None = None,
    ) -> LabelTrackingRecord | None:
        """Register a record (first call) and update its windows.

        Returns the active :class:`LabelTrackingRecord` for the
        candidate, or ``None`` when the runtime is disabled.

        Idempotent on ``adaptive.opportunity_id``.
        """
        if not self._config.enabled:
            return None

        # Resolve identity inputs from the adaptive context.
        runtime_metrics = adaptive.runtime_calibration
        first_seen_ts = (
            int(runtime_metrics.candidate_first_seen_ts)
            if runtime_metrics is not None
            and runtime_metrics.candidate_first_seen_ts > 0
            else int(adaptive.candidate_stage.first_seen_ts or adaptive.timestamp_ms)
        )
        first_seen_price = (
            float(runtime_metrics.candidate_first_seen_price)
            if runtime_metrics is not None
            and runtime_metrics.candidate_first_seen_price > 0.0
            else float(adaptive.candidate_stage.first_seen_price or 0.0)
        )
        cp_value: float
        if current_price is not None and float(current_price) > 0.0:
            cp_value = float(current_price)
        elif (
            runtime_metrics is not None
            and runtime_metrics.current_price > 0.0
        ):
            cp_value = float(runtime_metrics.current_price)
        else:
            cp_value = float(adaptive.candidate_stage.current_price or 0.0)
        ts_value = int(ts_ms if ts_ms is not None else adaptive.timestamp_ms)
        if cp_value <= 0.0 or first_seen_price <= 0.0:
            # Cannot reasonably compute MFE / MAE without prices; drop.
            return None

        early_tail = (
            float(runtime_metrics.early_tail_score)
            if runtime_metrics is not None
            else 0.0
        )
        late_chase = (
            float(runtime_metrics.late_chase_risk)
            if runtime_metrics is not None
            else float(adaptive.candidate_stage.late_chase_risk * 100.0)
        )
        freshness = (
            float(runtime_metrics.freshness_score)
            if runtime_metrics is not None
            else float(adaptive.candidate_stage.freshness)
        )
        distance_from_fs = (
            float(runtime_metrics.distance_from_first_seen)
            if runtime_metrics is not None
            else float(adaptive.candidate_stage.distance_from_first_seen)
        )
        distance_to_high = (
            float(runtime_metrics.distance_to_24h_high)
            if runtime_metrics is not None
            else float(adaptive.candidate_stage.distance_to_24h_high)
        )

        existing = self._lookup(
            opportunity_id=adaptive.opportunity_id,
            symbol=adaptive.symbol,
            first_seen_ts=first_seen_ts,
            first_seen_price=first_seen_price,
        )
        if existing is None:
            # Capacity guard - do NOT grow unbounded.
            if (
                len(self._records)
                >= int(self._config.max_pending_records)
            ):
                self._records_dropped_capacity += 1
                logger.debug(
                    "[phase11c.1c-c-a] label-queue at capacity; dropping "
                    "candidate symbol={} opp={}",
                    adaptive.symbol,
                    adaptive.opportunity_id,
                )
                return None
            record = self._create_record(
                adaptive=adaptive,
                source_event_id=source_event_id,
                first_seen_ts=first_seen_ts,
                first_seen_price=first_seen_price,
                current_price=cp_value,
                tracking_started_ts=ts_value,
                early_tail_score=early_tail,
                late_chase_risk=late_chase,
                freshness_score=freshness,
                distance_from_first_seen=distance_from_fs,
                distance_to_24h_high=distance_to_high,
                virtual_risk_unit_pct=virtual_risk_unit_pct,
            )
            self._emit_label_tracking_started(record=record)
            existing = record
        else:
            # Refresh adaptive snapshot fields so a later
            # consumer can see the most recent stage / score / mode.
            existing.early_tail_score = early_tail
            existing.opportunity_score = float(
                adaptive.opportunity_score.score
            )
            existing.strategy_mode = str(adaptive.strategy_mode.mode)
            existing.candidate_stage = str(adaptive.candidate_stage.stage)
            existing.late_chase_risk = late_chase
            existing.freshness_score = freshness
            existing.distance_from_first_seen = distance_from_fs
            existing.distance_to_24h_high = distance_to_high
            if (
                virtual_risk_unit_pct is not None
                and existing.virtual_risk_unit_pct is None
            ):
                existing.virtual_risk_unit_pct = float(
                    virtual_risk_unit_pct
                )

        # Apply a price update (also triggers window-completion checks).
        self.update_price(
            symbol=adaptive.symbol,
            ts_ms=ts_value,
            price=cp_value,
            tracking_id=existing.tracking_id,
        )
        return existing

    # ------------------------------------------------------------------
    def update_price(
        self,
        *,
        symbol: str,
        ts_ms: int,
        price: float,
        tracking_id: str | None = None,
    ) -> None:
        """Apply a fresh price tick to the matching record(s).

        ``tracking_id`` may be supplied to scope the update; otherwise
        every active record for ``symbol`` is updated.
        """
        if price <= 0.0:
            return
        targets: list[LabelTrackingRecord] = []
        if tracking_id is not None:
            rec = self._records.get(tracking_id)
            if rec is not None:
                targets.append(rec)
        else:
            for rec in self._records.values():
                if rec.symbol == symbol and rec.status == "pending":
                    targets.append(rec)
        for rec in targets:
            self._apply_price_to_record(record=rec, ts_ms=ts_ms, price=price)

    def _apply_price_to_record(
        self,
        *,
        record: LabelTrackingRecord,
        ts_ms: int,
        price: float,
    ) -> None:
        record.current_price = float(price)
        record.last_update_ts = int(ts_ms)
        any_window_advanced = False
        for window in record.tracking_windows:
            if window.completed:
                continue
            advanced = update_window_with_price(
                window=window,
                candidate_first_seen_ts=record.candidate_first_seen_ts,
                first_seen_price=record.first_seen_price,
                ts_ms=ts_ms,
                price=price,
                virtual_risk_unit_pct=record.virtual_risk_unit_pct,
                config=self._config,
            )
            if advanced:
                any_window_advanced = True
                self._emit_label_window_updated(
                    record=record, window=window
                )
        # Now check for completions that the price observation may
        # have triggered (e.g. window_end_ts <= ts_ms).
        self._maybe_complete_windows(record=record, now_ms=int(ts_ms))

    # ------------------------------------------------------------------
    def tick(self, *, now_ms: int | None = None) -> None:
        """Periodic timer hook. Walks every record and:

          - completes any window whose ``window_end_ts`` <= ``now_ms``;
          - expires any record whose final window's grace period has
            elapsed without a primary-window completion.

        Safe to call as often as the runner likes; the runtime is
        idempotent in the steady state.
        """
        if now_ms is None:
            now_ms = int(self._clock_ms_fn())
        nm = int(now_ms)
        for record in list(self._records.values()):
            if record.status == "pending":
                self._maybe_complete_windows(record=record, now_ms=nm)
            self._maybe_expire(record=record, now_ms=nm)

    # ------------------------------------------------------------------
    def _maybe_complete_windows(
        self,
        *,
        record: LabelTrackingRecord,
        now_ms: int,
    ) -> None:
        primary_window = self._config.primary_window_for_tail_label
        for window in record.tracking_windows:
            if window.completed:
                continue
            if int(now_ms) < int(window.window_end_ts):
                continue
            # Freeze the window. If we never observed a price within
            # this window, we cannot label it - mark unresolved with
            # the no_virtual_risk_unit flag preserved for diagnostics.
            had_observation = window.last_observation_ts > 0
            if not had_observation:
                window.latest_price = record.first_seen_price
                window.mfe_price = record.first_seen_price
                window.mae_price = record.first_seen_price
                window.completed = True
                window.tail_label = "unresolved"
                self._emit_label_window_completed(
                    record=record, window=window
                )
                self._emit_tail_label_assigned(record=record, window=window)
                if window.window_name == primary_window:
                    record.status = "unresolved"
                    record.final_tail_label = "unresolved"
                continue
            window.completed = True
            label, missed_tail, fake_breakout = assign_tail_label_for_window(
                window=window, record=record, config=self._config
            )
            window.tail_label = label
            window.missed_tail = bool(missed_tail)
            window.fake_breakout = bool(fake_breakout)
            self._emit_label_window_completed(record=record, window=window)
            self._emit_tail_label_assigned(record=record, window=window)
            if missed_tail:
                self._emit_missed_tail_detected(
                    record=record, window=window
                )
            if fake_breakout:
                self._emit_fake_breakout_detected(
                    record=record, window=window
                )
            if window.window_name == primary_window:
                record.status = "completed"
                record.final_tail_label = label

    def _maybe_expire(
        self,
        *,
        record: LabelTrackingRecord,
        now_ms: int,
    ) -> None:
        if record.status not in {"pending"}:
            return
        if not record.tracking_windows:
            return
        last_window_end = max(
            int(w.window_end_ts) for w in record.tracking_windows
        )
        grace_ms = int(self._config.grace_period_seconds) * 1000
        if int(now_ms) < last_window_end + grace_ms:
            return
        # Past every window + grace. Mark expired (or unresolved if a
        # window completed but the primary window did not).
        had_any_completed = any(
            w.completed for w in record.tracking_windows
        )
        if had_any_completed and record.final_tail_label is None:
            record.status = "unresolved"
        else:
            record.status = "expired"

    # ------------------------------------------------------------------
    def _create_record(
        self,
        *,
        adaptive: AdaptiveCandidateContext,
        source_event_id: str,
        first_seen_ts: int,
        first_seen_price: float,
        current_price: float,
        tracking_started_ts: int,
        early_tail_score: float,
        late_chase_risk: float,
        freshness_score: float,
        distance_from_first_seen: float,
        distance_to_24h_high: float,
        virtual_risk_unit_pct: float | None,
    ) -> LabelTrackingRecord:
        tracking_id = f"label_track_{uuid.uuid4().hex}"
        windows: list[TrackingWindowState] = []
        for window_name, seconds in self._config.window_seconds_map.items():
            seconds_int = int(seconds)
            if seconds_int <= 0:
                continue
            window_end_ts = int(first_seen_ts) + seconds_int * 1000
            already_past = int(tracking_started_ts) > window_end_ts
            window = TrackingWindowState(
                window_name=str(window_name),
                window_seconds=seconds_int,
                window_start_ts=int(first_seen_ts),
                window_end_ts=window_end_ts,
                start_price=float(first_seen_price),
                latest_price=float(current_price),
                mfe_price=(
                    0.0 if already_past else float(current_price)
                ),
                mae_price=(
                    0.0 if already_past else float(current_price)
                ),
                no_virtual_risk_unit=(
                    virtual_risk_unit_pct is None
                    or virtual_risk_unit_pct <= 0.0
                ),
            )
            # Seed with the current observation when the window is
            # still active so the first ``update_window_with_price``
            # call doesn't have to special-case the empty state.
            if not already_past:
                pct = compute_pct_return(
                    baseline_price=first_seen_price,
                    observed_price=current_price,
                )
                window.mfe_pct = float(pct) if pct > 0 else 0.0
                window.mae_pct = float(pct) if pct < 0 else 0.0
                window.max_future_return = window.mfe_pct
                window.max_adverse_return = window.mae_pct
                window.last_observation_ts = int(tracking_started_ts)
            windows.append(window)
        record = LabelTrackingRecord(
            tracking_id=tracking_id,
            opportunity_id=str(adaptive.opportunity_id),
            scan_batch_id=str(adaptive.scan_batch_id),
            symbol=str(adaptive.symbol),
            candidate_first_seen_ts=int(first_seen_ts),
            first_seen_price=float(first_seen_price),
            current_price=float(current_price),
            tracking_started_ts=int(tracking_started_ts),
            source_event_id=str(source_event_id),
            early_tail_score=float(early_tail_score),
            opportunity_score=float(adaptive.opportunity_score.score),
            strategy_mode=str(adaptive.strategy_mode.mode),
            candidate_stage=str(adaptive.candidate_stage.stage),
            late_chase_risk=float(late_chase_risk),
            freshness_score=float(freshness_score),
            distance_from_first_seen=float(distance_from_first_seen),
            distance_to_24h_high=float(distance_to_24h_high),
            virtual_risk_unit_pct=(
                float(virtual_risk_unit_pct)
                if virtual_risk_unit_pct is not None
                else None
            ),
            tracking_windows=windows,
            status="pending",
            last_update_ts=int(tracking_started_ts),
        )
        self._records[tracking_id] = record
        if record.opportunity_id:
            self._index_by_opp[record.opportunity_id] = tracking_id
        else:
            self._index_by_fallback[
                (
                    record.symbol,
                    record.candidate_first_seen_ts,
                    round(record.first_seen_price, 8),
                )
            ] = tracking_id
        return record

    def _lookup(
        self,
        *,
        opportunity_id: str | None,
        symbol: str,
        first_seen_ts: int,
        first_seen_price: float,
    ) -> LabelTrackingRecord | None:
        if opportunity_id:
            tid = self._index_by_opp.get(str(opportunity_id))
            if tid is not None:
                return self._records.get(tid)
        key = (
            str(symbol),
            int(first_seen_ts),
            round(float(first_seen_price), 8),
        )
        tid = self._index_by_fallback.get(key)
        if tid is not None:
            return self._records.get(tid)
        return None

    # ------------------------------------------------------------------
    # Event emission helpers
    # ------------------------------------------------------------------
    def _identity_block(
        self, *, record: LabelTrackingRecord
    ) -> dict[str, Any]:
        return {
            "schema_version": LABEL_TRACKING_SCHEMA_VERSION,
            "source_phase": self.SOURCE_PHASE,
            "tracking_id": record.tracking_id,
            "opportunity_id": record.opportunity_id,
            "scan_batch_id": record.scan_batch_id,
            "symbol": record.symbol,
            "source_event_id": record.source_event_id,
            "candidate_first_seen_ts": int(record.candidate_first_seen_ts),
            "first_seen_price": float(record.first_seen_price),
            "current_price": float(record.current_price),
            "tracking_started_ts": int(record.tracking_started_ts),
            "early_tail_score": float(record.early_tail_score),
            "opportunity_score": float(record.opportunity_score),
            "strategy_mode": str(record.strategy_mode),
            "candidate_stage": str(record.candidate_stage),
            "late_chase_risk": float(record.late_chase_risk),
            "freshness_score": float(record.freshness_score),
            "distance_from_first_seen": float(
                record.distance_from_first_seen
            ),
            "distance_to_24h_high": float(record.distance_to_24h_high),
            "virtual_risk_unit_pct": (
                float(record.virtual_risk_unit_pct)
                if record.virtual_risk_unit_pct is not None
                else None
            ),
            "tracking_windows": [
                w.window_name for w in record.tracking_windows
            ],
            "status": record.status,
            "final_tail_label": record.final_tail_label,
        }

    def _emit_label_tracking_started(
        self, *, record: LabelTrackingRecord
    ) -> None:
        payload = {
            **self._identity_block(record=record),
            "label_tracking_record": record.to_payload(),
        }
        self._emit(
            EventType.LABEL_TRACKING_STARTED,
            symbol=record.symbol,
            timestamp=record.tracking_started_ts,
            payload=payload,
        )
        self._tracking_started_count += 1

    def _emit_label_window_updated(
        self,
        *,
        record: LabelTrackingRecord,
        window: TrackingWindowState,
    ) -> None:
        payload = {
            **self._identity_block(record=record),
            "window": window.to_payload(),
        }
        self._emit(
            EventType.LABEL_WINDOW_UPDATED,
            symbol=record.symbol,
            timestamp=window.last_observation_ts,
            payload=payload,
        )
        self._window_updated_count += 1

    def _emit_label_window_completed(
        self,
        *,
        record: LabelTrackingRecord,
        window: TrackingWindowState,
    ) -> None:
        payload = {
            **self._identity_block(record=record),
            "window": window.to_payload(),
        }
        self._emit(
            EventType.LABEL_WINDOW_COMPLETED,
            symbol=record.symbol,
            timestamp=window.window_end_ts,
            payload=payload,
        )
        self._window_completed_count += 1

    def _emit_tail_label_assigned(
        self,
        *,
        record: LabelTrackingRecord,
        window: TrackingWindowState,
    ) -> None:
        payload = {
            **self._identity_block(record=record),
            "window_name": window.window_name,
            "tail_label": str(window.tail_label),
            "mfe_pct": float(window.mfe_pct),
            "mae_pct": float(window.mae_pct),
            "reached_2r": bool(window.reached_2r),
            "reached_3r": bool(window.reached_3r),
            "reached_5r": bool(window.reached_5r),
            "reached_10r": bool(window.reached_10r),
            "stopped_before_tail": bool(window.stopped_before_tail),
            "missed_tail": bool(window.missed_tail),
            "fake_breakout": bool(window.fake_breakout),
            "no_virtual_risk_unit": bool(window.no_virtual_risk_unit),
        }
        self._emit(
            EventType.TAIL_LABEL_ASSIGNED,
            symbol=record.symbol,
            timestamp=window.window_end_ts,
            payload=payload,
        )
        self._tail_label_assigned_count += 1

    def _emit_missed_tail_detected(
        self,
        *,
        record: LabelTrackingRecord,
        window: TrackingWindowState,
    ) -> None:
        payload = {
            **self._identity_block(record=record),
            "window_name": window.window_name,
            "mfe_pct": float(window.mfe_pct),
            "tail_label": str(window.tail_label),
            "candidate_stage": str(record.candidate_stage),
            "strategy_mode": str(record.strategy_mode),
        }
        self._emit(
            EventType.MISSED_TAIL_DETECTED,
            symbol=record.symbol,
            timestamp=window.window_end_ts,
            payload=payload,
        )
        self._missed_tail_detected_count += 1

    def _emit_fake_breakout_detected(
        self,
        *,
        record: LabelTrackingRecord,
        window: TrackingWindowState,
    ) -> None:
        payload = {
            **self._identity_block(record=record),
            "window_name": window.window_name,
            "mfe_pct": float(window.mfe_pct),
            "mae_pct": float(window.mae_pct),
            "tail_label": str(window.tail_label),
        }
        self._emit(
            EventType.FAKE_BREAKOUT_DETECTED,
            symbol=record.symbol,
            timestamp=window.window_end_ts,
            payload=payload,
        )
        self._fake_breakout_detected_count += 1

    def _emit(
        self,
        event_type: EventType,
        *,
        symbol: str,
        timestamp: int,
        payload: dict[str, Any],
    ) -> None:
        try:
            self._event_repo.append(
                Event(
                    event_type=event_type,
                    source_module=self.SOURCE_MODULE,
                    symbol=str(symbol),
                    timestamp=int(timestamp),
                    payload=payload,
                )
            )
        except Exception as exc:  # pragma: no cover - protective
            logger.error(
                "[phase11c.1c-c-a] failed to emit {} symbol={}: {}",
                event_type.value,
                symbol,
                exc,
            )

    # ------------------------------------------------------------------
    # Daily-report aggregates
    # ------------------------------------------------------------------
    def metrics_payload(self) -> dict[str, Any]:
        """Return a JSON-safe dict of Phase 11C.1C-C-A label-runtime
        aggregates the daily-report builder consumes."""
        records = list(self._records.values())
        pending = [r for r in records if r.status == "pending"]
        completed = [r for r in records if r.status == "completed"]
        expired = [r for r in records if r.status == "expired"]
        unresolved = [r for r in records if r.status == "unresolved"]

        tail_distribution: dict[str, int] = {label: 0 for label in TAIL_LABELS}
        reached = {"2r": 0, "3r": 0, "5r": 0, "10r": 0}

        # Bucket outcomes.
        early_tail_buckets: dict[str, dict[str, int]] = {}
        opp_score_buckets: dict[str, dict[str, int]] = {}
        strategy_mode_buckets: dict[str, dict[str, int]] = {}
        late_chase_buckets: dict[str, dict[str, int]] = {}

        # Top-MFE / worst-MAE / missed-tail / fake-breakout symbols.
        primary = self._config.primary_window_for_tail_label
        top_mfe: list[tuple[str, str, float]] = []  # (symbol, opp_id, mfe_pct)
        worst_mae: list[tuple[str, str, float]] = []
        missed_symbols: list[tuple[str, str, str]] = []
        fake_breakout_symbols: list[tuple[str, str, str]] = []

        def _bucket_outcome(
            buckets: dict[str, dict[str, int]],
            bucket_label: str,
            tail_label: str,
        ) -> None:
            inner = buckets.setdefault(
                bucket_label, {l: 0 for l in TAIL_LABELS}
            )
            inner[tail_label] = inner.get(tail_label, 0) + 1

        for rec in records:
            primary_win = next(
                (
                    w
                    for w in rec.tracking_windows
                    if w.window_name == primary
                ),
                None,
            )
            label = rec.final_tail_label or (
                primary_win.tail_label if primary_win else "unresolved"
            )
            label = label or "unresolved"
            tail_distribution[label] = tail_distribution.get(label, 0) + 1
            if primary_win is not None:
                reached["2r"] += int(bool(primary_win.reached_2r))
                reached["3r"] += int(bool(primary_win.reached_3r))
                reached["5r"] += int(bool(primary_win.reached_5r))
                reached["10r"] += int(bool(primary_win.reached_10r))
                top_mfe.append(
                    (rec.symbol, rec.opportunity_id, float(primary_win.mfe_pct))
                )
                worst_mae.append(
                    (rec.symbol, rec.opportunity_id, float(primary_win.mae_pct))
                )
                if primary_win.missed_tail:
                    missed_symbols.append(
                        (rec.symbol, rec.opportunity_id, label)
                    )
                if primary_win.fake_breakout:
                    fake_breakout_symbols.append(
                        (rec.symbol, rec.opportunity_id, label)
                    )
            # Bucket: early_tail_score in 20-pt bins.
            ets_bucket = _bucketize_pct(rec.early_tail_score, width=20)
            _bucket_outcome(early_tail_buckets, ets_bucket, label)
            ops_bucket = _bucketize_pct(rec.opportunity_score, width=20)
            _bucket_outcome(opp_score_buckets, ops_bucket, label)
            _bucket_outcome(
                strategy_mode_buckets, str(rec.strategy_mode or "unknown"), label
            )
            lcr_bucket = _bucketize_pct(rec.late_chase_risk, width=20)
            _bucket_outcome(late_chase_buckets, lcr_bucket, label)

        top_mfe.sort(key=lambda r: -r[2])
        worst_mae.sort(key=lambda r: r[2])  # most-negative first

        return {
            "schema_version": LABEL_TRACKING_SCHEMA_VERSION,
            "label_tracking_started_count": int(self._tracking_started_count),
            "label_window_updated_count": int(self._window_updated_count),
            "label_window_completed_count": int(self._window_completed_count),
            "tail_label_assigned_count": int(self._tail_label_assigned_count),
            "missed_tail_detected_count": int(
                self._missed_tail_detected_count
            ),
            "fake_breakout_detected_count": int(
                self._fake_breakout_detected_count
            ),
            "pending_label_records": len(pending),
            "completed_label_records": len(completed),
            "expired_label_records": len(expired),
            "unresolved_label_records": len(unresolved),
            "total_label_records": len(records),
            "records_dropped_capacity": int(self._records_dropped_capacity),
            "tail_label_distribution": dict(tail_distribution),
            "reached_2r_count": int(reached["2r"]),
            "reached_3r_count": int(reached["3r"]),
            "reached_5r_count": int(reached["5r"]),
            "reached_10r_count": int(reached["10r"]),
            "early_tail_score_bucket_outcomes": _stringify_buckets(
                early_tail_buckets
            ),
            "opportunity_score_bucket_outcomes": _stringify_buckets(
                opp_score_buckets
            ),
            "strategy_mode_outcomes": _stringify_buckets(
                strategy_mode_buckets
            ),
            "late_chase_risk_bucket_outcomes": _stringify_buckets(
                late_chase_buckets
            ),
            "top_mfe_symbols": [
                {"symbol": s, "opportunity_id": oid, "mfe_pct": float(p)}
                for s, oid, p in top_mfe[:10]
            ],
            "worst_mae_symbols": [
                {"symbol": s, "opportunity_id": oid, "mae_pct": float(p)}
                for s, oid, p in worst_mae[:10]
            ],
            "missed_tail_symbols": [
                {
                    "symbol": s,
                    "opportunity_id": oid,
                    "tail_label": label,
                }
                for s, oid, label in missed_symbols[:10]
            ],
            "fake_breakout_symbols": [
                {
                    "symbol": s,
                    "opportunity_id": oid,
                    "tail_label": label,
                }
                for s, oid, label in fake_breakout_symbols[:10]
            ],
            "primary_window_for_tail_label": primary,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _bucketize_pct(value: float, *, width: int = 20) -> str:
    """Return the bucket label for ``value`` in 0..100. ``20`` -> "0-20"."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.0
    if v < 0.0:
        v = 0.0
    if v > 100.0:
        v = 100.0
    lo = int(min(100 - width, int(v // width) * width))
    hi = lo + width
    return f"{lo}-{hi}"


def _stringify_buckets(
    buckets: dict[str, dict[str, int]],
) -> dict[str, dict[str, int]]:
    """Return a deterministic dict-of-dicts (sorted keys) for export."""
    out: dict[str, dict[str, int]] = {}
    for k in sorted(buckets):
        inner = buckets[k]
        out[k] = {label: int(inner.get(label, 0)) for label in TAIL_LABELS}
    return out


__all__ = [
    "DEFAULT_PRIMARY_WINDOW",
    "DEFAULT_TRACKING_WINDOW_SECONDS",
    "KNOWN_LABEL_TRACKING_SCHEMA_VERSIONS",
    "LABEL_TRACKING_SCHEMA_VERSION",
    "LABEL_TRACKING_STATUSES",
    "LabelQueueRuntime",
    "LabelQueueRuntimeConfig",
    "LabelTrackingRecord",
    "TAIL_LABELS",
    "TrackingWindowState",
    "assign_tail_label_for_window",
    "compute_pct_return",
    "update_window_with_price",
]
