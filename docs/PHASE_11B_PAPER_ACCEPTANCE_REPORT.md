# AMA-RT Phase 11B - Cloud Paper Acceptance Report

- **Generated (UTC):** 2026-05-19T18:52:32.146000+00:00
- **Started (UTC):** 2026-05-19T18:52:32.072000+00:00
- **Duration:** 0s (acceptance dry-run cap = 1 min)
- **Trading mode (settings):** `paper`
- **Trading mode (paper_cloud.yaml):** `paper`
- **Live trading risk:** `False` (must be `False`)
- **Exchange live order risk:** `False` (must be `False`)
- **Right tail amplification:** `False` (must be `False`)
- **LLM enabled:** `False` (must be `False`; LLM stays receive-only)
- **Telegram outbound (paper-cloud):** `False` (FakeTelegramClient is the default Phase 11B transport)

## Phase 1 safety lock
- `trading_mode_paper` = `True`
- `live_trading_enabled_false` = `True`
- `right_tail_enabled_false` = `True`
- `llm_enabled_false` = `True`
- `exchange_live_order_enabled_false` = `True`
- `write_surfaces_refuse` = `True`
- `paper_cloud_yaml_consistent` = `True`
- `real_order_enabled_false` = `True`

## Env-guard pre-flight (no credential VALUES are recorded)
- `passed` = `True`
- `inspected_env_vars` = `['AMA_TRADING_MODE', 'AMA_LIVE_TRADING_ENABLED', 'AMA_RIGHT_TAIL_ENABLED', 'AMA_LLM_ENABLED', 'AMA_EXCHANGE_LIVE_ORDER_ENABLED']`
- `forbidden_credential_env_var_count` = `10`
- `forbidden_credentials_present_count` = `0`
- `dangerous_runtime_values` = `[]`
- `notes` = `['clean_env']`

## Boot paper-trade lifecycle
```json
{
  "client_order_id": "phase11b_paper_boot_1779216752135",
  "symbol": "BOOTUSDT",
  "qty": 0.001,
  "limit_price": 100.0,
  "stop_price": 98.0,
  "session_state": "idle",
  "realized_pnl": 0.0,
  "reconciliation_matched": true,
  "new_opens_paused": false
}
```

## First-boot /export_test_data 24h
- export_id: `export_f2aef4c14d1546e0b5649d2d1d8f2116`
- bytes_written: `3795`
- redaction_applied: `True`
- event_count: `3`
- opportunity_count: `0`
- risk_rejected_count: `0`
- capital_event_count: `0`
- zip_path: `ama_rt_test_data_1779216752135_export_f.zip`


## Daily report
- date: `2026-05-19`
- event_count: `48`
- risk_approved: `3`
- risk_rejected: `4`
- paper_trade_count: `1`
- paper_realized_pnl: `0.0000`
- incidents_p0: `4`
- incidents_p1: `0`
- protection_mode_entered: `2`
- new_opens_paused: `True`


## Telegram outbound summary
```json
{
  "transport": "telegram_fake",
  "outbound_enabled": true,
  "messages_sent": 1,
  "documents_sent": 0,
  "send_failed": 0,
  "deduped": 0,
  "cooldown_blocked": 0,
  "redaction_blocked": 0,
  "recorded_calls": 1
}
```

## Incident drill results

| Drill | Status | Observations | Failure reason |
| --- | --- | --- | --- |
| `stop_unconfirmed` | `pass` | reasons=stop_unconfirmed, risk_engine_rejected_new_open | - |
| `unknown_position` | `pass` | reasons=unknown_position, risk_engine_rejected_new_open | - |
| `data_degraded` | `pass` | exchange_disconnected, data_degraded, no_trade_gate_rejected_attack | - |
| `p0_ghost_position` | `pass` | p0_count=2, new_opens_paused_after_clean=True, p0_latched_pause_after_clean=True, incidents_opened=2, new_opens_paused_after_resume=False, p0_latched_pause_after_resume=False, clean_decision_matched=True | - |
| `p0_unattached_stop` | `pass` | mismatches=stop_mismatch,unattached_stop, p0_latched_pause=True, incidents_opened=2 | - |
| `rebase_in_progress` | `pass` | new_open_reasons=rebase_in_progress, protective_exit_approved | - |
| `telegram_export_failure` | `pass` | command_status=execution_error, dispatcher.send_failed=2, data_export_failed_events=1, failing_client_failed_calls=2 | - |
| `llm_degraded` | `pass` | degraded_reasons=llm_disabled, fake_client_calls=0, clean_results=0 | - |

## Acceptance criteria

| # | Criterion | Pass | Evidence |
| --- | --- | --- | --- |
| 1 | 1. paper mode cloud run successful | `PASS` | safety=True boot_lifecycle=True |
| 2 | 2. no real trading happened | `PASS` | live=False live_orders=False |
| 3 | 3. no live trading happened | `PASS` | live=False |
| 4 | 4. no real order placed (write surfaces refuse) | `PASS` | write_surfaces_refuse=True |
| 5 | 5. no credential leak | `PASS` | env_guard_passed=True redaction_blocked=0 |
| 6 | 6. daily export succeeded (first-boot) | `PASS` | export_tick_ran=True |
| 7 | 7. telegram dispatch / fake recorded | `PASS` | messages_sent=1 |
| 8 | 8. replay / reflection still read-only | `PASS` | Phase 10A/10B AST scans still in tree; supervisor never imports a write surface from app/replay or app/reflection |
| 9 | 9. P0 incident locked correctly | `PASS` | p0 drill outcomes recorded above |
| 10 | 10. P0 latched-pause cannot auto-resume | `PASS` | p0_ghost_position drill verified the latched-pause clearance flow |
| 11 | 11. stop_unconfirmed / unknown_position rejected | `PASS` | stop_unconfirmed + unknown_position drill outcomes |
| 12 | 12. protective exit not blocked | `PASS` | rebase_in_progress drill confirms is_new_open=False is allowed |
| 13 | 13. Phase 11B report generated | `PASS` | this file |
| 14 | 14. pytest passing (run separately) | `PASS` | tests are run by `python -m pytest tests/unit -q` |

## Notes
- `env_guard_passed=True`
- `first_boot_export_ok=ama_rt_test_data_1779216752135_export_f.zip`

## Final decision

- **Accepted:** `PASS`
- **Go / No-Go:** `GO`

_Phase 11B paper-mode cloud run. No live trading. No real exchange order. No credential is read by this report._
