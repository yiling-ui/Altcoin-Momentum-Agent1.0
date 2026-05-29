"""Blind walk-forward run scoring + status taxonomy for Phase
11C.1D-D-G (PR100 - Blind Walk-forward Runner v0).

Strict blind walk-forward post-window scoring substrate. This module
is the scoring half of the **seventh** anti-future-lookahead
infrastructure block of the strict blind walk-forward stack defined
by Phase 11C.1D-D (the *Strict Blind Walk-forward Sim-Live
Constitution*, PR93). It builds strictly on top of the PR94 / PR95
/ PR96 / PR97 / PR98 / PR99 substrate and is consumed by
:mod:`app.sim.blind_walk_forward_runner`.

Scoring NEVER runs inside the blind window. Scoring NEVER reads any
field that did not become available at or before
``window.blind_end``. Scoring outputs are commentary / evidence
ONLY: they NEVER turn into a runtime config patch, NEVER turn into
a strategy parameter patch, NEVER turn into a Risk Engine override,
NEVER turn into a Telegram command, NEVER authorise live trading,
NEVER authorise auto-tuning, NEVER authorise Phase 12.

Status taxonomy (PR100 brief §8):

  * ``INSUFFICIENT_EVIDENCE``        - the run produced too little
                                       data to score (e.g. zero
                                       batches, zero closed candles,
                                       zero ledger entries).
  * ``EVIDENCE_GENERATED``           - the run produced evidence and
                                       passed every safety boundary.
  * ``INVALIDATED_LOOKAHEAD_OR_DRIFT`` - the run touched future data,
                                       drifted on a frozen artefact,
                                       leaked an outcome label, or
                                       allowed an AI / runtime
                                       override; the run is
                                       AUDIT-ONLY and does NOT
                                       authorise the next step.
  * ``FAILED_SAFETY_BOUNDARY``       - the run reached a forbidden
                                       state (e.g. live_trading
                                       flipped to True, real Telegram
                                       outbound observed, Binance
                                       private API reachable).
  * ``PARTIAL_EVIDENCE``             - the run produced evidence but
                                       part of the window was
                                       degraded (e.g. data gaps that
                                       prevented full coverage).

Hard safety boundary: same as
:mod:`app.sim.blind_walk_forward_manifest`. Phase 12 remains
**FORBIDDEN**.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import (
    Any,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
)

from app.sim.simulation_clock import ensure_utc_aware
from app.sim.time_wall_guard import assert_no_forbidden_fields


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

PHASE_NAME: str = (
    "Phase 11C.1D-D-G / PR100 / Blind Walk-forward Runner v0"
)


# ---------------------------------------------------------------------------
# Closed status taxonomy
# ---------------------------------------------------------------------------


class BlindRunStatus:
    """Closed taxonomy of blind-run scoring statuses (brief §8)."""

    INSUFFICIENT_EVIDENCE: str = "INSUFFICIENT_EVIDENCE"
    EVIDENCE_GENERATED: str = "EVIDENCE_GENERATED"
    INVALIDATED_LOOKAHEAD_OR_DRIFT: str = "INVALIDATED_LOOKAHEAD_OR_DRIFT"
    FAILED_SAFETY_BOUNDARY: str = "FAILED_SAFETY_BOUNDARY"
    PARTIAL_EVIDENCE: str = "PARTIAL_EVIDENCE"

    ALLOWED: FrozenSet[str] = frozenset(
        {
            INSUFFICIENT_EVIDENCE,
            EVIDENCE_GENERATED,
            INVALIDATED_LOOKAHEAD_OR_DRIFT,
            FAILED_SAFETY_BOUNDARY,
            PARTIAL_EVIDENCE,
        }
    )


# ---------------------------------------------------------------------------
# Closed taxonomy of run-invalidation reasons (brief §9)
# ---------------------------------------------------------------------------


class BlindRunInvalidationReason:
    """Closed taxonomy of run-invalidation reasons.

    These are the conditions that flip a run to
    :data:`BlindRunStatus.INVALIDATED_LOOKAHEAD_OR_DRIFT`. Mirrored
    one-for-one from PR100 brief §9.
    """

    FUTURE_RECORD_ACCESS: str = "FUTURE_RECORD_ACCESS"
    CONFIG_DRIFT: str = "CONFIG_DRIFT"
    RULE_HASH_DRIFT: str = "RULE_HASH_DRIFT"
    FEATURE_SCHEMA_DRIFT: str = "FEATURE_SCHEMA_DRIFT"
    DATA_MANIFEST_DRIFT_DURING_BLIND_WINDOW: str = (
        "DATA_MANIFEST_DRIFT_DURING_BLIND_WINDOW"
    )
    UNIVERSE_MANIFEST_DRIFT_DURING_BLIND_WINDOW: str = (
        "UNIVERSE_MANIFEST_DRIFT_DURING_BLIND_WINDOW"
    )
    TAIL_LABEL_LEAKAGE: str = "TAIL_LABEL_LEAKAGE"
    POST_DISCOVERY_OUTCOME_LEAKAGE: str = (
        "POST_DISCOVERY_OUTCOME_LEAKAGE"
    )
    REPLAY_REFLECTION_LEAKAGE: str = "REPLAY_REFLECTION_LEAKAGE"
    AI_OUTPUT_USED_AS_TRUTH_OR_LABEL: str = (
        "AI_OUTPUT_USED_AS_TRUTH_OR_LABEL"
    )
    MANUAL_SAMPLE_DELETION: str = "MANUAL_SAMPLE_DELETION"
    VALIDATION_TEST_TUNING: str = "VALIDATION_TEST_TUNING"
    MISSING_FAILURE_LEDGER: str = "MISSING_FAILURE_LEDGER"
    UNLOGGED_RUNTIME_OVERRIDE: str = "UNLOGGED_RUNTIME_OVERRIDE"

    ALLOWED: FrozenSet[str] = frozenset(
        {
            FUTURE_RECORD_ACCESS,
            CONFIG_DRIFT,
            RULE_HASH_DRIFT,
            FEATURE_SCHEMA_DRIFT,
            DATA_MANIFEST_DRIFT_DURING_BLIND_WINDOW,
            UNIVERSE_MANIFEST_DRIFT_DURING_BLIND_WINDOW,
            TAIL_LABEL_LEAKAGE,
            POST_DISCOVERY_OUTCOME_LEAKAGE,
            REPLAY_REFLECTION_LEAKAGE,
            AI_OUTPUT_USED_AS_TRUTH_OR_LABEL,
            MANUAL_SAMPLE_DELETION,
            VALIDATION_TEST_TUNING,
            MISSING_FAILURE_LEDGER,
            UNLOGGED_RUNTIME_OVERRIDE,
        }
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safety_payload() -> Dict[str, Any]:
    return {
        "phase": PHASE_NAME,
        "mode": "historical_blind_sim_live",
        "sandbox_only": True,
        "simulated_only": True,
        "no_live_order": True,
        "live_trading": False,
        "live_capital_enabled": False,
        "exchange_live_orders": False,
        "binance_private_api_enabled": False,
        "telegram_outbound_enabled": False,
        "telegram_live_command_authority": False,
        "telegram_production_channel_enabled": False,
        "ai_trade_authority": False,
        "trade_authority": False,
        "auto_tuning_inside_blind_window": False,
        "auto_tuning_allowed": False,
        "phase_12_forbidden": True,
        "is_blind_walk_forward_score": True,
        "is_real_exchange_order": False,
        "is_real_account": False,
        "is_real_telegram_outbound": False,
        "is_runtime_patch": False,
    }


# ---------------------------------------------------------------------------
# BlindRunScore
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BlindRunScore:
    """Frozen, JSON-serialisable score for one strict blind walk-forward
    run.

    Computed ONLY after ``window.blind_end``. NEVER consumed by the
    Risk Engine, the Execution FSM, the Capital Flow Engine, the
    Strategy Validator, the Auto-tuner (which is forbidden in this
    phase), or any AI hot path. The score is OPERATOR EVIDENCE ONLY.
    """

    run_id: str
    window_id: str
    status: str
    scored_at: datetime
    sample_count: int
    closed_trade_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    total_realized_pnl: float
    total_fees: float
    total_slippage_bps: float
    max_drawdown: float
    median_mfe: float
    median_mae: float
    no_lookahead_violation_count: int
    failure_ledger_entry_count: int
    invalidation_reasons: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()
    # Hard-pinned safety markers:
    sandbox_only: bool = True
    simulated_only: bool = True
    no_live_order: bool = True
    live_trading: bool = False
    exchange_live_orders: bool = False
    binance_private_api_enabled: bool = False
    auto_tuning_inside_blind_window: bool = False
    auto_tuning_allowed: bool = False
    trade_authority: bool = False
    ai_trade_authority: bool = False
    phase_12_forbidden: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("run_id must be a non-empty string")
        if not isinstance(self.window_id, str) or not self.window_id:
            raise ValueError("window_id must be a non-empty string")
        if self.status not in BlindRunStatus.ALLOWED:
            raise ValueError(
                f"status must be one of "
                f"{sorted(BlindRunStatus.ALLOWED)}; got "
                f"{self.status!r}"
            )
        ts = ensure_utc_aware(self.scored_at, "scored_at")
        for fname in (
            "sample_count",
            "closed_trade_count",
            "win_count",
            "loss_count",
            "breakeven_count",
            "no_lookahead_violation_count",
            "failure_ledger_entry_count",
        ):
            v = getattr(self, fname)
            if not isinstance(v, int) or isinstance(v, bool):
                raise TypeError(
                    f"{fname} must be int; got {type(v)!r}"
                )
            if v < 0:
                raise ValueError(f"{fname} must be >= 0")
        for fname in (
            "total_realized_pnl",
            "total_fees",
            "total_slippage_bps",
            "max_drawdown",
            "median_mfe",
            "median_mae",
        ):
            v = getattr(self, fname)
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise TypeError(
                    f"{fname} must be int / float; got {type(v)!r}"
                )
        invs: List[str] = []
        for r in self.invalidation_reasons:
            if not isinstance(r, str) or not r:
                raise ValueError(
                    "invalidation_reasons entries must be non-empty "
                    "strings"
                )
            if r not in BlindRunInvalidationReason.ALLOWED:
                raise ValueError(
                    f"invalidation_reasons entry {r!r} not in closed "
                    f"taxonomy "
                    f"{sorted(BlindRunInvalidationReason.ALLOWED)}"
                )
            invs.append(r)
        notes: List[str] = []
        for n in self.notes:
            if not isinstance(n, str):
                raise TypeError(
                    f"notes entries must be strings; got {type(n)!r}"
                )
            notes.append(n)
        # Hard-pinned safety markers cannot be flipped.
        for fname, expected in (
            ("sandbox_only", True),
            ("simulated_only", True),
            ("no_live_order", True),
            ("live_trading", False),
            ("exchange_live_orders", False),
            ("binance_private_api_enabled", False),
            ("auto_tuning_inside_blind_window", False),
            ("auto_tuning_allowed", False),
            ("trade_authority", False),
            ("ai_trade_authority", False),
            ("phase_12_forbidden", True),
        ):
            if getattr(self, fname) is not expected:
                raise ValueError(f"{fname} must be {expected!r}")
        # Status / invalidation_reasons must be consistent.
        if (
            self.status
            == BlindRunStatus.INVALIDATED_LOOKAHEAD_OR_DRIFT
        ):
            if not invs:
                raise ValueError(
                    "status INVALIDATED_LOOKAHEAD_OR_DRIFT requires "
                    "at least one invalidation reason"
                )
        object.__setattr__(self, "scored_at", ts)
        object.__setattr__(self, "invalidation_reasons", tuple(invs))
        object.__setattr__(self, "notes", tuple(notes))

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "run_id": self.run_id,
            "window_id": self.window_id,
            "status": self.status,
            "scored_at": self.scored_at.isoformat(),
            "sample_count": int(self.sample_count),
            "closed_trade_count": int(self.closed_trade_count),
            "win_count": int(self.win_count),
            "loss_count": int(self.loss_count),
            "breakeven_count": int(self.breakeven_count),
            "total_realized_pnl": float(self.total_realized_pnl),
            "total_fees": float(self.total_fees),
            "total_slippage_bps": float(self.total_slippage_bps),
            "max_drawdown": float(self.max_drawdown),
            "median_mfe": float(self.median_mfe),
            "median_mae": float(self.median_mae),
            "no_lookahead_violation_count": int(
                self.no_lookahead_violation_count
            ),
            "failure_ledger_entry_count": int(
                self.failure_ledger_entry_count
            ),
            "invalidation_reasons": list(self.invalidation_reasons),
            "notes": list(self.notes),
            "is_blind_run_score": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


# ---------------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------------


def score_blind_run(
    *,
    run_id: str,
    window_id: str,
    scored_at: datetime,
    sample_count: int,
    ledger_summary: Mapping[str, Any],
    no_lookahead_violation_count: int,
    failure_ledger_entry_count: int,
    invalidation_reasons: Iterable[str] = (),
    safety_boundary_failed: bool = False,
    partial_evidence_reasons: Iterable[str] = (),
) -> BlindRunScore:
    """Build a :class:`BlindRunScore` from already-collected aggregates.

    The function is **pure**: it makes no I/O, no network call, no AI
    call, and no decision that could feed the Risk Engine, the
    Execution FSM, the Capital Flow Engine, or the (still-FORBIDDEN)
    Phase 12 path.

    Status decision rule (closed):

      1. ``safety_boundary_failed`` -> ``FAILED_SAFETY_BOUNDARY``.
      2. any ``invalidation_reasons`` -> ``INVALIDATED_LOOKAHEAD_OR_DRIFT``.
      3. ``sample_count == 0`` AND no ledger entries -> ``INSUFFICIENT_EVIDENCE``.
      4. any ``partial_evidence_reasons`` -> ``PARTIAL_EVIDENCE``.
      5. otherwise -> ``EVIDENCE_GENERATED``.
    """
    if not isinstance(ledger_summary, Mapping):
        raise TypeError(
            f"ledger_summary must be a Mapping; got "
            f"{type(ledger_summary)!r}"
        )
    inv = tuple(invalidation_reasons)
    partial = tuple(partial_evidence_reasons)

    if safety_boundary_failed:
        status = BlindRunStatus.FAILED_SAFETY_BOUNDARY
    elif inv:
        status = BlindRunStatus.INVALIDATED_LOOKAHEAD_OR_DRIFT
    elif sample_count == 0 and int(
        ledger_summary.get("trade_count", 0) or 0
    ) == 0:
        status = BlindRunStatus.INSUFFICIENT_EVIDENCE
    elif partial:
        status = BlindRunStatus.PARTIAL_EVIDENCE
    else:
        status = BlindRunStatus.EVIDENCE_GENERATED

    notes: List[str] = []
    for r in partial:
        if isinstance(r, str) and r:
            notes.append(f"partial_evidence:{r}")
    if (
        status == BlindRunStatus.FAILED_SAFETY_BOUNDARY
        and not inv
    ):
        # Defensive safety-boundary breach without a closed
        # invalidation reason is still informative for the operator.
        notes.append("safety_boundary_failed")

    return BlindRunScore(
        run_id=run_id,
        window_id=window_id,
        status=status,
        scored_at=scored_at,
        sample_count=int(sample_count),
        closed_trade_count=int(
            ledger_summary.get("trade_count", 0) or 0
        ),
        win_count=int(ledger_summary.get("win_count", 0) or 0),
        loss_count=int(ledger_summary.get("loss_count", 0) or 0),
        breakeven_count=int(
            ledger_summary.get("breakeven_count", 0) or 0
        ),
        total_realized_pnl=float(
            ledger_summary.get("total_realized_pnl", 0.0) or 0.0
        ),
        total_fees=float(ledger_summary.get("total_fees", 0.0) or 0.0),
        total_slippage_bps=float(
            ledger_summary.get("total_slippage_bps", 0.0) or 0.0
        ),
        max_drawdown=float(
            ledger_summary.get("max_drawdown", 0.0) or 0.0
        ),
        median_mfe=float(ledger_summary.get("median_mfe", 0.0) or 0.0),
        median_mae=float(ledger_summary.get("median_mae", 0.0) or 0.0),
        no_lookahead_violation_count=int(no_lookahead_violation_count),
        failure_ledger_entry_count=int(failure_ledger_entry_count),
        invalidation_reasons=inv,
        notes=tuple(notes),
    )


__all__ = [
    "PHASE_NAME",
    "BlindRunStatus",
    "BlindRunInvalidationReason",
    "BlindRunScore",
    "score_blind_run",
]
