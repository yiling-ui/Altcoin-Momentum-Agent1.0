"""Full-system sandbox audit data contracts (PR117 - Full-System Single-Altcoin
Live Sandbox Audit v0).

PR117 is the FINAL full-system sandbox audit. It runs the *real*
PR110-PR116 live chain (path isolation -> capital profile -> live risk
-> right-tail leverage gate -> execution gateway -> Binance execution
adapter -> order ledger -> funding-aware PnL -> Telegram operator
console -> DeepSeek live briefing -> kill switch) against a single fake
altcoin (``RAVEUSDT_SANDBOX``) using fake transports only:

  * :class:`app.live.fake_live_market.FakeLiveMarketAdapter`
  * :class:`app.live.fake_live_exchange.FakeBinanceLiveAdapter`
  * :class:`app.live.fake_live_telegram.FakeTelegramTransport`
  * :class:`app.live.fake_live_deepseek.FakeDeepSeekTransport`

This module holds the frozen, log-safe data contracts the audit runner
(:mod:`app.live.full_system_sandbox`) and the CLI
(``scripts/live_full_system_sandbox_audit.py``) share.

HARD PR117 posture (the brief):
  * NEVER places a real order. ``no_real_order_sent`` is always True.
  * NEVER uses a real Binance / Telegram / DeepSeek transport.
    ``fake_transports_used`` is always True.
  * Default ``live_trading`` / ``exchange_live_orders`` /
    ``trade_authority`` / ``ai_trade_authority`` are all False.
  * blind / replay / sim / paper-shadow sources stay isolated from the
    live path.

Nothing in this module performs IO, places an order, or flips a safety
flag; these are pure data contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

FULL_SYSTEM_AUDIT_MODELS_MODULE = "live.full_system_audit_models"

# Tri-state audit verdict vocabulary (kept as plain strings so they embed
# verbatim in JSON output / events).
AUDIT_PASS = "PASS"
AUDIT_WARN = "WARN"
AUDIT_FAIL = "FAIL"

# Check severity vocabulary.
SEVERITY_BLOCKER = "blocker"  # a failed blocker -> scenario FAIL
SEVERITY_WARNING = "warning"  # a failed warning -> scenario WARN
SEVERITY_INFO = "info"        # informational only; never affects status

_STATUS_RANK = {AUDIT_PASS: 0, AUDIT_WARN: 1, AUDIT_FAIL: 2}

# The default sandbox altcoin symbol.
DEFAULT_SANDBOX_SYMBOL = "RAVEUSDT_SANDBOX"


def worst_audit_status(statuses: Iterable[str]) -> str:
    """Return the worst (most severe) audit status in ``statuses``.

    An empty collection yields ``PASS`` (nothing failed).
    """
    worst = AUDIT_PASS
    for s in statuses:
        if _STATUS_RANK.get(s, 0) > _STATUS_RANK.get(worst, 0):
            worst = s
    return worst


@dataclass(frozen=True)
class AuditCheck:
    """A single audit assertion line.

    ``passed`` is the boolean outcome. ``severity`` decides how a failure
    rolls up: a failed ``blocker`` is a FAIL, a failed ``warning`` is a
    WARN, a failed ``info`` is recorded but never changes the status.
    """

    check_id: str
    passed: bool
    severity: str = SEVERITY_BLOCKER
    detail: str = ""
    value: Any = None

    @property
    def status(self) -> str:
        if self.passed:
            return AUDIT_PASS
        if self.severity == SEVERITY_BLOCKER:
            return AUDIT_FAIL
        if self.severity == SEVERITY_WARNING:
            return AUDIT_WARN
        return AUDIT_PASS

    @property
    def is_blocker_failure(self) -> bool:
        return (not self.passed) and self.severity == SEVERITY_BLOCKER

    @property
    def is_warning_failure(self) -> bool:
        return (not self.passed) and self.severity == SEVERITY_WARNING

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "passed": self.passed,
            "severity": self.severity,
            "status": self.status,
            "detail": self.detail,
            "value": self.value,
        }


@dataclass(frozen=True)
class ScenarioResult:
    """The aggregate result of one audit scenario."""

    scenario: str
    status: str
    checks: tuple[AuditCheck, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in (AUDIT_PASS, AUDIT_WARN)

    @property
    def passed(self) -> bool:
        return self.status == AUDIT_PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "status": self.status,
            "ok": self.ok,
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "details": dict(self.details),
        }


class ScenarioBuilder:
    """A small mutable accumulator that builds a frozen :class:`ScenarioResult`.

    Used by the audit runner to record checks one at a time and then
    ``build()`` the immutable result.
    """

    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self._checks: list[AuditCheck] = []
        self._details: dict[str, Any] = {}

    def check(
        self,
        check_id: str,
        passed: bool,
        *,
        severity: str = SEVERITY_BLOCKER,
        detail: str = "",
        value: Any = None,
    ) -> AuditCheck:
        c = AuditCheck(
            check_id=check_id,
            passed=bool(passed),
            severity=severity,
            detail=detail,
            value=value,
        )
        self._checks.append(c)
        return c

    def blocker(self, check_id: str, passed: bool, *, detail: str = "", value: Any = None) -> AuditCheck:
        return self.check(check_id, passed, severity=SEVERITY_BLOCKER, detail=detail, value=value)

    def warn(self, check_id: str, passed: bool, *, detail: str = "", value: Any = None) -> AuditCheck:
        return self.check(check_id, passed, severity=SEVERITY_WARNING, detail=detail, value=value)

    def info(self, check_id: str, passed: bool = True, *, detail: str = "", value: Any = None) -> AuditCheck:
        return self.check(check_id, passed, severity=SEVERITY_INFO, detail=detail, value=value)

    def detail(self, key: str, value: Any) -> None:
        self._details[key] = value

    def merge_details(self, mapping: dict[str, Any]) -> None:
        self._details.update(mapping)

    @property
    def checks(self) -> tuple[AuditCheck, ...]:
        return tuple(self._checks)

    def build(self) -> ScenarioResult:
        blockers = tuple(c.check_id for c in self._checks if c.is_blocker_failure)
        warnings = tuple(c.check_id for c in self._checks if c.is_warning_failure)
        status = worst_audit_status(c.status for c in self._checks)
        return ScenarioResult(
            scenario=self.scenario,
            status=status,
            checks=tuple(self._checks),
            blockers=blockers,
            warnings=warnings,
            details=dict(self._details),
        )


# Mapping of scenario name -> the chain-ok flag it drives in the report.
SCENARIO_TO_CHAIN_FLAG: dict[str, str] = {
    "strategy_lifecycle": "strategy_chain_ok",
    "execution_lifecycle": "execution_chain_ok",
    "live_risk": "live_risk_chain_ok",
    "capital_ladder": "capital_ladder_chain_ok",
    "funding_fee_pnl": "funding_pnl_chain_ok",
    "telegram_operator": "telegram_chain_ok",
    "ai_guard": "ai_chain_ok",
    "blind_isolation": "blind_isolation_ok",
    "kill_switch": "kill_switch_chain_ok",
}

# The canonical set of scenario names runnable via --scenario all.
ALL_SCENARIOS: tuple[str, ...] = (
    "strategy_lifecycle",
    "execution_lifecycle",
    "live_risk",
    "capital_ladder",
    "funding_fee_pnl",
    "telegram_operator",
    "ai_guard",
    "blind_isolation",
    "kill_switch",
)


@dataclass(frozen=True)
class FullSystemAuditReport:
    """The full-system single-altcoin sandbox audit report (PR117).

    Carries the overall verdict, every scenario result, the per-chain ok
    flags, the safe-by-default markers, and the
    ``ready_for_real_key_validation`` gate. Running the audit NEVER sends
    a real order: ``no_real_order_sent`` is always True and
    ``fake_transports_used`` is always True.
    """

    overall_status: str
    symbol: str
    scenario_results: tuple[ScenarioResult, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    # Per-chain roll-ups.
    full_system_chain_ok: bool
    strategy_chain_ok: bool
    live_risk_chain_ok: bool
    execution_chain_ok: bool
    telegram_chain_ok: bool
    ai_chain_ok: bool
    funding_pnl_chain_ok: bool
    capital_ladder_chain_ok: bool
    blind_isolation_ok: bool
    kill_switch_chain_ok: bool

    # Hard PR117 safety markers.
    no_real_order_sent: bool = True
    fake_transports_used: bool = True
    live_trading: bool = False
    exchange_live_orders: bool = False
    trade_authority: bool = False
    ai_trade_authority: bool = False

    ready_for_real_key_validation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit": "PR117_FULL_SYSTEM_SANDBOX_AUDIT",
            "overall_status": self.overall_status,
            "symbol": self.symbol,
            "scenario_results": [s.to_dict() for s in self.scenario_results],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            # Per-chain ok flags.
            "full_system_chain_ok": self.full_system_chain_ok,
            "strategy_chain_ok": self.strategy_chain_ok,
            "live_risk_chain_ok": self.live_risk_chain_ok,
            "execution_chain_ok": self.execution_chain_ok,
            "telegram_chain_ok": self.telegram_chain_ok,
            "ai_chain_ok": self.ai_chain_ok,
            "funding_pnl_chain_ok": self.funding_pnl_chain_ok,
            "capital_ladder_chain_ok": self.capital_ladder_chain_ok,
            "blind_isolation_ok": self.blind_isolation_ok,
            "kill_switch_chain_ok": self.kill_switch_chain_ok,
            # Hard PR117 safety markers.
            "no_real_order_sent": self.no_real_order_sent,
            "fake_transports_used": self.fake_transports_used,
            "live_trading": self.live_trading,
            "exchange_live_orders": self.exchange_live_orders,
            "trade_authority": self.trade_authority,
            "ai_trade_authority": self.ai_trade_authority,
            "ready_for_real_key_validation": self.ready_for_real_key_validation,
            "phase_12_forbidden": True,
        }

    @classmethod
    def build(
        cls,
        *,
        symbol: str,
        scenario_results: Iterable[ScenarioResult],
        no_real_order_sent: bool = True,
    ) -> "FullSystemAuditReport":
        """Roll up a sequence of scenario results into the full report."""
        results = tuple(scenario_results)
        by_name = {r.scenario: r for r in results}

        overall_status = worst_audit_status(r.status for r in results)

        blockers: list[str] = []
        warnings: list[str] = []
        for r in results:
            for b in r.blockers:
                blockers.append(f"{r.scenario}:{b}")
            for w in r.warnings:
                warnings.append(f"{r.scenario}:{w}")

        def _chain_ok(scenario: str) -> bool:
            r = by_name.get(scenario)
            # A scenario that did not run is treated as ok (not evaluated),
            # so partial runs (single --scenario) do not falsely fail an
            # unrelated chain flag.
            return True if r is None else r.ok

        strategy_chain_ok = _chain_ok("strategy_lifecycle")
        execution_chain_ok = _chain_ok("execution_lifecycle")
        live_risk_chain_ok = _chain_ok("live_risk")
        capital_ladder_chain_ok = _chain_ok("capital_ladder")
        funding_pnl_chain_ok = _chain_ok("funding_fee_pnl")
        telegram_chain_ok = _chain_ok("telegram_operator")
        ai_chain_ok = _chain_ok("ai_guard")
        blind_isolation_ok = _chain_ok("blind_isolation")
        kill_switch_chain_ok = _chain_ok("kill_switch")

        full_system_chain_ok = all(r.ok for r in results) if results else False

        # The audit clears the system for real-key validation only when the
        # full sandbox chain passed (no FAIL), the blind isolation held, and
        # no real order was ever sent. A real-key validation is the ONLY
        # remaining step before a funded 10U LIVE_LIMITED launch.
        ready_for_real_key_validation = bool(
            overall_status != AUDIT_FAIL
            and full_system_chain_ok
            and blind_isolation_ok
            and no_real_order_sent
        )

        return cls(
            overall_status=overall_status,
            symbol=symbol,
            scenario_results=results,
            blockers=tuple(blockers),
            warnings=tuple(warnings),
            full_system_chain_ok=full_system_chain_ok,
            strategy_chain_ok=strategy_chain_ok,
            live_risk_chain_ok=live_risk_chain_ok,
            execution_chain_ok=execution_chain_ok,
            telegram_chain_ok=telegram_chain_ok,
            ai_chain_ok=ai_chain_ok,
            funding_pnl_chain_ok=funding_pnl_chain_ok,
            capital_ladder_chain_ok=capital_ladder_chain_ok,
            blind_isolation_ok=blind_isolation_ok,
            kill_switch_chain_ok=kill_switch_chain_ok,
            no_real_order_sent=no_real_order_sent,
            ready_for_real_key_validation=ready_for_real_key_validation,
        )


__all__ = [
    "FULL_SYSTEM_AUDIT_MODELS_MODULE",
    "AUDIT_PASS",
    "AUDIT_WARN",
    "AUDIT_FAIL",
    "SEVERITY_BLOCKER",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    "DEFAULT_SANDBOX_SYMBOL",
    "ALL_SCENARIOS",
    "SCENARIO_TO_CHAIN_FLAG",
    "worst_audit_status",
    "AuditCheck",
    "ScenarioResult",
    "ScenarioBuilder",
    "FullSystemAuditReport",
]
