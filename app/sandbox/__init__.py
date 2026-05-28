"""Offline sandbox package for AMA-RT V1.4.

This package contains strictly offline, deterministic, sandbox-only modules.

Hard safety boundaries:
  - sandbox_only = True
  - writes_runtime_config = False
  - auto_tuning_allowed = False
  - trade_authority = False
  - phase_12_forbidden = True
  - No imports of app.risk / app.execution / app.exchanges / app.telegram / app.config
  - No LLM / DeepSeek / network calls
"""

from app.sandbox.offline_rule_sandbox import (
    FORBIDDEN_OUTPUT_FIELDS,
    HypotheticalRuleChange,
    OfflineRuleSandboxEngine,
    OfflineRuleSandboxInput,
    OfflineRuleSandboxReport,
    OfflineRuleSandboxResult,
    OfflineRuleSandboxScenario,
    RecommendationLevel,
    SandboxEvent,
    SandboxStatus,
)

__all__ = [
    "FORBIDDEN_OUTPUT_FIELDS",
    "HypotheticalRuleChange",
    "OfflineRuleSandboxEngine",
    "OfflineRuleSandboxInput",
    "OfflineRuleSandboxReport",
    "OfflineRuleSandboxResult",
    "OfflineRuleSandboxScenario",
    "RecommendationLevel",
    "SandboxEvent",
    "SandboxStatus",
]
