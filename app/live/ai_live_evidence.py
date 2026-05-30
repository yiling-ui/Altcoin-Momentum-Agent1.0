"""Live AI Evidence Bundle (PR115 - DeepSeek Live Intelligence v0).

PR115 connects DeepSeek to the live operator workflow as MARKET
INTELLIGENCE ONLY. Before any briefing is generated, the live-approved
evidence is compressed into a single :class:`LiveAIEvidenceBundle`. The
bundle is the ONLY thing the AI is ever allowed to see, and it carries a
hard source boundary:

  * source_scope is always ``LIVE_ONLY``.
  * Only live-approved evidence may enter the bundle:
      - Binance public live market data
      - Binance private read account / positions / income
      - LiveCapitalState
      - LivePnlSummary
      - LiveRiskDecision
      - LiveExecutionGateway / LiveOrderLedger
      - Telegram Operator state
      - Capital Profile state
      - Funding attribution result
      - System health check
  * A non-live source is REFUSED. ``SIM`` / ``BLIND`` / ``REPLAY`` /
    ``PAPER_SHADOW`` / ``BACKTEST`` / ``OFFLINE_AI`` / ``TELEGRAM_SANDBOX``
    (and the simulation module class names that produce them) cause the
    bundle to be rejected and a
    ``LIVE_AI_EVIDENCE_REJECTED_FOR_NONLIVE_SOURCE`` event to be emitted.

The builder is pure (no network IO). It never places an order, never
changes capital / mode / profile / risk, and never flips a safety flag.
Every bundle pins ``ai_trade_authority = False``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from app.core.clock import now_ms
from app.core.enums import LiveRuntimeMode, OrderSource
from app.core.events import Event, EventType
from app.exports.redaction import redact

AI_LIVE_EVIDENCE_MODULE = "live.ai_live_evidence"

# Every PR115 evidence bundle is LIVE-only.
SOURCE_SCOPE_LIVE_ONLY = "LIVE_ONLY"


# ---------------------------------------------------------------------------
# Source taxonomy
# ---------------------------------------------------------------------------
#: Live-approved evidence source labels (the ONLY admissible provenance).
LIVE_APPROVED_EVIDENCE_SOURCES: frozenset[str] = frozenset(
    {
        "LIVE",
        "BINANCE_PUBLIC",
        "BINANCE_PUBLIC_MARKET",
        "BINANCE_PRIVATE_READ",
        "LIVE_CAPITAL_STATE",
        "LIVE_PNL_SUMMARY",
        "LIVE_RISK_DECISION",
        "LIVE_EXECUTION_GATEWAY",
        "LIVE_ORDER_LEDGER",
        "TELEGRAM_OPERATOR",
        "TELEGRAM_OPERATOR_STATE",
        "CAPITAL_PROFILE",
        "CAPITAL_PROFILE_STATE",
        "FUNDING_ATTRIBUTION",
        "SYSTEM_HEALTH",
        "SYSTEM_HEALTH_CHECK",
        "API_HEALTH",
    }
)

#: Forbidden (non-live) evidence source labels. These mirror the PR110 /
#: PR114 non-live :class:`OrderSource` values plus the simulation module
#: class names that produce them. A bundle carrying ANY of these is
#: rejected wholesale.
FORBIDDEN_EVIDENCE_SOURCES: frozenset[str] = frozenset(
    {
        # Non-live OrderSource values.
        "SIM",
        "BLIND",
        "REPLAY",
        "PAPER_SHADOW",
        "BACKTEST",
        "OFFLINE_AI",
        "TELEGRAM_SANDBOX",
        # Simulation / blind / replay / paper-shadow module class names.
        "BLINDWALKFORWARDRUNNER",
        "BLIND_WALK_FORWARD_RUNNER",
        "HISTORICALMARKETSTORE",
        "HISTORICAL_MARKET_STORE",
        "REPLAYFEEDPROVIDER",
        "REPLAY_FEED_PROVIDER",
        "MOCKEXCHANGE",
        "MOCK_EXCHANGE",
        "SIMULATEDCAPITALFLOW",
        "SIMULATED_CAPITAL_FLOW",
        "PAPERSHADOWSTRATEGYBRIDGE",
        "PAPER_SHADOW_STRATEGY_BRIDGE",
        "BLIND_REPORT",
        "REPLAY_OUTCOME",
        "REFLECTION_OUTCOME",
        "HISTORICAL_MFE",
        "HISTORICAL_MAE",
        "COMPLETED_TAIL_LABEL",
        "SIMULATED_TRADE_LEDGER",
        "TELEGRAM_SANDBOX_OUTBOX",
        "OFFLINE_AI_REPLAY",
    }
)

_LIVE_APPROVED_UPPER: frozenset[str] = frozenset(
    s.upper() for s in LIVE_APPROVED_EVIDENCE_SOURCES
)
_FORBIDDEN_UPPER: frozenset[str] = frozenset(
    s.upper() for s in FORBIDDEN_EVIDENCE_SOURCES
)


def normalise_source(source: Any) -> str:
    """Return the canonical string label for a source value."""
    if isinstance(source, OrderSource):
        return source.value
    return str(source).strip()


def is_live_approved_source(source: Any) -> bool:
    """True only when ``source`` is an explicitly live-approved label."""
    if isinstance(source, OrderSource):
        return source.is_live
    label = normalise_source(source).upper()
    return label in _LIVE_APPROVED_UPPER


def is_forbidden_source(source: Any) -> bool:
    """True when ``source`` is a known non-live / simulation source.

    Fail-safe: a source that is neither explicitly live-approved nor a
    known live-context label is treated as forbidden (unknown provenance
    can never reach the AI), mirroring the PR110 path-isolation rule that
    an unknown module maps to a blocked source.
    """
    if isinstance(source, OrderSource):
        return not source.is_live
    label = normalise_source(source)
    if label == "":
        # An empty / missing tag is unknown provenance -> fail safe.
        return True
    upper = label.upper()
    if upper in _FORBIDDEN_UPPER:
        return True
    if upper in _LIVE_APPROVED_UPPER:
        return False
    # Unknown label -> fail safe (forbidden).
    return True


def detect_forbidden_sources(sources: Iterable[Any]) -> tuple[str, ...]:
    """Return the sorted, de-duplicated list of forbidden sources found."""
    found: set[str] = set()
    for source in sources or ():
        if is_forbidden_source(source):
            found.add(normalise_source(source) or "<unknown>")
    return tuple(sorted(found))


# ---------------------------------------------------------------------------
# Bundle
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LiveAIEvidenceBundle:
    """A compressed, LIVE-only evidence bundle handed to the AI (PR115).

    Every section is a read-only snapshot drawn from a live-approved
    source. The bundle never carries a raw secret (it is redacted on
    construction) and always reports ``ai_trade_authority == False`` and
    ``source_scope == LIVE_ONLY``.
    """

    evidence_bundle_id: str
    created_at: int
    runtime_mode: str
    capital_profile_id: str
    account_status: dict[str, Any] = field(default_factory=dict)
    pnl_summary: dict[str, Any] = field(default_factory=dict)
    open_positions: tuple[dict[str, Any], ...] = ()
    risk_summary: dict[str, Any] = field(default_factory=dict)
    recent_order_summary: dict[str, Any] = field(default_factory=dict)
    funding_summary: dict[str, Any] = field(default_factory=dict)
    telegram_state: dict[str, Any] = field(default_factory=dict)
    api_health_summary: dict[str, Any] = field(default_factory=dict)
    market_snapshot_summary: dict[str, Any] | None = None
    evidence_refs: tuple[str, ...] = ()
    forbidden_sources_detected: tuple[str, ...] = ()
    source_scope: str = SOURCE_SCOPE_LIVE_ONLY
    ai_trade_authority: bool = False  # pinned False

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_bundle_id": self.evidence_bundle_id,
            "created_at": self.created_at,
            "source_scope": SOURCE_SCOPE_LIVE_ONLY,
            "runtime_mode": self.runtime_mode,
            "capital_profile_id": self.capital_profile_id,
            "account_status": dict(self.account_status),
            "pnl_summary": dict(self.pnl_summary),
            "open_positions": [dict(p) for p in self.open_positions],
            "risk_summary": dict(self.risk_summary),
            "recent_order_summary": dict(self.recent_order_summary),
            "funding_summary": dict(self.funding_summary),
            "telegram_state": dict(self.telegram_state),
            "api_health_summary": dict(self.api_health_summary),
            "market_snapshot_summary": (
                dict(self.market_snapshot_summary)
                if self.market_snapshot_summary is not None
                else None
            ),
            "evidence_refs": list(self.evidence_refs),
            "forbidden_sources_detected": list(self.forbidden_sources_detected),
            # Hard-pinned PR115 markers.
            "ai_trade_authority": False,
            "trade_authority": False,
            "exchange_live_orders": False,
            "live_trading": False,
            "phase_12_forbidden": True,
        }


@dataclass(frozen=True)
class EvidenceBundleResult:
    """Outcome of building a live AI evidence bundle."""

    accepted: bool
    bundle: LiveAIEvidenceBundle | None
    forbidden_sources_detected: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "bundle": self.bundle.to_dict() if self.bundle else None,
            "forbidden_sources_detected": list(self.forbidden_sources_detected),
            "reason": self.reason,
            "source_scope": SOURCE_SCOPE_LIVE_ONLY,
            "ai_trade_authority": False,
        }


def _mode_value(mode: LiveRuntimeMode | str | None) -> str:
    if isinstance(mode, LiveRuntimeMode):
        return mode.value
    if isinstance(mode, str) and mode:
        return mode
    return LiveRuntimeMode.LIVE_SHADOW.value


def _as_dict(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    return dict(value)


def build_live_ai_evidence_bundle(
    *,
    runtime_mode: LiveRuntimeMode | str = LiveRuntimeMode.LIVE_SHADOW,
    capital_profile_id: str = "L0_SHADOW",
    account_status: Mapping[str, Any] | None = None,
    pnl_summary: Mapping[str, Any] | None = None,
    open_positions: Iterable[Mapping[str, Any]] | None = None,
    risk_summary: Mapping[str, Any] | None = None,
    recent_order_summary: Mapping[str, Any] | None = None,
    funding_summary: Mapping[str, Any] | None = None,
    telegram_state: Mapping[str, Any] | None = None,
    api_health_summary: Mapping[str, Any] | None = None,
    market_snapshot_summary: Mapping[str, Any] | None = None,
    sources: Iterable[Any] | None = None,
    evidence_refs: Iterable[str] | None = None,
    event_repo: Any | None = None,
    clock: Any = now_ms,
) -> EvidenceBundleResult:
    """Compress live-approved evidence into a :class:`LiveAIEvidenceBundle`.

    ``sources`` is the declared provenance of the supplied evidence. When
    omitted it defaults to ``[OrderSource.LIVE]``. If ANY source is a
    non-live / simulation source the bundle is REJECTED, a
    ``LIVE_AI_EVIDENCE_REJECTED_FOR_NONLIVE_SOURCE`` event is emitted, and
    the result carries ``accepted=False`` with the offending sources.

    Evidence content is redacted on construction (defence in depth) so a
    secret can never reach the AI prompt even if a caller passes one.
    """

    declared_sources = list(sources) if sources is not None else [OrderSource.LIVE]
    forbidden = detect_forbidden_sources(declared_sources)
    if forbidden:
        _emit(
            event_repo,
            EventType.LIVE_AI_EVIDENCE_REJECTED_FOR_NONLIVE_SOURCE,
            {
                "forbidden_sources_detected": list(forbidden),
                "source_scope": SOURCE_SCOPE_LIVE_ONLY,
                "reason": "non_live_evidence_source_refused",
            },
        )
        return EvidenceBundleResult(
            accepted=False,
            bundle=None,
            forbidden_sources_detected=forbidden,
            reason="non_live_evidence_source_refused",
        )

    positions = [redact(dict(p)) for p in (open_positions or ())]
    refs = tuple(str(r) for r in (evidence_refs or ()))

    bundle = LiveAIEvidenceBundle(
        evidence_bundle_id="AIEV-" + uuid.uuid4().hex[:12].upper(),
        created_at=int(clock()),
        runtime_mode=_mode_value(runtime_mode),
        capital_profile_id=str(capital_profile_id),
        account_status=redact(_as_dict(account_status)),
        pnl_summary=redact(_as_dict(pnl_summary)),
        open_positions=tuple(positions),
        risk_summary=redact(_as_dict(risk_summary)),
        recent_order_summary=redact(_as_dict(recent_order_summary)),
        funding_summary=redact(_as_dict(funding_summary)),
        telegram_state=redact(_as_dict(telegram_state)),
        api_health_summary=redact(_as_dict(api_health_summary)),
        market_snapshot_summary=(
            redact(_as_dict(market_snapshot_summary))
            if market_snapshot_summary is not None
            else None
        ),
        evidence_refs=refs,
        forbidden_sources_detected=(),
    )
    return EvidenceBundleResult(
        accepted=True,
        bundle=bundle,
        forbidden_sources_detected=(),
        reason="ok",
    )


def _emit(event_repo: Any | None, event_type: EventType, payload: dict[str, Any]) -> None:
    if event_repo is None:
        return
    try:
        event_repo.append(
            Event(
                event_type=event_type,
                source_module=AI_LIVE_EVIDENCE_MODULE,
                payload={
                    **payload,
                    "ai_trade_authority": False,
                    "trade_authority": False,
                    "exchange_live_orders": False,
                    "phase_12_forbidden": True,
                },
            )
        )
    except Exception:  # pragma: no cover - event emit is best-effort
        pass


__all__ = [
    "AI_LIVE_EVIDENCE_MODULE",
    "SOURCE_SCOPE_LIVE_ONLY",
    "LIVE_APPROVED_EVIDENCE_SOURCES",
    "FORBIDDEN_EVIDENCE_SOURCES",
    "normalise_source",
    "is_live_approved_source",
    "is_forbidden_source",
    "detect_forbidden_sources",
    "LiveAIEvidenceBundle",
    "EvidenceBundleResult",
    "build_live_ai_evidence_bundle",
]
