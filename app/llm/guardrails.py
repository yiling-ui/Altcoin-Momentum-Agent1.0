"""Phase 10C - LLM Guardrails (Issue #10 Part 3 / Spec §22.3).

Pure-function guardrails the orchestrator uses to neutralise any
output the LLM could produce that would otherwise risk overstepping
the Spec §22.3 envelope:

  - whitelist enforcer: drop any non-whitelisted output key
  - forbidden field stripper: drop + record any trade-action field
  - prompt-injection detector: pure regex / substring sniffer
  - input cleaner: trim + collapse + length-cap; preserves enough
    context for the model but strips obvious adversarial markers

Phase 10C boundary
------------------

This module:

  - imports nothing outside the Python standard library + the
    project's own enum vocabularies
  - never opens a socket
  - never reads ``os.environ``
  - defines no write surface
  - defines no ``send_*`` reference
  - never raises into the caller - every helper returns a value
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

#: Spec §22.2 closed output whitelist. Any key outside this set is
#: dropped during enforcement; tests pin the constant.
LLM_OUTPUT_WHITELIST: frozenset[str] = frozenset(
    {
        "narrative",
        "catalyst",
        "evidence_quality",
        "source_diversity",
        "kol_concentration",
        "bot_risk",
        "hype_stage",
        "contradictions",
        "risk_tags",
        "confidence",
    }
)


#: The complete forbidden-field set. Issue #10 Part 10C explicitly
#: enumerates every field; this is its machine-readable mirror. Tests
#: pin the value verbatim. The interpreter strips ANY of these and
#: records them in ``stripped_fields``; if any is present the result
#: is degraded.
LLM_FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {
        "direction",
        "leverage",
        "position_size",
        "target_price",
        "order_type",
        "stop_price",
        "take_profit",
        "should_buy",
        "should_short",
        "trade_decision",
        "entry",
        "exit",
        "liquidation_price",
        "margin_mode",
        "risk_budget",
        "order",
        "signal_to_trade",
    }
)


#: A subset of forbidden fields whose presence indicates the model
#: tried to produce a trade action. Phase 10C marks the result as
#: degraded with an additional risk_tag whenever ANY of these land.
HIGH_RISK_FORBIDDEN_FIELDS: frozenset[str] = LLM_FORBIDDEN_FIELDS


#: Default cap on the length of cleaned source text fed to the model.
#: Long enough for a typical Twitter / Telegram / forum post but short
#: enough to keep token usage bounded.
DEFAULT_INPUT_MAX_CHARS = 4096


#: Prompt-injection patterns. The regexes are deliberately lower-cased
#: + permissive about whitespace so an attacker who types
#: "Ignore   Previous   Instructions" still trips the detector.
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bignore\s+(all\s+|the\s+)?previous\s+instructions?\b"),
    re.compile(r"\bdisregard\s+(all\s+|the\s+)?(previous|above)\b"),
    re.compile(r"\boverride\s+(the\s+)?(system|safety)\b"),
    re.compile(r"\bforget\s+(everything|the rules?|the spec)\b"),
    re.compile(r"\bact\s+as\s+(the\s+)?(admin|root|developer|trader)\b"),
    re.compile(r"\b(reveal|disclose|print|return)\s+(the\s+)?(api[_ ]?key|secret|password|token)\b"),
    re.compile(r"\benvironment\s+variable", re.IGNORECASE),
    re.compile(r"\b(shell|exec|system\(|os\.system|subprocess)\b"),
    re.compile(r"\bcall\s+(the\s+)?(create_order|place_order|submit_order)\b"),
    re.compile(r"\b(buy|short|long|sell)\s+(now|the\s+(coin|token|asset))\b"),
    re.compile(r"\b(target\s+price|leverage|position\s+size|stop\s+price)\b"),
    re.compile(r"\bshould[_ ]?buy\b|\bshould[_ ]?short\b|\bshould[_ ]?sell\b"),
)


def detect_prompt_injection(text: str) -> bool:
    """True if ``text`` contains any known prompt-injection marker.

    Pure function. Phase 10C does not return *which* pattern fired
    because the caller only needs the boolean to decide whether to
    flip ``risk_tags`` and ``degraded``.
    """
    if not isinstance(text, str) or not text:
        return False
    haystack = text.lower()
    return any(p.search(haystack) for p in _INJECTION_PATTERNS)


# ---------------------------------------------------------------------------
# Input cleaner
# ---------------------------------------------------------------------------
_CONTROL_CHARS = "".join(
    chr(c) for c in range(32) if chr(c) not in ("\n", "\r", "\t")
)
_CONTROL_TABLE = str.maketrans({c: " " for c in _CONTROL_CHARS})


def sanitize_input_text(
    text: str,
    *,
    max_chars: int = DEFAULT_INPUT_MAX_CHARS,
) -> str:
    """Light-touch input cleaner.

    Operations:
      - NFC unicode normalise so look-alike adversarial characters
        collapse into their canonical form.
      - Strip ASCII control characters except newline / carriage
        return / tab.
      - Collapse internal whitespace runs into single spaces while
        preserving newlines (so the model still sees paragraph
        structure).
      - Truncate to ``max_chars`` so a 1MB blob from a malicious
        feed cannot blow up the token budget.

    Phase 10C deliberately does NOT remove the prompt-injection
    marker substrings - the *injection detector* records the marker
    so the audit trail can prove we noticed; stripping the markers
    silently would lose that audit signal.
    """
    if not isinstance(text, str):
        return ""
    if not text:
        return ""
    # Unicode canonical form.
    text = unicodedata.normalize("NFC", text)
    # Drop control chars (keep \n / \r / \t).
    text = text.translate(_CONTROL_TABLE)
    # Collapse runs of whitespace per-line.
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        cleaned_lines.append(re.sub(r"[ \t]+", " ", line).strip())
    text = "\n".join(cleaned_lines).strip()
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars]
    return text


# ---------------------------------------------------------------------------
# Whitelist + forbidden-field enforcement
# ---------------------------------------------------------------------------
def enforce_field_whitelist(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Drop any key not in :data:`LLM_OUTPUT_WHITELIST`.

    Returns ``(filtered_payload, dropped_keys)``. The caller decides
    whether to add ``schema_violation`` to ``risk_tags`` based on
    the dropped keys. Note: this helper does NOT touch nested dicts
    (the schema does not allow nested objects); a value that looks
    suspicious nested inside a string is the responsibility of the
    schema validator above.
    """
    if not isinstance(payload, dict):
        return {}, []
    out: dict[str, Any] = {}
    dropped: list[str] = []
    for key, value in payload.items():
        if key in LLM_OUTPUT_WHITELIST:
            out[key] = value
        else:
            dropped.append(key)
    return out, dropped


def strip_forbidden_fields(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Strip any forbidden trade-action key.

    Returns ``(safe_payload, stripped_keys)`` where ``stripped_keys``
    is the list of forbidden fields that were present. The Phase 10C
    interpreter records this list in ``stripped_fields`` and adds
    ``LLMRiskTag.FORBIDDEN_FIELD_STRIPPED`` to ``risk_tags``.
    """
    if not isinstance(payload, dict):
        return {}, []
    out: dict[str, Any] = {}
    stripped: list[str] = []
    for key, value in payload.items():
        if key in LLM_FORBIDDEN_FIELDS:
            stripped.append(key)
            continue
        out[key] = value
    return out, stripped


def coerce_string_list(value: Any, *, max_items: int = 32) -> list[str]:
    """Best-effort coercion to ``list[str]``.

    Used by the interpreter when filling ``contradictions`` /
    ``risk_tags`` from a model that stuffed an integer or a None
    into the array. Non-string items are dropped silently; this is
    consistent with the schema validator returning False for the
    array, but here we are lenient because the goal is to keep the
    output JSON-safe even when the model misbehaves.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value][:max_items]
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item:
                out.append(item)
            if len(out) >= max_items:
                break
        return out
    return []


__all__ = [
    "LLM_OUTPUT_WHITELIST",
    "LLM_FORBIDDEN_FIELDS",
    "HIGH_RISK_FORBIDDEN_FIELDS",
    "DEFAULT_INPUT_MAX_CHARS",
    "detect_prompt_injection",
    "sanitize_input_text",
    "enforce_field_whitelist",
    "strip_forbidden_fields",
    "coerce_string_list",
]
