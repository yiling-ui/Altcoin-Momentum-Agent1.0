"""Event types and Event dataclass for AMA-RT Event Sourcing.

Spec references:
    §12  Event Sourcing
    §12.1 Required event fields
    §12.2 Event type vocabulary
    §28.3 Capital events
    §38   Incident events

Phase 1 ships the full vocabulary plus the `DATA_UNRELIABLE` event flagged
in Issue #4 as a Phase-4 concern, so future phases can append events
without amending this file.

CRITICAL
--------
The persistence layer for events lives in `app.database.repositories`.
This module only defines the canonical event TYPE strings and the
in-memory `Event` payload object.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.clock import now_ms


class EventType(str, Enum):
    # ---- Market data ------------------------------------------------------
    MARKET_SNAPSHOT = "MARKET_SNAPSHOT"
    DATA_UNRELIABLE = "DATA_UNRELIABLE"  # Issue #4 - declared early; emitted from Phase 3 onward

    # ---- Exchange Gateway (Phase 3 - Issue #3) ---------------------------
    EXCHANGE_CONNECTED = "EXCHANGE_CONNECTED"
    EXCHANGE_DISCONNECTED = "EXCHANGE_DISCONNECTED"
    EXCHANGE_DEGRADED = "EXCHANGE_DEGRADED"

    # ---- Regime / Universe ------------------------------------------------
    REGIME_UPDATED = "REGIME_UPDATED"
    UNIVERSE_FILTERED = "UNIVERSE_FILTERED"

    # ---- Scanners ---------------------------------------------------------
    PRE_ANOMALY_DETECTED = "PRE_ANOMALY_DETECTED"
    ANOMALY_DETECTED = "ANOMALY_DETECTED"

    # ---- Confirmation / Manipulation -------------------------------------
    LIQUIDITY_CHECKED = "LIQUIDITY_CHECKED"
    TRADE_CONFIRMED = "TRADE_CONFIRMED"
    MANIPULATION_DETECTED = "MANIPULATION_DETECTED"

    # ---- LLM / Scoring ----------------------------------------------------
    # LLM_INTERPRETED was declared in Phase 1 / 6; Phase 10C populates it.
    LLM_INTERPRETED = "LLM_INTERPRETED"
    # Phase 10C - LLM Guarded Interpreter (Issue #10 Part 3)
    LLM_DEGRADED = "LLM_DEGRADED"
    LLM_SCHEMA_REJECTED = "LLM_SCHEMA_REJECTED"
    RIGHT_TAIL_SCORED = "RIGHT_TAIL_SCORED"
    OPPORTUNITY_GRADED = "OPPORTUNITY_GRADED"

    # ---- State machine / Risk --------------------------------------------
    STATE_TRANSITION = "STATE_TRANSITION"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"

    # ---- Orders -----------------------------------------------------------
    ORDER_SENT = "ORDER_SENT"
    ORDER_ACK = "ORDER_ACK"
    ORDER_PARTIAL_FILLED = "ORDER_PARTIAL_FILLED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_CANCELLED = "ORDER_CANCELLED"

    # ---- Stops ------------------------------------------------------------
    STOP_SENT = "STOP_SENT"
    STOP_CONFIRMED = "STOP_CONFIRMED"
    STOP_FAILED = "STOP_FAILED"

    # ---- Positions --------------------------------------------------------
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_UPDATED = "POSITION_UPDATED"
    POSITION_CLOSED = "POSITION_CLOSED"
    EXIT_TRIGGERED = "EXIT_TRIGGERED"

    # ---- Capital flow (Spec §28.3) ---------------------------------------
    CAPITAL_DEPOSIT = "CAPITAL_DEPOSIT"
    CAPITAL_WITHDRAWAL = "CAPITAL_WITHDRAWAL"
    PROFIT_HARVEST = "PROFIT_HARVEST"
    CAPITAL_REBASE = "CAPITAL_REBASE"
    RISK_BUDGET_RECALCULATED = "RISK_BUDGET_RECALCULATED"

    # ---- Reconciliation --------------------------------------------------
    RECONCILIATION_STARTED = "RECONCILIATION_STARTED"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
    RECONCILIATION_RESOLVED = "RECONCILIATION_RESOLVED"

    # ---- Protection / Incidents ------------------------------------------
    PROTECTION_MODE_ENTERED = "PROTECTION_MODE_ENTERED"
    PROTECTION_MODE_EXITED = "PROTECTION_MODE_EXITED"
    INCIDENT_OPENED = "INCIDENT_OPENED"
    INCIDENT_RESOLVED = "INCIDENT_RESOLVED"

    # ---- Telegram --------------------------------------------------------
    TELEGRAM_COMMAND_RECEIVED = "TELEGRAM_COMMAND_RECEIVED"
    # Phase 10D - Telegram Outbound + Export Commands (Issue #10 Part 4)
    TELEGRAM_COMMAND_REJECTED = "TELEGRAM_COMMAND_REJECTED"
    TELEGRAM_MESSAGE_SENT = "TELEGRAM_MESSAGE_SENT"
    TELEGRAM_SEND_FAILED = "TELEGRAM_SEND_FAILED"

    # ---- Data export (Phase 10D - Issue #10 Part 4) ----------------------
    DATA_EXPORT_GENERATED = "DATA_EXPORT_GENERATED"
    DATA_EXPORT_FAILED = "DATA_EXPORT_FAILED"

    # ---- Phase 11C.1A - Binance Public REST Rate-Limit Governor ----------
    # The governor wraps every public REST call. The five events below
    # describe its full lifecycle:
    #
    #   RATE_LIMIT_429              - HTTP 429 observed; the governor is
    #                                 about to start a Retry-After backoff.
    #   RATE_LIMIT_BACKOFF_STARTED  - the governor entered the backoff
    #                                 sleep window. No new REST call may
    #                                 land until BACKOFF_ENDED is emitted.
    #   RATE_LIMIT_BACKOFF_ENDED    - the backoff window expired and the
    #                                 governor is accepting requests
    #                                 again.
    #   RATE_LIMIT_418              - HTTP 418 observed; Binance has IP
    #                                 banned the gateway. The governor
    #                                 latches into protection mode and
    #                                 raises on every subsequent call.
    #   RATE_LIMIT_PROTECTION_ENTERED - the governor latched into rate
    #                                 limit protection mode. Pairs with
    #                                 a P1 INCIDENT_OPENED so the
    #                                 incident timeline matches.
    RATE_LIMIT_429 = "RATE_LIMIT_429"
    RATE_LIMIT_BACKOFF_STARTED = "RATE_LIMIT_BACKOFF_STARTED"
    RATE_LIMIT_BACKOFF_ENDED = "RATE_LIMIT_BACKOFF_ENDED"
    RATE_LIMIT_418 = "RATE_LIMIT_418"
    RATE_LIMIT_PROTECTION_ENTERED = "RATE_LIMIT_PROTECTION_ENTERED"

    # ---- Phase 11C.1B - Binance Public WebSocket all-market radar --------
    # The Phase 11C.1B WebSocket client emits these events to describe the
    # public WS lifecycle (no listenKey, no user data stream, no private
    # WS, no trading WebSocket API). They pair with the existing
    # ``DATA_UNRELIABLE`` and ``EXCHANGE_*`` events so the Phase 4
    # MarketDataBuffer + No-Trade Gate keep working unchanged.
    #
    #   PUBLIC_WS_CONNECTED           - the WS link is up; messages may flow.
    #   PUBLIC_WS_DISCONNECTED        - the WS link dropped; the client
    #                                   will attempt a backoff reconnect.
    #   PUBLIC_WS_STALE               - no message has arrived for
    #                                   ``ws_staleness_threshold_ms``; the
    #                                   runner downgrades data quality
    #                                   and may fall back to bootstrap REST.
    PUBLIC_WS_CONNECTED = "PUBLIC_WS_CONNECTED"
    PUBLIC_WS_DISCONNECTED = "PUBLIC_WS_DISCONNECTED"
    PUBLIC_WS_STALE = "PUBLIC_WS_STALE"

    # ---- Phase 11C.1B - SymbolUniverse (exchangeInfo-as-truth) -----------
    # The WS-radar receives ``!ticker@arr`` / ``!miniTicker@arr`` /
    # ``!bookTicker`` / ``!markPrice@arr`` / ``!forceOrder@arr`` pushes
    # for EVERY symbol Binance lists - including non-ASCII contracts
    # such as ``我踏马来了USDT`` or ``币安人生USDT``. Phase 11C.1B refuses
    # to use any character-class regex (``^[A-Z0-9_]{2,30}USDT$``) for
    # symbol validation; the only authoritative source is the snapshot
    # pulled from ``/fapi/v1/exchangeInfo`` at runner startup
    # (:class:`app.market_data_public.symbol_universe.SymbolUniverse`).
    #
    #   WS_SYMBOL_REJECTED            - the candidate pool refused a
    #                                   WS-radar symbol because it is
    #                                   NOT in the bootstrapped
    #                                   exchangeInfo set. The payload
    #                                   carries the rejected symbol +
    #                                   the reason tag so the daily
    #                                   report and Reflection can
    #                                   audit drift between bootstrap
    #                                   and live WS pushes.
    WS_SYMBOL_REJECTED = "WS_SYMBOL_REJECTED"

    # ---- Phase 11C.1C-A - Adaptive Candidate Regime & Strategy Selector ----
    # The Phase 11C.1C-A WS-radar event-chain driver emits these six
    # events alongside the existing ``PRE_ANOMALY_DETECTED`` /
    # ``ANOMALY_DETECTED`` / ``STATE_TRANSITION`` chain so Reflection
    # / Replay / Export can carry the adaptive sub-blocks forward
    # without re-deriving them from a free-form audit dict.
    #
    # Every payload includes the Phase 8.5 identity fields
    # (``opportunity_id`` / ``scan_batch_id`` / ``symbol`` /
    # ``timestamp``), the Phase 11C.1C-A version labels
    # (``strategy_version`` / ``scoring_version`` /
    # ``risk_config_version`` / ``state_machine_version``), and the
    # corresponding sub-block dict. The events are descriptive only
    # - none of them authorises a real trade and none of them flips
    # a Phase 1 safety flag.
    #
    #   MARKET_REGIME_ASSESSED      - macro-cycle bucket + risk
    #                                 multiplier + allowed strategy
    #                                 modes for the current scan batch.
    #   CANDIDATE_STAGE_CLASSIFIED  - the candidate's life-cycle stage
    #                                 (early / mid / late / blowoff /
    #                                 dumped) + supporting numerics.
    #   OPPORTUNITY_SCORED          - weighted-sum score + S / A / B /
    #                                 C grade.
    #   STRATEGY_MODE_SELECTED      - paper / virtual strategy
    #                                 expression (follow / pullback /
    #                                 observe / reject). Does NOT
    #                                 authorise opening a position.
    #   CLUSTER_CONTEXT_ATTACHED    - cluster_id + cluster_leader +
    #                                 cluster_rank for the candidate.
    #   LABEL_QUEUE_ENQUEUED        - future MFE / MAE / Tail-label
    #                                 tracking-window contract for
    #                                 the candidate. Phase 11C.1C-A
    #                                 does NOT implement the MFE/MAE
    #                                 processor; the queue is
    #                                 descriptive.
    MARKET_REGIME_ASSESSED = "MARKET_REGIME_ASSESSED"
    CANDIDATE_STAGE_CLASSIFIED = "CANDIDATE_STAGE_CLASSIFIED"
    OPPORTUNITY_SCORED = "OPPORTUNITY_SCORED"
    STRATEGY_MODE_SELECTED = "STRATEGY_MODE_SELECTED"
    CLUSTER_CONTEXT_ATTACHED = "CLUSTER_CONTEXT_ATTACHED"
    LABEL_QUEUE_ENQUEUED = "LABEL_QUEUE_ENQUEUED"

    # ---- Phase 11C.1C-C-A - MFE / MAE Label Queue Runtime & Tail Outcome --
    # Tracking. The Phase 11C.1C-C-A runtime starts an MFE / MAE
    # tracking record per ACTIVE candidate (after the Phase 11C.1C-A
    # ``LABEL_QUEUE_ENQUEUED`` event lands), updates the per-window
    # MFE / MAE / R-multiple state on every fresh price tick, and
    # closes each window when its end_ts is reached. The events below
    # describe the full lifecycle.
    #
    # Phase 11C.1C-C-A boundary:
    # - The runtime records *candidate outcome labels only*. It NEVER
    #   opens / closes a real position, NEVER reads a private API,
    #   NEVER signs a request, NEVER infers live position PnL,
    #   and NEVER calls an LLM / Telegram outbound / DeepSeek
    #   trade-decision endpoint.
    # - Every payload carries a ``schema_version`` field so future
    #   PRs can extend the shape; old events without the runtime
    #   sub-block remain replayable verbatim.
    #
    #   LABEL_TRACKING_STARTED   - the runtime registered a NEW
    #                              :class:`LabelTrackingRecord` for an
    #                              opportunity. Idempotent: a duplicate
    #                              ``observe()`` for the same
    #                              opportunity_id (or fall-back identity
    #                              tuple) does NOT re-emit this event.
    #   LABEL_WINDOW_UPDATED     - the runtime advanced the MFE / MAE
    #                              of one tracking window because a
    #                              fresh price tick hit a new high or
    #                              low. The payload carries the
    #                              window_name + the running stats.
    #   LABEL_WINDOW_COMPLETED   - the window's ``window_end_ts`` was
    #                              reached; the runtime froze the
    #                              window's stats and assigned the
    #                              per-window tail_label. The
    #                              candidate's *primary window* (5m by
    #                              default) drives the record's
    #                              ``status`` flip to ``completed``.
    #   TAIL_LABEL_ASSIGNED      - the runtime picked one of
    #                              ``strong_tail`` /
    #                              ``moderate_tail`` /
    #                              ``weak_tail`` /
    #                              ``fake_breakout`` /
    #                              ``late_chase_failure`` /
    #                              ``dumped`` / ``unresolved`` for the
    #                              window and (when the window is the
    #                              configured primary) for the record
    #                              as a whole. Rule-based; no LLM.
    #   MISSED_TAIL_DETECTED     - a window completed with
    #                              ``missed_tail=True`` (a meaningful
    #                              upside ran but the candidate had
    #                              been classified ``late`` /
    #                              ``blowoff`` and the chain emitted
    #                              ``observe`` instead of ``follow``).
    #                              Helps Strategy Validation Lab
    #                              measure how often the runtime missed
    #                              real demon coins.
    #   FAKE_BREAKOUT_DETECTED   - a window completed with
    #                              ``fake_breakout=True`` (early
    #                              upside followed by adverse
    #                              reversal that wiped most of the
    #                              gain). Helps measure how often
    #                              an early_tail signal turned out to
    #                              be noise.
    LABEL_TRACKING_STARTED = "LABEL_TRACKING_STARTED"
    LABEL_WINDOW_UPDATED = "LABEL_WINDOW_UPDATED"
    LABEL_WINDOW_COMPLETED = "LABEL_WINDOW_COMPLETED"
    TAIL_LABEL_ASSIGNED = "TAIL_LABEL_ASSIGNED"
    MISSED_TAIL_DETECTED = "MISSED_TAIL_DETECTED"
    FAKE_BREAKOUT_DETECTED = "FAKE_BREAKOUT_DETECTED"

    # ---- Phase 11C.1C-C-B-A - Strategy Validation Lab v0 & Cluster --------
    # Exposure Control Contracts. The Phase 11C.1C-C-B-A runtime
    # consumes the Phase 11C.1C-C-A label-tracking outcomes
    # (``TAIL_LABEL_ASSIGNED`` / ``LABEL_WINDOW_COMPLETED`` /
    # ``MISSED_TAIL_DETECTED`` / ``FAKE_BREAKOUT_DETECTED``) and
    # produces:
    #
    #   - one :class:`StrategyValidationSample` per opportunity that
    #     reached at least the primary tracking window;
    #   - one :class:`StrategyValidationReport` per scheduled flush
    #     (start-of-loop + shutdown);
    #   - per-mode / per-stage / per-bucket cohort stats so a human
    #     reviewer can audit "is the strategy_mode actually right?";
    #   - per-cluster :class:`ClusterExposureAssessment` records so a
    #     human reviewer can audit "are we accidentally building
    #     exposure to one narrative?".
    #
    # Phase 11C.1C-C-B-A boundary:
    # - The Lab is paper / report only. No event below authorises a
    #   real trade, modifies a real position, or flips a Phase 1
    #   safety flag.
    # - ``suggested_cluster_action`` is descriptive (one of
    #   ``leader_only`` / ``observe_followers`` / ``reject_cluster``
    #   / ``no_action``); the Risk Engine remains the single
    #   trade-decision gate.
    # - Every payload carries ``schema_version`` so future PRs can
    #   extend the shape; old events without the v0 sub-block remain
    #   replayable verbatim.
    #
    #   STRATEGY_VALIDATION_SAMPLE_CREATED   - one sample emitted per
    #                                          opportunity outcome.
    #   STRATEGY_VALIDATION_REPORT_GENERATED - one report emitted per
    #                                          scheduled flush.
    #   STRATEGY_MODE_VALIDATED              - per-mode cohort stats
    #                                          (follow / pullback /
    #                                          observe / reject).
    #   CANDIDATE_STAGE_VALIDATED            - per-stage cohort stats
    #                                          (early / mid / late /
    #                                          blowoff / dumped).
    #   SCORE_BUCKET_VALIDATED               - per-bucket cohort stats
    #                                          (opportunity_score +
    #                                          early_tail_score).
    #   CLUSTER_EXPOSURE_ASSESSED            - per-cluster exposure
    #                                          assessment + paper-only
    #                                          suggested_cluster_action.
    #   CLUSTER_LEADER_VALIDATED             - per-cluster leader vs.
    #                                          follower comparison.
    STRATEGY_VALIDATION_SAMPLE_CREATED = "STRATEGY_VALIDATION_SAMPLE_CREATED"
    STRATEGY_VALIDATION_REPORT_GENERATED = (
        "STRATEGY_VALIDATION_REPORT_GENERATED"
    )
    STRATEGY_MODE_VALIDATED = "STRATEGY_MODE_VALIDATED"
    CANDIDATE_STAGE_VALIDATED = "CANDIDATE_STAGE_VALIDATED"
    SCORE_BUCKET_VALIDATED = "SCORE_BUCKET_VALIDATED"
    CLUSTER_EXPOSURE_ASSESSED = "CLUSTER_EXPOSURE_ASSESSED"
    CLUSTER_LEADER_VALIDATED = "CLUSTER_LEADER_VALIDATED"

    # ---- Phase 11C.1C-C-B-B-A - Strategy Validation Dataset Builder &
    # Quality Gate v0. The Phase 11C.1C-C-B-B-A runtime turns the
    # Phase 11C.1C-C-B-A :class:`StrategyValidationSample` artefacts
    # into a dataset that is exportable, replayable, and auditable.
    # The first version of the quality gate is a *sample trust*
    # gate, not a *strategy quality* gate; it does NOT judge whether
    # the strategy is profitable.
    #
    # Phase 11C.1C-C-B-B-A boundary:
    # - Every event below is paper / report only. None of them
    #   authorises a real trade, modifies a real position, or flips
    #   a Phase 1 safety flag.
    # - The ``gate_status`` carried by
    #   ``STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED`` is a
    #   *descriptive* label - one of ``pass`` / ``warn`` / ``fail``.
    #   It is NEVER an input to a trade-decision pipeline; the Risk
    #   Engine remains the single trade-decision gate.
    # - Every payload carries ``schema_version`` so future PRs can
    #   extend the shape; old events without the v0 sub-block remain
    #   replayable verbatim.
    #
    #   STRATEGY_VALIDATION_DATASET_BUILT          - one
    #     :class:`StrategyValidationDataset` was assembled from the
    #     most recent :class:`StrategyValidationReport`. The payload
    #     carries the dataset summary + record count + every
    #     brief-mandated identity field.
    #   STRATEGY_VALIDATION_DATASET_EXPORTED       - the dataset
    #     payload was successfully serialised through
    #     ``export_validation_dataset_payload`` (paper / report only;
    #     no Telegram outbound, no real upload). The payload is
    #     descriptive: a downstream auditor can replay the dataset
    #     by feeding the export bundle's events.jsonl through
    #     ``load_validation_dataset_payload``.
    #   STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED - the quality
    #     gate v0 produced a ``gate_status`` of ``pass`` / ``warn``
    #     / ``fail`` plus the diagnostic reasons. The result is
    #     descriptive only and MUST NEVER trigger a real trade.
    STRATEGY_VALIDATION_DATASET_BUILT = "STRATEGY_VALIDATION_DATASET_BUILT"
    STRATEGY_VALIDATION_DATASET_EXPORTED = (
        "STRATEGY_VALIDATION_DATASET_EXPORTED"
    )
    STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED = (
        "STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED"
    )

    # ---- Phase 11C.1C-C-B-B-B-A - Paper Alpha Gate v0. The Paper
    # Alpha Gate v0 runtime turns the Phase 11C.1C-C-B-B-A
    # :class:`StrategyValidationDataset` /
    # :class:`StrategyValidationQualityGateResult` artefacts (and,
    # transitively, the Phase 11C.1C-C-B-A
    # :class:`StrategyValidationReport`) into a single descriptive
    # alpha-evidence verdict for human review:
    # ``PASS`` / ``WARN`` / ``FAIL`` / ``INCONCLUSIVE``.
    #
    # Phase 11C.1C-C-B-B-B-A boundary:
    # - Every event below is paper / report only. None of them
    #   authorises a real trade, modifies a real position, or flips
    #   a Phase 1 safety flag.
    # - The ``gate_status`` carried by every payload is a
    #   *descriptive* label - one of ``PASS`` / ``WARN`` / ``FAIL``
    #   / ``INCONCLUSIVE``. It is NEVER an input to a trade-decision
    #   pipeline; the Risk Engine remains the single trade-decision
    #   gate.
    # - The verdict MUST NEVER modify position size, leverage,
    #   stop-loss, target price, the Risk Engine, or the Execution
    #   FSM.
    # - This is **NOT** AI Learning, **NOT** automatic parameter
    #   optimisation, **NOT** reinforcement learning, **NOT** the
    #   complete Strategy Validation Lab follow-up, **NOT**
    #   Phase 12.
    # - Every payload carries ``schema_version`` so future PRs can
    #   extend the shape; old events without the v0 sub-block remain
    #   replayable verbatim.
    #
    #   PAPER_ALPHA_GATE_EVALUATED   - the top-level gate decision
    #     was reached and the verdict (``PASS`` / ``WARN`` /
    #     ``FAIL`` / ``INCONCLUSIVE``) is recorded together with the
    #     diagnostic reasons + warnings.
    #   PAPER_ALPHA_RULE_EVALUATED   - one named rule was checked
    #     against the input. The payload carries the rule id, the
    #     observed value, the threshold, the severity, and whether
    #     the rule fired.
    #   PAPER_ALPHA_COHORT_EVALUATED - one cohort dimension
    #     (``strategy_mode`` / ``candidate_stage`` /
    #     ``opportunity_score_bucket`` /
    #     ``early_tail_score_bucket`` /
    #     ``cluster_leader_vs_follower`` /
    #     ``tail_label_distribution``) was evaluated. The payload
    #     carries the per-cohort signals, warnings, and metrics.
    #   PAPER_ALPHA_REPORT_GENERATED - the full
    #     :class:`PaperAlphaGateReport` payload was assembled and is
    #     available for export / replay.
    PAPER_ALPHA_GATE_EVALUATED = "PAPER_ALPHA_GATE_EVALUATED"
    PAPER_ALPHA_RULE_EVALUATED = "PAPER_ALPHA_RULE_EVALUATED"
    PAPER_ALPHA_COHORT_EVALUATED = "PAPER_ALPHA_COHORT_EVALUATED"
    PAPER_ALPHA_REPORT_GENERATED = "PAPER_ALPHA_REPORT_GENERATED"

    # ------------------------------------------------------------------
    # Phase 11C.1C-C-B-B-B-B - Regime & Cluster Cohort Evidence Pack v0.
    #
    # The Regime & Cluster Cohort Evidence Pack v0 is a paper / report
    # / evidence-only compression layer that aggregates the Phase
    # 11C.1C-C-B-B-A :class:`StrategyValidationDataset` (and
    # transitively the Phase 11C.1C-C-B-A
    # :class:`StrategyValidationReport` cohort stats and the Phase
    # 11C.1C-C-B-B-B-A :class:`PaperAlphaGateReport` verdict) into a
    # structured cohort summary across ``market_regime`` /
    # ``cluster_id`` / ``cluster_leader_vs_follower`` /
    # ``candidate_stage`` / ``strategy_mode`` /
    # ``opportunity_score_bucket`` / ``early_tail_score_bucket``.
    #
    # Phase 11C.1C-C-B-B-B-B boundary:
    # - Every event below is paper / report / evidence only. None of
    #   them authorises a real trade, modifies a real position, or
    #   flips a Phase 1 safety flag.
    # - The ``evidence_pack_status`` carried by every payload is a
    #   *descriptive* roll-up - one of ``INSUFFICIENT_SAMPLE`` /
    #   ``OBSERVE_ONLY`` / ``WARNING`` / ``EVIDENCE_SIGNAL``. It is
    #   NEVER an input to a trade-decision pipeline; the Risk Engine
    #   remains the single trade-decision gate.
    # - The pack MUST NEVER modify position size, leverage,
    #   stop-loss, target price, the Risk Engine, or the Execution
    #   FSM.
    # - This is **NOT** a new strategy, **NOT** a trading module,
    #   **NOT** AI Learning, **NOT** automatic parameter
    #   optimisation, **NOT** reinforcement learning, **NOT** the
    #   complete Strategy Validation Lab follow-up, **NOT** Phase
    #   12.
    # - Every payload carries ``schema_version`` so future PRs can
    #   extend the shape; old events without the v0 sub-block remain
    #   replayable verbatim.
    #
    #   REGIME_CLUSTER_EVIDENCE_PACK_GENERATED   - the full
    #     :class:`RegimeClusterEvidencePack` payload was assembled
    #     and is available for export / replay.
    #   REGIME_CLUSTER_COHORT_SUMMARY_GENERATED - one named cohort
    #     summary (``regime_cohort_summary`` /
    #     ``cluster_cohort_summary`` / ``score_bucket_summary`` /
    #     ``stage_outcome_summary`` /
    #     ``strategy_mode_outcome_summary``) was emitted. The
    #     payload's ``summary_name`` field disambiguates.
    REGIME_CLUSTER_EVIDENCE_PACK_GENERATED = (
        "REGIME_CLUSTER_EVIDENCE_PACK_GENERATED"
    )
    REGIME_CLUSTER_COHORT_SUMMARY_GENERATED = (
        "REGIME_CLUSTER_COHORT_SUMMARY_GENERATED"
    )

    # ------------------------------------------------------------------
    # Phase 11C.1C-C-B-B-B-D - Mover Capture Recall & Missed-Tail
    # Coverage Audit v0 (*异动币捕捉召回与漏捕右尾覆盖审计 v0*).
    #
    # The Mover Capture Recall & Missed-Tail Coverage Audit v0 is a
    # paper-only / report-only / evidence-only coverage audit layer
    # that institutionalises the operator's "did the system see this
    # mover?" cross-check. It consumes existing surfaces (Binance
    # public 24h ticker / public market data, ``EventRepository``,
    # daily report, Phase 8.5 export / Phase 10A replay,
    # ``StrategyValidationDataset``, ``PaperAlphaGateReport``,
    # ``RegimeClusterEvidencePack``, ``SymbolUniverse`` /
    # exchangeInfo-as-truth catalogue) and produces:
    #
    #   - one :class:`MoverCaptureRecallAuditReport` per audit
    #     window;
    #   - one :class:`MoverCaptureAuditRecord` per top mover
    #     (captured, partially captured, missed, excluded, or
    #     insufficient-data);
    #   - per-mover capture-path evidence + miss-reason taxonomy.
    #
    # Phase 11C.1C-C-B-B-B-D boundary:
    # - Every event below is paper / report / evidence only. None of
    #   them authorises a real trade, modifies a real position, or
    #   flips a Phase 1 safety flag.
    # - The ``audit_status`` carried by every payload is a
    #   *descriptive* label - one of ``CAPTURED`` /
    #   ``PARTIALLY_CAPTURED`` / ``MISSED`` / ``EXCLUDED`` /
    #   ``INSUFFICIENT_DATA``. It is NEVER an input to a
    #   trade-decision pipeline; the Risk Engine remains the single
    #   trade-decision gate.
    # - The audit MUST NEVER modify position size, leverage,
    #   stop-loss, target price, the Risk Engine, the Execution FSM,
    #   ``symbol_limit``, candidate-pool capacity, anomaly
    #   thresholds, Regime weights, or any other runtime knob.
    # - This is **NOT** a new strategy, **NOT** a trading module,
    #   **NOT** AI Learning, **NOT** automatic parameter
    #   optimisation, **NOT** reinforcement learning, **NOT** a
    #   Historical 30D+ Blind Replay / Walk-forward Validation gate
    #   (that gate is a Phase 12 candidate pre-gate and is
    #   explicitly out of scope here), **NOT** Phase 12.
    # - Captured-but-rejected ≠ failure; missed-but-not-in-universe
    #   ≠ failure; coverage warnings only fire when the mover is in
    #   the eligible USDT-perpetual universe AND shows a clear
    #   right-tail signal AND was missed for a system-correctable
    #   reason. A single coin proves nothing.
    # - Every payload carries ``schema_version`` so future PRs can
    #   extend the shape; old events without the v0 sub-block remain
    #   replayable verbatim.
    #
    #   MOVER_CAPTURE_RECALL_AUDIT_GENERATED - the full
    #     :class:`MoverCaptureRecallAuditReport` payload was
    #     assembled and is available for export / replay.
    #   MOVER_CAPTURE_PATH_AUDITED           - one per audited top
    #     mover. Carries the per-mover capture-path evidence + the
    #     descriptive ``audit_status`` + the ``miss_reasons`` (if
    #     any). Paper / evidence only - cannot trigger orders or
    #     modify the Risk Engine / Execution FSM.
    MOVER_CAPTURE_RECALL_AUDIT_GENERATED = (
        "MOVER_CAPTURE_RECALL_AUDIT_GENERATED"
    )
    MOVER_CAPTURE_PATH_AUDITED = "MOVER_CAPTURE_PATH_AUDITED"

    # ------------------------------------------------------------------
    # Phase 11C.1C-C-B-B-B-D-A - Historical 60D Mover Coverage Backfill
    # Audit v0 (*历史 60 天异动币覆盖回填审计 v0*).
    #
    # The Historical 60D Mover Coverage Backfill Audit v0 is a
    # paper-only / report-only / evidence-only DISCOVERY-LAYER
    # historical coverage audit. It consumes existing surfaces
    # (a local Historical Market Store of public Binance 24h
    # ticker / klines / exchangeInfo snapshots, the existing
    # ``EventRepository`` event log, the Phase 11C.1C-C-B-B-B-D
    # ``MoverCaptureRecallAuditReport``, the
    # ``StrategyValidationDataset``, the ``PaperAlphaGateReport``,
    # the ``RegimeClusterEvidencePack``, the ``SymbolUniverse`` /
    # exchangeInfo-as-truth catalogue) and produces:
    #
    #   - one :class:`HistoricalMoverCoverageBackfillReport` per
    #     audit window (default: the trailing 60 days);
    #   - one :class:`HistoricalMoverCoverageRecord` per top mover
    #     in the historical reference set (CAPTURED /
    #     PARTIALLY_CAPTURED / MISSED / EXCLUDED).
    #
    # Phase 11C.1C-C-B-B-B-D-A boundary:
    # - Every event below is paper / report / evidence only. None
    #   of them authorises a real trade, modifies a real position,
    #   or flips a Phase 1 safety flag.
    # - The ``backfill_status`` carried by every payload is a
    #   *descriptive* roll-up - one of ``READY`` / ``PARTIAL`` /
    #   ``DEGRADED`` / ``INSUFFICIENT_HISTORY`` /
    #   ``FAILED_REFERENCE_DATA``. It is NEVER an input to a
    #   trade-decision pipeline; the Risk Engine remains the
    #   single trade-decision gate.
    # - The audit MUST NEVER modify position size, leverage,
    #   stop-loss, target price, the Risk Engine, the Execution
    #   FSM, ``symbol_limit``, candidate-pool capacity, anomaly
    #   thresholds, Regime weights, or any other runtime knob.
    # - This is **NOT** a complete strategy blind replay, **NOT**
    #   a PnL backtest, **NOT** a trading module, **NOT** AI
    #   Learning, **NOT** automatic parameter optimisation,
    #   **NOT** reinforcement learning, **NOT** the small-money
    #   live-trading pre-validation gate, **NOT** Phase 12.
    # - Lookahead Guard (carried in the payload, the docs, and
    #   every event): completed_tail_label MUST NOT drive
    #   reference selection, future return / final max gain MUST
    #   NOT pollute the simulated live radar score, replay label
    #   MUST NOT contaminate ``first_seen_time``, reflection /
    #   report text / LLM narrative MUST NOT serve as a capture
    #   event source, ``first_seen_time`` MUST come from the
    #   timestamp of an event that already existed at audit time,
    #   and the top-mover reference set MUST only be used for
    #   post-hoc audit (it cannot rewrite past decisions).
    # - Every payload carries ``schema_version`` so future PRs
    #   can extend the shape; old events without the v0 sub-block
    #   remain replayable verbatim.
    #
    #   HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED - the full
    #     :class:`HistoricalMoverCoverageBackfillReport` payload
    #     was assembled and is available for export / replay.
    #   HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED      - one per
    #     audited historical top mover. Carries the per-mover
    #     capture-path evidence + the descriptive
    #     ``coverage_status`` + the ``miss_reason`` (if any).
    #     Paper / evidence only - cannot trigger orders or
    #     modify the Risk Engine / Execution FSM.
    HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED = (
        "HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED"
    )
    HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED = (
        "HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED"
    )

    # ------------------------------------------------------------------
    # Phase 11C.1C-C-B-B-B-D-B - Post-Discovery Outcome Metrics v0
    # (*发现后结果度量 v0*).
    #
    # The Post-Discovery Outcome Metrics v0 layer turns the Phase
    # 11C.1C-C-B-B-B-D-A historical mover coverage records from
    # "where did we see this mover?" into "how much room remained
    # to be captured after we first saw it?". For every audited
    # mover the runtime computes:
    #
    #   - first_seen anchor (timestamp + event type + price);
    #   - prior-high anchor + distance_to_prior_high_pct;
    #   - post-seen high / low extrema along the observed price
    #     path;
    #   - remaining_upside_to_peak_pct,
    #     post_seen_drawdown_pct, mfe_pct, mae_pct,
    #     time_to_peak_seconds;
    #   - a closed detection_timing_label
    #     (EARLY / EARLY_BUT_CHOPPY / MID_MOVE / LATE / TOO_LATE
    #     / MISSED / INSUFFICIENT_DATA);
    #   - a closed outcome_label (EARLY_CONTINUATION /
    #     EARLY_BUT_CHOPPY / LATE_TOP_CHASE / LATE_REVERSAL /
    #     MISSED_STRONG_TAIL / FAKE_BREAKOUT / DUMPED /
    #     EXHAUSTION_CANDIDATE / NO_CLEAR_EDGE /
    #     INSUFFICIENT_PRICE_PATH).
    #
    # Phase 11C.1C-C-B-B-B-D-B boundary:
    # - Every event below is paper / report / evidence only. None
    #   of them authorises a real trade, modifies a real position,
    #   or flips a Phase 1 safety flag.
    # - The detection_timing_label / outcome_label carried by
    #   every payload are *descriptive* labels - they are NEVER an
    #   input to a trade-decision pipeline; the Risk Engine remains
    #   the single trade-decision gate.
    # - The metrics MUST NEVER modify position size, leverage,
    #   stop-loss, target price, the Risk Engine, the Execution
    #   FSM, ``symbol_limit``, candidate-pool capacity, anomaly
    #   thresholds, Regime weights, or any other runtime knob.
    # - The payload MUST NOT include any of:
    #   buy / sell / long / short / direction / entry / exit /
    #   position_size / leverage / stop / stop_loss / target /
    #   take_profit / risk_budget / order / execution_command /
    #   runtime_config_patch / symbol_limit_patch /
    #   threshold_patch / candidate_pool_patch /
    #   regime_weight_patch.
    # - Every payload carries ``schema_version`` so future PRs
    #   can extend the shape; old events without the v0 sub-block
    #   remain replayable verbatim.
    #
    #   POST_DISCOVERY_OUTCOME_EVALUATED         - one
    #     :class:`PostDiscoveryOutcomeRecord` was emitted for one
    #     audited mover. Carries the descriptive labels + metrics
    #     + ``evidence_refs``.
    #   POST_DISCOVERY_OUTCOME_REPORT_GENERATED  - one
    #     :class:`PostDiscoveryOutcomeReport` was assembled across
    #     many records. Carries the aggregate counts +
    #     descriptive medians.
    POST_DISCOVERY_OUTCOME_EVALUATED = "POST_DISCOVERY_OUTCOME_EVALUATED"
    POST_DISCOVERY_OUTCOME_REPORT_GENERATED = (
        "POST_DISCOVERY_OUTCOME_REPORT_GENERATED"
    )

    # ------------------------------------------------------------------
    # Phase 11C.1C-C-B-B-B-D-C-A - Reject-to-Outcome Attribution v0
    # (*拒绝决策到结果归因 v0*).
    #
    # The Reject-to-Outcome Attribution v0 layer closes the loop
    # between:
    #
    #     opportunity_id
    #         -> risk_reject_reason / no_trade_reason / strategy_mode
    #         -> tail_label / post_discovery_outcome
    #         -> reject correctness verdict
    #
    # For every audited candidate the runtime emits a closed
    # ``RejectAttributionVerdict`` (CORRECT_PROTECTIVE_REJECT /
    # FALSE_NEGATIVE_REJECT / DATA_QUALITY_REJECT /
    # LIQUIDITY_PROTECTIVE_REJECT / MANIPULATION_PROTECTIVE_REJECT /
    # STOP_SAFETY_REJECT / REBASE_PROTECTIVE_REJECT /
    # SYSTEM_SAFETY_REJECT / STRATEGY_MODE_FALSE_NEGATIVE /
    # NO_REJECT_FOUND / INSUFFICIENT_EVIDENCE / UNKNOWN).
    #
    # Phase 11C.1C-C-B-B-B-D-C-A boundary:
    # - Every event below is paper / report / evidence only. None
    #   of them authorises a real trade, modifies a real position,
    #   or flips a Phase 1 safety flag.
    # - The ``verdict`` carried by every payload is *descriptive* -
    #   it is NEVER an input to a trade-decision pipeline; the Risk
    #   Engine remains the single trade-decision gate.
    # - The attribution MUST NEVER modify position size, leverage,
    #   stop-loss, target price, the Risk Engine, the Execution
    #   FSM, ``symbol_limit``, candidate-pool capacity, anomaly
    #   thresholds, Regime weights, or any other runtime knob.
    # - The payload MUST NOT include any of:
    #   buy / sell / long / short / direction / entry / exit /
    #   position_size / leverage / stop / stop_loss / target /
    #   take_profit / risk_budget / order / execution_command /
    #   runtime_config_patch / symbol_limit_patch /
    #   threshold_patch / candidate_pool_patch /
    #   regime_weight_patch.
    # - Every payload MUST carry ``auto_tuning_allowed=False`` and
    #   ``evidence_refs``.
    # - A ``FALSE_NEGATIVE_REJECT`` verdict does **NOT** authorise
    #   the Risk Engine to be loosened. It routes the case to a
    #   human reviewer.
    #
    #   REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED - one
    #     :class:`RejectAttributionReport` was assembled across
    #     many records. Carries the aggregate counts, the verdict
    #     / reason summaries, and the operator-review / rule-review
    #     / data-recovery symbol lists.
    #   REJECT_TO_OUTCOME_CASE_ATTRIBUTED        - one
    #     :class:`RejectAttributionRecord` was emitted for one
    #     audited candidate. Carries the descriptive verdict +
    #     primary / secondary reasons + ``evidence_refs``.
    #   FALSE_NEGATIVE_REJECT_DETECTED           - shorthand event
    #     for the operator-review queue: one record was attributed
    #     ``FALSE_NEGATIVE_REJECT`` or ``STRATEGY_MODE_FALSE_NEGATIVE``.
    #   CORRECT_PROTECTIVE_REJECT_CONFIRMED      - shorthand event
    #     for the closed-out queue: one record was attributed as
    #     a correct protective reject (CORRECT_PROTECTIVE_REJECT
    #     or any of the hard-safety protective verdicts).
    REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED = (
        "REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED"
    )
    REJECT_TO_OUTCOME_CASE_ATTRIBUTED = "REJECT_TO_OUTCOME_CASE_ATTRIBUTED"
    FALSE_NEGATIVE_REJECT_DETECTED = "FALSE_NEGATIVE_REJECT_DETECTED"
    CORRECT_PROTECTIVE_REJECT_CONFIRMED = "CORRECT_PROTECTIVE_REJECT_CONFIRMED"

    # ------------------------------------------------------------------
    # Phase 11C.1C-C-B-B-B-D-C-B - Severe Missed Tail Triage v0.
    #
    # The Severe Missed Tail Triage v0 layer consumes the simplified
    # outputs of:
    #
    #   * Phase 11C.1C-C-B-B-B-D-A  Historical 60D Mover Coverage
    #     Audit (capture_status, miss reason, candidate-pool /
    #     universe / symbol-limit gating signals, data-gap flags),
    #   * Phase 11C.1C-C-B-B-B-D-B  Post-Discovery Outcome Metrics
    #     (outcome label, detection-timing label, post-seen MFE /
    #     MAE, remaining-upside-to-peak),
    #   * Phase 11C.1C-C-B-B-B-D-B.1 Historical Price Path /
    #     Kline-Path Adapter (price_path_status,
    #     price_path_missing_reason),
    #   * Phase 11C.1C-C-B-B-B-D-C-A Reject-to-Outcome Attribution
    #     (reject_attribution_verdict, primary reason),
    #
    # and emits, per audited candidate, a closed
    # ``SevereMissRootCause`` (UNIVERSE_GAP / SYMBOL_LIMIT_GAP /
    # CANDIDATE_POOL_EVICTED / THRESHOLD_TOO_STRICT /
    # PRE_ANOMALY_WEAK / ANOMALY_TOO_LATE / WS_DATA_GAP /
    # REST_REFERENCE_GAP / EVENT_HISTORY_MISSING /
    # PRICE_PATH_MISSING / PRICE_PATH_INSUFFICIENT /
    # NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME /
    # RISK_REJECTED_PROTECTIVE / RISK_REJECTED_FALSE_NEGATIVE /
    # STRATEGY_MODE_FALSE_NEGATIVE / LABEL_WINDOW_TOO_SHORT /
    # TRUE_DISCOVERY_FAILURE / INSUFFICIENT_EVIDENCE / UNKNOWN)
    # plus a closed ``SevereMissSeverity`` (LOW / MEDIUM / HIGH /
    # SEVERE / CRITICAL / INSUFFICIENT_EVIDENCE).
    #
    # Phase 11C.1C-C-B-B-B-D-C-B boundary:
    # - Every event below is paper / report / evidence only. None
    #   of them authorises a real trade, modifies a real position,
    #   or flips a Phase 1 safety flag.
    # - ``severity`` and ``root_cause`` are *descriptive* labels.
    #   They are NEVER inputs to a trade-decision pipeline; the
    #   Risk Engine remains the single trade-decision gate.
    # - The triage MUST NEVER modify position size, leverage,
    #   stop-loss, target price, the Risk Engine, the Execution
    #   FSM, ``symbol_limit``, candidate-pool capacity, anomaly
    #   thresholds, Regime weights, or any other runtime knob.
    # - The payload MUST NOT include any of: buy / sell / long /
    #   short / direction / entry / exit / position_size /
    #   leverage / stop / stop_loss / target / take_profit /
    #   risk_budget / order / execution_command /
    #   runtime_config_patch / symbol_limit_patch /
    #   threshold_patch / candidate_pool_patch /
    #   regime_weight_patch.
    # - Every payload MUST carry ``auto_tuning_allowed=False`` and
    #   ``evidence_refs``.
    # - A ``CRITICAL`` severity (e.g.
    #   ``RISK_REJECTED_FALSE_NEGATIVE``) does **NOT** authorise
    #   the Risk Engine to be loosened. It routes the case to a
    #   human reviewer via the operator-review queue.
    # - ``RAVEUSDT`` / ``STOUSDT`` and similar severe-miss
    #   candidates are recorded as **data-gap or severe-miss
    #   triage candidates only**; this layer never asserts a
    #   parameter error from a single coin.
    #
    #   SEVERE_MISSED_TAIL_TRIAGE_GENERATED      - one
    #     :class:`SevereMissTriageReport` was assembled across
    #     many records. Carries the aggregate counts, the
    #     root_cause summary, and the operator-review /
    #     rule-review / data-recovery symbol lists.
    #   SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED   - one
    #     :class:`SevereMissTriageRecord` was emitted for one
    #     audited candidate. Carries the descriptive root_cause +
    #     severity + ``evidence_refs``.
    #   SEVERE_MISS_ESCALATION_REQUIRED          - shorthand event
    #     for the operator-review / rule-review queue: one record
    #     was attributed ``SEVERE`` / ``CRITICAL`` severity OR a
    #     rule-related root_cause that needs human review.
    SEVERE_MISSED_TAIL_TRIAGE_GENERATED = "SEVERE_MISSED_TAIL_TRIAGE_GENERATED"
    SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED = (
        "SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED"
    )
    SEVERE_MISS_ESCALATION_REQUIRED = "SEVERE_MISS_ESCALATION_REQUIRED"


# Capital-flow event types per Issue #2 / Spec §28.3.
CAPITAL_EVENT_TYPES = frozenset(
    {
        EventType.CAPITAL_DEPOSIT,
        EventType.CAPITAL_WITHDRAWAL,
        EventType.PROFIT_HARVEST,
        EventType.CAPITAL_REBASE,
        EventType.RISK_BUDGET_RECALCULATED,
    }
)


@dataclass(frozen=True)
class Event:
    """Canonical event payload (Spec §12.1 + Issue #2 field contract).

    `event_id`     - lazily generated UUID4
    `timestamp`    - wall-clock ms when the event was *produced*
    `event_type`   - one of `EventType`
    `source_module`- module that emitted the event
    `symbol`       - optional symbol the event is about
    `position_id`  - optional position the event is about
    `order_id`     - optional order the event is about
    `payload`      - JSON-serialisable dict of free-form context
    `created_at`   - wall-clock ms when the row was *persisted*; populated
                     by SQLite on insert, returned to in-memory readers
                     by `EventRepository`. None for events that have not
                     yet been persisted.

    `payload` MUST be JSON-serialisable - the repository layer enforces
    this on append.
    """

    event_type: EventType
    source_module: str
    payload: dict[str, Any] = field(default_factory=dict)
    symbol: str | None = None
    position_id: str | None = None
    order_id: str | None = None
    timestamp: int = field(default_factory=now_ms)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type.value,
            "source_module": self.source_module,
            "symbol": self.symbol,
            "position_id": self.position_id,
            "order_id": self.order_id,
            "payload": self.payload,
            "created_at": self.created_at,
        }

    def serialise_payload(self) -> str:
        """Return a JSON string of `payload`. Raises if payload is not JSON-safe."""
        return json.dumps(self.payload, separators=(",", ":"), sort_keys=True)
