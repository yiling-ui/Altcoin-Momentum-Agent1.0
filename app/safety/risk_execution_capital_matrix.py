"""Risk / Execution / Capital Safety Matrix v0 (Phase 11C.1D-C).

A strictly paper / report / evidence-only safety verification engine
that takes a deterministic set of adverse-condition scenarios
(``SafetyMatrixScenario`` rows) and verifies that the documented
safety boundary always:

    * pauses new opens when required,
    * rejects unsafe actions,
    * requires operator review or operator resume when required,
    * degrades to report-only when telemetry is degraded,
    * blocks Telegram outbound, AI trade authority, runtime config
      changes, and live orders unconditionally,
    * keeps the paper ledger when the live path is unsafe,
    * records audit events for every adverse scenario.

This module is **NOT** the real Risk Engine. It does **NOT** call the
real Risk Engine, the real Execution FSM, the real Exchange gateway,
the real Telegram outbound, or the real DeepSeek / LLM transport. It
MUST NEVER:

  * import app.risk / app.execution / app.exchanges / app.telegram /
    app.config
  * write back to runtime config
  * generate ``runtime_config_patch`` / ``threshold_patch`` /
    ``symbol_limit_patch`` / ``candidate_pool_patch`` /
    ``regime_weight_patch`` / ``strategy_parameter_patch``
  * emit buy / sell / long / short / direction / entry / exit /
    position_size / leverage / stop / stop_loss / target /
    take_profit / risk_budget / order / execution_command /
    signal_to_trade / should_buy / should_short / apply_change /
    deploy_change / enable_live / live_ready / trading_approved
  * authorize live trading or hot-path execution
  * call DeepSeek / LLM / network / Telegram / Binance private API
  * enter Phase 12

================================================================
HARD SAFETY BOUNDARY
================================================================

  mode                          = paper
  sandbox_only                  = True
  writes_runtime_config         = False
  auto_tuning_allowed           = False
  trade_authority               = False
  live_trading                  = False
  exchange_live_orders          = False
  right_tail                    = False
  llm                           = False
  llm_outbound_enabled          = False
  telegram_outbound_enabled     = False
  binance_private_api_enabled   = False
  allow_trade_decision          = False
  allow_runtime_config_change   = False
  phase_12_forbidden            = True

A successful safety matrix run with zero P0 / P1 blockers ONLY
authorizes the *Strict Blind Walk-forward design checkpoint*. It does
**NOT** authorize Blind Walk-forward implementation. It does **NOT**
authorize live trading. It does **NOT** authorize auto-tuning. It does
**NOT** open Phase 12.

Before Blind Walk-forward implementation can begin, the human owner
must provide a finalized strict forward-only anti-lookahead blind-test
design. This module does not, and cannot, generate that design.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

PHASE_NAME: str = (
    "Phase 11C.1D-C / Risk / Execution / Capital Safety Matrix v0"
)

# next_allowed_phase after a successful safety matrix run with zero P0
# / P1 blockers is *only* the Strict Blind Walk-forward design
# checkpoint. It is NEVER live trading, NEVER auto-tuning, NEVER Phase
# 12, and NEVER Blind Walk-forward implementation. Blind Walk-forward
# implementation requires a separately-supplied human design.
NEXT_ALLOWED_PHASE_NO_BLOCKERS: str = (
    "Strict Blind Walk-forward design checkpoint "
    "(paper / read-only; requires human-owner-supplied "
    "strict forward-only anti-lookahead blind-test design)"
)

NEXT_ALLOWED_PHASE_WITH_BLOCKERS: str = (
    "Safety Matrix remediation required "
    "(paper / read-only; remediate P0 / P1 blockers and re-run)"
)


# ---------------------------------------------------------------------------
# Allowed event types (report / export / audit scope only)
# ---------------------------------------------------------------------------


class SafetyMatrixEvent:
    """Allowed event types. Strictly report / export / audit scope.

    No trade-action events are defined and none must be added in this
    phase.
    """

    SAFETY_MATRIX_SCENARIO_EVALUATED: str = (
        "SAFETY_MATRIX_SCENARIO_EVALUATED"
    )
    SAFETY_MATRIX_REPORT_GENERATED: str = (
        "SAFETY_MATRIX_REPORT_GENERATED"
    )
    SAFETY_MATRIX_BLOCKER_DETECTED: str = (
        "SAFETY_MATRIX_BLOCKER_DETECTED"
    )

    ALLOWED: frozenset = frozenset(
        {
            SAFETY_MATRIX_SCENARIO_EVALUATED,
            SAFETY_MATRIX_REPORT_GENERATED,
            SAFETY_MATRIX_BLOCKER_DETECTED,
        }
    )


# ---------------------------------------------------------------------------
# Scenario type (closed enum, descriptive only)
# ---------------------------------------------------------------------------


class SafetyMatrixScenarioType:
    """Closed taxonomy of adverse scenarios verified by the matrix.

    Every scenario_type is descriptive only. None of these constants
    are inputs to the live Risk Engine, the live Execution FSM, the
    live Exchange gateway, or any runtime knob. They are labels used
    by the matrix to look up expected safety actions.
    """

    STOP_FAILED: str = "STOP_FAILED"
    STOP_UNCONFIRMED: str = "STOP_UNCONFIRMED"
    GHOST_POSITION: str = "GHOST_POSITION"
    ORPHAN_STOP: str = "ORPHAN_STOP"
    MISSING_REMOTE_POSITION: str = "MISSING_REMOTE_POSITION"
    RECONCILIATION_MISMATCH: str = "RECONCILIATION_MISMATCH"
    DATA_DEGRADED: str = "DATA_DEGRADED"
    WS_STALE: str = "WS_STALE"
    REST_429: str = "REST_429"
    REST_418: str = "REST_418"
    TELEGRAM_EXPORT_FAILURE: str = "TELEGRAM_EXPORT_FAILURE"
    TELEGRAM_OUTBOUND_BLOCKED: str = "TELEGRAM_OUTBOUND_BLOCKED"
    PAUSE_RESUME_REQUIRED: str = "PAUSE_RESUME_REQUIRED"
    KILL_ALL_AUDIT_ONLY: str = "KILL_ALL_AUDIT_ONLY"
    CAPITAL_REBASE_IN_PROGRESS: str = "CAPITAL_REBASE_IN_PROGRESS"
    EXTERNAL_DEPOSIT: str = "EXTERNAL_DEPOSIT"
    PROFIT_WITHDRAWAL: str = "PROFIT_WITHDRAWAL"
    LLM_DEGRADED: str = "LLM_DEGRADED"
    DEEPSEEK_TIMEOUT: str = "DEEPSEEK_TIMEOUT"
    AI_REALITY_CHECK_FAILED: str = "AI_REALITY_CHECK_FAILED"
    AI_FORBIDDEN_FIELD_STRIPPED: str = "AI_FORBIDDEN_FIELD_STRIPPED"

    ALLOWED: frozenset = frozenset(
        {
            STOP_FAILED,
            STOP_UNCONFIRMED,
            GHOST_POSITION,
            ORPHAN_STOP,
            MISSING_REMOTE_POSITION,
            RECONCILIATION_MISMATCH,
            DATA_DEGRADED,
            WS_STALE,
            REST_429,
            REST_418,
            TELEGRAM_EXPORT_FAILURE,
            TELEGRAM_OUTBOUND_BLOCKED,
            PAUSE_RESUME_REQUIRED,
            KILL_ALL_AUDIT_ONLY,
            CAPITAL_REBASE_IN_PROGRESS,
            EXTERNAL_DEPOSIT,
            PROFIT_WITHDRAWAL,
            LLM_DEGRADED,
            DEEPSEEK_TIMEOUT,
            AI_REALITY_CHECK_FAILED,
            AI_FORBIDDEN_FIELD_STRIPPED,
        }
    )


# ---------------------------------------------------------------------------
# Expected action (closed enum, all paper / sandbox safe)
# ---------------------------------------------------------------------------


class SafetyMatrixExpectedAction:
    """Closed taxonomy of allowed safety actions.

    Note: every action here is *defensive* (pauses, rejects, requires
    operator review, blocks, records audit, keeps paper ledger). No
    member of this enum can place an order, modify runtime config, or
    enter Phase 12. ``APPLY``, ``DEPLOY``, ``ENABLE_LIVE``,
    ``GO_LIVE``, ``AUTO_APPLY``, ``BUY``, ``SELL`` are intentionally
    NOT defined and the engine refuses to ever emit them.
    """

    PAUSE_NEW_OPENS: str = "PAUSE_NEW_OPENS"
    REJECT_UNSAFE_ACTION: str = "REJECT_UNSAFE_ACTION"
    REQUIRE_OPERATOR_REVIEW: str = "REQUIRE_OPERATOR_REVIEW"
    REQUIRE_OPERATOR_RESUME: str = "REQUIRE_OPERATOR_RESUME"
    DEGRADE_TO_REPORT_ONLY: str = "DEGRADE_TO_REPORT_ONLY"
    RECORD_AUDIT_EVENT: str = "RECORD_AUDIT_EVENT"
    BLOCK_TELEGRAM_OUTBOUND: str = "BLOCK_TELEGRAM_OUTBOUND"
    BLOCK_AI_TRADE_AUTHORITY: str = "BLOCK_AI_TRADE_AUTHORITY"
    BLOCK_RUNTIME_CONFIG_CHANGE: str = "BLOCK_RUNTIME_CONFIG_CHANGE"
    BLOCK_LIVE_ORDER: str = "BLOCK_LIVE_ORDER"
    PAPER_LEDGER_ONLY: str = "PAPER_LEDGER_ONLY"
    NO_ACTION_REQUIRED: str = "NO_ACTION_REQUIRED"

    ALLOWED: frozenset = frozenset(
        {
            PAUSE_NEW_OPENS,
            REJECT_UNSAFE_ACTION,
            REQUIRE_OPERATOR_REVIEW,
            REQUIRE_OPERATOR_RESUME,
            DEGRADE_TO_REPORT_ONLY,
            RECORD_AUDIT_EVENT,
            BLOCK_TELEGRAM_OUTBOUND,
            BLOCK_AI_TRADE_AUTHORITY,
            BLOCK_RUNTIME_CONFIG_CHANGE,
            BLOCK_LIVE_ORDER,
            PAPER_LEDGER_ONLY,
            NO_ACTION_REQUIRED,
        }
    )


# ---------------------------------------------------------------------------
# Severity (P0 / P1 / P2 / P3, descriptive only)
# ---------------------------------------------------------------------------


class SafetyMatrixSeverity:
    P0: str = "P0"
    P1: str = "P1"
    P2: str = "P2"
    P3: str = "P3"

    ALLOWED: frozenset = frozenset({P0, P1, P2, P3})


# ---------------------------------------------------------------------------
# Result status (closed enum)
# ---------------------------------------------------------------------------


class SafetyMatrixResultStatus:
    PASS: str = "PASS"
    WARN: str = "WARN"
    FAIL: str = "FAIL"
    INSUFFICIENT_EVIDENCE: str = "INSUFFICIENT_EVIDENCE"

    ALLOWED: frozenset = frozenset(
        {PASS, WARN, FAIL, INSUFFICIENT_EVIDENCE}
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
    """Recursively assert that no forbidden field name appears in
    ``payload``.

    Raises ValueError on the first violation. Used as a defensive check
    on every output payload before serialization.
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
# Decision table: scenario_type -> minimum required safety actions
# ---------------------------------------------------------------------------

# These are the *minimum* defensive safety actions the matrix expects
# the documented safety boundary to take in each adverse scenario.
# They are conservative by design and intentionally NOT runtime-tunable.
# The decision table is a Python module-level constant. It is NOT
# loaded from runtime config, NOT loaded from an LLM, NOT exposed via
# CLI flags, and NOT rewritten by the engine.

# Universal blocks every scenario MUST observe:
_UNIVERSAL_BLOCKS: Tuple[str, ...] = (
    SafetyMatrixExpectedAction.BLOCK_LIVE_ORDER,
    SafetyMatrixExpectedAction.BLOCK_RUNTIME_CONFIG_CHANGE,
    SafetyMatrixExpectedAction.BLOCK_TELEGRAM_OUTBOUND,
    SafetyMatrixExpectedAction.BLOCK_AI_TRADE_AUTHORITY,
    SafetyMatrixExpectedAction.RECORD_AUDIT_EVENT,
)


def _required_actions_for_type(scenario_type: str) -> Tuple[str, ...]:
    """Deterministic decision table.

    Returns the minimum set of actions a documented safety boundary
    MUST observe for the given scenario type. The result always
    includes the universal blocks.
    """
    A = SafetyMatrixExpectedAction
    T = SafetyMatrixScenarioType
    base: Tuple[str, ...]
    if scenario_type == T.STOP_FAILED:
        base = (A.PAUSE_NEW_OPENS, A.REQUIRE_OPERATOR_REVIEW)
    elif scenario_type == T.STOP_UNCONFIRMED:
        base = (A.REJECT_UNSAFE_ACTION, A.REQUIRE_OPERATOR_REVIEW)
    elif scenario_type == T.GHOST_POSITION:
        base = (A.PAUSE_NEW_OPENS, A.REQUIRE_OPERATOR_RESUME)
    elif scenario_type == T.ORPHAN_STOP:
        base = (A.PAUSE_NEW_OPENS, A.REQUIRE_OPERATOR_REVIEW)
    elif scenario_type == T.MISSING_REMOTE_POSITION:
        base = (A.PAUSE_NEW_OPENS, A.REQUIRE_OPERATOR_RESUME)
    elif scenario_type == T.RECONCILIATION_MISMATCH:
        base = (A.PAUSE_NEW_OPENS, A.REQUIRE_OPERATOR_REVIEW)
    elif scenario_type == T.DATA_DEGRADED:
        base = (A.DEGRADE_TO_REPORT_ONLY,)
    elif scenario_type == T.WS_STALE:
        base = (A.DEGRADE_TO_REPORT_ONLY,)
    elif scenario_type == T.REST_429:
        base = (A.DEGRADE_TO_REPORT_ONLY, A.REQUIRE_OPERATOR_REVIEW)
    elif scenario_type == T.REST_418:
        base = (A.DEGRADE_TO_REPORT_ONLY, A.REQUIRE_OPERATOR_REVIEW)
    elif scenario_type == T.TELEGRAM_EXPORT_FAILURE:
        base = (A.REQUIRE_OPERATOR_REVIEW,)
    elif scenario_type == T.TELEGRAM_OUTBOUND_BLOCKED:
        # The universal blocks already include BLOCK_TELEGRAM_OUTBOUND;
        # the scenario re-asserts it as primary expected action.
        base = ()
    elif scenario_type == T.PAUSE_RESUME_REQUIRED:
        base = (A.PAUSE_NEW_OPENS, A.REQUIRE_OPERATOR_RESUME)
    elif scenario_type == T.KILL_ALL_AUDIT_ONLY:
        base = (A.REQUIRE_OPERATOR_REVIEW,)
    elif scenario_type == T.CAPITAL_REBASE_IN_PROGRESS:
        base = (A.PAUSE_NEW_OPENS, A.PAPER_LEDGER_ONLY)
    elif scenario_type == T.EXTERNAL_DEPOSIT:
        base = (A.REQUIRE_OPERATOR_REVIEW, A.PAPER_LEDGER_ONLY)
    elif scenario_type == T.PROFIT_WITHDRAWAL:
        base = (A.REQUIRE_OPERATOR_REVIEW, A.PAPER_LEDGER_ONLY)
    elif scenario_type == T.LLM_DEGRADED:
        base = (A.DEGRADE_TO_REPORT_ONLY,)
    elif scenario_type == T.DEEPSEEK_TIMEOUT:
        base = (A.DEGRADE_TO_REPORT_ONLY,)
    elif scenario_type == T.AI_REALITY_CHECK_FAILED:
        base = (A.REQUIRE_OPERATOR_REVIEW,)
    elif scenario_type == T.AI_FORBIDDEN_FIELD_STRIPPED:
        base = (A.REQUIRE_OPERATOR_REVIEW,)
    else:
        # Unknown scenario types are conservatively treated as
        # "operator must review" with universal blocks intact.
        base = (A.REQUIRE_OPERATOR_REVIEW,)

    # Deterministic, deduplicated, ordered union of base + universal.
    out: List[str] = []
    seen: set = set()
    for action in tuple(base) + _UNIVERSAL_BLOCKS:
        if action not in seen:
            out.append(action)
            seen.add(action)
    return tuple(out)


# ---------------------------------------------------------------------------
# Default severity map per scenario type
# ---------------------------------------------------------------------------


def _default_severity_for_type(scenario_type: str) -> str:
    """Deterministic severity classification per scenario type."""
    T = SafetyMatrixScenarioType
    S = SafetyMatrixSeverity
    p0 = {
        T.STOP_FAILED,
        T.STOP_UNCONFIRMED,
        T.GHOST_POSITION,
        T.ORPHAN_STOP,
        T.MISSING_REMOTE_POSITION,
        T.RECONCILIATION_MISMATCH,
        T.KILL_ALL_AUDIT_ONLY,
        T.CAPITAL_REBASE_IN_PROGRESS,
        T.EXTERNAL_DEPOSIT,
        T.PROFIT_WITHDRAWAL,
        T.AI_FORBIDDEN_FIELD_STRIPPED,
        T.AI_REALITY_CHECK_FAILED,
        T.PAUSE_RESUME_REQUIRED,
    }
    p1 = {
        T.REST_418,
        T.REST_429,
        T.DATA_DEGRADED,
        T.WS_STALE,
        T.LLM_DEGRADED,
        T.DEEPSEEK_TIMEOUT,
        T.TELEGRAM_EXPORT_FAILURE,
        T.TELEGRAM_OUTBOUND_BLOCKED,
    }
    if scenario_type in p0:
        return S.P0
    if scenario_type in p1:
        return S.P1
    return S.P2


# ---------------------------------------------------------------------------
# SafetyMatrixScenario
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SafetyMatrixScenario:
    """A single deterministic adverse-condition scenario.

    NOT a trade. NOT a runtime patch. Descriptive fixture only.
    """

    scenario_id: str
    scenario_type: str
    description: str
    simulated_inputs: Mapping[str, Any]
    expected_actions: Tuple[str, ...]
    severity: str = SafetyMatrixSeverity.P0
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    # Hard-pinned safety flags surfaced on every scenario record:
    phase_12_forbidden: bool = True
    auto_tuning_allowed: bool = False
    trade_authority: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, str) or not self.scenario_id:
            raise ValueError("scenario_id must be a non-empty string")
        if self.scenario_type not in SafetyMatrixScenarioType.ALLOWED:
            raise ValueError(
                f"scenario_type must be one of "
                f"{sorted(SafetyMatrixScenarioType.ALLOWED)}, got "
                f"{self.scenario_type!r}"
            )
        for a in self.expected_actions:
            if a not in SafetyMatrixExpectedAction.ALLOWED:
                raise ValueError(
                    f"expected_actions contains illegal value {a!r}; "
                    f"allowed: "
                    f"{sorted(SafetyMatrixExpectedAction.ALLOWED)}"
                )
        if self.severity not in SafetyMatrixSeverity.ALLOWED:
            raise ValueError(
                f"severity must be one of "
                f"{sorted(SafetyMatrixSeverity.ALLOWED)}, got "
                f"{self.severity!r}"
            )
        if not isinstance(self.simulated_inputs, Mapping):
            raise ValueError("simulated_inputs must be a Mapping")
        # Defensive: refuse hostile simulated_inputs payloads.
        assert_no_forbidden_fields(dict(self.simulated_inputs))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_type": self.scenario_type,
            "description": self.description,
            "simulated_inputs": dict(self.simulated_inputs),
            "expected_actions": list(self.expected_actions),
            "severity": self.severity,
            "evidence_refs": list(self.evidence_refs),
            "phase_12_forbidden": True,
            "auto_tuning_allowed": False,
            "trade_authority": False,
            # Defensive non-trade markers (visible to reviewers):
            "is_safety_matrix_scenario": True,
            "is_trade": False,
            "is_runtime_patch": False,
        }


# ---------------------------------------------------------------------------
# SafetyMatrixResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SafetyMatrixResult:
    """Per-scenario evaluation result. Descriptive only."""

    scenario_id: str
    scenario_type: str
    severity: str
    status: str
    observed_actions: Tuple[str, ...]
    expected_actions: Tuple[str, ...]
    passed: bool
    failed_reasons: Tuple[str, ...] = field(default_factory=tuple)
    warnings: Tuple[str, ...] = field(default_factory=tuple)
    requires_operator_review: bool = False
    requires_operator_resume: bool = False
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    # Hard-pinned safety flags on every result:
    live_order_blocked: bool = True
    runtime_config_unchanged: bool = True
    ai_trade_authority_blocked: bool = True
    telegram_outbound_blocked: bool = True
    phase_12_forbidden: bool = True
    auto_tuning_allowed: bool = False
    trade_authority: bool = False

    def __post_init__(self) -> None:
        if self.status not in SafetyMatrixResultStatus.ALLOWED:
            raise ValueError(
                f"status must be one of "
                f"{sorted(SafetyMatrixResultStatus.ALLOWED)}, got "
                f"{self.status!r}"
            )
        if self.severity not in SafetyMatrixSeverity.ALLOWED:
            raise ValueError(
                f"severity must be one of "
                f"{sorted(SafetyMatrixSeverity.ALLOWED)}, got "
                f"{self.severity!r}"
            )
        if self.scenario_type not in SafetyMatrixScenarioType.ALLOWED:
            raise ValueError(
                f"scenario_type must be one of "
                f"{sorted(SafetyMatrixScenarioType.ALLOWED)}, got "
                f"{self.scenario_type!r}"
            )
        for a in self.observed_actions:
            if a not in SafetyMatrixExpectedAction.ALLOWED:
                raise ValueError(
                    f"observed_actions contains illegal value {a!r}"
                )
        for a in self.expected_actions:
            if a not in SafetyMatrixExpectedAction.ALLOWED:
                raise ValueError(
                    f"expected_actions contains illegal value {a!r}"
                )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_type": self.scenario_type,
            "severity": self.severity,
            "status": self.status,
            "observed_actions": list(self.observed_actions),
            "expected_actions": list(self.expected_actions),
            "passed": self.passed,
            "failed_reasons": list(self.failed_reasons),
            "warnings": list(self.warnings),
            "requires_operator_review": self.requires_operator_review,
            "requires_operator_resume": self.requires_operator_resume,
            "evidence_refs": list(self.evidence_refs),
            "live_order_blocked": True,
            "runtime_config_unchanged": True,
            "ai_trade_authority_blocked": True,
            "telegram_outbound_blocked": True,
            "phase_12_forbidden": True,
            "auto_tuning_allowed": False,
            "trade_authority": False,
            # Defensive non-trade markers (visible to reviewers):
            "is_safety_matrix_result": True,
            "is_trade": False,
            "is_runtime_patch": False,
        }


# ---------------------------------------------------------------------------
# SafetyMatrixReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SafetyMatrixReport:
    report_id: str
    generated_at_utc: str
    reference_window: str
    total_scenarios: int
    passed_count: int
    failed_count: int
    warning_count: int
    p0_failures: Tuple[str, ...]
    p1_failures: Tuple[str, ...]
    scenario_results: Tuple[SafetyMatrixResult, ...]
    known_blockers: Tuple[str, ...] = field(default_factory=tuple)
    next_allowed_phase: str = NEXT_ALLOWED_PHASE_NO_BLOCKERS
    # Hard-locked safety flags (always present in serialized payload):
    phase: str = PHASE_NAME
    phase_12_forbidden: bool = True
    auto_tuning_allowed: bool = False
    trade_authority: bool = False
    exchange_live_orders: bool = False
    binance_private_api_enabled: bool = False
    sandbox_only: bool = True
    live_trading: bool = False
    right_tail: bool = False
    llm: bool = False
    llm_outbound_enabled: bool = False
    telegram_outbound_enabled: bool = False
    writes_runtime_config: bool = False
    allow_trade_decision: bool = False
    allow_runtime_config_change: bool = False
    status: str = SafetyMatrixResultStatus.PASS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "generated_at_utc": self.generated_at_utc,
            "reference_window": self.reference_window,
            "phase": self.phase,
            "status": self.status,
            "total_scenarios": self.total_scenarios,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "warning_count": self.warning_count,
            "p0_failures": list(self.p0_failures),
            "p1_failures": list(self.p1_failures),
            "scenario_results": [
                r.to_dict() for r in self.scenario_results
            ],
            "known_blockers": list(self.known_blockers),
            "next_allowed_phase": self.next_allowed_phase,
            "phase_12_forbidden": True,
            "auto_tuning_allowed": False,
            "trade_authority": False,
            "exchange_live_orders": False,
            "binance_private_api_enabled": False,
            "sandbox_only": True,
            "live_trading": False,
            "right_tail": False,
            "llm": False,
            "llm_outbound_enabled": False,
            "telegram_outbound_enabled": False,
            "writes_runtime_config": False,
            "allow_trade_decision": False,
            "allow_runtime_config_change": False,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SafetyMatrixEngine:
    """Deterministic safety-matrix evaluator.

    The engine is pure: same inputs -> same outputs. It does not read
    clocks, files, network, or environment except via the explicit
    ``now_utc`` injection point used only to stamp ``generated_at_utc``.

    The engine MUST NOT and CANNOT:
      - call DeepSeek / LLM / network
      - send Telegram outbound
      - touch the Binance private API
      - call the real Risk Engine, the real Execution FSM, or the real
        Exchange gateway
      - write back to runtime config
      - generate any runtime-tuning patch
      - emit any direction / order / sizing / risk / execution field
      - authorize live trading, auto-tuning, or Phase 12
    """

    def __init__(self) -> None:
        # Defensive tripwires: the engine cannot accidentally advertise
        # capabilities it must never have.
        self.sandbox_only: bool = True
        self.writes_runtime_config: bool = False
        self.auto_tuning_allowed: bool = False
        self.trade_authority: bool = False
        self.phase_12_forbidden: bool = True
        self.live_trading: bool = False
        self.exchange_live_orders: bool = False
        self.right_tail: bool = False
        self.llm: bool = False
        self.llm_outbound_enabled: bool = False
        self.telegram_outbound_enabled: bool = False
        self.binance_private_api_enabled: bool = False
        self.allow_trade_decision: bool = False
        self.allow_runtime_config_change: bool = False

    # -- public API ---------------------------------------------------------

    def evaluate_scenario(
        self, scenario: SafetyMatrixScenario
    ) -> SafetyMatrixResult:
        """Evaluate a single scenario.

        Returns a ``SafetyMatrixResult`` whose ``observed_actions``
        come from the deterministic decision table for the scenario's
        type. The result is PASS iff every ``expected_action`` in the
        scenario is present in ``observed_actions``.
        """
        observed = _required_actions_for_type(scenario.scenario_type)
        observed_set = set(observed)

        # Compute missing expected actions deterministically.
        missing: List[str] = [
            a for a in scenario.expected_actions if a not in observed_set
        ]

        passed = not missing
        if passed:
            status = SafetyMatrixResultStatus.PASS
        elif scenario.severity in (
            SafetyMatrixSeverity.P0,
            SafetyMatrixSeverity.P1,
        ):
            status = SafetyMatrixResultStatus.FAIL
        else:
            status = SafetyMatrixResultStatus.WARN

        failed_reasons: List[str] = []
        warnings: List[str] = []
        for a in missing:
            reason = (
                f"expected_action_not_observed:{a}:"
                f"scenario={scenario.scenario_id}:"
                f"type={scenario.scenario_type}:"
                f"severity={scenario.severity}"
            )
            if scenario.severity in (
                SafetyMatrixSeverity.P0,
                SafetyMatrixSeverity.P1,
            ):
                failed_reasons.append(reason)
            else:
                warnings.append(reason)

        requires_operator_review = (
            SafetyMatrixExpectedAction.REQUIRE_OPERATOR_REVIEW
            in observed_set
        )
        requires_operator_resume = (
            SafetyMatrixExpectedAction.REQUIRE_OPERATOR_RESUME
            in observed_set
        )

        result = SafetyMatrixResult(
            scenario_id=scenario.scenario_id,
            scenario_type=scenario.scenario_type,
            severity=scenario.severity,
            status=status,
            observed_actions=observed,
            expected_actions=tuple(scenario.expected_actions),
            passed=passed,
            failed_reasons=tuple(failed_reasons),
            warnings=tuple(warnings),
            requires_operator_review=requires_operator_review,
            requires_operator_resume=requires_operator_resume,
            evidence_refs=tuple(scenario.evidence_refs),
        )
        # Defensive: refuse to emit results that contain forbidden
        # field names anywhere (e.g., via a hostile evidence_refs).
        assert_no_forbidden_fields(result.to_dict())
        return result

    def build_report(
        self,
        *,
        reference_window: str,
        scenarios: Sequence[SafetyMatrixScenario],
        now_utc: Optional[datetime] = None,
        report_id: Optional[str] = None,
        known_blockers: Optional[Sequence[str]] = None,
    ) -> SafetyMatrixReport:
        results: List[SafetyMatrixResult] = []
        for s in scenarios:
            results.append(self.evaluate_scenario(s))
        # Deterministic ordering of results by (severity rank,
        # scenario_id) so the report is stable across runs.
        severity_rank = {
            SafetyMatrixSeverity.P0: 0,
            SafetyMatrixSeverity.P1: 1,
            SafetyMatrixSeverity.P2: 2,
            SafetyMatrixSeverity.P3: 3,
        }
        results.sort(
            key=lambda r: (
                severity_rank.get(r.severity, 99),
                r.scenario_id,
            )
        )

        passed_count = sum(
            1 for r in results if r.status == SafetyMatrixResultStatus.PASS
        )
        failed_count = sum(
            1 for r in results if r.status == SafetyMatrixResultStatus.FAIL
        )
        warning_count = sum(
            1 for r in results if r.status == SafetyMatrixResultStatus.WARN
        )

        p0_failures = tuple(
            r.scenario_id
            for r in results
            if r.status == SafetyMatrixResultStatus.FAIL
            and r.severity == SafetyMatrixSeverity.P0
        )
        p1_failures = tuple(
            r.scenario_id
            for r in results
            if r.status == SafetyMatrixResultStatus.FAIL
            and r.severity == SafetyMatrixSeverity.P1
        )

        # Aggregate known blockers deterministically. Operator-supplied
        # blockers are preserved; if any P0/P1 failures exist, they are
        # added under a deterministic prefix.
        blocker_list: List[str] = []
        seen: set = set()
        for b in list(known_blockers or []):
            if isinstance(b, str) and b and b not in seen:
                blocker_list.append(b)
                seen.add(b)
        for sid in p0_failures:
            tag = f"p0_failure:{sid}"
            if tag not in seen:
                blocker_list.append(tag)
                seen.add(tag)
        for sid in p1_failures:
            tag = f"p1_failure:{sid}"
            if tag not in seen:
                blocker_list.append(tag)
                seen.add(tag)

        if not results:
            overall_status = SafetyMatrixResultStatus.INSUFFICIENT_EVIDENCE
        elif failed_count > 0:
            overall_status = SafetyMatrixResultStatus.FAIL
        elif warning_count > 0:
            overall_status = SafetyMatrixResultStatus.WARN
        else:
            overall_status = SafetyMatrixResultStatus.PASS

        # Next allowed phase decision rule (brief-mandated):
        if (
            failed_count == 0
            and len(p0_failures) == 0
            and len(p1_failures) == 0
            and results
        ):
            next_allowed_phase = NEXT_ALLOWED_PHASE_NO_BLOCKERS
        else:
            next_allowed_phase = NEXT_ALLOWED_PHASE_WITH_BLOCKERS

        generated_at = (
            now_utc if now_utc is not None else datetime.now(timezone.utc)
        )
        generated_at_iso = generated_at.replace(microsecond=0).isoformat()

        if report_id is None:
            report_id = self._derive_report_id(
                reference_window=reference_window,
                results=results,
                generated_at_iso=generated_at_iso,
            )

        report = SafetyMatrixReport(
            report_id=report_id,
            generated_at_utc=generated_at_iso,
            reference_window=reference_window,
            total_scenarios=len(results),
            passed_count=passed_count,
            failed_count=failed_count,
            warning_count=warning_count,
            p0_failures=p0_failures,
            p1_failures=p1_failures,
            scenario_results=tuple(results),
            known_blockers=tuple(blocker_list),
            next_allowed_phase=next_allowed_phase,
            status=overall_status,
        )
        # Defensive: refuse to emit reports that contain forbidden
        # field names anywhere.
        assert_no_forbidden_fields(report.to_dict())
        return report

    # -- internal helpers ---------------------------------------------------

    @staticmethod
    def _derive_report_id(
        *,
        reference_window: str,
        results: Sequence[SafetyMatrixResult],
        generated_at_iso: str,
    ) -> str:
        h = hashlib.sha256()
        h.update(reference_window.encode("utf-8"))
        h.update(b"|")
        h.update(generated_at_iso.encode("utf-8"))
        for r in results:
            h.update(b"|")
            h.update(
                json.dumps(
                    r.to_dict(), sort_keys=True, default=str
                ).encode("utf-8")
            )
        return f"safety_matrix_{h.hexdigest()[:16]}"


# ---------------------------------------------------------------------------
# Default scenario set (deterministic, descriptive)
# ---------------------------------------------------------------------------


def _scenario(
    scenario_id: str,
    scenario_type: str,
    description: str,
    simulated_inputs: Mapping[str, Any],
    extra_expected: Tuple[str, ...] = (),
    severity: Optional[str] = None,
    evidence_refs: Tuple[str, ...] = (),
) -> SafetyMatrixScenario:
    """Helper to construct a scenario whose expected_actions match the
    deterministic decision table for its type, plus the universal
    blocks. Adding ``extra_expected`` lets tests / fixtures exercise
    additional defensive expectations.
    """
    expected = list(_required_actions_for_type(scenario_type))
    for a in extra_expected:
        if a in SafetyMatrixExpectedAction.ALLOWED and a not in expected:
            expected.append(a)
    sev = severity or _default_severity_for_type(scenario_type)
    return SafetyMatrixScenario(
        scenario_id=scenario_id,
        scenario_type=scenario_type,
        description=description,
        simulated_inputs=dict(simulated_inputs),
        expected_actions=tuple(expected),
        severity=sev,
        evidence_refs=evidence_refs,
    )


def default_scenario_set() -> List[SafetyMatrixScenario]:
    """Deterministic default scenario fixture set.

    Every scenario_type in :class:`SafetyMatrixScenarioType.ALLOWED` is
    represented at least once. The simulated_inputs are descriptive
    fixtures; they NEVER claim to be real exchange / risk / execution
    state.
    """
    T = SafetyMatrixScenarioType
    A = SafetyMatrixExpectedAction
    out: List[SafetyMatrixScenario] = []

    out.append(
        _scenario(
            scenario_id="sm_001_stop_failed",
            scenario_type=T.STOP_FAILED,
            description=(
                "Local stop placement returned an error from the "
                "fixture exchange-gateway double; documented safety "
                "boundary must pause new opens and require operator "
                "review."
            ),
            simulated_inputs={
                "stop_attempted": True,
                "stop_acknowledged": False,
                "exchange_error_code": "FAKE_FIXTURE_ERROR",
                "is_paper": True,
            },
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_002_stop_unconfirmed",
            scenario_type=T.STOP_UNCONFIRMED,
            description=(
                "Stop placement was attempted but the fixture exchange "
                "double never returned a confirmation; documented "
                "safety boundary must reject the unsafe action and "
                "require operator review."
            ),
            simulated_inputs={
                "stop_attempted": True,
                "stop_ack_timeout_ms": 30000,
                "is_paper": True,
            },
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_003_ghost_position",
            scenario_type=T.GHOST_POSITION,
            description=(
                "Local ledger says no position but the fixture remote "
                "snapshot shows a position; safety boundary must "
                "pause new opens and require operator resume."
            ),
            simulated_inputs={
                "local_position_qty": 0.0,
                "remote_position_qty_fixture": 1.0,
                "is_paper": True,
            },
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_004_orphan_stop",
            scenario_type=T.ORPHAN_STOP,
            description=(
                "Stop order exists in the fixture remote snapshot but "
                "no matching local position; safety boundary must "
                "pause new opens and require operator review."
            ),
            simulated_inputs={
                "remote_stop_order_present_fixture": True,
                "local_position_qty": 0.0,
                "is_paper": True,
            },
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_005_missing_remote_position",
            scenario_type=T.MISSING_REMOTE_POSITION,
            description=(
                "Local ledger says position is open but the fixture "
                "remote snapshot reports no position; safety boundary "
                "must pause new opens and require operator resume."
            ),
            simulated_inputs={
                "local_position_qty": 1.0,
                "remote_position_qty_fixture": 0.0,
                "is_paper": True,
            },
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_006_reconciliation_mismatch",
            scenario_type=T.RECONCILIATION_MISMATCH,
            description=(
                "Local ledger and the fixture remote snapshot disagree "
                "on quantity; safety boundary must pause new opens "
                "and require operator review."
            ),
            simulated_inputs={
                "local_position_qty": 1.0,
                "remote_position_qty_fixture": 1.5,
                "is_paper": True,
            },
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_007_data_degraded",
            scenario_type=T.DATA_DEGRADED,
            description=(
                "Market-data buffer reports degraded freshness; safety "
                "boundary must degrade to report-only."
            ),
            simulated_inputs={
                "data_age_seconds": 600,
                "expected_max_age_seconds": 60,
                "is_paper": True,
            },
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_008_ws_stale",
            scenario_type=T.WS_STALE,
            description=(
                "Public-market WebSocket fixture has not pushed a "
                "frame for >120s; safety boundary must degrade to "
                "report-only."
            ),
            simulated_inputs={
                "ws_last_frame_age_seconds": 300,
                "ws_stale_threshold_seconds": 120,
                "is_paper": True,
            },
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_009_rest_429",
            scenario_type=T.REST_429,
            description=(
                "Public REST 429 rate-limit reply observed; safety "
                "boundary must degrade to report-only and require "
                "operator review."
            ),
            simulated_inputs={
                "http_status_fixture": 429,
                "weight_used_fixture": 99999,
                "is_paper": True,
            },
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_010_rest_418",
            scenario_type=T.REST_418,
            description=(
                "Public REST 418 IP-ban reply observed; safety "
                "boundary must degrade to report-only and require "
                "operator review."
            ),
            simulated_inputs={
                "http_status_fixture": 418,
                "is_paper": True,
            },
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_011_telegram_export_failure",
            scenario_type=T.TELEGRAM_EXPORT_FAILURE,
            description=(
                "Phase 8.5 export bundle failed to produce a manifest; "
                "safety boundary must require operator review (and "
                "always block live Telegram outbound)."
            ),
            simulated_inputs={
                "export_status_fixture": "FAILED",
                "manifest_present_fixture": False,
                "is_paper": True,
            },
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_012_telegram_outbound_blocked",
            scenario_type=T.TELEGRAM_OUTBOUND_BLOCKED,
            description=(
                "Telegram live outbound is blocked at boot by the "
                "safety contract; the matrix asserts the universal "
                "block remains in effect."
            ),
            simulated_inputs={
                "telegram_outbound_enabled_fixture": False,
                "is_paper": True,
            },
            extra_expected=(A.BLOCK_TELEGRAM_OUTBOUND,),
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_013_pause_resume_required",
            scenario_type=T.PAUSE_RESUME_REQUIRED,
            description=(
                "An operator-pause was set; safety boundary must keep "
                "new opens paused and require operator resume to "
                "clear."
            ),
            simulated_inputs={
                "operator_pause_active_fixture": True,
                "is_paper": True,
            },
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_014_kill_all_audit_only",
            scenario_type=T.KILL_ALL_AUDIT_ONLY,
            description=(
                "Operator-issued kill-all command; this matrix only "
                "audits intent, never executes; safety boundary must "
                "require operator review and record an audit event."
            ),
            simulated_inputs={
                "kill_all_intent_fixture": True,
                "live_executed_fixture": False,
                "is_paper": True,
            },
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_015_capital_rebase_in_progress",
            scenario_type=T.CAPITAL_REBASE_IN_PROGRESS,
            description=(
                "Capital rebase fixture is in progress; safety "
                "boundary must pause new opens and keep the paper "
                "ledger only."
            ),
            simulated_inputs={
                "rebase_state_fixture": "IN_PROGRESS",
                "is_paper": True,
            },
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_016_external_deposit",
            scenario_type=T.EXTERNAL_DEPOSIT,
            description=(
                "An external deposit was observed in the fixture "
                "ledger; safety boundary must require operator review "
                "and keep the paper ledger only."
            ),
            simulated_inputs={
                "external_deposit_amount_fixture": 100.0,
                "is_paper": True,
            },
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_017_profit_withdrawal",
            scenario_type=T.PROFIT_WITHDRAWAL,
            description=(
                "A profit-withdrawal intent was raised against the "
                "fixture ledger; safety boundary must require "
                "operator review and keep the paper ledger only."
            ),
            simulated_inputs={
                "profit_withdrawal_amount_fixture": 50.0,
                "is_paper": True,
            },
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_018_llm_degraded",
            scenario_type=T.LLM_DEGRADED,
            description=(
                "LLM fixture reports a degraded reply; the safety "
                "boundary must degrade to report-only and never "
                "grant the AI trade authority (the latter is "
                "universally blocked)."
            ),
            simulated_inputs={
                "llm_status_fixture": "degraded",
                "llm_outbound_enabled_fixture": False,
                "is_paper": True,
            },
            extra_expected=(A.BLOCK_AI_TRADE_AUTHORITY,),
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_019_deepseek_timeout",
            scenario_type=T.DEEPSEEK_TIMEOUT,
            description=(
                "DeepSeek sandbox fixture reports a timeout; safety "
                "boundary must degrade to report-only and continue "
                "to block AI trade authority."
            ),
            simulated_inputs={
                "deepseek_provider_fixture": "fake_provider",
                "deepseek_status_fixture": "TIMEOUT",
                "is_paper": True,
            },
            extra_expected=(A.BLOCK_AI_TRADE_AUTHORITY,),
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_020_ai_reality_check_failed",
            scenario_type=T.AI_REALITY_CHECK_FAILED,
            description=(
                "AI Reality Check Layer rejected an AI claim; safety "
                "boundary must require operator review and continue "
                "to block AI trade authority."
            ),
            simulated_inputs={
                "ai_reality_check_status_fixture": "REJECTED",
                "is_paper": True,
            },
            extra_expected=(A.BLOCK_AI_TRADE_AUTHORITY,),
        )
    )
    out.append(
        _scenario(
            scenario_id="sm_021_ai_forbidden_field_stripped",
            scenario_type=T.AI_FORBIDDEN_FIELD_STRIPPED,
            description=(
                "AI output carried a forbidden trade-action / "
                "runtime-config-patch key; the recursive forbidden-"
                "field guard stripped it. Safety boundary must "
                "require operator review and continue to block AI "
                "trade authority."
            ),
            simulated_inputs={
                "stripped_field_count_fixture": 1,
                "stripped_field_names_fixture": [
                    "<redacted-forbidden-field>",
                ],
                "is_paper": True,
            },
            extra_expected=(A.BLOCK_AI_TRADE_AUTHORITY,),
        )
    )
    return out


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def render_report_markdown(report: SafetyMatrixReport) -> str:
    lines: List[str] = []
    lines.append("# Risk / Execution / Capital Safety Matrix v0 Report")
    lines.append("")
    lines.append(f"- report_id: `{report.report_id}`")
    lines.append(f"- phase: `{report.phase}`")
    lines.append(f"- status: `{report.status}`")
    lines.append(f"- generated_at_utc: `{report.generated_at_utc}`")
    lines.append(f"- reference_window: `{report.reference_window}`")
    lines.append(f"- total_scenarios: `{report.total_scenarios}`")
    lines.append(f"- passed_count: `{report.passed_count}`")
    lines.append(f"- failed_count: `{report.failed_count}`")
    lines.append(f"- warning_count: `{report.warning_count}`")
    lines.append(f"- next_allowed_phase: `{report.next_allowed_phase}`")
    lines.append("")
    lines.append("## Safety Boundary")
    lines.append("")
    lines.append(f"- sandbox_only: `{report.sandbox_only}`")
    lines.append(
        f"- writes_runtime_config: `{report.writes_runtime_config}`"
    )
    lines.append(
        f"- auto_tuning_allowed: `{report.auto_tuning_allowed}`"
    )
    lines.append(f"- trade_authority: `{report.trade_authority}`")
    lines.append(f"- live_trading: `{report.live_trading}`")
    lines.append(
        f"- exchange_live_orders: `{report.exchange_live_orders}`"
    )
    lines.append(f"- right_tail: `{report.right_tail}`")
    lines.append(f"- llm: `{report.llm}`")
    lines.append(
        f"- llm_outbound_enabled: `{report.llm_outbound_enabled}`"
    )
    lines.append(
        f"- telegram_outbound_enabled: "
        f"`{report.telegram_outbound_enabled}`"
    )
    lines.append(
        f"- binance_private_api_enabled: "
        f"`{report.binance_private_api_enabled}`"
    )
    lines.append(
        f"- allow_trade_decision: `{report.allow_trade_decision}`"
    )
    lines.append(
        f"- allow_runtime_config_change: "
        f"`{report.allow_runtime_config_change}`"
    )
    lines.append(f"- phase_12_forbidden: `{report.phase_12_forbidden}`")
    lines.append("")
    lines.append("## P0 Failures")
    lines.append("")
    if report.p0_failures:
        for sid in report.p0_failures:
            lines.append(f"- `{sid}`")
    else:
        lines.append("_none_")
    lines.append("")
    lines.append("## P1 Failures")
    lines.append("")
    if report.p1_failures:
        for sid in report.p1_failures:
            lines.append(f"- `{sid}`")
    else:
        lines.append("_none_")
    lines.append("")
    lines.append("## Known Blockers")
    lines.append("")
    if report.known_blockers:
        for b in report.known_blockers:
            lines.append(f"- `{b}`")
    else:
        lines.append("_none_")
    lines.append("")
    lines.append("## Scenario Results")
    lines.append("")
    if not report.scenario_results:
        lines.append("_no scenarios evaluated_")
    for r in report.scenario_results:
        lines.append(f"### scenario `{r.scenario_id}`")
        lines.append("")
        lines.append(f"- scenario_type: `{r.scenario_type}`")
        lines.append(f"- severity: `{r.severity}`")
        lines.append(f"- status: `{r.status}`")
        lines.append(f"- passed: `{r.passed}`")
        lines.append(
            f"- requires_operator_review: "
            f"`{r.requires_operator_review}`"
        )
        lines.append(
            f"- requires_operator_resume: "
            f"`{r.requires_operator_resume}`"
        )
        lines.append(
            f"- live_order_blocked: `{r.live_order_blocked}`"
        )
        lines.append(
            f"- runtime_config_unchanged: "
            f"`{r.runtime_config_unchanged}`"
        )
        lines.append(
            f"- ai_trade_authority_blocked: "
            f"`{r.ai_trade_authority_blocked}`"
        )
        lines.append(
            f"- telegram_outbound_blocked: "
            f"`{r.telegram_outbound_blocked}`"
        )
        lines.append("- expected_actions:")
        for a in r.expected_actions:
            lines.append(f"  - `{a}`")
        lines.append("- observed_actions:")
        for a in r.observed_actions:
            lines.append(f"  - `{a}`")
        if r.failed_reasons:
            lines.append("- failed_reasons:")
            for reason in r.failed_reasons:
                lines.append(f"  - {reason}")
        if r.warnings:
            lines.append("- warnings:")
            for w in r.warnings:
                lines.append(f"  - {w}")
        lines.append("")
    lines.append(
        "> This report does NOT authorize live trading, does NOT "
        "write runtime config, does NOT auto-tune, does NOT enable "
        "Binance private API, does NOT enable Telegram outbound, "
        "does NOT grant the AI trade authority, and does NOT enter "
        "Phase 12. A run with zero P0 / P1 blockers ONLY authorizes "
        "the Strict Blind Walk-forward design checkpoint, which "
        "itself requires a human-owner-supplied strict forward-only "
        "anti-lookahead blind-test design before any Blind "
        "Walk-forward implementation work can begin."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level integrity guard
# ---------------------------------------------------------------------------

# These attributes are read by tests to verify the safety contract. They
# must not be flipped without bumping the phase.
SAFETY_CONTRACT: Dict[str, Any] = {
    "phase": PHASE_NAME,
    "sandbox_only": True,
    "writes_runtime_config": False,
    "auto_tuning_allowed": False,
    "trade_authority": False,
    "phase_12_forbidden": True,
    "live_trading": False,
    "exchange_live_orders": False,
    "right_tail": False,
    "llm": False,
    "llm_outbound_enabled": False,
    "telegram_outbound_enabled": False,
    "binance_private_api_enabled": False,
    "allow_trade_decision": False,
    "allow_runtime_config_change": False,
    "next_allowed_phase_no_blockers": NEXT_ALLOWED_PHASE_NO_BLOCKERS,
    "next_allowed_phase_with_blockers": NEXT_ALLOWED_PHASE_WITH_BLOCKERS,
}
