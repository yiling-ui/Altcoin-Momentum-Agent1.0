"""Paper Shadow package for AMA-RT V1.4.

This package contains strictly paper-only / report-only / evidence-only
modules used to validate discovery patterns, sandbox candidate scenarios,
and regime-cluster cohorts on historical evidence WITHOUT placing any
real or paper trade.

Hard safety boundaries (Phase 11C.1D-B):
  - sandbox_only = True
  - writes_runtime_config = False
  - auto_tuning_allowed = False
  - trade_authority = False
  - live_trading = False
  - exchange_live_orders = False
  - right_tail = False
  - llm = False
  - llm_outbound_enabled = False
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
    strategy_parameter_patch
  - authorize live trading or hot-path execution
  - enter Phase 12

A "paper shadow validation" run is a *retrospective, descriptive*
roll-up of historical evidence into cohort-level metrics. It is never
applied anywhere outside of the in-memory evaluation and the JSON /
Markdown report on disk.
"""

from app.paper_shadow.strategy_validation import (
    FORBIDDEN_OUTPUT_FIELDS,
    NEXT_ALLOWED_PHASE,
    PHASE_NAME,
    SAFETY_CONTRACT,
    PaperShadowCohortEvaluation,
    PaperShadowCohortKey,
    PaperShadowEvent,
    PaperShadowSample,
    PaperShadowStrategyValidationEngine,
    PaperShadowStrategyValidationReport,
    PaperShadowValidationStatus,
    RecommendationLevel,
    assert_no_forbidden_fields,
    build_samples_from_reports,
    example_fixture_samples,
    render_report_markdown,
)

__all__ = [
    "FORBIDDEN_OUTPUT_FIELDS",
    "NEXT_ALLOWED_PHASE",
    "PHASE_NAME",
    "SAFETY_CONTRACT",
    "PaperShadowCohortEvaluation",
    "PaperShadowCohortKey",
    "PaperShadowEvent",
    "PaperShadowSample",
    "PaperShadowStrategyValidationEngine",
    "PaperShadowStrategyValidationReport",
    "PaperShadowValidationStatus",
    "RecommendationLevel",
    "assert_no_forbidden_fields",
    "build_samples_from_reports",
    "example_fixture_samples",
    "render_report_markdown",
]
