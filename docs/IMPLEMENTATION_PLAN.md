# AMA-RT Implementation Plan

> Companion to `docs/ROADMAP.md` (the milestone map) and
> `docs/PHASE_GATE.md` (the formal gate ledger). This file answers
> **"what is done, what is in flight, and what is next"** in milestone
> order. It uses the readable `M##` / `S#` ids defined in
> `docs/ROADMAP.md`; the legacy phase codes are kept in that mapping.

Last reconciled: `PR117` head (`M67`, `IN_REVIEW`).

---

## 1. Done (foundation through discovery)

| Stage | Milestones | Status |
| --- | --- | --- |
| S0 Core & Safety Foundation | M01–M04 | CLOSED |
| S1 Market Structure, Signals & Risk | M05–M08 | CLOSED |
| S2 Learning-Ready Data | M09 | CLOSED |
| S3 Execution | M10 | CLOSED |
| S4 Operator Intelligence | M11–M14 | CLOSED |
| S5 Cloud Paper Operations | M15–M16 | CLOSED |
| S6 Real Public Market Data | M17–M19 | CLOSED |
| S7 Adaptive Discovery & Strategy Selector | M20–M24 | CLOSED |

These stages are accepted in `PHASE_GATE.md` with evidence on record and
are not expected to change except for bug fixes.

## 2. In flight (discovery quality + live chain)

### S8 — Discovery Quality, Alpha Evidence & Audit
- **CLOSED:** M25 Paper Alpha Gate, M26 Regime & Cluster Cohort Evidence
  Pack, M27 Long-Window Cohort Stability, M28 Mover Capture Recall Audit,
  M29 Historical 60D Mover Coverage Backfill.
- **PARTIAL:** M30 Post-Discovery Outcome Metrics (toolchain accepted,
  price-path data incomplete), M31 Historical Price Path / Kline-Path
  Adapter (daily-bucket only).
- **IN_REVIEW:** M33 Severe Missed Tail Triage, M34 Discovery Quality
  Scorecard, M35 Block B Integrated Evidence Checkpoint, M39 Block C
  Integrated Checkpoint.
- **SHIPPED:** M32 Reject-to-Outcome Attribution, M36 Replay Extension,
  M37 Reflection Extension, M38 Evidence Contract Baseline.

### S9 — Blind Walk-Forward Simulation (M40–M51) — SHIPPED
Full sim-live constitution, historical store, replay feed, pessimistic
fill model, simulated capital flow + safety floor / kill switch, blind
walk-forward runner, and the bounded-memory store-query fix.

### S10 — AI Intelligence Layer (M52–M58) — SHIPPED
Evidence bundle, truth-layer citation contract, reality check, intelligence
output schema + DeepSeek offline sandbox, operator briefing + evidence
compression, replay/reflection integration, integrated checkpoint. The AI
has **no trade authority** at any milestone.

### S11 — Live Launch Chain (M60–M67) — IN_REVIEW (current focus)
M60 Live Foundation → M61 API Integration → M62 Live Capital/Risk/PnL →
M63 Live Execution Gateway → M64 Telegram Operator Console → M65 DeepSeek
Live Intelligence → M66 10U LIVE_LIMITED Launch Pack → **M67 Full-System
Single-Altcoin Live Sandbox Audit (head)**. Sandbox result
`overall_status=PASS`, `ready_for_real_key_validation=true`. Default
posture stays safe; no real order is sent by default.

## 3. Next allowed steps (in order)

1. **Close out the S11 live chain.** Move M60–M67 from `IN_REVIEW` to
   `ACCEPTED` via maintainer review + the documented acceptance evidence
   for each. No new live capability is needed for this — it is review and
   evidence capture.
2. **Real-key validation (not go-live).** Run
   `scripts/live_launch_check.py --require-real-keys` with real read-only
   credentials and the PR113 execution handshake in shadow. This validates
   connectivity/permissions only; it does **not** flip any safety flag.
3. **Finish the S8 IN_REVIEW slices** (M33–M35, M39) so discovery-quality
   evidence is complete before any capital is risked.
4. **Phase 12 (M68) remains FORBIDDEN.** The only path is the Spec §41
   Go/No-Go checklist, which has **not** been initiated. No S11 milestone
   authorises it.

## 4. Tracked maintenance tasks (code; out of scope for the docs-only refactor)

These are recorded here so they are not lost. They require code changes
and were intentionally **not** done during the documentation refactor:

- **T1 — Re-align the runtime build tag.** `app/__init__.py` still declares
  `__phase__ = "Phase 11C.1C-B-IN_REVIEW …"` (M21-era) and
  `__version__ = "1.4.0a11c.1c.b"`. Update both to reflect the current head
  (e.g. an M67 / PR117 label) so the boot banner stops printing stale
  text. Note the existing `__version__` is **not** PEP 440-valid, which
  breaks `pip install -e .`; pick a PEP 440-valid string when updating.
- **T2 — Optional:** surface the `M##` milestone id in the boot banner
  alongside (or instead of) the legacy phase code.

## 5. Working rules

- One milestone = one readable name + next free `M##`; never append another
  `-A`/`-B` suffix to an existing code (see `ROADMAP.md` §5).
- Keep `ROADMAP.md` (readable index), `PHASE_GATE.md` (formal gate ledger),
  and this plan consistent in the same change that ships a milestone.
- The five Phase 1 safety flags stay locked across every milestone below
  Phase 12.
