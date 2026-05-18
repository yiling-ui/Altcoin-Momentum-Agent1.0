"""Typed error hierarchy for AMA-RT.

These error classes are referenced by the skeleton modules (Risk Engine,
Execution FSM, Telegram, Monitoring) so that Phase 2+ can raise them
without further refactor.
"""

from __future__ import annotations


class AMARTError(Exception):
    """Base exception for all AMA-RT failures."""


class ConfigError(AMARTError):
    """Configuration is invalid or missing."""


class SafetyViolation(AMARTError):
    """A caller attempted an action forbidden in the current phase.

    Examples: live order in paper mode, bypassing the Risk Engine,
    enabling right-tail amplification before paper acceptance.
    """


class RiskRejection(AMARTError):
    """The Risk Engine refused to approve an action."""


class ExecutionError(AMARTError):
    """Execution FSM detected an inconsistent or unsafe state."""


class ReconciliationError(AMARTError):
    """Local state and exchange state disagree."""
