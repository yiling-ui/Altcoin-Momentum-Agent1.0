"""Safety package for AMA-RT V1.4.

This package contains strictly paper / report / evidence-only safety
verification modules. Nothing in this package places an order, sends a
real Telegram message, calls a private exchange API, or modifies the
runtime config.

Hard safety boundaries (Phase 11C.1D-C / Risk / Execution / Capital
Safety Matrix v0):
  - mode = paper
  - sandbox_only = True
  - live_trading = False
  - exchange_live_orders = False
  - right_tail = False
  - llm = False
  - llm_outbound_enabled = False
  - allow_trade_decision = False
  - allow_runtime_config_change = False
  - auto_tuning_allowed = False
  - trade_authority = False
  - telegram_outbound_enabled = False
  - binance_private_api_enabled = False
  - phase_12_forbidden = True

This package MUST NOT:
  - import app.risk / app.execution / app.exchanges / app.telegram /
    app.config
  - call DeepSeek / LLM / Telegram / Binance private API / network
  - write back to runtime config
  - emit buy / sell / long / short / direction / entry / exit /
    position_size / leverage / stop / target / risk_budget
  - emit runtime_config_patch / threshold_patch / symbol_limit_patch /
    candidate_pool_patch / regime_weight_patch /
    strategy_parameter_patch / signal_to_trade / should_buy /
    should_short / apply_change / deploy_change / enable_live /
    live_ready / trading_approved
  - authorize live trading or hot-path execution
  - enter Phase 12

A "safety matrix" run is a *deterministic, descriptive verification* of
the system's documented safety boundaries against a fixed set of
adverse scenarios. It is never wired into a hot path. It never produces
an order. It never produces a runtime tuning patch. It never authorizes
Phase 12.
"""

from app.safety.risk_execution_capital_matrix import (
    FORBIDDEN_OUTPUT_FIELDS,
    NEXT_ALLOWED_PHASE_NO_BLOCKERS,
    NEXT_ALLOWED_PHASE_WITH_BLOCKERS,
    PHASE_NAME,
    SAFETY_CONTRACT,
    SafetyMatrixEngine,
    SafetyMatrixEvent,
    SafetyMatrixExpectedAction,
    SafetyMatrixReport,
    SafetyMatrixResult,
    SafetyMatrixResultStatus,
    SafetyMatrixScenario,
    SafetyMatrixScenarioType,
    SafetyMatrixSeverity,
    assert_no_forbidden_fields,
    default_scenario_set,
    render_report_markdown,
)

__all__ = [
    "FORBIDDEN_OUTPUT_FIELDS",
    "NEXT_ALLOWED_PHASE_NO_BLOCKERS",
    "NEXT_ALLOWED_PHASE_WITH_BLOCKERS",
    "PHASE_NAME",
    "SAFETY_CONTRACT",
    "SafetyMatrixEngine",
    "SafetyMatrixEvent",
    "SafetyMatrixExpectedAction",
    "SafetyMatrixReport",
    "SafetyMatrixResult",
    "SafetyMatrixResultStatus",
    "SafetyMatrixScenario",
    "SafetyMatrixScenarioType",
    "SafetyMatrixSeverity",
    "assert_no_forbidden_fields",
    "default_scenario_set",
    "render_report_markdown",
]
