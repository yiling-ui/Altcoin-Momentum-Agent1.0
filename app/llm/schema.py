"""Phase 10C - LLM Output JSON Schema (Issue #10 Part 3 / Spec §22.2).

Pure-function validator. No external dependency (we DELIBERATELY do
NOT import ``jsonschema`` because it would be a new dependency in
``requirements.txt`` and Phase 10C is restricted to the existing
minimal dep set). The validator implements just enough of JSON
Schema for the Spec §22.2 contract:

  - required keys
  - type checks (string / integer / number / array)
  - enum membership
  - bounded numeric ranges
  - bounded array element types

If any check fails the validator returns a list of
:class:`SchemaValidationError` so the caller can record exactly which
fields drifted; it never raises.

Phase 10C boundary
------------------

This module:

  - imports nothing outside the Python standard library + the
    project's own enum vocabularies
  - never opens a socket
  - never reads ``os.environ``
  - defines no write surface
  - defines no ``send_*`` reference
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.llm.models import (
    CatalystStrength,
    EvidenceQuality,
    HypeStage,
)

#: Versioned JSON-schema label.
SCHEMA_VERSION = "v1.4.0a10c"


@dataclass(frozen=True)
class SchemaValidationError:
    """One reason a payload failed schema validation."""

    field: str
    code: str
    message: str

    def to_payload(self) -> dict[str, str]:
        return {"field": self.field, "code": self.code, "message": self.message}


#: The closed Spec §22.2 schema. Listed structurally so a future
#: maintainer can grep the contract.
LLM_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "version": SCHEMA_VERSION,
    "required": [
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
    ],
    "additional_properties": False,
    "properties": {
        "narrative": {
            "type": "string",
            "max_length": 1024,
        },
        "catalyst": {
            "type": "string",
            "enum": [v.value for v in CatalystStrength],
        },
        "evidence_quality": {
            "type": "string",
            "enum": [v.value for v in EvidenceQuality],
        },
        "source_diversity": {
            "type": "integer",
            "minimum": 0,
            "maximum": 10_000,
        },
        "kol_concentration": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "bot_risk": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "hype_stage": {
            "type": "string",
            "enum": [v.value for v in HypeStage],
        },
        "contradictions": {
            "type": "array",
            "items": {"type": "string", "max_length": 256},
            "max_items": 32,
        },
        "risk_tags": {
            "type": "array",
            "items": {"type": "string", "max_length": 96},
            "max_items": 64,
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
    },
}


def validate_llm_output(
    payload: Any,
) -> tuple[dict[str, Any], list[SchemaValidationError]]:
    """Validate ``payload`` against :data:`LLM_OUTPUT_SCHEMA`.

    Returns a ``(coerced_payload, errors)`` tuple. The
    ``coerced_payload`` contains only whitelisted keys and is safe to
    feed to the guardrail layer even when ``errors`` is non-empty;
    the caller decides whether to degrade.

    Implementation detail: the validator is intentionally permissive
    about *value coercion* (e.g. accepts an integer where a number is
    expected, accepts a list[str | int] for a string array as long as
    each item ``str()`` -s cleanly) because we must never raise. The
    *strict* enforcement happens in the guardrail layer where we
    enforce the field whitelist and the forbidden-field stripper.
    """
    errors: list[SchemaValidationError] = []
    coerced: dict[str, Any] = {}

    if not isinstance(payload, dict):
        errors.append(
            SchemaValidationError(
                field="<root>",
                code="not_an_object",
                message=(
                    f"expected a JSON object, got {type(payload).__name__}"
                ),
            )
        )
        return coerced, errors

    schema = LLM_OUTPUT_SCHEMA
    required = schema["required"]
    properties = schema["properties"]

    for key in required:
        if key not in payload:
            errors.append(
                SchemaValidationError(
                    field=key,
                    code="missing_required_field",
                    message=f"required field {key!r} is missing",
                )
            )

    for key, value in payload.items():
        if key not in properties:
            # Extra keys are reported as schema violations BUT the
            # final removal happens in the field-whitelist layer.
            errors.append(
                SchemaValidationError(
                    field=key,
                    code="unknown_field",
                    message=f"field {key!r} is not in the Spec §22.2 schema",
                )
            )
            continue
        spec = properties[key]
        ok, coerced_value = _check_field(key, spec, value, errors)
        if ok:
            coerced[key] = coerced_value

    return coerced, errors


# ===========================================================================
# Internal helpers
# ===========================================================================
def _check_field(
    key: str,
    spec: dict[str, Any],
    value: Any,
    errors: list[SchemaValidationError],
) -> tuple[bool, Any]:
    expected_type = spec.get("type")
    if expected_type == "string":
        if not isinstance(value, str):
            errors.append(
                SchemaValidationError(
                    field=key,
                    code="bad_type",
                    message=f"expected string for {key!r}, got {type(value).__name__}",
                )
            )
            return False, None
        max_len = spec.get("max_length")
        if max_len is not None and len(value) > max_len:
            errors.append(
                SchemaValidationError(
                    field=key,
                    code="too_long",
                    message=f"{key!r} exceeds max_length={max_len}",
                )
            )
            return False, None
        if "enum" in spec and value not in spec["enum"]:
            errors.append(
                SchemaValidationError(
                    field=key,
                    code="enum_mismatch",
                    message=(
                        f"{key!r} must be one of {spec['enum']}, got {value!r}"
                    ),
                )
            )
            return False, None
        return True, value

    if expected_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(
                SchemaValidationError(
                    field=key,
                    code="bad_type",
                    message=f"expected integer for {key!r}, got {type(value).__name__}",
                )
            )
            return False, None
        return _bounded_number(key, spec, value, errors)

    if expected_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(
                SchemaValidationError(
                    field=key,
                    code="bad_type",
                    message=f"expected number for {key!r}, got {type(value).__name__}",
                )
            )
            return False, None
        return _bounded_number(key, spec, float(value), errors)

    if expected_type == "array":
        if not isinstance(value, (list, tuple)):
            errors.append(
                SchemaValidationError(
                    field=key,
                    code="bad_type",
                    message=f"expected array for {key!r}, got {type(value).__name__}",
                )
            )
            return False, None
        max_items = spec.get("max_items")
        if max_items is not None and len(value) > max_items:
            errors.append(
                SchemaValidationError(
                    field=key,
                    code="too_many_items",
                    message=f"{key!r} exceeds max_items={max_items}",
                )
            )
            return False, None
        item_spec = spec.get("items", {})
        out_items: list[Any] = []
        for index, item in enumerate(value):
            ok, coerced_item = _check_field(
                f"{key}[{index}]", item_spec, item, errors
            )
            if ok:
                out_items.append(coerced_item)
            else:
                # Reject the whole array if any item fails - this is
                # safer than silently dropping malformed elements.
                return False, None
        return True, tuple(out_items)

    errors.append(
        SchemaValidationError(
            field=key,
            code="unsupported_spec",
            message=f"schema for {key!r} declares unsupported type {expected_type!r}",
        )
    )
    return False, None


def _bounded_number(
    key: str,
    spec: dict[str, Any],
    value: float,
    errors: list[SchemaValidationError],
) -> tuple[bool, Any]:
    minimum = spec.get("minimum")
    maximum = spec.get("maximum")
    if minimum is not None and value < minimum:
        errors.append(
            SchemaValidationError(
                field=key,
                code="below_minimum",
                message=f"{key!r} below minimum {minimum}: got {value}",
            )
        )
        return False, None
    if maximum is not None and value > maximum:
        errors.append(
            SchemaValidationError(
                field=key,
                code="above_maximum",
                message=f"{key!r} above maximum {maximum}: got {value}",
            )
        )
        return False, None
    return True, value


__all__ = [
    "SCHEMA_VERSION",
    "LLM_OUTPUT_SCHEMA",
    "SchemaValidationError",
    "validate_llm_output",
]
