"""Secret loading and masking for the Live API Integration Pack (PR111).

This module is the single place that reads API credentials from the
process environment. It enforces the PR111 secret-handling rules:

  1. A missing secret NEVER crashes the process. Loading returns a
     :class:`SecretValue` whose :meth:`SecretValue.is_present` is
     ``False``; callers map that into ``API_HEALTH_MISSING_SECRET``.
  2. A secret value NEVER appears in ``repr`` / ``str`` / ``dict`` /
     ``json`` output. :class:`SecretValue` overrides ``__repr__`` /
     ``__str__`` to return only a masked form (``abc***xyz``).
  3. The raw value is only obtainable through :meth:`SecretValue.reveal`,
     which is used exclusively by the HTTP signing / auth path. The
     revealed value is never logged.
  4. ``mask_secret`` is the canonical masking helper (e.g. ``abc***xyz``).

No third-party dependency is imported here; only the standard library.
"""

from __future__ import annotations

import os
from typing import Final


# Sentinel returned when a secret is requested for display but absent.
SECRET_ABSENT_DISPLAY: Final[str] = "<absent>"

# Health status strings used across the pack when a secret is missing.
API_HEALTH_MISSING_SECRET: Final[str] = "API_HEALTH_MISSING_SECRET"

# PR112 hardening: a secret that is *present* but is obviously a
# placeholder / dummy value (e.g. copied from .env.example and never
# filled in). Detected BEFORE any real HTTP call so a placeholder never
# produces a confusing HTTP 401 / getMe error.
PLACEHOLDER_SECRET_CONFIGURED: Final[str] = "PLACEHOLDER_SECRET_CONFIGURED"
# A secret that is missing entirely (treated as "no real secret yet").
MISSING_REAL_SECRET: Final[str] = "MISSING_REAL_SECRET"

# Exact placeholder tokens shipped in .env.example / docs. Matched
# case-insensitively. These MUST NEVER reach a real Binance / Telegram /
# DeepSeek HTTP call.
PLACEHOLDER_SECRET_VALUES: frozenset[str] = frozenset(
    {
        "put_your_key_here",
        "put_your_secret_here",
        "put_your_bot_token_here",
        "put_your_chat_id_here",
        "put_your_deepseek_key_here",
        "put_your_api_key_here",
        "put_your_token_here",
        "your_key_here",
        "your_secret_here",
        "your_token_here",
        "your_api_key_here",
        "changeme",
        "change_me",
        "placeholder",
        "todo",
        "tbd",
        "none",
        "null",
        "xxx",
        "xxxx",
        "xxxxx",
    }
)


def is_placeholder_secret(value: str | None) -> bool:
    """Return True if ``value`` is an obvious placeholder / dummy secret.

    A *missing* value is NOT a placeholder (it is simply missing -
    callers distinguish the two). The check is deliberately conservative
    so a legitimate (if fake-looking) credential is never mis-flagged:

      - empty / whitespace-only -> False (that is "missing", not placeholder)
      - an exact match in :data:`PLACEHOLDER_SECRET_VALUES` (case-insensitive)
      - a value that contains ``put_your`` or ends with ``_here``
      - a value wrapped in angle brackets (``<your-key>``)
      - a value made only of the repeated ``x`` / ``*`` / ``.`` filler char
    """

    if value is None:
        return False
    text = str(value).strip()
    if text == "":
        return False
    lowered = text.lower()
    if lowered in PLACEHOLDER_SECRET_VALUES:
        return True
    if "put_your" in lowered or lowered.endswith("_here"):
        return True
    if text.startswith("<") and text.endswith(">"):
        return True
    # All-filler tokens like "xxxxxxxx", "********", "........".
    stripped = text.strip("xX*. _-")
    if stripped == "":
        return True
    return False


def mask_secret(value: str | None, *, show: int = 3) -> str:
    """Return a masked form of ``value`` safe to log / display.

    Examples
    --------
    ``mask_secret("abcdefghijklmnopqrstuvwxyz")`` -> ``"abc***xyz"``
    ``mask_secret("short")``                      -> ``"*****"``
    ``mask_secret("")``                           -> ``"<absent>"``
    ``mask_secret(None)``                         -> ``"<absent>"``

    A value short enough that revealing ``show`` leading + ``show``
    trailing characters would expose more than half of it is masked
    completely. This keeps short tokens from leaking.
    """

    if value is None:
        return SECRET_ABSENT_DISPLAY
    text = str(value)
    if text == "":
        return SECRET_ABSENT_DISPLAY
    if show < 1:
        return "*" * len(text)
    # If the value is too short to safely reveal head+tail, mask fully.
    if len(text) <= show * 2:
        return "*" * len(text)
    return f"{text[:show]}***{text[-show:]}"


class SecretValue:
    """An opaque holder for a credential value.

    Intentionally NOT a dataclass: the raw value is stored in a private
    instance attribute (via ``__slots__``) so that
    :func:`dataclasses.asdict` on a config object holding a
    ``SecretValue`` can never recurse into and expose the raw string.
    ``__repr__`` / ``__str__`` only ever return a masked form, and the
    only way to obtain the raw value is :meth:`reveal`, reserved for the
    HTTP signing / auth path.

    A ``SecretValue`` constructed from a missing env var has
    ``is_present == False`` and a raw value of ``""``; callers treat
    that as ``API_HEALTH_MISSING_SECRET``.
    """

    __slots__ = ("name", "__raw")

    def __init__(self, name: str, _raw: str = "") -> None:
        self.name = name
        # Double-underscore + __slots__ keeps the raw value off any
        # generic introspection path (asdict / vars / __dict__).
        object.__setattr__(self, "_SecretValue__raw", "" if _raw is None else str(_raw))

    @property
    def is_present(self) -> bool:
        return self.__raw != ""

    @property
    def is_placeholder(self) -> bool:
        """True if a value is present but is an obvious placeholder/dummy."""
        return is_placeholder_secret(self.__raw)

    @property
    def is_real(self) -> bool:
        """True only when present AND not a placeholder."""
        return self.is_present and not self.is_placeholder

    def health_status(self) -> str:
        """Return the secret-health tag for this value.

        ``MISSING_REAL_SECRET`` when absent, ``PLACEHOLDER_SECRET_CONFIGURED``
        when a placeholder is present, or ``""`` (empty) when a real value
        is present. Used by the health checks to short-circuit BEFORE any
        real HTTP call.
        """
        if not self.is_present:
            return MISSING_REAL_SECRET
        if self.is_placeholder:
            return PLACEHOLDER_SECRET_CONFIGURED
        return ""

    def reveal(self) -> str:
        """Return the raw secret. ONLY for HTTP signing / auth.

        The caller MUST NOT log, export, or embed the returned value in
        any user-facing text. There is no path in PR111 that passes the
        revealed value to a logger, a Telegram message, an exception, or
        an export artefact.
        """
        return self.__raw

    def masked(self, *, show: int = 3) -> str:
        if not self.is_present:
            return SECRET_ABSENT_DISPLAY
        return mask_secret(self.__raw, show=show)

    # -- Hard guarantees that the raw value never leaks --------------
    def __repr__(self) -> str:  # pragma: no cover - exercised in tests
        return f"SecretValue(name={self.name!r}, value={self.masked()!r}, present={self.is_present})"

    def __str__(self) -> str:  # pragma: no cover - exercised in tests
        return self.masked()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SecretValue):
            return NotImplemented
        return self.name == other.name and self.__raw == other.__raw

    def __hash__(self) -> int:
        return hash((self.name, self.__raw))

    def to_safe_dict(self) -> dict[str, object]:
        """JSON-safe view that NEVER carries the raw value."""
        return {
            "name": self.name,
            "present": self.is_present,
            "masked": self.masked(),
        }


def load_secret(env_name: str, *, environ: dict[str, str] | None = None) -> SecretValue:
    """Load a secret from the environment.

    Returns a :class:`SecretValue`. A missing or blank variable yields a
    ``SecretValue`` with ``is_present == False`` - it never raises.

    ``environ`` may be injected for tests; it defaults to ``os.environ``.
    """

    source = environ if environ is not None else os.environ
    raw = source.get(env_name, "")
    if raw is None:
        raw = ""
    return SecretValue(name=env_name, _raw=str(raw).strip())


__all__ = [
    "API_HEALTH_MISSING_SECRET",
    "PLACEHOLDER_SECRET_CONFIGURED",
    "MISSING_REAL_SECRET",
    "PLACEHOLDER_SECRET_VALUES",
    "SECRET_ABSENT_DISPLAY",
    "SecretValue",
    "is_placeholder_secret",
    "load_secret",
    "mask_secret",
]
