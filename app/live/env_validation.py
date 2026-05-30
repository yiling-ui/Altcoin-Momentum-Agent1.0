"""`.env.live` validation helper (PR112 - PR111 usability hardening).

A fresh server deployment of PR111 produced a `.env.live` with a
malformed line around ``AMA_SECRET_LOGGING_ALLOWED`` (an operator had
pasted a shell command, e.g. ``chmod 600 .env.liveALLOWED=false``). This
helper validates an env file's *structure* WITHOUT ever revealing a
secret value:

  - it flags any line whose key half contains spaces / shell tokens
    (``ENV_FILE_SUSPICIOUS_LINE``);
  - it warns when ``AMA_SECRET_LOGGING_ALLOWED`` is missing (it must
    exist and default ``false``) or is set to a truthy value;
  - it never prints / returns a secret value (only key names + booleans).

This is structure-only validation: it does NOT load secrets, contact
any API, place an order, or change runtime state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Reason tags surfaced to the operator.
ENV_FILE_SUSPICIOUS_LINE = "ENV_FILE_SUSPICIOUS_LINE"
ENV_SECRET_LOGGING_KEY_MISSING = "ENV_SECRET_LOGGING_KEY_MISSING"
ENV_SECRET_LOGGING_ENABLED = "ENV_SECRET_LOGGING_ENABLED"
ENV_FILE_NOT_FOUND = "ENV_FILE_NOT_FOUND"

SECRET_LOGGING_KEY = "AMA_SECRET_LOGGING_ALLOWED"

# Shell-ish tokens that should never appear inside an env KEY.
_SHELL_TOKENS = ("&&", "||", ";", "|", "`", "$(", ">", "<", "chmod", "rm ", "sudo")

# A valid env key is letters/digits/underscore (optionally with `export `).
_VALID_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class EnvLineFinding:
    """A single suspicious-line finding (line numbers are 1-indexed)."""

    line_number: int
    reason: str
    key_fragment: str  # never carries the value

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_number": self.line_number,
            "reason": self.reason,
            "key_fragment": self.key_fragment,
        }


@dataclass(frozen=True)
class EnvValidationResult:
    """Result of validating an env file's structure (no secret values)."""

    path: str
    exists: bool
    warnings: tuple[str, ...] = ()
    findings: tuple[EnvLineFinding, ...] = ()
    secret_logging_present: bool = False
    secret_logging_allowed: bool = False
    keys_seen: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.exists and not self.warnings and not self.findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "exists": self.exists,
            "ok": self.ok,
            "warnings": list(self.warnings),
            "findings": [f.to_dict() for f in self.findings],
            "secret_logging_present": self.secret_logging_present,
            "secret_logging_allowed": self.secret_logging_allowed,
            "keys_seen": list(self.keys_seen),
        }


def _is_truthy(value: str) -> bool:
    return value.strip().strip("\"'").lower() in {"1", "true", "yes", "on"}


def validate_env_lines(lines: list[str], *, path: str = "<lines>") -> EnvValidationResult:
    """Validate the structure of env-file lines (no IO, no secret values)."""

    warnings: list[str] = []
    findings: list[EnvLineFinding] = []
    keys_seen: list[str] = []
    secret_logging_present = False
    secret_logging_allowed = False

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            # A non-comment, non-blank line with no '=' is malformed.
            findings.append(
                EnvLineFinding(
                    line_number=idx,
                    reason=ENV_FILE_SUSPICIOUS_LINE,
                    key_fragment=stripped[:40],
                )
            )
            continue
        key_part, _value = stripped.split("=", 1)
        key = key_part.strip()
        # `export FOO=bar` is allowed; strip the export prefix for checks.
        if key.lower().startswith("export "):
            key = key[len("export "):].strip()

        lowered_keypart = key_part.lower()
        suspicious = (
            not _VALID_KEY_RE.match(key)
            or any(tok in lowered_keypart for tok in _SHELL_TOKENS)
            or " " in key
        )
        if suspicious:
            findings.append(
                EnvLineFinding(
                    line_number=idx,
                    reason=ENV_FILE_SUSPICIOUS_LINE,
                    key_fragment=key_part.strip()[:40],
                )
            )
            continue

        keys_seen.append(key)
        if key == SECRET_LOGGING_KEY:
            secret_logging_present = True
            secret_logging_allowed = _is_truthy(_value)

    if findings:
        warnings.append(ENV_FILE_SUSPICIOUS_LINE)
    if not secret_logging_present:
        warnings.append(ENV_SECRET_LOGGING_KEY_MISSING)
    elif secret_logging_allowed:
        warnings.append(ENV_SECRET_LOGGING_ENABLED)

    return EnvValidationResult(
        path=path,
        exists=True,
        warnings=tuple(dict.fromkeys(warnings)),
        findings=tuple(findings),
        secret_logging_present=secret_logging_present,
        secret_logging_allowed=secret_logging_allowed,
        keys_seen=tuple(keys_seen),
    )


def validate_env_file(path: str | Path) -> EnvValidationResult:
    """Validate the structure of an env file at ``path``.

    A missing file is reported (``ENV_FILE_NOT_FOUND``) rather than
    raising, so a CLI can warn the operator without crashing.
    """
    p = Path(path)
    if not p.exists():
        return EnvValidationResult(
            path=str(p),
            exists=False,
            warnings=(ENV_FILE_NOT_FOUND,),
        )
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return EnvValidationResult(
            path=str(p),
            exists=False,
            warnings=(ENV_FILE_NOT_FOUND,),
        )
    return validate_env_lines(text.splitlines(), path=str(p))


__all__ = [
    "ENV_FILE_SUSPICIOUS_LINE",
    "ENV_SECRET_LOGGING_KEY_MISSING",
    "ENV_SECRET_LOGGING_ENABLED",
    "ENV_FILE_NOT_FOUND",
    "SECRET_LOGGING_KEY",
    "EnvLineFinding",
    "EnvValidationResult",
    "validate_env_lines",
    "validate_env_file",
]
