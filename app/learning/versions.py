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

Default version labels are derived from :data:`app.__version__` at
import time so a future ``__version__`` bump is automatically
picked up by every event payload that does not override the value
explicitly. The labels are formatted ``"v<__version__>"`` (e.g.
``"v1.4.0a8.5"``). Future phases that promote a sub-config to its
own release cadence (a rare but supported case) can override per
event by passing their own :class:`ConfigVersions`.

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


def _resolve_app_version_label() -> str:
    """Return the canonical default version label.

    Reads :data:`app.__version__` lazily and prefixes a ``"v"`` so
    every default tracks the running code version automatically.
    The lookup is wrapped in ``try`` purely for defence-in-depth: if
    a future packaging bug ever surfaces an ``ImportError`` here we
    still want :class:`ConfigVersions` to instantiate (the resulting
    label is a clearly-non-secret placeholder, never a credential).
    """
    try:
        from app import __version__ as _app_version  # local import: no cycle
    except ImportError:  # pragma: no cover - extremely defensive
        return "vunknown"
    return f"v{_app_version}"


# Phase 8.5 default version labels. These intentionally track
# :data:`app.__version__` so the Reflection engine sees a stable
# anchor that bumps automatically when the codebase advances. Future
# phases that need a separate cadence override per :class:`ConfigVersions`.
APP_VERSION_LABEL: str = _resolve_app_version_label()
DEFAULT_STRATEGY_VERSION: str = APP_VERSION_LABEL
DEFAULT_RISK_CONFIG_VERSION: str = APP_VERSION_LABEL
DEFAULT_SCORING_VERSION: str = APP_VERSION_LABEL
DEFAULT_CAPITAL_STATE_VERSION: str = APP_VERSION_LABEL
DEFAULT_STATE_MACHINE_VERSION: str = APP_VERSION_LABEL
# llm_prompt_version is "n/a" by default because Phase 8.5 forbids
# any LLM trade involvement (Spec rule 7). Issue #10 will replace
# this with a real prompt version label.
DEFAULT_LLM_PROMPT_VERSION: str = "n/a"


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
