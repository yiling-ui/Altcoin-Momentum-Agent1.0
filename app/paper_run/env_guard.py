"""Phase 11B environment-variable pre-flight guard.

The cloud supervisor inspects the process environment BEFORE opening
any database. If any forbidden credential env-var is present (e.g.
``BINANCE_API_KEY``, ``TELEGRAM_BOT_TOKEN``, ``DEEPSEEK_API_KEY``)
the supervisor refuses to start. The guard ALSO rechecks the
``AMA_*`` runtime-flag values that Phase 1 :mod:`app.config.settings`
already coerces, so a cloud operator who accidentally exports
``AMA_LIVE_TRADING_ENABLED=true`` sees the failure before the boot
banner fires.

The guard reads ``os.environ`` directly. Phase 1 already does this
(via :func:`app.config.settings._apply_env_overrides`); the env-guard
is a louder, narrower wrapper that:

  - never reads a credential VALUE; it only checks PRESENCE
  - never persists a credential VALUE
  - never logs a credential VALUE
  - records the inspection result as a redacted summary the
    supervisor stitches into the daily report

Phase 11B boundary (re-stated)
------------------------------

  - opens NO socket
  - imports NO exchange / LLM / Telegram SDK
  - holds NO ``api_key`` / ``api_secret`` / ``bot_token`` parameter
    or literal
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Mapping

from app.core.errors import SafetyViolation
from app.paper_run.config import EnvGuardConfig


# Values that, when present in an AMA_*_ENABLED env var, indicate
# the operator wanted to flip a safety flag. The Phase 1 lock will
# coerce the resolved Settings back to safe values, but we surface
# the dangerous *intent* loudly here so the cloud deploy log captures
# the misconfiguration.
_DANGEROUS_TRUTHY: frozenset[str] = frozenset(
    {"1", "true", "yes", "on"}
)


# Banner-friendly placeholder used when describing whether a
# forbidden credential env var was found. We NEVER emit the value.
_REDACTED_PRESENT = "<present-but-redacted>"


def _hash_label(name: str) -> str:
    """Return a deterministic, redaction-safe label for an env-var
    name. We refuse to embed the literal name (e.g.
    ``BINANCE_API_KEY``) anywhere because the Phase 8.5 redaction
    gate considers those names forbidden literals. The hash prefix
    is short enough to be readable AND deterministic enough that
    tests can pin specific names without serialising them."""
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    return f"cred:{digest}"


@dataclass(frozen=True)
class EnvGuardReport:
    """Result of one env-guard pass.

    The report exposes booleans and counts only; it carries NO
    credential value. The supervisor stitches this into the daily
    report and the Phase 11B acceptance report.
    """

    inspected_env_vars: tuple[str, ...]
    forbidden_credential_env_vars_checked: tuple[str, ...]
    forbidden_credentials_present: tuple[str, ...]
    dangerous_runtime_values: tuple[tuple[str, str], ...] = field(
        default_factory=tuple
    )
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return (
            not self.forbidden_credentials_present
            and not self.dangerous_runtime_values
        )

    def to_payload(self) -> dict[str, object]:
        """JSON-safe view. Credential VALUES are NEVER included; only
        the variable NAMES that were observed. The names of forbidden
        credential env-vars are returned as deterministic hashed
        labels (e.g. ``cred:7f3a1b2c``) so the rendered Markdown does
        not contain literals like ``BINANCE_API_KEY`` that would trip
        the Phase 8.5 :func:`assert_no_forbidden_substrings` gate.
        The ``inspected_env_vars`` list is safe to expose verbatim:
        it contains only ``AMA_*`` runtime-flag names, which are not
        forbidden literals.
        """
        return {
            "inspected_env_vars": list(self.inspected_env_vars),
            "forbidden_credential_env_var_count": len(
                self.forbidden_credential_env_vars_checked
            ),
            "forbidden_credentials_present_count": len(
                self.forbidden_credentials_present
            ),
            "forbidden_credentials_present_labels": [
                _hash_label(name) for name in self.forbidden_credentials_present
            ],
            "dangerous_runtime_values": [
                {"name": name, "value": _REDACTED_PRESENT}
                for name, _ in self.dangerous_runtime_values
            ],
            "notes": list(self.notes),
            "passed": bool(self.passed),
        }


class EnvGuard:
    """Phase 11B env-var pre-flight guard.

    Construct once per supervisor boot. The guard never holds a
    credential value; it only records which variable NAMES were
    present so the daily report can audit the deploy environment
    without leaking secrets.
    """

    def __init__(
        self,
        *,
        config: EnvGuardConfig,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._config = config
        # Snapshot the environment at construction so the guard's
        # behaviour is deterministic regardless of later mutations.
        self._environ: dict[str, str] = dict(environ or os.environ)

    @property
    def config(self) -> EnvGuardConfig:
        return self._config

    # ------------------------------------------------------------------
    def evaluate(self) -> EnvGuardReport:
        """Run the guard against the snapshotted environment.

        Returns an :class:`EnvGuardReport`; does NOT raise. The
        supervisor decides whether to refuse boot based on
        ``config.refuse_on_dangerous_value`` AND ``report.passed``.
        """
        if not self._config.enabled:
            return EnvGuardReport(
                inspected_env_vars=tuple(self._config.inspected_env_vars),
                forbidden_credential_env_vars_checked=tuple(
                    self._config.forbidden_credential_env_vars
                ),
                forbidden_credentials_present=(),
                dangerous_runtime_values=(),
                notes=("env_guard_disabled",),
            )

        # 1. Forbidden credential PRESENCE check.
        forbidden_present: list[str] = []
        for name in self._config.forbidden_credential_env_vars:
            value = self._environ.get(name)
            if value is None:
                continue
            if value.strip() == "":
                # An explicitly-empty env var is treated as absent. The
                # ``.env.example`` template ships every credential as
                # an empty placeholder, so an operator who copies it
                # verbatim does not trip the guard.
                continue
            forbidden_present.append(name)

        # 2. Dangerous AMA_*_ENABLED truthy check. We do NOT consume the
        # value as a fact; Phase 1 settings already does that. We only
        # surface the dangerous *intent*.
        dangerous: list[tuple[str, str]] = []
        for name in self._config.inspected_env_vars:
            value = self._environ.get(name)
            if value is None:
                continue
            stripped = value.strip().lower()
            if not stripped:
                continue
            if name == "AMA_TRADING_MODE":
                if stripped != "paper":
                    dangerous.append((name, stripped))
                continue
            if name.endswith("_ENABLED") and stripped in _DANGEROUS_TRUTHY:
                # AMA_LIVE_TRADING_ENABLED / AMA_RIGHT_TAIL_ENABLED /
                # AMA_LLM_ENABLED / AMA_EXCHANGE_LIVE_ORDER_ENABLED
                # were set to a truthy value. The Phase 1 safety lock
                # will coerce the Settings back to False, but the
                # operator's intent is dangerous and we record it.
                dangerous.append((name, stripped))

        notes: list[str] = []
        if forbidden_present:
            notes.append(
                f"forbidden_credentials_present_count={len(forbidden_present)}"
            )
        if dangerous:
            notes.append(
                "dangerous_runtime_values="
                + ",".join(name for name, _ in dangerous)
            )
        if not forbidden_present and not dangerous:
            notes.append("clean_env")

        return EnvGuardReport(
            inspected_env_vars=tuple(self._config.inspected_env_vars),
            forbidden_credential_env_vars_checked=tuple(
                self._config.forbidden_credential_env_vars
            ),
            forbidden_credentials_present=tuple(forbidden_present),
            dangerous_runtime_values=tuple(dangerous),
            notes=tuple(notes),
        )

    # ------------------------------------------------------------------
    def assert_safe(self) -> EnvGuardReport:
        """Refuse to boot if the guard fails AND the config asks for it.

        Returns the :class:`EnvGuardReport` on success.
        """
        report = self.evaluate()
        if not self._config.refuse_on_dangerous_value:
            return report
        if not report.passed:
            # Build a short refusal message that NEVER leaks credential
            # values. Only env-var names + a generic note.
            forbidden = list(report.forbidden_credentials_present)
            dangerous_names = [name for name, _ in report.dangerous_runtime_values]
            raise SafetyViolation(
                "Phase 11B env-guard refused to boot. "
                f"forbidden_credentials_present={forbidden} "
                f"dangerous_runtime_values={dangerous_names}. "
                "Unset every flagged variable before redeploying."
            )
        return report


__all__ = [
    "EnvGuard",
    "EnvGuardReport",
]
