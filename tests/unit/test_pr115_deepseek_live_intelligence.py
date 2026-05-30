"""PR115 - DeepSeek Live Intelligence v0 tests (fake DeepSeek transport only).

Covers the 26 required scenarios:

  1-5.  Evidence bundle accepts LIVE / rejects BLIND / REPLAY / SIM /
         PAPER_SHADOW source.
  6.     AI prompt excludes trade authority.
  7-11.  AI output with should_buy / direction / leverage / stop_price /
         runtime_config_patch is rejected / stripped.
  12.    Valid briefing has ai_trade_authority=false.
  13.    Missing DeepSeek key returns disabled / missing secret.
  14.    DeepSeek HTTP failure returns a safe error.
  15.    /ai_status returns MARKET_INTELLIGENCE_ONLY.
  16.    /brief does not create an order intent.
  17.    /explain_position does not recommend hold / add / close.
  18.    /summarize_pnl includes commission and funding.
  19.    /summarize_rejections does not suggest bypass.
  20.    AI cannot call LiveExecutionGateway.
  21.    AI cannot change runtime mode.
  22.    AI cannot change capital profile.
  23.    AI cannot trigger a Telegram live order command.
  24.    Telegram AI briefing card includes ai_trade_authority=false.
  25.    Safety flags remain false.
  26.    (covered by the rest of tests/unit) PR110-114 tests still pass.

No real network call is made anywhere in this module.
"""

from __future__ import annotations

import json

import pytest

from app.core.enums import LiveRuntimeMode, OrderSource
from app.core.errors import LiveApiError
from app.core.events import Event, EventType
from app.live.ai_live_briefing import (
    LIVE_AI_SYSTEM_PROMPT,
    LiveAIBriefingGenerator,
    build_prompt_messages,
)
from app.live.ai_live_evidence import (
    FORBIDDEN_EVIDENCE_SOURCES,
    build_live_ai_evidence_bundle,
)
from app.live.ai_output_guard import (
    ALLOWED_BRIEFING_FIELDS,
    FORBIDDEN_OUTPUT_FIELDS,
    BriefingStatus,
    sanitize_ai_output,
)
from app.live.ai_telegram import AIBriefingTelegram, AICardType
from app.live.api_config import LiveApiConfig

FAKE_KEY = "sk-fake-deepseek-key-not-real-00000000000000000000"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeEventRepo:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, event: Event) -> None:
        self.events.append(event)

    def types(self):
        return [e.event_type for e in self.events]


class FakeDeepSeekTransport:
    """Records calls; returns a canned chat-completion response."""

    def __init__(self, response, *, fail_if_called: bool = False, raise_exc=None) -> None:
        self.response = response
        self.calls: list[tuple[str, dict]] = []
        self.fail_if_called = fail_if_called
        self.raise_exc = raise_exc

    def __call__(self, url: str, headers, body):
        if self.fail_if_called:
            raise AssertionError("deepseek transport must NOT be called")
        self.calls.append((url, dict(body)))
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response


def _chat_response(content: dict) -> dict:
    return {
        "model": "deepseek-chat",
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        "choices": [{"message": {"role": "assistant", "content": json.dumps(content)}}],
    }


def _enabled_cfg(extra: dict | None = None) -> LiveApiConfig:
    env = {"AMA_DEEPSEEK_API_KEY": FAKE_KEY, "AMA_DEEPSEEK_ENABLED": "true"}
    if extra:
        env.update(extra)
    return LiveApiConfig.from_env(env)


def _good_bundle(**kwargs):
    base = dict(
        runtime_mode=LiveRuntimeMode.LIVE_SHADOW,
        capital_profile_id="L1_10U_PROBE",
        account_status={"account_equity_usdt": 10.0, "available_balance_usdt": 9.0,
                        "open_position_count": 1},
        pnl_summary={
            "gross_realized_pnl_usdt": 2.0,
            "commission_total_usdt": 0.4,
            "funding_total_usdt": -0.1,
            "net_strategy_pnl_usdt": 1.5,
            "external_deposit_total_usdt": 10.0,
            "external_withdrawal_total_usdt": 0.0,
        },
        open_positions=[{"symbol": "RAVEUSDT", "side": "LONG", "notional_usdt": 8.0,
                         "unrealized_pnl": 0.3, "leverage": 5.0}],
        risk_summary={"profile_status": "PROFILE_OK", "flags": [], "risk_halt_active": False,
                      "max_leverage": 5.0},
        recent_order_summary={"reject_reasons": ["runtime_mode_shadow_no_real_order"]},
        funding_summary={"funding_total_usdt": -0.1, "funding_attribution_status": "ACCOUNT_LEVEL_ONLY"},
        telegram_state={"runtime_mode": "LIVE_SHADOW", "paused": False},
        api_health_summary={"overall_status": "PASS"},
        sources=["LIVE", "BINANCE_PRIVATE_READ", "LIVE_CAPITAL_STATE", "LIVE_PNL_SUMMARY"],
    )
    base.update(kwargs)
    return build_live_ai_evidence_bundle(**base)


# ---------------------------------------------------------------------------
# 1-5: Evidence bundle source rules
# ---------------------------------------------------------------------------
def test_evidence_bundle_accepts_live_source():
    repo = FakeEventRepo()
    result = build_live_ai_evidence_bundle(
        runtime_mode=LiveRuntimeMode.LIVE_SHADOW,
        capital_profile_id="L1_10U_PROBE",
        account_status={"account_equity_usdt": 10.0},
        sources=[OrderSource.LIVE],
        event_repo=repo,
    )
    assert result.accepted is True
    assert result.bundle is not None
    assert result.bundle.source_scope == "LIVE_ONLY"
    assert result.bundle.ai_trade_authority is False
    assert result.bundle.to_dict()["ai_trade_authority"] is False
    assert EventType.LIVE_AI_EVIDENCE_REJECTED_FOR_NONLIVE_SOURCE not in repo.types()


@pytest.mark.parametrize(
    "bad_source",
    [OrderSource.BLIND, OrderSource.REPLAY, OrderSource.SIM, OrderSource.PAPER_SHADOW],
)
def test_evidence_bundle_rejects_non_live_source(bad_source):
    repo = FakeEventRepo()
    result = build_live_ai_evidence_bundle(
        runtime_mode=LiveRuntimeMode.LIVE_SHADOW,
        capital_profile_id="L1_10U_PROBE",
        account_status={"account_equity_usdt": 10.0},
        sources=[OrderSource.LIVE, bad_source],
        event_repo=repo,
    )
    assert result.accepted is False
    assert result.bundle is None
    assert bad_source.value in result.forbidden_sources_detected
    assert EventType.LIVE_AI_EVIDENCE_REJECTED_FOR_NONLIVE_SOURCE in repo.types()


def test_evidence_bundle_rejects_simulation_module_names():
    # The simulation / blind / replay / paper-shadow class names are forbidden.
    for name in ("HistoricalMarketStore", "ReplayFeedProvider", "MockExchange",
                 "TELEGRAM_SANDBOX", "BACKTEST", "OFFLINE_AI"):
        result = build_live_ai_evidence_bundle(sources=["LIVE", name])
        assert result.accepted is False, name
    # Every forbidden label is recognised.
    assert "BLIND" in FORBIDDEN_EVIDENCE_SOURCES


def test_evidence_bundle_unknown_source_fails_safe():
    # Unknown provenance is treated as forbidden (fail-safe).
    result = build_live_ai_evidence_bundle(sources=["MYSTERY_FEED"])
    assert result.accepted is False


# ---------------------------------------------------------------------------
# 6: AI prompt excludes trade authority
# ---------------------------------------------------------------------------
def test_ai_prompt_excludes_trade_authority():
    bundle = _good_bundle().bundle
    messages = build_prompt_messages(bundle)
    system = messages[0]["content"]
    user = messages[1]["content"]
    # The system prompt declares market-intelligence only + no trade decisions.
    assert "MARKET_INTELLIGENCE_ONLY" in system
    assert "CANNOT decide trades" in system
    assert "CANNOT output leverage" in system
    # The requested output schema never asks for a trade-authority field.
    requested = set(ALLOWED_BRIEFING_FIELDS)
    assert requested.isdisjoint(FORBIDDEN_OUTPUT_FIELDS)
    for forbidden in ("should_buy", "direction", "leverage", "stop_price", "order_type"):
        # The forbidden field is never a *requested* JSON key.
        assert f'"{forbidden}":' not in user.split("LIVE EVIDENCE")[0]


# ---------------------------------------------------------------------------
# 7-11: forbidden output fields are rejected / stripped
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "forbidden_field,value",
    [
        ("should_buy", True),
        ("direction", "long"),
        ("leverage", 20),
        ("stop_price", 59000),
        ("runtime_config_patch", {"symbol_limit": 50}),
    ],
)
def test_ai_output_forbidden_field_rejected(forbidden_field, value):
    repo = FakeEventRepo()
    payload = {"market_summary": "looks hot", forbidden_field: value}
    guard = sanitize_ai_output(payload, event_repo=repo)
    assert forbidden_field in guard.forbidden_fields_detected
    assert forbidden_field not in guard.clean_payload
    assert guard.clean_payload["market_summary"] == "looks hot"
    assert guard.status == BriefingStatus.REJECTED_FOR_TRADE_AUTHORITY
    assert guard.ai_trade_authority is False
    assert EventType.AI_FORBIDDEN_FIELD_STRIPPED in repo.types()
    assert EventType.DEEPSEEK_OUTPUT_REJECTED_FOR_TRADE_AUTHORITY in repo.types()


def test_ai_output_strips_nested_and_case_insensitive():
    payload = {
        "market_summary": "ok",
        "nested": {"Should_Buy": True, "LEVERAGE": 10, "note": "keep"},
        "strategy_patch": {"x": 1},
    }
    guard = sanitize_ai_output(payload)
    assert guard.had_forbidden_fields
    assert guard.clean_payload["nested"] == {"note": "keep"}
    assert "strategy_patch" not in guard.clean_payload


def test_full_generate_strips_forbidden_and_marks_rejected():
    repo = FakeEventRepo()
    transport = FakeDeepSeekTransport(
        _chat_response(
            {
                "market_summary": "BTC sideways",
                "should_sell": True,
                "target_price": 1.23,
                "execute": "yes",
            }
        )
    )
    gen = LiveAIBriefingGenerator(
        _enabled_cfg().deepseek, transport=transport, event_repo=repo
    )
    briefing = gen.generate(_good_bundle().bundle)
    assert briefing.status == BriefingStatus.REJECTED_FOR_TRADE_AUTHORITY
    assert briefing.ai_trade_authority is False
    assert "should_sell" in briefing.forbidden_fields_detected
    # The clean summary survives; no forbidden field is ever a briefing key.
    d = briefing.to_dict()
    assert d["market_summary"] == "BTC sideways"
    assert set(d).isdisjoint(FORBIDDEN_OUTPUT_FIELDS)


# ---------------------------------------------------------------------------
# 12: valid briefing has ai_trade_authority=false
# ---------------------------------------------------------------------------
def test_valid_briefing_ai_trade_authority_false():
    repo = FakeEventRepo()
    transport = FakeDeepSeekTransport(
        _chat_response(
            {
                "market_summary": "Alt liquidity contracting.",
                "risk_summary": "Funding neutral; profile capped at 10U.",
                "operator_notes": "Observe; no clear right-tail setup.",
                "evidence_quality": "STRONG",
            }
        )
    )
    gen = LiveAIBriefingGenerator(
        _enabled_cfg().deepseek, transport=transport, event_repo=repo
    )
    briefing = gen.generate(_good_bundle().bundle)
    assert briefing.status == BriefingStatus.OK
    assert briefing.ai_trade_authority is False
    d = briefing.to_dict()
    assert d["ai_trade_authority"] is False
    assert d["authority"] == "MARKET_INTELLIGENCE_ONLY"
    assert d["source_scope"] == "LIVE_ONLY"
    assert briefing.actionable is False
    assert EventType.LIVE_AI_BRIEFING_GENERATED in repo.types()
    # The key only travels in the Authorization header, never in the body.
    assert all(FAKE_KEY not in str(body) for _, body in transport.calls)


# ---------------------------------------------------------------------------
# 13: missing key -> disabled / missing secret
# ---------------------------------------------------------------------------
def test_missing_key_returns_missing_secret_no_crash():
    repo = FakeEventRepo()
    cfg = LiveApiConfig.from_env({"AMA_DEEPSEEK_ENABLED": "true"})  # enabled, no key
    transport = FakeDeepSeekTransport(None, fail_if_called=True)
    gen = LiveAIBriefingGenerator(cfg.deepseek, transport=transport, event_repo=repo)
    briefing = gen.generate(_good_bundle().bundle)
    assert briefing.status == BriefingStatus.MISSING_SECRET
    assert briefing.ai_trade_authority is False
    assert transport.calls == []
    assert EventType.LIVE_AI_BRIEFING_FAILED in repo.types()


def test_disabled_returns_disabled_no_crash():
    cfg = LiveApiConfig.from_env(
        {"AMA_DEEPSEEK_API_KEY": FAKE_KEY, "AMA_DEEPSEEK_ENABLED": "false"}
    )
    transport = FakeDeepSeekTransport(None, fail_if_called=True)
    gen = LiveAIBriefingGenerator(cfg.deepseek, transport=transport)
    briefing = gen.generate(_good_bundle().bundle)
    assert briefing.status == BriefingStatus.DISABLED
    assert transport.calls == []


# ---------------------------------------------------------------------------
# 14: HTTP failure -> safe error
# ---------------------------------------------------------------------------
def test_http_failure_returns_safe_error():
    repo = FakeEventRepo()
    transport = FakeDeepSeekTransport(None, raise_exc=LiveApiError("deepseek: HTTP error 500"))
    gen = LiveAIBriefingGenerator(_enabled_cfg().deepseek, transport=transport, event_repo=repo)
    briefing = gen.generate(_good_bundle().bundle)
    assert briefing.status == BriefingStatus.ERROR
    assert "HTTP error 500" in briefing.error_message
    assert briefing.ai_trade_authority is False
    assert EventType.LIVE_AI_BRIEFING_FAILED in repo.types()


# ---------------------------------------------------------------------------
# Telegram fixtures
# ---------------------------------------------------------------------------
def _telegram(repo, *, content: dict | None = None, transport=None):
    cfg = _enabled_cfg()
    if transport is None:
        transport = FakeDeepSeekTransport(
            _chat_response(content or {"market_summary": "ok", "risk_summary": "ok",
                                       "position_notes": "RAVEUSDT open", "evidence_quality": "STRONG"})
        )
    gen = LiveAIBriefingGenerator(cfg.deepseek, transport=transport, event_repo=repo)
    provider = lambda: _good_bundle()  # noqa: E731
    return AIBriefingTelegram(generator=gen, evidence_provider=provider, event_repo=repo)


# ---------------------------------------------------------------------------
# 15: /ai_status returns MARKET_INTELLIGENCE_ONLY
# ---------------------------------------------------------------------------
def test_ai_status_market_intelligence_only():
    repo = FakeEventRepo()
    tg = _telegram(repo)
    result = tg.handle("/ai_status")
    assert result.ok is True
    assert result.card["card_type"] == AICardType.AI_STATUS
    assert result.card["authority"] == "MARKET_INTELLIGENCE_ONLY"
    assert result.card["ai_trade_authority"] is False
    assert result.card["source_scope"] == "LIVE_ONLY"
    assert "MARKET_INTELLIGENCE_ONLY" in result.text


# ---------------------------------------------------------------------------
# 16: /brief does not create an order intent
# ---------------------------------------------------------------------------
def test_brief_no_order_intent():
    repo = FakeEventRepo()
    tg = _telegram(repo)
    result = tg.handle("/brief")
    assert result.ok is True
    assert result.card["card_type"] == AICardType.AI_BRIEFING
    assert result.card["no_order_instruction"] is True
    assert result.card["recommends_action"] is False
    assert result.card["real_order"] is False
    assert result.card["ai_trade_authority"] is False
    # No order / execution event was ever emitted by the AI handler.
    order_events = {
        EventType.LIVE_ORDER_SUBMITTED,
        EventType.LIVE_ORDER_SUBMIT_REQUESTED,
        EventType.ORDER_SENT,
    }
    assert order_events.isdisjoint(set(repo.types()))
    assert EventType.AI_TELEGRAM_BRIEFING_SENT in repo.types()


# ---------------------------------------------------------------------------
# 17: /explain_position does not recommend hold/add/close
# ---------------------------------------------------------------------------
def test_explain_position_no_recommendation():
    repo = FakeEventRepo()
    tg = _telegram(repo)
    result = tg.handle("/explain_position RAVEUSDT")
    assert result.ok is True
    assert result.card["card_type"] == AICardType.AI_POSITION_EXPLANATION
    assert result.card["symbol"] == "RAVEUSDT"
    assert result.card["recommends_action"] is False
    assert result.card["no_order_instruction"] is True
    note = result.card["note"].lower()
    assert "no hold" in note and "close" in note  # explicit non-recommendation


# ---------------------------------------------------------------------------
# 18: /summarize_pnl includes commission and funding
# ---------------------------------------------------------------------------
def test_summarize_pnl_includes_commission_and_funding():
    repo = FakeEventRepo()
    tg = _telegram(repo)
    result = tg.handle("/summarize_pnl")
    assert result.ok is True
    assert result.card["card_type"] == AICardType.AI_PNL_SUMMARY
    assert result.card["commission_total"] == 0.4
    assert result.card["funding_total"] == -0.1
    assert result.card["net_strategy_pnl"] == 1.5
    # deposits / withdrawals are kept separate.
    assert result.card["deposits"] == 10.0
    assert result.card["withdrawals"] == 0.0


# ---------------------------------------------------------------------------
# 19: /summarize_rejections does not suggest bypass
# ---------------------------------------------------------------------------
def test_summarize_rejections_no_bypass():
    repo = FakeEventRepo()
    tg = _telegram(repo)
    result = tg.handle("/summarize_rejections")
    assert result.ok is True
    assert result.card["card_type"] == AICardType.AI_REJECTION_SUMMARY
    assert result.card["no_bypass_suggested"] is True
    assert "bypass" in result.card["note"].lower()
    assert result.card["recommends_action"] is False


# ---------------------------------------------------------------------------
# 20: AI cannot call LiveExecutionGateway
# ---------------------------------------------------------------------------
def test_ai_cannot_call_execution_gateway():
    # The AI modules never IMPORT or CALL the execution gateway / adapter.
    # (Docstrings may *name* the gateway as a forbidden surface; we only
    # forbid real import lines and call sites.)
    import app.live.ai_live_briefing as brief_mod
    import app.live.ai_telegram as tg_mod
    import app.live.ai_output_guard as guard_mod
    import app.live.ai_live_evidence as ev_mod

    banned_imports = ("execution_gateway", "binance_execution_adapter", "order_ledger")
    banned_calls = ("LiveExecutionGateway(", "BinanceExecutionAdapter(", ".submit_order(")
    for mod in (brief_mod, tg_mod, guard_mod, ev_mod):
        src = open(mod.__file__, encoding="utf-8").read()
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                for banned in banned_imports:
                    assert banned not in stripped, f"{mod.__name__}: {stripped}"
        for call in banned_calls:
            assert call not in src, f"{mod.__name__} calls {call}"


# ---------------------------------------------------------------------------
# 21-23: AI cannot change mode / profile / trigger live command
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "cmd",
    [
        "/mode live_limited",
        "/confirm_live LIVE-DEADBEEF",
        "/kill_all",
        "/profile set L3_100U_ATTACK_TEST",
        "/order BUY RAVEUSDT",
        "/buy RAVEUSDT",
    ],
)
def test_ai_blocks_live_and_state_changing_commands(cmd):
    repo = FakeEventRepo()
    tg = _telegram(repo)
    result = tg.handle(cmd)
    assert result.ok is False
    assert result.blocked is True
    assert result.card["card_type"] == AICardType.AI_COMMAND_BLOCKED
    assert EventType.AI_TELEGRAM_BRIEFING_BLOCKED in repo.types()
    # No mode / profile / kill events were emitted by the AI handler.
    forbidden_events = {
        EventType.LIVE_MODE_CHANGED,
        EventType.LIVE_MODE_SWITCH_CONFIRMED,
        EventType.CAPITAL_PROFILE_CHANGED,
        EventType.LIVE_KILL_SWITCH,
        EventType.LIVE_ORDER_SUBMITTED,
    }
    assert forbidden_events.isdisjoint(set(repo.types()))


def test_ai_non_live_source_blocked():
    repo = FakeEventRepo()
    tg = _telegram(repo)
    for bad in (OrderSource.SIM, OrderSource.BLIND, OrderSource.TELEGRAM_SANDBOX):
        result = tg.handle("/brief", source=bad)
        assert result.blocked is True
        assert result.reason == "non_live_source_rejected"
    assert EventType.AI_TELEGRAM_BRIEFING_BLOCKED in repo.types()


def test_ai_brief_blocked_when_briefing_leaks_trade_authority():
    repo = FakeEventRepo()
    # The model leaks a forbidden field -> briefing rejected -> not actionable.
    tg = _telegram(repo, content={"market_summary": "hot", "should_long": True})
    result = tg.handle("/brief")
    assert result.blocked is True
    assert result.reason == BriefingStatus.REJECTED_FOR_TRADE_AUTHORITY
    assert result.card["blocked_reason"] == BriefingStatus.REJECTED_FOR_TRADE_AUTHORITY
    assert EventType.AI_TELEGRAM_BRIEFING_BLOCKED in repo.types()


# ---------------------------------------------------------------------------
# 24: Telegram AI briefing card includes ai_trade_authority=false
# ---------------------------------------------------------------------------
def test_telegram_ai_card_includes_markers():
    repo = FakeEventRepo()
    tg = _telegram(repo)
    for cmd in ("/brief", "/explain_risk", "/summarize_pnl", "/summarize_rejections"):
        result = tg.handle(cmd)
        card = result.card
        assert card["ai_trade_authority"] is False
        assert card["source_scope"] == "LIVE_ONLY"
        assert card["header"] == "[AI Briefing / MARKET_INTELLIGENCE_ONLY]"
        assert card["no_order_instruction"] is True
        assert card["exchange_live_orders"] is False
        assert card["trade_authority"] is False


# ---------------------------------------------------------------------------
# 25: Safety flags remain false
# ---------------------------------------------------------------------------
def test_safety_flags_remain_false():
    cfg = LiveApiConfig.from_env({})
    # Default config: live trading off, exchange orders off.
    from app.live.health import build_safety_flags

    flags = build_safety_flags(cfg)
    assert flags["live_trading"] is False
    assert flags["exchange_live_orders"] is False
    assert flags["trade_authority"] is False
    assert flags["ai_trade_authority"] is False
    assert flags["live_runtime_mode"] == LiveRuntimeMode.LIVE_SHADOW.value

    # The briefing + bundle pin the same markers.
    bundle = build_live_ai_evidence_bundle(sources=[OrderSource.LIVE]).bundle.to_dict()
    assert bundle["ai_trade_authority"] is False
    assert bundle["exchange_live_orders"] is False
    assert bundle["live_trading"] is False


# ---------------------------------------------------------------------------
# CLI smoke tests (no network)
# ---------------------------------------------------------------------------
def test_cli_status_json_no_creds(capsys):
    import scripts.live_ai_briefing as cli_mod

    rc = cli_mod.main(["--status-json"])
    out = json.loads(capsys.readouterr().out)
    assert out["authority"] == "MARKET_INTELLIGENCE_ONLY"
    assert out["ai_trade_authority"] is False
    assert out["source_scope"] == "LIVE_ONLY"
    assert out["deepseek_enabled"] is False
    assert rc in (0, 1)


def test_cli_brief_dry_run_no_network(capsys):
    import scripts.live_ai_briefing as cli_mod

    rc = cli_mod.main(["--brief", "--dry-run", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["ai_trade_authority"] is False
    assert out["source_scope"] == "LIVE_ONLY"
    assert out["status"] in (BriefingStatus.OK, BriefingStatus.INSUFFICIENT_EVIDENCE)
    assert rc in (0, 1)


def test_cli_validate_output_rejects_trade_authority(capsys, tmp_path):
    import scripts.live_ai_briefing as cli_mod

    sample = tmp_path / "sample.json"
    sample.write_text(
        json.dumps({"market_summary": "ok", "should_buy": True, "leverage": 10}),
        encoding="utf-8",
    )
    rc = cli_mod.main(["--validate-output", str(sample)])
    out = json.loads(capsys.readouterr().out)
    assert "should_buy" in out["forbidden_fields_detected"]
    assert "leverage" in out["forbidden_fields_detected"]
    assert out["status"] == BriefingStatus.REJECTED_FOR_TRADE_AUTHORITY
    assert out["ai_trade_authority"] is False
    assert rc == 1


def test_cli_missing_key_brief_no_crash(capsys):
    import scripts.live_ai_briefing as cli_mod

    # No DeepSeek key + not dry-run -> MISSING_SECRET / DISABLED, never crash.
    rc = cli_mod.main(["--brief", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["status"] in (BriefingStatus.DISABLED, BriefingStatus.MISSING_SECRET)
    assert out["ai_trade_authority"] is False
    assert rc == 1
