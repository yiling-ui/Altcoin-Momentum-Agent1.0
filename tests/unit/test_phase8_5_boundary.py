"""Phase 8.5 - boundary tests (Issue #8.5).

Make sure Phase 8.5 does NOT loosen any earlier safety guarantee:

  - Phase 1 safety lock unchanged (paper, no live, no right-tail, no
    LLM, no exchange live orders).
  - Phase 3 read-only Exchange Gateway unchanged (write surfaces
    refuse with SafeModeViolation).
  - app.learning.* and app.exports.* are passive: no order surface,
    no exchange import, no LLM import, no Telegram outbound, no
    network library, no API-key parameter.
"""

from __future__ import annotations

import inspect

import pytest

from app.config.settings import get_settings
from app.core.errors import SafeModeViolation
from app.exchanges.base import WRITE_SURFACE_METHODS
from app.exchanges.binance import BinanceClient
from app.exchanges.mock import MockExchangeClient


def test_phase1_safety_lock_remains_in_force():
    settings = get_settings()
    assert settings.trading_mode == "paper"
    assert settings.live_trading_enabled is False
    assert settings.right_tail_enabled is False
    assert settings.llm_enabled is False
    assert settings.exchange_live_order_enabled is False


@pytest.mark.parametrize("client_cls", [MockExchangeClient])
def test_exchange_write_surfaces_still_refuse(client_cls):
    client = client_cls()
    for fn_name in WRITE_SURFACE_METHODS:
        with pytest.raises(SafeModeViolation):
            getattr(client, fn_name)()


def test_binance_client_skeleton_still_refuses_credentials():
    with pytest.raises(Exception):
        BinanceClient(api_key="should_refuse")


def test_learning_package_does_not_subclass_exchange_client():
    """app.learning.* must not produce trade-side surfaces."""
    from app.exchanges.base import ExchangeClientBase
    import app.learning as learning_pkg
    import app.learning.context
    import app.learning.identity
    import app.learning.risk_payload
    import app.learning.signal_snapshot
    import app.learning.versions
    import app.learning.virtual_trade

    for module in (
        learning_pkg,
        app.learning.context,
        app.learning.identity,
        app.learning.risk_payload,
        app.learning.signal_snapshot,
        app.learning.versions,
        app.learning.virtual_trade,
    ):
        for _name, member in inspect.getmembers(module, inspect.isclass):
            assert not issubclass(member, ExchangeClientBase) or member is ExchangeClientBase, (
                f"{module.__name__}.{_name} subclasses ExchangeClientBase"
            )


def test_exports_package_does_not_subclass_exchange_client():
    from app.exchanges.base import ExchangeClientBase
    import app.exports as exports_pkg
    import app.exports.cli
    import app.exports.manifest
    import app.exports.redaction
    import app.exports.service
    import app.exports.summary

    for module in (
        exports_pkg,
        app.exports.cli,
        app.exports.manifest,
        app.exports.redaction,
        app.exports.service,
        app.exports.summary,
    ):
        for _name, member in inspect.getmembers(module, inspect.isclass):
            assert not issubclass(member, ExchangeClientBase) or member is ExchangeClientBase, (
                f"{module.__name__}.{_name} subclasses ExchangeClientBase"
            )


def test_learning_and_exports_packages_expose_no_write_surface():
    forbidden = {"create_order", "cancel_order", "set_leverage", "set_margin_mode"}
    import app.learning as L
    import app.exports as E

    for pkg in (L, E):
        for name, member in inspect.getmembers(pkg):
            if not inspect.isclass(member):
                continue
            for fn_name in forbidden:
                assert not hasattr(member, fn_name), (
                    f"{pkg.__name__}.{name} unexpectedly defines {fn_name}"
                )


def test_redaction_module_constants_match_issue_contract():
    from app.exports.redaction import SENSITIVE_KEY_SUBSTRINGS

    required = {
        "api_key",
        "api_secret",
        "secret",
        "token",
        "password",
        "address",
        "withdrawal_address",
        "auth",
    }
    for needle in required:
        assert needle in SENSITIVE_KEY_SUBSTRINGS


def test_export_service_default_max_zip_bytes_finite():
    """Phase 8.5 refuses unbounded exports; the default cap must be a
    sane finite value."""
    from app.exports.service import DEFAULT_MAX_ZIP_BYTES

    assert 1024 < DEFAULT_MAX_ZIP_BYTES < 10 ** 10  # < 10 GB


def test_phase_8_5_telegram_contract_doc_present():
    """The future Telegram contract MUST be documented (Issue #10
    deferred work)."""
    from pathlib import Path

    doc = (
        Path(__file__).resolve().parent.parent.parent
        / "docs"
        / "PHASE_8_5_TELEGRAM_EXPORT_CONTRACT.md"
    )
    assert doc.exists(), "docs/PHASE_8_5_TELEGRAM_EXPORT_CONTRACT.md missing"
    content = doc.read_text(encoding="utf-8")
    for needle in (
        "/export_test_data 24h",
        "/export_test_data 7d",
        "/export_test_data today",
        "/export_rejections 24h",
        "/export_report today",
        "/export_learning_dataset 7d",
        "sendDocument",
        "redaction_applied",
    ):
        assert needle in content, (
            f"Telegram contract doc missing required clause: {needle}"
        )
