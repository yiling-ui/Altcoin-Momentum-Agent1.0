"""BlindWalkForwardWindow + BlindRunManifest for Phase 11C.1D-D-G
(PR100 - Blind Walk-forward Runner v0).

Strict blind walk-forward run-manifest substrate. This module is the
manifest-only half of the **seventh** anti-future-lookahead
infrastructure block of the strict blind walk-forward stack defined
by Phase 11C.1D-D (the *Strict Blind Walk-forward Sim-Live
Constitution*, PR93). It builds strictly on top of the PR94 / PR95
/ PR96 / PR97 / PR98 / PR99 substrate and is consumed by
:mod:`app.sim.blind_walk_forward_runner`.

A :class:`BlindWalkForwardWindow` is an immutable description of
one strict blind walk-forward window:

  * ``train_start`` / ``train_end``     - the training segment
  * ``blind_start`` / ``blind_end``     - the blind segment
  * ``score_time``                      - the post-window scoring
                                           moment (>= ``blind_end``)
  * ``reference_window``                - the descriptive reference
                                           window string (e.g. ``"60d"``)
  * ``window_id``                       - deterministic id

A :class:`BlindRunManifest` captures every frozen artefact hash and
every hard-pinned safety flag that downstream reviewers must see at
a glance to verify that:

  * the run was **strict blind walk-forward**, not live trading,
  * no Binance private API was reachable,
  * no real Telegram outbound was reachable,
  * no AI / DeepSeek output entered the trade-decision chain,
  * no auto-tuning was performed inside the blind window,
  * Phase 12 remained **FORBIDDEN**.

Hard safety boundary (Phase 11C.1D-D-G / PR100):

  - mode = historical_blind_sim_live
  - sandbox_only = True
  - simulated_only = True
  - no_live_order = True
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
  - telegram_production_channel_enabled = False
  - ai_trade_authority = False
  - trade_authority = False
  - auto_tuning_inside_blind_window = False
  - auto_tuning_allowed = False
  - phase_12_forbidden = True

This module MUST NOT and CANNOT:

  - import app.risk / app.execution / app.exchanges / app.telegram /
    app.config
  - call DeepSeek / LLM / Telegram / Binance private API / any
    network
  - place an order
  - emit any runtime_config_patch / threshold_patch /
    symbol_limit_patch / candidate_pool_patch / regime_weight_patch /
    strategy_parameter_patch / signal_to_trade / should_buy /
    should_short / apply_change / deploy_change / enable_live /
    live_ready / trading_approved
  - emit a real exchange order id, a real account id, an api key,
    an api secret, a Telegram bot token, a production channel id,
    or a signed-endpoint reference
  - authorise live trading or auto-tuning
  - enter Phase 12

Successful PR100 acceptance only authorises a **paper-only blind-run
checkpoint / operator evidence run**. It does NOT authorise live
trading, auto-tuning, real Telegram outbound, real exchange orders,
the Binance private API, or Phase 12.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Tuple

from app.sim.simulation_clock import (
    ensure_utc_aware,
    parse_interval_seconds,
)
from app.sim.time_wall_guard import assert_no_forbidden_fields


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

PHASE_NAME: str = (
    "Phase 11C.1D-D-G / PR100 / Blind Walk-forward Runner v0"
)


# ---------------------------------------------------------------------------
# Allowed timeframes (Constitution §6 + PR100 brief §4)
# ---------------------------------------------------------------------------

ALLOWED_TIMEFRAMES: Tuple[str, ...] = (
    "1m",
    "5m",
    "15m",
    "1h",
    "4h",
    "1d",
)

DEFAULT_BASE_CLOCK_STEP: str = "1m"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safety_payload() -> Dict[str, Any]:
    """Project-wide blind-walk-forward safety boundary, re-pinned on
    every serialisation boundary so that no payload can ever be
    misread as authorising live trading, auto-tuning, real Telegram
    outbound, the Binance private API, or Phase 12.
    """
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
        "auto_tuning_inside_blind_window": False,
        "auto_tuning_allowed": False,
        "phase_12_forbidden": True,
        # Defensive non-trade markers:
        "is_blind_walk_forward_payload": True,
        "is_real_exchange_order": False,
        "is_real_account": False,
        "is_real_telegram_outbound": False,
        "is_runtime_patch": False,
    }


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    raise TypeError(
        f"Object of type {type(obj)!r} is not JSON serialisable"
    )


def _stable_hash(payload: Any) -> str:
    """Return a deterministic ``sha256:<hex>`` hash for ``payload``.

    The payload is serialised with ``sort_keys=True`` and the
    :func:`_json_default` fallback so two manifests produced from
    identical inputs always carry identical hashes.
    """
    text = json.dumps(payload, sort_keys=True, default=_json_default)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _validate_timeframes(tfs: Iterable[Any]) -> Tuple[str, ...]:
    out: List[str] = []
    seen: set = set()
    for tf in tfs:
        if not isinstance(tf, str) or not tf:
            raise TypeError(
                f"timeframe must be a non-empty string, got {type(tf)!r}"
            )
        if tf not in ALLOWED_TIMEFRAMES:
            raise ValueError(
                f"timeframe {tf!r} not in allowed set "
                f"{ALLOWED_TIMEFRAMES}"
            )
        if tf in seen:
            raise ValueError(
                f"timeframe {tf!r} duplicated in allowed_timeframes"
            )
        seen.add(tf)
        out.append(tf)
    if not out:
        raise ValueError("allowed_timeframes must be non-empty")
    return tuple(out)


def _validate_step(step: str) -> str:
    if not isinstance(step, str) or not step:
        raise TypeError(
            f"base_clock_step must be a non-empty string, got "
            f"{type(step)!r}"
        )
    if step not in ALLOWED_TIMEFRAMES:
        raise ValueError(
            f"base_clock_step {step!r} not in allowed set "
            f"{ALLOWED_TIMEFRAMES}"
        )
    # PR100 brief §4: v0 base step is at least 1m.
    if parse_interval_seconds(step) < parse_interval_seconds(
        DEFAULT_BASE_CLOCK_STEP
    ):
        raise ValueError(
            f"base_clock_step must be >= {DEFAULT_BASE_CLOCK_STEP}; "
            f"got {step!r}"
        )
    return step


# ---------------------------------------------------------------------------
# BlindWalkForwardWindow
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BlindWalkForwardWindow:
    """Frozen description of one strict blind walk-forward window.

    Hard rules:

      * ``train_start`` / ``train_end`` / ``blind_start`` /
        ``blind_end`` / ``score_time`` are all timezone-aware UTC.
      * ``train_start <= train_end <= blind_start < blind_end <=
        score_time``.
      * ``reference_window`` is a descriptive non-empty string
        (e.g. ``"60d"``).
      * ``window_id`` defaults to a deterministic format derived
        from the four boundary timestamps.
    """

    train_start: datetime
    train_end: datetime
    blind_start: datetime
    blind_end: datetime
    score_time: Optional[datetime] = None
    reference_window: str = "60d"
    window_id: Optional[str] = None

    def __post_init__(self) -> None:
        ts = ensure_utc_aware(self.train_start, "train_start")
        te = ensure_utc_aware(self.train_end, "train_end")
        bs = ensure_utc_aware(self.blind_start, "blind_start")
        be = ensure_utc_aware(self.blind_end, "blind_end")
        st: Optional[datetime] = None
        if self.score_time is not None:
            st = ensure_utc_aware(self.score_time, "score_time")
        if te < ts:
            raise ValueError("train_end must be >= train_start")
        if bs < te:
            raise ValueError("blind_start must be >= train_end")
        if be <= bs:
            raise ValueError("blind_end must be > blind_start")
        if st is None:
            st = be
        elif st < be:
            raise ValueError("score_time must be >= blind_end")
        if not isinstance(self.reference_window, str) or not (
            self.reference_window
        ):
            raise ValueError(
                "reference_window must be a non-empty string"
            )
        wid = self.window_id
        if wid is None:
            wid = (
                f"bwf_{ts.strftime('%Y%m%dT%H%M%S')}_"
                f"{bs.strftime('%Y%m%dT%H%M%S')}_"
                f"{be.strftime('%Y%m%dT%H%M%S')}"
            )
        if not isinstance(wid, str) or not wid:
            raise ValueError("window_id must be a non-empty string")
        object.__setattr__(self, "train_start", ts)
        object.__setattr__(self, "train_end", te)
        object.__setattr__(self, "blind_start", bs)
        object.__setattr__(self, "blind_end", be)
        object.__setattr__(self, "score_time", st)
        object.__setattr__(self, "window_id", wid)

    @property
    def blind_duration(self) -> timedelta:
        return self.blind_end - self.blind_start

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "window_id": self.window_id,
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "blind_start": self.blind_start.isoformat(),
            "blind_end": self.blind_end.isoformat(),
            "score_time": self.score_time.isoformat(),
            "reference_window": self.reference_window,
            "blind_duration_seconds": self.blind_duration.total_seconds(),
            "is_blind_walk_forward_window": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# BlindRunManifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BlindRunManifest:
    """Frozen manifest for one strict blind walk-forward run.

    Every hash field is the deterministic ``sha256:<hex>`` digest of
    the JSON-serialised content of the corresponding artefact. The
    hashes prove that the run was reproduced from the same training
    bundle / feature schema / fee model / slippage model / latency
    model / outage model / fill model, that no auto-tuning happened
    inside the blind window, and that no live boundary was reached.
    """

    run_id: str
    window: BlindWalkForwardWindow
    code_commit: str = "unknown"
    config_hash: str = "sha256:unknown"
    rule_hash: str = "sha256:unknown"
    feature_schema_hash: str = "sha256:unknown"
    data_manifest_hash: str = "sha256:unknown"
    universe_manifest_hash: str = "sha256:unknown"
    simulation_clock_start: Optional[datetime] = None
    simulation_clock_end: Optional[datetime] = None
    base_clock_step: str = DEFAULT_BASE_CLOCK_STEP
    allowed_timeframes: Tuple[str, ...] = ALLOWED_TIMEFRAMES
    fee_model_hash: str = "sha256:unknown"
    slippage_model_hash: str = "sha256:unknown"
    latency_model_hash: str = "sha256:unknown"
    outage_model_hash: str = "sha256:unknown"
    fill_model_hash: str = "sha256:unknown"
    ai_enabled_state: str = "OFFLINE_ASOF_ONLY"
    ai_post_window_summary_enabled: bool = False
    telegram_sandbox_state: str = "SANDBOX_FILE_ONLY"
    intrabar_ambiguity_policy: str = "WORST_CASE"
    strict_time_wall: bool = True
    strict_closed_candle_visibility: bool = True
    strict_feature_asof: bool = True
    # Hard-pinned safety markers (cannot be flipped by callers):
    phase_12_forbidden: bool = True
    live_trading: bool = False
    exchange_live_orders: bool = False
    binance_private_api_enabled: bool = False
    auto_tuning_inside_blind_window: bool = False
    auto_tuning_allowed: bool = False
    trade_authority: bool = False
    ai_trade_authority: bool = False
    sandbox_only: bool = True
    simulated_only: bool = True
    no_live_order: bool = True
    telegram_outbound_enabled: bool = False
    telegram_live_command_authority: bool = False
    telegram_production_channel_enabled: bool = False
    real_capital: bool = False
    real_exchange_order_path: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("run_id must be a non-empty string")
        if not isinstance(self.window, BlindWalkForwardWindow):
            raise TypeError(
                f"window must be BlindWalkForwardWindow, got "
                f"{type(self.window)!r}"
            )
        for fname in (
            "code_commit",
            "config_hash",
            "rule_hash",
            "feature_schema_hash",
            "data_manifest_hash",
            "universe_manifest_hash",
            "fee_model_hash",
            "slippage_model_hash",
            "latency_model_hash",
            "outage_model_hash",
            "fill_model_hash",
            "ai_enabled_state",
            "telegram_sandbox_state",
            "intrabar_ambiguity_policy",
        ):
            v = getattr(self, fname)
            if not isinstance(v, str) or not v:
                raise ValueError(
                    f"{fname} must be a non-empty string"
                )
        # Hash fields must look like ``"sha256:<hex>"`` or be
        # ``"sha256:unknown"``. We accept the unknown sentinel so the
        # manifest can be constructed even when an artefact has no
        # canonical hash yet (defensive).
        for fname in (
            "config_hash",
            "rule_hash",
            "feature_schema_hash",
            "data_manifest_hash",
            "universe_manifest_hash",
            "fee_model_hash",
            "slippage_model_hash",
            "latency_model_hash",
            "outage_model_hash",
            "fill_model_hash",
        ):
            v = getattr(self, fname)
            if not v.startswith("sha256:"):
                raise ValueError(
                    f"{fname} must start with 'sha256:'; got {v!r}"
                )
        # AI / telegram closed states.
        ai_states = {"OFFLINE_ASOF_ONLY", "OFFLINE_POST_WINDOW_ONLY"}
        if self.ai_enabled_state not in ai_states:
            raise ValueError(
                f"ai_enabled_state must be one of {sorted(ai_states)}; "
                f"got {self.ai_enabled_state!r}"
            )
        tel_states = {"SANDBOX_FILE_ONLY", "DISABLED"}
        if self.telegram_sandbox_state not in tel_states:
            raise ValueError(
                f"telegram_sandbox_state must be one of "
                f"{sorted(tel_states)}; got "
                f"{self.telegram_sandbox_state!r}"
            )
        amb = {"WORST_CASE", "AMBIGUOUS_INTRABAR_PATH", "AMBIGUOUS"}
        if self.intrabar_ambiguity_policy not in amb:
            raise ValueError(
                f"intrabar_ambiguity_policy must be one of "
                f"{sorted(amb)}; got "
                f"{self.intrabar_ambiguity_policy!r}"
            )
        # Validate timeframe taxonomy + base step.
        atf = _validate_timeframes(self.allowed_timeframes)
        bcs = _validate_step(self.base_clock_step)
        # Clock bounds.
        scs: Optional[datetime] = None
        sce: Optional[datetime] = None
        if self.simulation_clock_start is not None:
            scs = ensure_utc_aware(
                self.simulation_clock_start, "simulation_clock_start"
            )
        else:
            scs = self.window.blind_start
        if self.simulation_clock_end is not None:
            sce = ensure_utc_aware(
                self.simulation_clock_end, "simulation_clock_end"
            )
        else:
            sce = self.window.blind_end
        if sce < scs:
            raise ValueError(
                "simulation_clock_end must be >= simulation_clock_start"
            )
        # Hard-pinned safety markers cannot be flipped.
        for fname, expected in (
            ("phase_12_forbidden", True),
            ("live_trading", False),
            ("exchange_live_orders", False),
            ("binance_private_api_enabled", False),
            ("auto_tuning_inside_blind_window", False),
            ("auto_tuning_allowed", False),
            ("trade_authority", False),
            ("ai_trade_authority", False),
            ("sandbox_only", True),
            ("simulated_only", True),
            ("no_live_order", True),
            ("telegram_outbound_enabled", False),
            ("telegram_live_command_authority", False),
            ("telegram_production_channel_enabled", False),
            ("real_capital", False),
            ("real_exchange_order_path", False),
            ("strict_time_wall", True),
            ("strict_closed_candle_visibility", True),
            ("strict_feature_asof", True),
        ):
            if getattr(self, fname) is not expected:
                raise ValueError(f"{fname} must be {expected!r}")
        if not isinstance(self.ai_post_window_summary_enabled, bool):
            raise TypeError(
                "ai_post_window_summary_enabled must be bool"
            )
        object.__setattr__(self, "allowed_timeframes", atf)
        object.__setattr__(self, "base_clock_step", bcs)
        object.__setattr__(self, "simulation_clock_start", scs)
        object.__setattr__(self, "simulation_clock_end", sce)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "run_id": self.run_id,
            "window": self.window.to_dict(),
            "code_commit": self.code_commit,
            "config_hash": self.config_hash,
            "rule_hash": self.rule_hash,
            "feature_schema_hash": self.feature_schema_hash,
            "data_manifest_hash": self.data_manifest_hash,
            "universe_manifest_hash": self.universe_manifest_hash,
            "train_start": self.window.train_start.isoformat(),
            "train_end": self.window.train_end.isoformat(),
            "blind_start": self.window.blind_start.isoformat(),
            "blind_end": self.window.blind_end.isoformat(),
            "score_time": self.window.score_time.isoformat(),
            "reference_window": self.window.reference_window,
            "simulation_clock_start": (
                self.simulation_clock_start.isoformat()
            ),
            "simulation_clock_end": (
                self.simulation_clock_end.isoformat()
            ),
            "base_clock_step": self.base_clock_step,
            "allowed_timeframes": list(self.allowed_timeframes),
            "fee_model_hash": self.fee_model_hash,
            "slippage_model_hash": self.slippage_model_hash,
            "latency_model_hash": self.latency_model_hash,
            "outage_model_hash": self.outage_model_hash,
            "fill_model_hash": self.fill_model_hash,
            "ai_enabled_state": self.ai_enabled_state,
            "ai_post_window_summary_enabled": bool(
                self.ai_post_window_summary_enabled
            ),
            "telegram_sandbox_state": self.telegram_sandbox_state,
            "intrabar_ambiguity_policy": self.intrabar_ambiguity_policy,
            "strict_time_wall": True,
            "strict_closed_candle_visibility": True,
            "strict_feature_asof": True,
            "is_blind_run_manifest": True,
        }
        out.update(_safety_payload())
        # The hard-pinned safety markers in _safety_payload() already
        # set phase_12_forbidden=True, live_trading=False, etc; we
        # re-pin the explicit window-level fields too so the manifest
        # is self-describing for human reviewers.
        out["phase_12_forbidden"] = True
        out["live_trading"] = False
        out["exchange_live_orders"] = False
        out["binance_private_api_enabled"] = False
        out["auto_tuning_inside_blind_window"] = False
        out["auto_tuning_allowed"] = False
        out["trade_authority"] = False
        out["ai_trade_authority"] = False
        assert_no_forbidden_fields(out)
        return out

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), sort_keys=True, default=_json_default
        )


# ---------------------------------------------------------------------------
# Helpers exposed to the runner
# ---------------------------------------------------------------------------


def compute_artefact_hash(payload: Any) -> str:
    """Return a deterministic ``sha256:<hex>`` hash for ``payload``.

    Used by the runner to freeze fee / slippage / latency / fill /
    config / rule / feature-schema / data-manifest / universe-manifest
    artefacts at the start of the blind window. The hash function is
    pure and deterministic given identical inputs.
    """
    return _stable_hash(payload)


def safety_payload() -> Dict[str, Any]:
    """Return the project-wide blind-walk-forward safety payload."""
    out = _safety_payload()
    assert_no_forbidden_fields(out)
    return out


__all__ = [
    "PHASE_NAME",
    "ALLOWED_TIMEFRAMES",
    "DEFAULT_BASE_CLOCK_STEP",
    "BlindWalkForwardWindow",
    "BlindRunManifest",
    "compute_artefact_hash",
    "safety_payload",
]
