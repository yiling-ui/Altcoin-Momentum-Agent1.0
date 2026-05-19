"""Phase 8.5 - Test Data Export redaction.

Walks any JSON-safe value (dict / list / scalar) and returns a new
copy with sensitive fields replaced by ``[REDACTED]``.

Issue contract (forbidden in exports):

    - API Key
    - API Secret
    - Telegram Bot Token
    - .env content
    - environment variables
    - server path sensitive info
    - withdrawal address
    - non-redacted account-sensitive fields

The redactor is **defence-in-depth on top of the Phase 1 safety lock**:
the safety lock guarantees no real credential ever reaches the
process; this redactor guarantees that even if a future bug surfaces
something that *looks like* a credential into events.db, the export
artefact stays clean.

Phase 8.5 boundary
------------------

The redactor is a pure function:

  - It never reads ``os.environ``.
  - It never opens a socket.
  - It never imports an exchange / LLM / Telegram library.
  - It returns a new value; the input is never mutated.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

REDACTED = "[REDACTED]"


# Keys whose name (case-insensitive substring) marks the value as
# secret. Any value living under one of these keys is redacted.
SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "api_secret",
    "apisecret",
    "secret",
    "token",
    "password",
    "passwd",
    "pwd",
    "auth",
    "credential",
    "credentials",
    "private_key",
    "privatekey",
    "bot_token",
    "tg_token",
    "telegram_token",
    "webhook",
    "webhook_url",
    "deepseek_api",
    "openai_api",
    "anthropic_api",
    "binance_api",
    "withdrawal_address",
    "withdraw_address",
    "wallet_address",
    "address",  # broad on purpose - exports never need raw addresses
    "private",
    "passphrase",
    "session",
    "cookie",
    "ssh",
    "smtp",
)


# Specific full-key matches that we redact regardless of substring
# rules (these are common environment / path leaks).
SENSITIVE_FULL_KEYS: frozenset[str] = frozenset(
    {
        "env",
        "environ",
        "environment",
        ".env",
        "dotenv",
        "home",
        "user",
        "username",
        "hostname",
    }
)


# String value patterns that look like credentials regardless of the
# key they live under. Each pattern is conservative - it must look
# like a real credential, not just any long string.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Telegram bot token: 8-10 digits : 35 chars [A-Za-z0-9_-]
    re.compile(r"^\d{8,12}:[A-Za-z0-9_-]{30,}$"),
    # Binance-style API keys: 64 chars [A-Za-z0-9].
    re.compile(r"^[A-Za-z0-9]{64}$"),
    # AWS-style secrets: starts with AKIA / ASIA + 16 chars.
    re.compile(r"^A(KIA|SIA|GPA|IDA|ROA|IPA|NPA|NVA)[A-Z0-9]{16,}$"),
    # OpenAI / DeepSeek / Anthropic-style sk-... tokens.
    re.compile(r"^sk-[A-Za-z0-9_-]{20,}$"),
    # AMA_*_KEY / AMA_*_SECRET / AMA_*_TOKEN env-var literal references.
    re.compile(r"^AMA_.*_(KEY|SECRET|TOKEN|PASSWORD)$"),
)


def _key_is_sensitive(key: object) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    if lowered in SENSITIVE_FULL_KEYS:
        return True
    for needle in SENSITIVE_KEY_SUBSTRINGS:
        if needle in lowered:
            return True
    return False


def _value_looks_secret(value: str) -> bool:
    if not isinstance(value, str):
        return False
    if len(value) < 16:
        return False
    for pat in _PATTERNS:
        if pat.match(value):
            return True
    return False


def _looks_like_filesystem_path(value: str) -> bool:
    """Conservative heuristic for absolute server paths that may leak
    operator info (``/home/<user>/...``, ``/root/...``,
    ``/Users/<user>/...``, ``C:\\Users\\<user>\\...``)."""
    if not isinstance(value, str) or len(value) < 2:
        return False
    lowered = value.lower()
    candidates = (
        "/home/",
        "/root/",
        "/users/",
        "c:\\users\\",
        "/var/lib/",
        "/etc/",
        "/usr/local/",
    )
    return any(lowered.startswith(c) for c in candidates) or "/.env" in lowered or "\\.env" in lowered


def redact(value: Any) -> Any:
    """Return a new value with every sensitive field replaced.

    Recurses into dicts and lists. Scalars are passed through except
    for strings that pattern-match a credential template; those are
    redacted. The function never mutates ``value`` in place.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if _key_is_sensitive(k):
                out[k] = REDACTED
                continue
            out[k] = redact(v)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        if _value_looks_secret(value):
            return REDACTED
        if _looks_like_filesystem_path(value):
            return REDACTED
        return value
    return value


def forbidden_substrings() -> tuple[str, ...]:
    """Return the canonical list of substrings that an export must
    NEVER contain after redaction. Used by Phase 8.5 tests as a
    belt-and-braces audit (any bytes match here is a hard test fail).
    """
    return (
        "api_key=",
        "api_secret=",
        "API_KEY=",
        "API_SECRET=",
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "TELEGRAM_BOT_TOKEN",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    )


def assert_no_forbidden_substrings(text: str, *, extra: Iterable[str] | None = None) -> None:
    """Raise ``AssertionError`` if any forbidden substring is in ``text``.

    Used by tests; lives in production code so a future Telegram
    outbound (Issue #10) can call the same gate before sending a
    file.
    """
    needles = list(forbidden_substrings()) + list(extra or [])
    for needle in needles:
        if needle in text:
            raise AssertionError(
                f"Redaction failed: forbidden substring {needle!r} present"
            )
