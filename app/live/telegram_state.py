"""Persistent live operator state (PR114 - Operator Console v0).

A tiny, dependency-free, file-based persistence layer for the live
operator console. It keeps four JSON files under ``data/live_state/``:

  - ``runtime_mode.json``               - the current LIVE_SHADOW /
                                          LIVE_LIMITED mode + paused flag.
  - ``telegram_confirmation_state.json``- the pending / completed
                                          confirmation handshakes
                                          (LIVE_LIMITED + kill switch).
  - ``capital_profile_state.json``      - the active capital profile id.
  - ``kill_switch_state.json``          - the kill switch armed flag.

Hard rules (the brief):

  1. File writes are ATOMIC (write to a temp file in the same directory,
     ``os.replace`` onto the target) so a crash mid-write can never leave
     a half-written file.
  2. State is readable after restart.
  3. The DEFAULT is always ``LIVE_SHADOW`` when the file is missing.
  4. ``LIVE_LIMITED`` cannot persist as *armed* without a recorded
     confirmation. On load, an ``armed`` flag with no matching
     confirmation record fails safe to ``LIVE_SHADOW``.
  5. A corrupt / unparseable state file FAILS SAFE to ``LIVE_SHADOW``
     and records a warning (it never crashes the console and never
     resurrects a funded mode from garbage).

This module performs ONLY local file IO. It never opens a network
socket, never places an order, and never flips a Phase 1 safety flag.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.core.clock import now_ms
from app.core.enums import LiveRuntimeMode
from app.live.capital_profile import CapitalProfileId

LIVE_STATE_MODULE = "live.telegram_state"

# Default state root. Kept under data/ (git-ignored runtime data).
DEFAULT_LIVE_STATE_DIR = Path("data/live_state")

RUNTIME_MODE_FILE = "runtime_mode.json"
CONFIRMATION_FILE = "telegram_confirmation_state.json"
CAPITAL_PROFILE_FILE = "capital_profile_state.json"
KILL_SWITCH_FILE = "kill_switch_state.json"

# Warning tags surfaced when a file failed safe.
STATE_CORRUPT_FAILSAFE = "STATE_CORRUPT_FAILSAFE_TO_SHADOW"
STATE_ARMED_WITHOUT_CONFIRMATION = "ARMED_WITHOUT_CONFIRMATION_FAILSAFE_TO_SHADOW"


# ---------------------------------------------------------------------------
# State dataclasses
# ---------------------------------------------------------------------------
@dataclass
class RuntimeModeState:
    """Persisted live runtime mode + pause flag."""

    runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_SHADOW
    live_limited_armed: bool = False
    paused: bool = False
    updated_at: int = field(default_factory=now_ms)
    updated_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_mode": self.runtime_mode.value,
            "live_limited_armed": self.live_limited_armed,
            "paused": self.paused,
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
        }


@dataclass
class ConfirmationState:
    """Pending / completed operator confirmation handshakes.

    A pending code is short-lived (it expires). A completed
    ``live_limited_confirmed`` record is what authorises persisting an
    armed LIVE_LIMITED mode across a restart.
    """

    pending_code: str | None = None
    pending_target: str | None = None
    pending_issued_at: int | None = None
    pending_expires_at: int | None = None
    live_limited_confirmed: bool = False
    live_limited_confirmed_at: int | None = None
    pending_kill_code: str | None = None
    pending_kill_expires_at: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CapitalProfileStateRecord:
    """Persisted active capital profile id."""

    capital_profile_id: CapitalProfileId = CapitalProfileId.L0_SHADOW
    updated_at: int = field(default_factory=now_ms)
    updated_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "capital_profile_id": self.capital_profile_id.value,
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
        }


@dataclass
class KillSwitchState:
    """Persisted kill switch armed flag."""

    armed: bool = False
    armed_at: int | None = None
    armed_by: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LiveOperatorState:
    """The full persisted operator state + any fail-safe warnings."""

    runtime: RuntimeModeState
    confirmation: ConfirmationState
    capital_profile: CapitalProfileStateRecord
    kill_switch: KillSwitchState
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime": self.runtime.to_dict(),
            "confirmation": self.confirmation.to_dict(),
            "capital_profile": self.capital_profile.to_dict(),
            "kill_switch": self.kill_switch.to_dict(),
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Atomic file IO helpers
# ---------------------------------------------------------------------------
def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` as JSON to ``path`` atomically.

    Writes to a temp file in the same directory then ``os.replace`` so a
    crash mid-write never corrupts the target. ``os.replace`` is atomic
    on POSIX and Windows for same-filesystem moves.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"), sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, str(path))
    except Exception:
        # Best-effort cleanup of the temp file; re-raise the original.
        try:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
        except OSError:  # pragma: no cover
            pass
        raise


def _read_json(path: Path) -> tuple[dict[str, Any] | None, bool]:
    """Read JSON from ``path``.

    Returns ``(data, corrupt)``. A missing file yields ``(None, False)``;
    an unreadable / unparseable file yields ``(None, True)`` so the
    caller can fail safe + warn.
    """
    if not path.exists():
        return None, False
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return None, True
        return data, False
    except (json.JSONDecodeError, ValueError, OSError):
        return None, True


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------
class LiveOperatorStateStore:
    """Owns the four persisted JSON state files (PR114).

    Construct with a directory (defaults to ``data/live_state``). All
    reads fail safe to LIVE_SHADOW; all writes are atomic.
    """

    def __init__(self, state_dir: str | Path | None = None) -> None:
        self._dir = Path(state_dir) if state_dir is not None else DEFAULT_LIVE_STATE_DIR

    @property
    def state_dir(self) -> Path:
        return self._dir

    def _path(self, name: str) -> Path:
        return self._dir / name

    # -- runtime mode --------------------------------------------------
    def load_runtime_mode(self) -> tuple[RuntimeModeState, list[str]]:
        data, corrupt = _read_json(self._path(RUNTIME_MODE_FILE))
        warnings: list[str] = []
        if corrupt:
            warnings.append(f"{RUNTIME_MODE_FILE}:{STATE_CORRUPT_FAILSAFE}")
            return RuntimeModeState(), warnings
        if not data:
            return RuntimeModeState(), warnings
        try:
            mode = LiveRuntimeMode(str(data.get("runtime_mode", "LIVE_SHADOW")))
        except ValueError:
            warnings.append(f"{RUNTIME_MODE_FILE}:{STATE_CORRUPT_FAILSAFE}")
            return RuntimeModeState(), warnings
        return (
            RuntimeModeState(
                runtime_mode=mode,
                live_limited_armed=bool(data.get("live_limited_armed", False)),
                paused=bool(data.get("paused", False)),
                updated_at=int(data.get("updated_at", now_ms())),
                updated_by=data.get("updated_by"),
            ),
            warnings,
        )

    def save_runtime_mode(self, state: RuntimeModeState) -> None:
        _atomic_write_json(self._path(RUNTIME_MODE_FILE), state.to_dict())

    # -- confirmation --------------------------------------------------
    def load_confirmation(self) -> tuple[ConfirmationState, list[str]]:
        data, corrupt = _read_json(self._path(CONFIRMATION_FILE))
        warnings: list[str] = []
        if corrupt:
            warnings.append(f"{CONFIRMATION_FILE}:{STATE_CORRUPT_FAILSAFE}")
            return ConfirmationState(), warnings
        if not data:
            return ConfirmationState(), warnings
        return (
            ConfirmationState(
                pending_code=data.get("pending_code"),
                pending_target=data.get("pending_target"),
                pending_issued_at=data.get("pending_issued_at"),
                pending_expires_at=data.get("pending_expires_at"),
                live_limited_confirmed=bool(data.get("live_limited_confirmed", False)),
                live_limited_confirmed_at=data.get("live_limited_confirmed_at"),
                pending_kill_code=data.get("pending_kill_code"),
                pending_kill_expires_at=data.get("pending_kill_expires_at"),
            ),
            warnings,
        )

    def save_confirmation(self, state: ConfirmationState) -> None:
        _atomic_write_json(self._path(CONFIRMATION_FILE), state.to_dict())

    # -- capital profile ----------------------------------------------
    def load_capital_profile(self) -> tuple[CapitalProfileStateRecord, list[str]]:
        data, corrupt = _read_json(self._path(CAPITAL_PROFILE_FILE))
        warnings: list[str] = []
        if corrupt:
            warnings.append(f"{CAPITAL_PROFILE_FILE}:{STATE_CORRUPT_FAILSAFE}")
            return CapitalProfileStateRecord(), warnings
        if not data:
            return CapitalProfileStateRecord(), warnings
        try:
            pid = CapitalProfileId(str(data.get("capital_profile_id", "L0_SHADOW")))
        except ValueError:
            warnings.append(f"{CAPITAL_PROFILE_FILE}:{STATE_CORRUPT_FAILSAFE}")
            return CapitalProfileStateRecord(), warnings
        return (
            CapitalProfileStateRecord(
                capital_profile_id=pid,
                updated_at=int(data.get("updated_at", now_ms())),
                updated_by=data.get("updated_by"),
            ),
            warnings,
        )

    def save_capital_profile(self, state: CapitalProfileStateRecord) -> None:
        _atomic_write_json(self._path(CAPITAL_PROFILE_FILE), state.to_dict())

    # -- kill switch ---------------------------------------------------
    def load_kill_switch(self) -> tuple[KillSwitchState, list[str]]:
        data, corrupt = _read_json(self._path(KILL_SWITCH_FILE))
        warnings: list[str] = []
        if corrupt:
            warnings.append(f"{KILL_SWITCH_FILE}:{STATE_CORRUPT_FAILSAFE}")
            return KillSwitchState(), warnings
        if not data:
            return KillSwitchState(), warnings
        return (
            KillSwitchState(
                armed=bool(data.get("armed", False)),
                armed_at=data.get("armed_at"),
                armed_by=data.get("armed_by"),
                reason=data.get("reason"),
            ),
            warnings,
        )

    def save_kill_switch(self, state: KillSwitchState) -> None:
        _atomic_write_json(self._path(KILL_SWITCH_FILE), state.to_dict())

    # -- aggregate -----------------------------------------------------
    def load(self) -> LiveOperatorState:
        """Load the full operator state, applying every fail-safe rule.

        - Corrupt files fail safe to defaults + record a warning.
        - An armed LIVE_LIMITED with no completed confirmation record is
          DOWNGRADED to LIVE_SHADOW (a restart can never silently resume
          a funded mode).
        """
        runtime, w1 = self.load_runtime_mode()
        confirmation, w2 = self.load_confirmation()
        profile, w3 = self.load_capital_profile()
        kill, w4 = self.load_kill_switch()
        warnings = [*w1, *w2, *w3, *w4]

        # Fail-safe: armed LIVE_LIMITED requires a completed confirmation.
        armed_limited = (
            runtime.runtime_mode is LiveRuntimeMode.LIVE_LIMITED
            or runtime.live_limited_armed
        )
        if armed_limited and not confirmation.live_limited_confirmed:
            warnings.append(
                f"{RUNTIME_MODE_FILE}:{STATE_ARMED_WITHOUT_CONFIRMATION}"
            )
            runtime = RuntimeModeState(
                runtime_mode=LiveRuntimeMode.LIVE_SHADOW,
                live_limited_armed=False,
                paused=runtime.paused,
                updated_at=runtime.updated_at,
                updated_by=runtime.updated_by,
            )

        return LiveOperatorState(
            runtime=runtime,
            confirmation=confirmation,
            capital_profile=profile,
            kill_switch=kill,
            warnings=tuple(warnings),
        )

    def reset(self) -> None:
        """Delete all four state files (return to fresh-boot defaults)."""
        for name in (RUNTIME_MODE_FILE, CONFIRMATION_FILE, CAPITAL_PROFILE_FILE, KILL_SWITCH_FILE):
            p = self._path(name)
            try:
                if p.exists():
                    p.unlink()
            except OSError:  # pragma: no cover
                pass


__all__ = [
    "LIVE_STATE_MODULE",
    "DEFAULT_LIVE_STATE_DIR",
    "RUNTIME_MODE_FILE",
    "CONFIRMATION_FILE",
    "CAPITAL_PROFILE_FILE",
    "KILL_SWITCH_FILE",
    "STATE_CORRUPT_FAILSAFE",
    "STATE_ARMED_WITHOUT_CONFIRMATION",
    "RuntimeModeState",
    "ConfirmationState",
    "CapitalProfileStateRecord",
    "KillSwitchState",
    "LiveOperatorState",
    "LiveOperatorStateStore",
]
