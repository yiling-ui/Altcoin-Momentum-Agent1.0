"""Fake live DeepSeek transport (PR117 - Full-System Single-Altcoin Live
Sandbox Audit v0).

Lets the REAL PR115 :class:`app.live.ai_live_briefing.LiveAIBriefingGenerator`
+ :func:`app.live.ai_output_guard.sanitize_ai_output` run end to end
against a fake DeepSeek model without ever contacting the network.

  * :class:`FakeDeepSeekTransport` - a transport callable
    ``(url, headers, json_body) -> json`` returning a chat-completions
    shaped response whose ``content`` is a JSON string. It can return a
    clean market-intelligence briefing OR one with forbidden
    trade-authority fields injected (so the audit can PROVE the AI output
    guard strips / rejects them).
  * :func:`fake_sandbox_deepseek_config` - an enabled, fake-key DeepSeek
    config so the generator actually calls the (fake) model.

HARD boundaries (the brief): DeepSeek output is MARKET_INTELLIGENCE_ONLY.
The AI can NEVER decide a trade / direction / size / leverage / stop /
take-profit / order / execution / config patch; every such field is
stripped + rejected by the real output guard. This module only models
the transport.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from app.live.api_config import DeepSeekApiConfig
from app.live.secrets import SecretValue

FAKE_LIVE_DEEPSEEK_MODULE = "live.fake_live_deepseek"

# A clean, market-intelligence-only briefing body (no forbidden field).
CLEAN_BRIEFING_PAYLOAD: dict[str, Any] = {
    "market_summary": "RAVEUSDT_SANDBOX shows a right-tail breakout with volume + OI expansion.",
    "account_summary": "Funded sandbox account on L1_10U_PROBE; usable capital capped at the profile cap.",
    "risk_summary": "Liquidity and spread are within the profile floor; no risk halt active.",
    "pnl_summary": "Strategy PnL is net of commission and funding; external flows excluded.",
    "funding_summary": "Funding is carried into net PnL; attribution pending position link.",
    "position_notes": "No open positions in the evidence bundle.",
    "rejection_summary": "No recent rejections.",
    "anomaly_notes": "No manipulation anomalies detected in the snapshot.",
    "operator_notes": "Market-intelligence only. AI has no trade authority.",
    "evidence_quality": "MODERATE",
    "missing_evidence": [],
}

# A briefing body with EVERY forbidden trade-authority field injected, at
# the top level AND nested, so the audit proves the guard strips at depth.
FORBIDDEN_BRIEFING_PAYLOAD: dict[str, Any] = {
    "market_summary": "RAVE looks strong.",
    # Top-level forbidden fields (the brief's list).
    "should_buy": True,
    "should_sell": False,
    "direction": "LONG",
    "leverage": 20,
    "stop_price": 0.9,
    "take_profit": 1.5,
    "position_size": 1000,
    "order_type": "MARKET",
    "entry_price": 1.05,
    "exit_price": 1.4,
    "runtime_config_patch": {"max_leverage": 50},
    # Nested forbidden field (defence-in-depth: must be stripped at depth).
    "operator_notes": "informational",
    "nested": {"should_long": True, "ai_trade_authority": True},
}


def fake_sandbox_deepseek_config(*, enabled: bool = True) -> DeepSeekApiConfig:
    """An enabled, fake-key DeepSeek config so the generator calls the fake."""
    return DeepSeekApiConfig(
        api_key=SecretValue(name="AMA_DEEPSEEK_API_KEY", _raw="sandbox-fake-deepseek-key-117"),
        base_url="https://api.deepseek.com",
        model="deepseek-chat-sandbox",
        enabled=enabled,
    )


class FakeDeepSeekTransport:
    """A deterministic fake DeepSeek transport (no socket, ever).

    Returns a chat-completions shaped response whose message content is a
    JSON string. ``payload`` selects what the fake model "returns":
    a clean briefing, or one with forbidden trade-authority fields.
    """

    def __init__(self, *, payload: dict[str, Any] | None = None, inject_forbidden: bool = False) -> None:
        if payload is not None:
            self.payload = dict(payload)
        elif inject_forbidden:
            self.payload = dict(FORBIDDEN_BRIEFING_PAYLOAD)
        else:
            self.payload = dict(CLEAN_BRIEFING_PAYLOAD)
        self.calls: list[dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def __call__(self, url: str, headers: Mapping[str, str], body: Mapping[str, Any]) -> Any:
        # url + headers carry the key; we deliberately never store them.
        self.calls.append({"messages": list((body or {}).get("messages", []))})
        return {
            "model": "deepseek-chat-sandbox",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(self.payload, ensure_ascii=False),
                    },
                    "finish_reason": "stop",
                }
            ],
        }


__all__ = [
    "FAKE_LIVE_DEEPSEEK_MODULE",
    "CLEAN_BRIEFING_PAYLOAD",
    "FORBIDDEN_BRIEFING_PAYLOAD",
    "fake_sandbox_deepseek_config",
    "FakeDeepSeekTransport",
]
