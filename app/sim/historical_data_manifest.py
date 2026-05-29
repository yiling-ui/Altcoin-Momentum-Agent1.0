"""HistoricalDataManifest + UniverseManifest for Phase 11C.1D-D-H
(PR101 - Historical Data Ingestion / Backfill v0).

Strict blind walk-forward historical data-manifest substrate. This
module is the manifest / coverage-audit half of the **eighth**
anti-future-lookahead infrastructure block of the strict blind
walk-forward stack defined by Phase 11C.1D-D (the *Strict Blind
Walk-forward Sim-Live Constitution*, PR93). It builds strictly on top
of the PR94 (:class:`SimulationClock` / :class:`TimeWallGuard` /
:class:`CandleVisibilityGuard`) and PR95
(:class:`HistoricalMarketStore` / :class:`HistoricalMarketRecord` /
:class:`HistoricalKlineRecord` / :class:`SymbolStatusRecord`)
substrate and is consumed by :mod:`app.sim.historical_data_ingestion`.

A :class:`HistoricalDataManifest` is an immutable description of one
historical-data ingestion run: which window was ingested, which
symbols / intervals were requested, how many records of each type
were produced, how complete the per-symbol coverage was, where the
data gaps are, how many late-arriving / revised records were seen,
which source files were consumed, and a deterministic
``data_manifest_hash`` over the content (excluding wall-clock
metadata).

A :class:`UniverseManifest` is an immutable as-of universe
description that records every :class:`SymbolStatusRecord` produced
during ingestion - including delisted symbols - so the downstream
strict forward-only blind walk-forward never reconstructs the past
from the *current* symbol list (Constitution §9: survivorship bias is
forbidden).

A coverage / data-manifest report is **NOT** a strategy-effectiveness
conclusion. It proves only *which historical data we have and how
complete it is*; it never proves any direction / entry / exit /
profit / win-rate claim. See ``is_strategy_effectiveness_conclusion``
pinned ``False`` on every output payload.

Hard safety boundary (Phase 11C.1D-D-H / PR101):

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
  - emit any runtime_config_patch / threshold_patch /
    symbol_limit_patch / candidate_pool_patch / regime_weight_patch /
    strategy_parameter_patch / signal_to_trade / should_buy /
    should_short / apply_change / deploy_change / enable_live /
    live_ready / trading_approved
  - emit an api key, an api secret, a listenKey, a signed-endpoint
    reference, a private-websocket reference, a real exchange order
    id, or a real account id
  - present a coverage report as a strategy-effectiveness conclusion
  - authorise live trading or auto-tuning
  - enter Phase 12

Successful PR101 acceptance only authorises a **historical data
coverage checkpoint / short-window no-lookahead trial preparation**.
It does NOT authorise live trading, auto-tuning, real Telegram
outbound, real exchange orders, the Binance private API, the
30D / 60D / 90D / 2Y runner, or Phase 12.
"""

from __future__ import annotations

import copy
import hashlib
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

from app.sim.historical_market_store import (
    DataCompletenessState,
    SymbolStatus,
    SymbolStatusRecord,
)
from app.sim.simulation_clock import ensure_utc_aware
from app.sim.time_wall_guard import assert_no_forbidden_fields


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

PHASE_NAME: str = (
    "Phase 11C.1D-D-H / PR101 / Historical Data Ingestion / "
    "Backfill v0"
)


# ---------------------------------------------------------------------------
# Closed taxonomies
# ---------------------------------------------------------------------------


class HistoricalDataSourceType:
    """Closed taxonomy of historical-data *file* source types (v0).

    Every member is a **public / file** source. This taxonomy NEVER
    includes a private / signed / account / order / position /
    leverage / margin endpoint, and NEVER includes a private
    websocket or listenKey. The ingestion framework reads files only;
    it does not download data and does not reach any network.
    """

    BINANCE_PUBLIC_KLINE_FILE: str = "BINANCE_PUBLIC_KLINE_FILE"
    BINANCE_PUBLIC_FUNDING_FILE: str = "BINANCE_PUBLIC_FUNDING_FILE"
    BINANCE_PUBLIC_OPEN_INTEREST_FILE: str = (
        "BINANCE_PUBLIC_OPEN_INTEREST_FILE"
    )
    BINANCE_PUBLIC_TICKER_FILE: str = "BINANCE_PUBLIC_TICKER_FILE"
    EXCHANGE_INFO_FILE: str = "EXCHANGE_INFO_FILE"
    SYMBOL_STATUS_FILE: str = "SYMBOL_STATUS_FILE"
    MANUAL_FIXTURE_FILE: str = "MANUAL_FIXTURE_FILE"

    ALLOWED: FrozenSet[str] = frozenset(
        {
            BINANCE_PUBLIC_KLINE_FILE,
            BINANCE_PUBLIC_FUNDING_FILE,
            BINANCE_PUBLIC_OPEN_INTEREST_FILE,
            BINANCE_PUBLIC_TICKER_FILE,
            EXCHANGE_INFO_FILE,
            SYMBOL_STATUS_FILE,
            MANUAL_FIXTURE_FILE,
        }
    )


class DataIngestionStatus:
    """Closed taxonomy of historical-data ingestion result statuses.

    ``EVIDENCE_GENERATED`` and ``PARTIAL_EVIDENCE`` are descriptive
    data-coverage states ONLY. Neither is a strategy-effectiveness
    conclusion and neither authorises live trading, auto-tuning, the
    30D / 60D / 90D / 2Y runner, or Phase 12.
    """

    EVIDENCE_GENERATED: str = "EVIDENCE_GENERATED"
    PARTIAL_EVIDENCE: str = "PARTIAL_EVIDENCE"
    INSUFFICIENT_EVIDENCE: str = "INSUFFICIENT_EVIDENCE"
    FAILED_SCHEMA_VALIDATION: str = "FAILED_SCHEMA_VALIDATION"
    INVALIDATED_TIME_FIELDS: str = "INVALIDATED_TIME_FIELDS"

    ALLOWED: FrozenSet[str] = frozenset(
        {
            EVIDENCE_GENERATED,
            PARTIAL_EVIDENCE,
            INSUFFICIENT_EVIDENCE,
            FAILED_SCHEMA_VALIDATION,
            INVALIDATED_TIME_FIELDS,
        }
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safety_payload() -> Dict[str, Any]:
    """Project-wide PR101 safety boundary, re-pinned on every
    serialisation boundary so that no payload can ever be misread as
    authorising live trading, auto-tuning, real Telegram outbound, the
    Binance private API, the 30D / 60D / 90D / 2Y runner, or Phase 12,
    and so that no coverage report can be misread as a
    strategy-effectiveness conclusion.
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
        "ai_trade_authority": False,
        "trade_authority": False,
        "auto_tuning_allowed": False,
        "phase_12_forbidden": True,
        # Defensive non-trade / non-conclusion markers:
        "is_historical_data_ingestion_payload": True,
        "is_strategy_effectiveness_conclusion": False,
        "is_real_exchange_order": False,
        "is_real_account": False,
        "is_real_telegram_outbound": False,
        "is_trade": False,
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


def compute_artefact_hash(payload: Any) -> str:
    """Return a deterministic ``sha256:<hex>`` hash for ``payload``.

    Pure / deterministic given identical inputs. Used to freeze the
    data manifest and the universe manifest so the downstream blind
    runner can pin ``data_manifest_hash`` / ``universe_manifest_hash``.
    """
    return _stable_hash(payload)


def safety_payload() -> Dict[str, Any]:
    """Return the project-wide PR101 historical-data safety payload."""
    out = _safety_payload()
    assert_no_forbidden_fields(out)
    return out


def _validate_str_tuple(values: Iterable[Any], name: str) -> Tuple[str, ...]:
    out: List[str] = []
    seen: set = set()
    for v in values:
        if not isinstance(v, str) or not v:
            raise ValueError(
                f"{name} entries must be non-empty strings, got {v!r}"
            )
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return tuple(out)


def _jsonable(payload: Optional[Mapping[str, Any]], name: str) -> Dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise TypeError(
            f"{name} must be a Mapping or None, got {type(payload)!r}"
        )
    out: Dict[str, Any] = copy.deepcopy(dict(payload))
    assert_no_forbidden_fields(out)
    try:
        json.dumps(out, sort_keys=True, default=_json_default)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{name} must be JSON serialisable: {exc}"
        ) from exc
    return out


def _short_hash_id(prefix: str, content_hash: str) -> str:
    # content_hash looks like ``sha256:<hex>``; take a stable slice.
    hexpart = content_hash.split(":", 1)[-1]
    return f"{prefix}_{hexpart[:16]}"


# ---------------------------------------------------------------------------
# HistoricalDataManifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoricalDataManifest:
    """Frozen manifest for one historical-data ingestion run.

    Hard rules:

      * ``start_time`` / ``end_time`` are timezone-aware UTC and
        ``end_time >= start_time``.
      * ``record_counts_by_type`` / ``coverage_by_symbol`` /
        ``data_gap_summary`` are JSON-serialisable and contain no
        forbidden field name at any nesting depth.
      * ``data_manifest_hash`` is a deterministic ``sha256:<hex>``
        digest of the manifest *content* (everything EXCEPT the
        wall-clock ``generated_at_utc``, the derived ``manifest_id``,
        and the hash itself). Identical inputs therefore always carry
        an identical ``data_manifest_hash`` (determinism contract).
      * ``manifest_id`` defaults to ``hdm_<first-16-hex-of-hash>``.
    """

    input_root: str
    start_time: datetime
    end_time: datetime
    symbols: Tuple[str, ...] = ()
    intervals: Tuple[str, ...] = ()
    source_type: str = HistoricalDataSourceType.MANUAL_FIXTURE_FILE
    record_counts_by_type: Mapping[str, int] = field(default_factory=dict)
    coverage_by_symbol: Mapping[str, Any] = field(default_factory=dict)
    data_gap_summary: Mapping[str, Any] = field(default_factory=dict)
    late_arrival_count: int = 0
    revised_record_count: int = 0
    source_files: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    generated_at_utc: Optional[datetime] = None
    manifest_id: Optional[str] = None
    data_manifest_hash: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.input_root, str):
            raise TypeError("input_root must be a string")
        st = ensure_utc_aware(self.start_time, "start_time")
        et = ensure_utc_aware(self.end_time, "end_time")
        if et < st:
            raise ValueError("end_time must be >= start_time")
        if self.source_type not in HistoricalDataSourceType.ALLOWED:
            raise ValueError(
                f"source_type must be one of "
                f"{sorted(HistoricalDataSourceType.ALLOWED)}, got "
                f"{self.source_type!r}"
            )
        symbols = _validate_str_tuple(self.symbols, "symbols")
        intervals = _validate_str_tuple(self.intervals, "intervals")
        source_files = _validate_str_tuple(
            self.source_files, "source_files"
        )
        warnings = tuple(str(w) for w in self.warnings)
        counts = _jsonable(
            self.record_counts_by_type, "record_counts_by_type"
        )
        coverage = _jsonable(
            self.coverage_by_symbol, "coverage_by_symbol"
        )
        gaps = _jsonable(self.data_gap_summary, "data_gap_summary")
        if not isinstance(self.late_arrival_count, int) or isinstance(
            self.late_arrival_count, bool
        ):
            raise TypeError("late_arrival_count must be int")
        if not isinstance(
            self.revised_record_count, int
        ) or isinstance(self.revised_record_count, bool):
            raise TypeError("revised_record_count must be int")
        if self.late_arrival_count < 0 or self.revised_record_count < 0:
            raise ValueError(
                "late_arrival_count / revised_record_count must be >= 0"
            )
        gen = (
            ensure_utc_aware(self.generated_at_utc, "generated_at_utc")
            if self.generated_at_utc is not None
            else None
        )

        object.__setattr__(self, "start_time", st)
        object.__setattr__(self, "end_time", et)
        object.__setattr__(self, "symbols", symbols)
        object.__setattr__(self, "intervals", intervals)
        object.__setattr__(self, "source_files", source_files)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "record_counts_by_type", counts)
        object.__setattr__(self, "coverage_by_symbol", coverage)
        object.__setattr__(self, "data_gap_summary", gaps)
        object.__setattr__(self, "generated_at_utc", gen)

        content = self._content_for_hash()
        computed_hash = _stable_hash(content)
        if self.data_manifest_hash is None:
            object.__setattr__(
                self, "data_manifest_hash", computed_hash
            )
        elif not str(self.data_manifest_hash).startswith("sha256:"):
            raise ValueError(
                "data_manifest_hash must start with 'sha256:'"
            )
        if self.manifest_id is None:
            object.__setattr__(
                self,
                "manifest_id",
                _short_hash_id("hdm", computed_hash),
            )
        elif not isinstance(self.manifest_id, str) or not (
            self.manifest_id
        ):
            raise ValueError(
                "manifest_id must be a non-empty string or None"
            )

    def _content_for_hash(self) -> Dict[str, Any]:
        """Canonical content used for the deterministic hash.

        Deliberately EXCLUDES the wall-clock ``generated_at_utc``, the
        derived ``manifest_id``, and the hash field itself so that two
        runs over identical inputs carry identical hashes.
        """
        return {
            "input_root": self.input_root,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "symbols": list(self.symbols),
            "intervals": list(self.intervals),
            "source_type": self.source_type,
            "record_counts_by_type": dict(self.record_counts_by_type),
            "coverage_by_symbol": dict(self.coverage_by_symbol),
            "data_gap_summary": dict(self.data_gap_summary),
            "late_arrival_count": int(self.late_arrival_count),
            "revised_record_count": int(self.revised_record_count),
            "source_files": list(self.source_files),
            "warnings": list(self.warnings),
        }

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "manifest_id": self.manifest_id,
            "generated_at_utc": (
                self.generated_at_utc.isoformat()
                if self.generated_at_utc is not None
                else None
            ),
            "input_root": self.input_root,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "symbols": list(self.symbols),
            "intervals": list(self.intervals),
            "source_type": self.source_type,
            "record_counts_by_type": dict(self.record_counts_by_type),
            "coverage_by_symbol": copy.deepcopy(
                dict(self.coverage_by_symbol)
            ),
            "data_gap_summary": copy.deepcopy(
                dict(self.data_gap_summary)
            ),
            "late_arrival_count": int(self.late_arrival_count),
            "revised_record_count": int(self.revised_record_count),
            "data_manifest_hash": self.data_manifest_hash,
            "source_files": list(self.source_files),
            "warnings": list(self.warnings),
            "is_historical_data_manifest": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), sort_keys=True, default=_json_default
        )


# ---------------------------------------------------------------------------
# UniverseManifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UniverseManifest:
    """Frozen as-of universe manifest (no survivorship bias).

    Constitution §9: the as-of universe MUST be reconstructed from
    per-symbol :class:`SymbolStatusRecord` listing / delisting
    timeline, NEVER from the *current* symbol list. The manifest
    therefore retains every status record - including delisted
    symbols - so that the downstream strict forward-only blind
    walk-forward can query the universe as it actually existed at any
    simulated time.

    ``survivorship_bias_guard`` is hard-pinned ``True``: a delisted
    symbol is preserved in the manifest (it is never silently dropped)
    and is excluded from the as-of universe ONLY at simulated times
    on / after its ``delisted_at`` - never retroactively erased.
    """

    start_time: datetime
    end_time: datetime
    symbol_status_records: Tuple[SymbolStatusRecord, ...] = ()
    warnings: Tuple[str, ...] = ()
    generated_at_utc: Optional[datetime] = None
    manifest_id: Optional[str] = None
    universe_manifest_hash: Optional[str] = None

    def __post_init__(self) -> None:
        st = ensure_utc_aware(self.start_time, "start_time")
        et = ensure_utc_aware(self.end_time, "end_time")
        if et < st:
            raise ValueError("end_time must be >= start_time")
        records: List[SymbolStatusRecord] = []
        for r in self.symbol_status_records:
            if not isinstance(r, SymbolStatusRecord):
                raise TypeError(
                    "symbol_status_records entries must be "
                    f"SymbolStatusRecord, got {type(r)!r}"
                )
            records.append(r)
        # Deterministic ordering by (symbol, listed_at, record_id).
        records.sort(
            key=lambda s: (
                s.symbol,
                s.listed_at,
                s.record_id or "",
            )
        )
        warnings = tuple(str(w) for w in self.warnings)
        gen = (
            ensure_utc_aware(self.generated_at_utc, "generated_at_utc")
            if self.generated_at_utc is not None
            else None
        )
        object.__setattr__(self, "start_time", st)
        object.__setattr__(self, "end_time", et)
        object.__setattr__(
            self, "symbol_status_records", tuple(records)
        )
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "generated_at_utc", gen)

        content = self._content_for_hash()
        computed_hash = _stable_hash(content)
        if self.universe_manifest_hash is None:
            object.__setattr__(
                self, "universe_manifest_hash", computed_hash
            )
        elif not str(self.universe_manifest_hash).startswith(
            "sha256:"
        ):
            raise ValueError(
                "universe_manifest_hash must start with 'sha256:'"
            )
        if self.manifest_id is None:
            object.__setattr__(
                self,
                "manifest_id",
                _short_hash_id("uvm", computed_hash),
            )
        elif not isinstance(self.manifest_id, str) or not (
            self.manifest_id
        ):
            raise ValueError(
                "manifest_id must be a non-empty string or None"
            )

    # ----- derived counts -----

    @property
    def symbols(self) -> Tuple[str, ...]:
        seen: set = set()
        out: List[str] = []
        for r in self.symbol_status_records:
            if r.symbol not in seen:
                seen.add(r.symbol)
                out.append(r.symbol)
        return tuple(sorted(out))

    @property
    def listed_count(self) -> int:
        """Number of distinct symbols that are NOT delisted by
        ``end_time`` and whose latest status is known."""
        listed, _delisted, _unknown = self._classify_symbols()
        return listed

    @property
    def delisted_count(self) -> int:
        """Number of distinct symbols delisted by ``end_time``.

        A symbol counts as delisted iff its latest record has
        ``status == DELISTED`` OR carries a ``delisted_at`` on / before
        ``end_time``. The delisted symbol is NEVER erased from the
        manifest (survivorship-bias guard); it is only *counted* as
        delisted here.
        """
        _listed, delisted, _unknown = self._classify_symbols()
        return delisted

    @property
    def status_unknown_count(self) -> int:
        _listed, _delisted, unknown = self._classify_symbols()
        return unknown

    def _classify_symbols(self) -> Tuple[int, int, int]:
        listed = 0
        delisted = 0
        unknown = 0
        for r in self._latest_by_symbol().values():
            is_delisted = r.status == SymbolStatus.DELISTED or (
                r.delisted_at is not None
                and r.delisted_at <= self.end_time
            )
            if is_delisted:
                delisted += 1
            elif r.status == SymbolStatus.UNKNOWN:
                unknown += 1
            else:
                listed += 1
        return listed, delisted, unknown

    def _latest_by_symbol(self) -> Dict[str, SymbolStatusRecord]:
        per_symbol: Dict[str, SymbolStatusRecord] = {}
        for r in self.symbol_status_records:
            cur = per_symbol.get(r.symbol)
            key_new = (r.event_time, r.available_at, r.record_id or "")
            if cur is None or key_new > (
                cur.event_time,
                cur.available_at,
                cur.record_id or "",
            ):
                per_symbol[r.symbol] = r
        return per_symbol

    def asof_universe_symbols(
        self, simulated_time: datetime
    ) -> Tuple[str, ...]:
        """Return the tradable / monitorable symbols at
        ``simulated_time``, reconstructed strictly from the
        per-symbol status timeline (no survivorship bias).

        A symbol qualifies iff its latest *visible* status record
        (``available_at <= simulated_time``) is tradable / monitorable
        and the symbol is listed and not yet delisted at that time.
        """
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        per_symbol: Dict[str, SymbolStatusRecord] = {}
        for r in self.symbol_status_records:
            if r.available_at > sim:
                continue
            cur = per_symbol.get(r.symbol)
            key_new = (r.event_time, r.available_at, r.record_id or "")
            if cur is None or key_new > (
                cur.event_time,
                cur.available_at,
                cur.record_id or "",
            ):
                per_symbol[r.symbol] = r
        out = [
            sym
            for sym, r in per_symbol.items()
            if r.is_tradable_or_monitorable_at(sim)
        ]
        return tuple(sorted(out))

    def _content_for_hash(self) -> Dict[str, Any]:
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "symbol_status_records": [
                r.to_dict() for r in self.symbol_status_records
            ],
            "warnings": list(self.warnings),
        }

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "manifest_id": self.manifest_id,
            "generated_at_utc": (
                self.generated_at_utc.isoformat()
                if self.generated_at_utc is not None
                else None
            ),
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "symbols": list(self.symbols),
            "symbol_status_records": [
                r.to_dict() for r in self.symbol_status_records
            ],
            "listed_count": self.listed_count,
            "delisted_count": self.delisted_count,
            "status_unknown_count": self.status_unknown_count,
            "universe_manifest_hash": self.universe_manifest_hash,
            "survivorship_bias_guard": True,
            "warnings": list(self.warnings),
            "is_universe_manifest": True,
        }
        out.update(_safety_payload())
        # Re-pin survivorship guard after the safety payload merge.
        out["survivorship_bias_guard"] = True
        assert_no_forbidden_fields(out)
        return out

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), sort_keys=True, default=_json_default
        )


__all__ = [
    "PHASE_NAME",
    "HistoricalDataSourceType",
    "DataIngestionStatus",
    "HistoricalDataManifest",
    "UniverseManifest",
    "compute_artefact_hash",
    "safety_payload",
    "DataCompletenessState",
]
