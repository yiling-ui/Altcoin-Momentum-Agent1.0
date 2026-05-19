"""Phase 11B - boot-time safety assertion (defence in depth).

The supervisor calls :func:`assert_paper_cloud_safety` BEFORE
opening any database, BEFORE constructing any wiring, and AGAIN
AFTER the boot drill finishes. The assertion refuses to start
the cloud loop if any of the Phase 1 safety flags has drifted, if
the four ExchangeClientBase write surfaces are not still refusing
with :class:`SafeModeViolation`, or if a paper-cloud config asserts
something that contradicts the resolved :class:`Settings`.

Phase 11B never modifies :class:`app.config.settings.Settings`; the
Phase 1 safety lock keeps the five trading flags coerced. This
module only AUDITS the resolved values - the cloud process is the
last line of defence before the operator pushes a deploy.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import Settings
from app.core.errors import SafeModeViolation, SafetyViolation
from app.exchanges.base import (
    WRITE_SURFACE_METHODS,
    ExchangeClientBase,
)
from app.paper_run.config import PaperCloudConfig


@dataclass(frozen=True)
class SafetyAssertionReport:
    """Outcome of one safety assertion pass.

    ``passed`` is False iff the assertion raises; we still expose this
    dataclass so the supervisor + tests can reason about WHICH
    invariants were checked without re-running them.
    """

    trading_mode_paper: bool
    live_trading_enabled_false: bool
    right_tail_enabled_false: bool
    llm_enabled_false: bool
    exchange_live_order_enabled_false: bool
    write_surfaces_refuse: bool
    paper_cloud_yaml_consistent: bool
    real_order_enabled_false: bool

    @property
    def passed(self) -> bool:
        return all(
            (
                self.trading_mode_paper,
                self.live_trading_enabled_false,
                self.right_tail_enabled_false,
                self.llm_enabled_false,
                self.exchange_live_order_enabled_false,
                self.write_surfaces_refuse,
                self.paper_cloud_yaml_consistent,
                self.real_order_enabled_false,
            )
        )


def assert_paper_cloud_safety(
    *,
    settings: Settings,
    paper_cloud: PaperCloudConfig,
    exchange_client: ExchangeClientBase | None = None,
) -> SafetyAssertionReport:
    """Refuse to boot the supervisor if any safety invariant has drifted.

    Args:
        settings:    The resolved :class:`Settings` (after the Phase 1
                     ``_apply_phase1_safety_lock`` has run).
        paper_cloud: The Phase 11B paper-cloud configuration.
        exchange_client: Optional read-only client used to walk the
                     four write surfaces and confirm each still raises
                     :class:`SafeModeViolation`. Pass ``None`` to skip
                     this check (tests that do not wire an exchange
                     can still exercise the rest of the assertion).

    Returns:
        :class:`SafetyAssertionReport` describing every check.

    Raises:
        :class:`SafetyViolation`  - the Phase 1 safety lock has
                                    drifted in :class:`Settings`.
        :class:`SafeModeViolation` - one of the four write surfaces
                                    no longer refuses, or the
                                    ``paper_cloud.yaml`` asserts an
                                    unsafe value.
    """
    # 1. Phase 1 safety lock - must already be in effect.
    if settings.trading_mode != "paper":
        raise SafetyViolation(
            "Phase 11B refuses to boot: settings.trading_mode="
            f"{settings.trading_mode!r}, must be 'paper'."
        )
    if settings.live_trading_enabled:
        raise SafetyViolation(
            "Phase 11B refuses to boot: settings.live_trading_enabled "
            "must be False."
        )
    if settings.right_tail_enabled:
        raise SafetyViolation(
            "Phase 11B refuses to boot: settings.right_tail_enabled "
            "must be False."
        )
    if settings.llm_enabled:
        raise SafetyViolation(
            "Phase 11B refuses to boot: settings.llm_enabled must be "
            "False; LLM Guarded Interpreter remains receive-only."
        )
    if settings.exchange_live_order_enabled:
        raise SafetyViolation(
            "Phase 11B refuses to boot: "
            "settings.exchange_live_order_enabled must be False."
        )

    # 2. paper_cloud.yaml hard expectations - already validated at load
    # time, but we re-assert here so a drifted in-memory config also
    # fails fast.
    if paper_cloud.trading_mode != "paper":
        raise SafetyViolation(
            "paper_cloud.trading_mode must be 'paper'; "
            f"got {paper_cloud.trading_mode!r}"
        )
    if paper_cloud.live_trading_enabled:
        raise SafetyViolation(
            "paper_cloud.live_trading_enabled must be false"
        )
    if paper_cloud.right_tail_enabled:
        raise SafetyViolation(
            "paper_cloud.right_tail_enabled must be false"
        )
    if paper_cloud.exchange_live_order_enabled:
        raise SafetyViolation(
            "paper_cloud.exchange_live_order_enabled must be false"
        )
    if paper_cloud.llm_enabled:
        raise SafetyViolation(
            "paper_cloud.llm_enabled must be false"
        )
    if paper_cloud.real_order_enabled:
        raise SafetyViolation(
            "paper_cloud.real_order_enabled must be false"
        )

    # 3. The four ExchangeClientBase write surfaces still refuse with
    # SafeModeViolation. This is a Phase 3 invariant we re-verify on
    # every Phase 11B boot.
    write_surfaces_refuse = True
    if exchange_client is not None:
        exchange_client.assert_read_only()
        for fn_name in WRITE_SURFACE_METHODS:
            fn = getattr(exchange_client, fn_name, None)
            if fn is None:
                raise SafeModeViolation(
                    f"{exchange_client.name}.{fn_name} is missing; "
                    "Phase 3 contract requires all four write surfaces "
                    "to exist and refuse."
                )
            try:
                fn()
            except SafeModeViolation:
                continue
            raise SafeModeViolation(
                f"{exchange_client.name}.{fn_name} did NOT refuse a "
                "probe call. Phase 11B refuses to start."
            )

    return SafetyAssertionReport(
        trading_mode_paper=settings.trading_mode == "paper",
        live_trading_enabled_false=not settings.live_trading_enabled,
        right_tail_enabled_false=not settings.right_tail_enabled,
        llm_enabled_false=not settings.llm_enabled,
        exchange_live_order_enabled_false=(
            not settings.exchange_live_order_enabled
        ),
        write_surfaces_refuse=write_surfaces_refuse,
        paper_cloud_yaml_consistent=True,
        real_order_enabled_false=not paper_cloud.real_order_enabled,
    )


__all__ = [
    "SafetyAssertionReport",
    "assert_paper_cloud_safety",
]
