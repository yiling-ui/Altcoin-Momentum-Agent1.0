"""Phase 11C - Offline Rule Sandbox Replay v0 package.

This package houses the AMA-RT *offline rule sandbox* - a paper /
report / evidence-only layer that lets an operator explore the
likely impact of a hypothetical rule change on **discovery
quality** without changing the runtime configuration, without
authorising live trading, without auto-tuning, and without
opening Phase 12.

The package re-exports the public surface of
:mod:`app.sandbox.offline_rule_sandbox`. Importing from this
package MUST NOT pull in :mod:`app.risk`, :mod:`app.execution`,
:mod:`app.exchanges`, :mod:`app.telegram`, :mod:`app.config`, any
LLM / DeepSeek transport, or any HTTP / WebSocket / network
library. The Risk Engine remains the single trade-decision gate.
Phase 12 remains FORBIDDEN.
"""

from app.sandbox.offline_rule_sandbox import (
    FORBIDDEN_SANDBOX_PAYLOAD_KEYS,
    HypotheticalRuleChange,
    OfflineRuleSandboxEngine,
    OfflineRuleSandboxInput,
    OfflineRuleSandboxReport,
    OfflineRuleSandboxResult,
    OfflineRuleSandboxScenario,
    RECOMMENDATION_LEVELS,
    SANDBOX_EVENT_REPORT_GENERATED,
    SANDBOX_EVENT_REPLAY_RUN,
    SANDBOX_EVENT_SCENARIO_EVALUATED,
    SANDBOX_REPORT_SCHEMA_VERSION,
    SANDBOX_RESULT_SCHEMA_VERSION,
    SANDBOX_SCENARIO_SCHEMA_VERSION,
    SANDBOX_SOURCE_PHASE,
    build_example_scenario,
    safety_flags_dict,
)

__all__ = [
    "FORBIDDEN_SANDBOX_PAYLOAD_KEYS",
    "HypotheticalRuleChange",
    "OfflineRuleSandboxEngine",
    "OfflineRuleSandboxInput",
    "OfflineRuleSandboxReport",
    "OfflineRuleSandboxResult",
    "OfflineRuleSandboxScenario",
    "RECOMMENDATION_LEVELS",
    "SANDBOX_EVENT_REPORT_GENERATED",
    "SANDBOX_EVENT_REPLAY_RUN",
    "SANDBOX_EVENT_SCENARIO_EVALUATED",
    "SANDBOX_REPORT_SCHEMA_VERSION",
    "SANDBOX_RESULT_SCHEMA_VERSION",
    "SANDBOX_SCENARIO_SCHEMA_VERSION",
    "SANDBOX_SOURCE_PHASE",
    "build_example_scenario",
    "safety_flags_dict",
]
