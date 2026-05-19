"""Phase 8.5 - Test Data Export manifest.

Issue contract: ``manifest.json`` must contain

    - export_id
    - generated_at
    - time_range_start
    - time_range_end
    - trading_mode
    - app_version
    - event_count
    - opportunity_count
    - risk_rejected_count
    - state_transition_count
    - capital_event_count
    - redaction_applied = true

Plus the per-export ``type_filter`` (``all``, ``events``, ``opportunities``,
``rejections``, ``capital``, ``state``, ``learning``) so the manifest is
self-describing.

Phase 8.5 boundary
------------------

The Manifest is a frozen Pydantic value object. ``to_dict()`` returns
a deterministic JSON-safe dict; ``to_json()`` serialises it sorted by
key with no trailing whitespace so file diffs are reproducible.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExportManifest(BaseModel):
    """The Phase 8.5 export manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    export_id: str
    generated_at: int
    time_range_start: int
    time_range_end: int
    trading_mode: str
    app_version: str
    event_count: int = 0
    opportunity_count: int = 0
    risk_rejected_count: int = 0
    risk_approved_count: int = 0
    state_transition_count: int = 0
    capital_event_count: int = 0
    virtual_trade_plan_count: int = 0
    signal_snapshot_count: int = 0
    incident_count: int = 0
    type_filter: str = "all"
    redaction_applied: bool = True
    # Files in the bundle; each entry is a JSON object with name,
    # row_count, byte_size so the consumer can sanity-check the zip.
    files: list[dict[str, Any]] = Field(default_factory=list)
    # Defence-in-depth: the manifest itself records a non-secret
    # safety summary so a reviewer can spot a leaked flag at a glance.
    safety_summary: dict[str, bool] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "export_id": self.export_id,
            "generated_at": int(self.generated_at),
            "time_range_start": int(self.time_range_start),
            "time_range_end": int(self.time_range_end),
            "trading_mode": str(self.trading_mode),
            "app_version": str(self.app_version),
            "event_count": int(self.event_count),
            "opportunity_count": int(self.opportunity_count),
            "risk_rejected_count": int(self.risk_rejected_count),
            "risk_approved_count": int(self.risk_approved_count),
            "state_transition_count": int(self.state_transition_count),
            "capital_event_count": int(self.capital_event_count),
            "virtual_trade_plan_count": int(self.virtual_trade_plan_count),
            "signal_snapshot_count": int(self.signal_snapshot_count),
            "incident_count": int(self.incident_count),
            "type_filter": str(self.type_filter),
            "redaction_applied": bool(self.redaction_applied),
            "files": [dict(f) for f in self.files],
            "safety_summary": dict(self.safety_summary),
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), separators=(",", ":"), sort_keys=True, ensure_ascii=False
        )

    def to_pretty_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)
