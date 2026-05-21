"""Phase 11C - Telegram outbound semantics.

Reviewer feedback fix: the Phase 11C accessor
``Settings.telegram_outbound_enabled`` previously returned
``defaults.telegram.enabled``. That conflated two concepts:

  - ``telegram.enabled``         - in-process command bus on/off
  - ``telegram.outbound_enabled`` - real Telegram HTTP outbound on/off

Phase 11C requires the second to remain False **independently** of the
first. This test module pins:

  1. ``telegram_outbound_enabled`` is False even when
     ``telegram.enabled=True`` (an operator may legitimately want the
     in-process FakeTelegramClient command-bus while real HTTP outbound
     stays off).
  2. The Phase 11C runner does NOT instantiate / import any real
     outbound transport. Only the FakeTelegramClient surface is
     reachable from the public-market read-only paper runner.
  3. The schema layer refuses ``telegram.outbound_enabled=True``
     outright.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config.schema import TelegramConfig
from app.config.settings import Settings, load_settings


ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# 1. telegram_outbound_enabled is independent of telegram.enabled
# ---------------------------------------------------------------------------
def test_phase11c_telegram_outbound_enabled_is_false_even_if_telegram_enabled_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Construct a Settings tree where ``telegram.enabled=True`` and
    confirm ``Settings.telegram_outbound_enabled`` STAYS False.

    The two flags are independent. Operator can wire the in-process
    command bus (which uses :class:`FakeTelegramClient` and never
    opens a socket) without ever enabling real HTTP outbound.
    """
    settings = load_settings()

    # Constructor-level: build a TelegramConfig with enabled=True but
    # outbound_enabled=False. This is the "in-process command bus only"
    # configuration. It must construct cleanly.
    tg = TelegramConfig(enabled=True, outbound_enabled=False)
    assert tg.enabled is True
    assert tg.outbound_enabled is False

    # Inject that into a fresh Settings tree.
    flipped_defaults = settings.defaults.model_copy(update={"telegram": tg})
    flipped = Settings(
        defaults=flipped_defaults,
        risk=settings.risk,
        strategy=settings.strategy,
        project_root=settings.project_root,
    )

    # Phase 11C invariant: outbound stays False regardless of
    # telegram.enabled.
    assert flipped.defaults.telegram.enabled is True
    assert flipped.defaults.telegram.outbound_enabled is False
    assert flipped.telegram_outbound_enabled is False, (
        "Phase 11C: telegram_outbound_enabled must remain False even "
        "when telegram.enabled is True"
    )


def test_phase11c_schema_refuses_to_load_outbound_enabled_true():
    """The Phase 11C schema validator refuses any
    ``telegram.outbound_enabled=True`` value at construction time."""
    with pytest.raises(ValidationError):
        TelegramConfig(outbound_enabled=True)
    # Even with enabled=True the schema MUST refuse outbound_enabled=True.
    with pytest.raises(ValidationError):
        TelegramConfig(enabled=True, outbound_enabled=True)


def test_phase11c_default_settings_have_both_flags_false():
    """The shipped ``defaults.yaml`` must have both flags False."""
    settings = load_settings()
    assert settings.defaults.telegram.enabled is False
    assert settings.defaults.telegram.outbound_enabled is False
    assert settings.telegram_outbound_enabled is False


# ---------------------------------------------------------------------------
# 2. The Phase 11C runner only uses the FakeTelegramClient surface
# ---------------------------------------------------------------------------
PHASE_11C_RUNTIME_FILES = [
    ROOT / "app" / "exchanges" / "binance_public.py",
    ROOT / "app" / "market_data_public" / "__init__.py",
    ROOT / "app" / "market_data_public" / "ingest.py",
    ROOT / "app" / "market_data_public" / "event_chain.py",
    ROOT / "scripts" / "run_public_market_paper.py",
]


def test_phase11c_fake_telegram_only_no_real_outbound():
    """The Phase 11C runtime source set must NOT import or instantiate
    any real outbound transport.

    Phase 10D ships :class:`FakeTelegramClient` (in-process recorder)
    and :class:`TelegramHttpClient` (refusal-only HTTP skeleton). The
    Phase 11C runner does not need EITHER - the public-market
    read-only runner is purely a market-data pipeline. We assert
    here that:

      - no Phase 11C source file imports :class:`TelegramHttpClient`
      - no Phase 11C source file imports :class:`AlertDispatcher` or
        :class:`TelegramExportBridge` or :class:`TelegramCommandCenter`
      - no Phase 11C source file calls ``send_message`` /
        ``send_document`` / ``send_photo``

    If a future Phase 11C+ change wants to wire a Telegram client, it
    MUST construct the deterministic :class:`FakeTelegramClient`
    explicitly; this test will catch any drift toward
    :class:`TelegramHttpClient` or any other real outbound surface.
    """
    forbidden_class_imports = {
        "TelegramHttpClient",
        "TelegramOutboundClient",
        "AlertDispatcher",
        "TelegramExportBridge",
        "TelegramCommandCenter",
    }
    forbidden_call_names = {
        "send_message",
        "send_document",
        "send_photo",
    }

    for path in PHASE_11C_RUNTIME_FILES:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            # ImportFrom: ``from app.telegram.outbound import TelegramHttpClient``
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    assert alias.name not in forbidden_class_imports, (
                        f"{path.relative_to(ROOT)} imports forbidden "
                        f"outbound class {alias.name}"
                    )
            # Bare ``import app.telegram.outbound`` is also forbidden
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "telegram" not in (alias.name or "").lower(), (
                        f"{path.relative_to(ROOT)} imports {alias.name}; "
                        "Phase 11C runtime must not import the Telegram "
                        "package directly"
                    )
            # Function-call surface
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr in forbidden_call_names:
                        raise AssertionError(
                            f"{path.relative_to(ROOT)} calls "
                            f".{node.func.attr}() which is a real "
                            "Telegram outbound surface; Phase 11C "
                            "runner must never call it"
                        )
                elif isinstance(node.func, ast.Name):
                    if node.func.id in forbidden_call_names:
                        raise AssertionError(
                            f"{path.relative_to(ROOT)} calls "
                            f"{node.func.id}(); Phase 11C runner must "
                            "never call a Telegram outbound surface"
                        )


def test_phase11c_runner_text_does_not_mention_real_telegram_transport():
    """Source-tree paranoia: even a stray docstring / comment that
    mentions :class:`TelegramHttpClient` would betray drift.
    Allowed mentions are confined to test files, not the runtime
    source set."""
    forbidden_substrings = (
        "TelegramHttpClient(",
        "TelegramHttpClient()",
        ".send_message(",
        ".send_document(",
        ".send_photo(",
    )
    for path in PHASE_11C_RUNTIME_FILES:
        text = path.read_text(encoding="utf-8")
        for needle in forbidden_substrings:
            assert needle not in text, (
                f"{path.relative_to(ROOT)} contains forbidden "
                f"outbound literal {needle!r}; Phase 11C runner MUST "
                "NOT instantiate or call any real Telegram transport"
            )



# ---------------------------------------------------------------------------
# 3. The Phase 11C runner banner reads from outbound_enabled, not enabled
# ---------------------------------------------------------------------------
def test_phase11c_runner_banner_reads_telegram_outbound_enabled_from_outbound_enabled_field(
    capsys: pytest.CaptureFixture[str],
):
    """The Phase 11C runner banner emitted by
    ``scripts.run_public_market_paper._print_banner`` must report
    ``telegram_outbound_enabled`` from the
    ``defaults.telegram.outbound_enabled`` field, NOT from
    ``defaults.telegram.enabled``.

    Concretely: an operator who flips ``telegram.enabled=True`` to
    wire the in-process FakeTelegramClient command-bus must still
    see ``telegram_outbound_enabled=False`` in the banner. If the
    accessor ever regresses to reading ``defaults.telegram.enabled``
    again, this test fails because the banner would print
    ``telegram_outbound_enabled=True``.
    """
    # Late import: the runner script does sys.path.insert at import
    # time, but importing it under pytest is harmless.
    from types import SimpleNamespace

    from scripts.run_public_market_paper import _print_banner

    settings = load_settings()

    # Build a Settings tree where telegram.enabled=True but
    # outbound_enabled=False - the legitimate "in-process command
    # bus only" configuration. Passes the schema validator (which
    # only refuses outbound_enabled=True).
    tg = TelegramConfig(enabled=True, outbound_enabled=False)
    flipped_defaults = settings.defaults.model_copy(update={"telegram": tg})
    flipped = Settings(
        defaults=flipped_defaults,
        risk=settings.risk,
        strategy=settings.strategy,
        project_root=settings.project_root,
    )

    # Sanity: the two flags really are different here.
    assert flipped.defaults.telegram.enabled is True
    assert flipped.defaults.telegram.outbound_enabled is False

    # Stub a BinancePublicClient-shaped object - the banner only reads
    # ``rest_base_url``.
    fake_client = SimpleNamespace(rest_base_url="https://fapi.binance.com")

    _print_banner(
        settings=flipped,
        client=fake_client,
        symbols=["BTCUSDT"],
        duration_seconds=60.0,
        poll_interval=5.0,
        dry_run=True,
        env_report_passed=True,
    )

    captured = capsys.readouterr().out

    # The banner must print outbound_enabled=False, NOT True. If a
    # future regression makes Settings.telegram_outbound_enabled
    # read .enabled again, the banner would print True here.
    assert "telegram_outbound_enabled=False" in captured, (
        "Phase 11C runner banner must report "
        "telegram_outbound_enabled=False when "
        "telegram.outbound_enabled=False, regardless of "
        "telegram.enabled. Banner was: " + captured
    )
    assert "telegram_outbound_enabled=True" not in captured, (
        "Phase 11C runner banner must NOT report "
        "telegram_outbound_enabled=True - the accessor has "
        "regressed to reading telegram.enabled. Banner was: "
        + captured
    )


def test_phase11c_runner_banner_field_sourced_from_settings_property(
    capsys: pytest.CaptureFixture[str],
):
    """Belt-and-braces companion to the test above: if
    ``Settings.telegram_outbound_enabled`` is True, the banner must
    print True. Confirms the banner is bound to the property (not
    a literal) so the previous test isn't tautological.

    We can't get the property to True without violating the schema
    validator (which is the whole point of Phase 11C), so we monkey
    patch the descriptor at the class level for this single test.
    """
    from types import SimpleNamespace
    from unittest.mock import PropertyMock, patch

    from scripts.run_public_market_paper import _print_banner

    settings = load_settings()
    fake_client = SimpleNamespace(rest_base_url="https://fapi.binance.com")

    # Force the property to report True for the duration of the
    # call. This proves the banner is dynamically bound to the
    # accessor; the previous test then proves the accessor is
    # bound to outbound_enabled.
    with patch.object(
        Settings,
        "telegram_outbound_enabled",
        new_callable=PropertyMock,
        return_value=True,
    ):
        _print_banner(
            settings=settings,
            client=fake_client,
            symbols=["BTCUSDT"],
            duration_seconds=60.0,
            poll_interval=5.0,
            dry_run=True,
            env_report_passed=True,
        )

    captured = capsys.readouterr().out
    assert "telegram_outbound_enabled=True" in captured
