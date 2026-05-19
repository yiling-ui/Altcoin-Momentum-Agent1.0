"""ConfigVersions contract (Phase 8.5).

A ``ConfigVersions`` value object pins the *governing config version*
for every event payload that may be replayed by future phases. The
six identifiers covered here are the Issue-mandated set:

  - strategy_version
  - risk_config_version
  - scoring_version
  - capital_state_version
  - state_machine_version
  - llm_prompt_version

Phase 8.5 ships sensible defaults pegged to the current code version
(``v1.4.0a8.5``). Future phases can override per-event by passing
their own ``ConfigVersions``.

Phase 8.5 boundary
------------------

This object is a frozen value object. Nothing in this module reads
``os.environ``, opens a socket, imports an exchange SDK, calls an
LLM, or mutates any global state. ``ConfigVersions`` is **NOT** an
LLM prompt template; the ``llm_prompt_version`` field merely
*records* the version label so Reflection (Issue #10) can detect
when a prompt change correlates with a behavioural shift.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Phase 8.5 default version labels. These intentionally match the
# project's current code version so the Reflection engine has a
# single anchor to start from. Future phases bump them per-config.
DEFAULT_STRATEGY_VERSION = "v1.4.0a8.5"
DEFAULT_RISK_CONFIG_VERSION = "v1.4.0a8.5"
DEFAULT_SCORING_VERSION = "v1.4.0a8.5"
DEFAULT_CAPITAL_STATE_VERSION = "v1.4.0a8.5"
DEFAULT_STATE_MACHINE_VERSION = "v1.4.0a8.5"
# llm_prompt_version is "n/a" by default because Phase 8.5 forbids
# any LLM trade involvement (Spec rule 7). Issue #10 will replace
# this with a real prompt version label.
DEFAULT_LLM_PROMPT_VERSION = "n/a"


class ConfigVersions(BaseModel):
    """Pin every governing config version for one event payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_version: str = Field(default=DEFAULT_STRATEGY_VERSION)
    risk_config_version: str = Field(default=DEFAULT_RISK_CONFIG_VERSION)
    scoring_version: str = Field(default=DEFAULT_SCORING_VERSION)
    capital_state_version: str = Field(default=DEFAULT_CAPITAL_STATE_VERSION)
    state_machine_version: str = Field(default=DEFAULT_STATE_MACHINE_VERSION)
    llm_prompt_version: str = Field(default=DEFAULT_LLM_PROMPT_VERSION)

    @classmethod
    def defaults(cls) -> "ConfigVersions":
        """Return the Phase 8.5 default versions."""
        return cls()

    def to_payload(self) -> dict[str, Any]:
        return config_versions_to_payload(self)


def config_versions_to_payload(versions: ConfigVersions) -> dict[str, Any]:
    """Return a JSON-safe dict suitable for event payloads."""
    return {
        "strategy_version": str(versions.strategy_version),
        "risk_config_version": str(versions.risk_config_version),
        "scoring_version": str(versions.scoring_version),
        "capital_state_version": str(versions.capital_state_version),
        "state_machine_version": str(versions.state_machine_version),
        "llm_prompt_version": str(versions.llm_prompt_version),
    }


def payload_to_config_versions(payload: dict[str, Any]) -> ConfigVersions:
    """Inverse of :func:`config_versions_to_payload`. Missing fields
    fall back to the Phase 8.5 defaults so legacy payloads can replay.
    """
    return ConfigVersions(
        strategy_version=str(
            payload.get("strategy_version", DEFAULT_STRATEGY_VERSION)
        ),
        risk_config_version=str(
            payload.get("risk_config_version", DEFAULT_RISK_CONFIG_VERSION)
        ),
        scoring_version=str(
            payload.get("scoring_version", DEFAULT_SCORING_VERSION)
        ),
        capital_state_version=str(
            payload.get("capital_state_version", DEFAULT_CAPITAL_STATE_VERSION)
        ),
        state_machine_version=str(
            payload.get("state_machine_version", DEFAULT_STATE_MACHINE_VERSION)
        ),
        llm_prompt_version=str(
            payload.get("llm_prompt_version", DEFAULT_LLM_PROMPT_VERSION)
        ),
    )
