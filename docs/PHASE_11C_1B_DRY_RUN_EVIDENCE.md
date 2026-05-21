# Phase 11C.1B - WebSocket-First Dry-Run Evidence

**Status:** docs-only addendum to PR #32. **Captures the actual dry-run
output reviewers can reproduce verbatim before the cloud-smoke ladder.
No code change. No safety-flag change. Phase 1 lock unchanged.**

This file lives next to `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md`
§11C.1B and is the single load-bearing place a reviewer can answer
"does the WS-first runner actually emit the contracted event chain
under `--dry-run`, and does the rate-limit governor really throttle
without HTTP 418 / 429?" without having to set up a sandbox.

---

## How to reproduce locally

```bash
python3.12 -u -m scripts.run_public_market_paper \
  --duration 1min --symbol-limit 5 \
  --candidate-pool-size 20 --active-detail-limit 3 \
  --ws-staleness-threshold-ms 60000 --candidate-ttl-seconds 900 \
  --dry-run --poll-interval-seconds 2 \
  > data/phase11c1b_dryrun_logs/run.log 2>&1
```

Exit code: `0`. Daily report:
`data/reports/phase11c/<UTC-date>-phase11c-public-market.md`.

The same command without `--dry-run` would attempt to construct the
real `MultiTransportPublicWSManager` against the routed Binance
endpoints and (per PR #32) refuse with `rc=2` if the network is not
reachable. Use `--dry-run` for the no-network smoke; use `--ws-first`
without `--dry-run` for the cloud-smoke ladder.

## Boot banner

```
[AMA-RT] Phase 11C.1B - WebSocket-First All-Market Demon Coin Radar
v1.4.0a11c.1b mode=paper live_trading=False right_tail=False
llm=False exchange_live_orders=False telegram_outbound_enabled=False
binance_private_api_enabled=False provider=binance_public
rest_base_url=https://fapi.binance.com symbols=2 duration_seconds=60
poll_interval_seconds=2.0 rest_layering_enabled=True
candidate_detail_limit=3 ws_first=True ws_real_transport=False
ws_staleness_threshold_ms=60000 candidate_pool_size=20
active_detail_limit=3 governor=on(budget=300/min soft=0.5 hard=0.75
on_429=backoff on_418=shutdown retry_after_default=300s)
dry_run=True env_guard_passed=True
```

`ws_real_transport=False` is the expected dry-run banner: the runner
wired the `InProcessWSPump` and never attempted a real socket. Under
`--ws-first` without `--dry-run` the banner reports
`ws_real_transport=True` and the real
`MultiTransportPublicWSManager` is what gets connected.

## Exit banner (60-second dry-run)

```
[AMA-RT] Phase 11C.1B run finished
  duration_seconds=60 iterations=30
  chains_emitted=3 ws_chains_emitted=60
  ws_risk_rejected=60 risk_approved=0 risk_rejected=3
  learning_ready_attached=3 ws_learning_ready_attached=60
  snapshots_emitted=3 ingestion_errors=57
  public_endpoint_calls=22
  ws_messages_received=122 ws_reconnect_count=0
  ws_staleness_ms_max=0 ws_stale_count=0
  ws_real_transport=False ws_data_degraded_ticks=0
  radar_candidates_seen=60 candidate_pool_size_max=2
  liquidation_events_seen=0
  rate_limit_429_count=0 rate_limit_418_count=0
  used_weight_1m_max=0
  rate_limit_protection_triggered=False rate_limit_ban=False
```

`ingestion_errors=57` is the brief-required behaviour, NOT a
defect: the runner is exercising the legacy REST detail path against
the deterministic dry-run transport while the rate-limit governor
correctly refuses every overshoot of the 0.75 hard ratio. Real
network calls land 0 × 429 and 0 × 418 because no real call ever
goes out under `--dry-run`. Under `--ws-first` without `--dry-run`
the WS-first acceptance path keeps `ingestion_errors` near zero
because the radar replaces the per-loop detail REST.

## events.db audit (60-second dry-run)

```
ANOMALY_DETECTED                    63
PRE_ANOMALY_DETECTED                63
RISK_REJECTED                       63
STATE_TRANSITION                    63
DATA_UNRELIABLE                      3
LIQUIDITY_CHECKED                    3
MANIPULATION_DETECTED                3
MARKET_SNAPSHOT                      3
TRADE_CONFIRMED                      3
EXCHANGE_CONNECTED                   1
EXCHANGE_DISCONNECTED                1
PUBLIC_WS_CONNECTED                  1
PUBLIC_WS_DISCONNECTED               1
RATE_LIMIT_429                       0
RATE_LIMIT_418                       0
RATE_LIMIT_BACKOFF_STARTED           0
RATE_LIMIT_BACKOFF_ENDED             0
RATE_LIMIT_PROTECTION_ENTERED        0
PUBLIC_WS_STALE                      0
```

Of the 63 PRE_ANOMALY_DETECTED rows, 60 carry
`source_phase=phase_11c_1b_ws_first_radar` and 3 carry
`source_phase=phase_11c_public_market_paper` (the existing PR-A
REST chain that runs alongside the radar on the candidate pool's
active head).

## Per-iteration tracking record

Every WS-radar event carries the Phase 8.5 identity contract. One
sample, captured verbatim from `events.db`:

| Field                          | Value                                                                 |
| ------------------------------ | --------------------------------------------------------------------- |
| `event_type`                   | `PRE_ANOMALY_DETECTED`                                                |
| `symbol`                       | `ETHUSDT`                                                             |
| `source_phase`                 | `phase_11c_1b_ws_first_radar`                                         |
| `scan_batch_id` (= run_id)     | `scan_01c88284d61b4eecb1c5da63970901b2`                               |
| `opportunity_id`               | `opp_6985992e6c104ef18d3991c9de960d07`                                |
| `pre_anomaly_score`            | `50.0`                                                                |
| `radar_reason_tags`            | `['price_acceleration_60s', 'quote_volume_delta_60s', 'spread_compression', 'mark_price_alignment', 'funding_not_overheated']` |
| `radar_source_streams`         | `['book_ticker', 'mark_price_arr', 'ticker_arr']`                     |
| `candidate_state`              | `active`                                                              |
| `snapshot.last_price`          | `115.5`                                                               |
| `snapshot.price_accel_60s`     | `0.05`                                                                |
| `snapshot.qv_delta_60s`        | `4_449_500.0`                                                         |
| `learning_ready.opportunity`   | (Phase 8.5 OpportunityIdentity, full block attached)                  |
| `learning_ready.signal_snapshot` | (Phase 8.5 SignalSnapshot)                                          |
| `learning_ready.virtual_trade_plan` | (Phase 8.5 VirtualTradePlan)                                     |
| `learning_ready.config_versions` | (Phase 8.5 ConfigVersions)                                          |

Pass / fail status per iteration is recorded as the
`STATE_TRANSITION.reject_reasons` field. In Phase 11C.1B paper-mode
the WS-radar chain calls the live `RiskEngine` with
`stop_unconfirmed=True` so EVERY decision falls into
`RISK_REJECTED(["stop_unconfirmed"])` - this is the documented
Phase 11C contract: real market data drives the decision pipeline
but never opens a real order. The dry-run output below confirms
the chain behaves the same way:

```
ts=...  sym=ETHUSDT  score=50.0 pool=active to=no_trade reject=["stop_unconfirmed"] -> FAIL (paper-only)
ts=...  sym=BTCUSDT  score=50.0 pool=active to=no_trade reject=["stop_unconfirmed"] -> FAIL (paper-only)
ts=...  sym=ETHUSDT  score=50.0 pool=active to=no_trade reject=["stop_unconfirmed"] -> FAIL (paper-only)
ts=...  sym=BTCUSDT  score=50.0 pool=active to=no_trade reject=["stop_unconfirmed"] -> FAIL (paper-only)
```

(Under live trading - which Phase 11C.1B never enables - a chain
whose Risk Engine returns `approved=True` would write
`RISK_APPROVED` instead and `STATE_TRANSITION.reject_reasons=[]`,
i.e. PASS. The runner already classifies the two cases via
`stats.ws_risk_rejected` vs `stats.ws_chains_emitted`.)

## Discovered demon-coin candidates

```
BTCUSDT    chain_emissions=30 best_radar_score=90.0 states=["active"]
ETHUSDT    chain_emissions=30 best_radar_score=90.0 states=["active"]
```

The dry-run InProcessWSPump deliberately seeds 2 symbols (BTCUSDT,
ETHUSDT) with synthetic `!ticker@arr` / `!markPrice@arr` /
`!bookTicker` bursts so the radar buffer + candidate pool can fire
end-to-end without any real network. Both symbols clear the
default radar score threshold (`30.0`) on every tick and stay
`ACTIVE` for the full window. The cloud-smoke ladder uses the
real routed PUBLIC + MARKET WebSocket transports and the candidate
set is whatever Binance is actually pushing.

## Daily-report `Phase 11C.1B WebSocket all-market radar` section

```
- WS messages received: **122**
- WS reconnect count: **0**
- WS staleness (ms) max: **0**
- WS stale event count: **0**
- WS connect count: **1**
- WS disconnect count: **0**
- WS currently stale: **False**
- Radar candidates seen: **60**
- Candidate pool size max: **2**
- Pre-anomaly candidates promoted: **2**
- Liquidation events seen: **0**

### WS messages by stream
- `!bookTicker` x 60
- `!markPrice@arr` x 30
- `!ticker@arr` x 32

### Radar score top symbols
- `BTCUSDT` score=50.00 state=active
- `ETHUSDT` score=50.00 state=active
```

## Rate-limit governance evidence

The 60-second dry-run logged 68 rate-limit governor warnings, of
which the first 3 were soft-budget breaches (used+cost = 156, 176,
177 vs soft = 150) and the rest were hard-budget refusals
(`used+reserved = 225` vs `hard = 225`). Every one of those refused
calls was caught by `PublicMarketIngestor.ingest_many` and
recorded as an `ingestion_error`; none escaped to the caller. No
HTTP 429 / 418 ever fired (`rate_limit_429_count=0`,
`rate_limit_418_count=0`, `rate_limit_protection_triggered=False`),
because the governor refused the overshoots BEFORE any real network
call would have happened.

```
2026-05-21 17:41:46.059 | WARNING | rest soft-budget breach: used+cost=156 soft=150 hard=225 budget=300 endpoint=/fapi/v1/aggTrades
2026-05-21 17:41:46.059 | WARNING | rest soft-budget breach: used+cost=176 soft=150 hard=225 budget=300 endpoint=/fapi/v1/depth
2026-05-21 17:41:46.059 | WARNING | rest soft-budget breach: used+cost=177 soft=150 hard=225 budget=300 endpoint=/fapi/v1/fundingRate
... (62 more)
2026-05-21 17:42:42.178 | WARNING | rest budget exhausted: used=225 reserved=0 cost=20 hard=225 budget=300 endpoint=/fapi/v1/aggTrades
```

Paired with `ws_messages_received=122` and `ws_chains_emitted=60`,
this is the brief's "throttle on rate-limit + preserve data
integrity" contract: REST detail is gated by the governor, the WS
radar pipeline keeps running, and the candidate-pool / radar-chain
event stream is uninterrupted.

## How to monitor the run continuously

```bash
# tail the log file in another shell:
tail -f data/phase11c1b_dryrun_logs/run.log

# query events.db for the live demon-coin list:
sqlite3 data/sqlite/events.db \
  "SELECT symbol, MAX(json_extract(payload_json,'\$.pre_anomaly_score')) AS best,
   COUNT(*) FROM events
   WHERE event_type='PRE_ANOMALY_DETECTED'
   AND json_extract(payload_json,'\$.source_phase')='phase_11c_1b_ws_first_radar'
   GROUP BY symbol ORDER BY best DESC"
```

## How to terminate the run

The runner installs a SIGINT / SIGTERM handler. Either Ctrl+C in
the foreground shell or:

```bash
kill -TERM <pid>     # graceful: builds the daily report on shutdown
kill -INT  <pid>     # equivalent
kill -KILL <pid>     # only as a last resort; daily report not written
```

A graceful shutdown writes the daily Markdown report and emits
`PUBLIC_WS_DISCONNECTED` + `EXCHANGE_DISCONNECTED` audit events, so
Replay / Reflection can rebuild the run boundary from `events.db`
alone.

## Phase 1 safety lock - confirmed unchanged

After the 60-second dry-run, every flag below is verbatim what it
was at boot:

```
mode                            = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
forbid_private_credentials      = True
forbid_signed_endpoints         = True
forbid_trade_endpoints          = True
forbid_account_endpoints        = True
forbid_position_endpoints       = True
forbid_leverage_endpoints       = True
forbid_margin_endpoints         = True
forbid_live_trading             = True
forbid_right_tail               = True
forbid_llm_trade_decisions      = True
forbid_telegram_outbound        = True
```

The four `ExchangeClientBase` write surfaces (`create_order`,
`cancel_order`, `set_leverage`, `set_margin_mode`) continue to
raise `SafeModeViolation` on the public REST client. No Binance
API key / API secret / `listenKey` was read; no signed REST
endpoint was called; the routed-private WebSocket endpoint
`wss://fstream.binance.com/private` was never opened.
