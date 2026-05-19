"""Phase 10C - LLM cache (Issue #10 Part 3).

A simple in-memory cache keyed by a deterministic hash of
(input_text, prompt_version, schema_version, model_name, throttle_tier,
symbol). The cache stores ONLY the JSON-safe payload of a successful
:class:`LLMInterpretationResult`; it never stores API keys / source
URLs / authorisation headers.

Phase 10C boundary
------------------

This module:

  - imports nothing outside the Python standard library
  - never opens a socket
  - never reads ``os.environ``
  - defines no write surface
  - defines no ``send_*`` reference
  - never raises into the caller - lookups always return ``None`` on
    miss; writes are best-effort

The cache lives in process memory by default. A future PR may layer
an SQLite-backed sibling on top; Phase 10C deliberately defers that
because Issue #10 Part 10C must NOT introduce a new on-disk
database schema.
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from app.core.clock import now_ms


@dataclass(frozen=True)
class LLMCacheEntry:
    """One row in the cache.

    The :attr:`payload` is the JSON-safe ``to_payload()`` of a
    successful :class:`LLMInterpretationResult`. The cache layer
    never stores credentials.
    """

    key: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: int = field(default_factory=now_ms)
    hits: int = 0


class LLMCache:
    """In-memory bounded LRU cache."""

    def __init__(self, *, max_entries: int = 1024) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._max_entries = int(max_entries)
        self._store: "OrderedDict[str, LLMCacheEntry]" = OrderedDict()

    # ------------------------------------------------------------------
    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def max_entries(self) -> int:
        return self._max_entries

    # ------------------------------------------------------------------
    @staticmethod
    def make_key(
        *,
        input_text: str,
        prompt_version: str,
        schema_version: str,
        model_name: str,
        throttle_tier: str,
        symbol: str | None = None,
    ) -> str:
        """Compute the cache key.

        We deliberately do NOT include the API key, the timestamp, or
        the correlation id - the cache must be keyed only on inputs
        that determine the model's response.
        """
        material = json.dumps(
            {
                "t": str(input_text),
                "p": str(prompt_version),
                "s": str(schema_version),
                "m": str(model_name),
                "tt": str(throttle_tier),
                "sym": str(symbol or ""),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    # ------------------------------------------------------------------
    def get(self, key: str) -> LLMCacheEntry | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        # LRU touch.
        self._store.move_to_end(key)
        # Increment hits in a fresh frozen dataclass so the entry
        # remains immutable from a caller's POV.
        new_entry = LLMCacheEntry(
            key=entry.key,
            payload=dict(entry.payload),
            created_at=entry.created_at,
            hits=entry.hits + 1,
        )
        self._store[key] = new_entry
        return new_entry

    def put(self, key: str, payload: dict[str, Any]) -> LLMCacheEntry:
        """Store a JSON-safe payload under ``key``.

        The payload MUST NOT contain a credential. Phase 10C never
        passes a credential into the cache because the interpreter
        builds the cache key BEFORE invoking the transport, and the
        transport's response is filtered by the guardrails before it
        reaches this method.
        """
        # Defence in depth: refuse to cache obvious credential keys.
        forbidden_substrings = (
            "api_key",
            "api_secret",
            "bot_token",
            "telegram_token",
            "deepseek_api",
            "openai_api",
            "anthropic_api",
            "binance_api",
            "private_key",
            "password",
            "session",
        )
        for k in payload.keys():
            lower = str(k).lower()
            for needle in forbidden_substrings:
                if needle in lower:
                    raise ValueError(
                        f"LLMCache refuses to store payload key {k!r}; "
                        "the cache must not retain credentials."
                    )
        entry = LLMCacheEntry(key=key, payload=dict(payload), hits=0)
        self._store[key] = entry
        self._store.move_to_end(key)
        # LRU eviction.
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)
        return entry

    def clear(self) -> None:
        self._store.clear()


__all__ = ["LLMCache", "LLMCacheEntry"]
