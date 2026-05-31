# AMA-RT Roadmap & Milestone Index

> **This document is the single canonical map of AMA-RT progress.**
> It replaces the unreadable fractal phase codes
> (`Phase 11C.1C-C-B-B-B-D-C-B`) with a flat, human-readable milestone
> scheme, and is the catch-up source of truth for "where are we now".
>
> The old phase codes are **not deleted** — they remain valid identifiers
> in code docstrings, events, tests, and the `docs/PHASE_GATE.md` gate
> ledger. This file is the **translation layer** between the legacy codes
> and readable names. When the two disagree, **trust this file for the
> human-facing status and `PHASE_GATE.md` for the formal gate record.**

---

## 1. Naming scheme

Two levels, both readable:

- **Stage** — `S0` … `S12`, a named band of related work
  (e.g. *S7 — Adaptive Discovery & Strategy Selector*).
- **Milestone** — a flat, ever-increasing id `M01` … `M68`, in ship /
  dependency order. A milestone never changes id once assigned, even if
  later milestones are inserted (new work gets the next free number).

Every milestone row carries its **legacy code** so nothing is lost and
any old docstring / event / test string can still be looked up here.

Status vocabulary:

| Status | Meaning |
| --- | --- |
| `CLOSED` | Formally accepted in `PHASE_GATE.md` with evidence on record. |
| `SHIPPED` | Implementation + doc + tests merged on `main`; formal gate closeout may still be pending (see the phase doc). |
| `IN_REVIEW` | Implementation merged, awaiting maintainer / evidence closeout. |
| `PARTIAL` | Toolchain accepted, but data / quality coverage explicitly incomplete (see notes). |
| `FORBIDDEN` | Locked by the Phase 1 safety lock; not started, not permitted yet. |

---

## 2. Where we are now (current position)

- **Latest head:** `M67 — Full-System Single-Altcoin Live Sandbox Audit`
  (legacy `PR117`), status `IN_REVIEW`. Sandbox result
  `overall_status=PASS`, `ready_for_real_key_validation=true`.
  This is a *go to real-key validation* signal, **not** a go-live.
- **Entire `S11` Live Launch Chain (M60–M67) is `IN_REVIEW`** — default
  posture stays safe (`live_trading=false`, `exchange_live_orders=false`,
  `trade_authority=false`, `ai_trade_authority=false`).
- **`M68 / Phase 12` (real money) is `FORBIDDEN`** and has not been
  initiated.
- **Known stale code constants** (left as-is on purpose; touching them is
  a code change, out of scope for the docs-only refactor): `app/__init__.py`
  still declares `__phase__ = "Phase 11C.1C-B-IN_REVIEW …"` and
  `__version__ = "1.4.0a11c.1c.b"`. The runtime banner therefore prints
  `M21`-era text even though the project head is `M67`. **Treat the banner
  as a build tag, not as the current milestone.** Re-aligning
  `__phase__` / `__version__` is filed as a future code task in
  `docs/IMPLEMENTATION_PLAN.md`.

```
Progress at a glance
S0  Core & Safety Foundation .................... ####  4/4   CLOSED
S1  Market Structure, Signals & Risk ............ ####  4/4   CLOSED
S2  Learning-Ready Data ........................ #     1/1   CLOSED
S3  Execution .................................. #     1/1   CLOSED
S4  Operator Intelligence ...................... ####  4/4   CLOSED
S5  Cloud Paper Operations ..................... ##    2/2   CLOSED
S6  Real Public Market Data .................... ###   3/3   CLOSED
S7  Adaptive Discovery & Strategy Selector ..... #####  5/5   CLOSED
S8  Discovery Quality, Alpha Evidence & Audit .. mixed (CLOSED + IN_REVIEW)
S9  Blind Walk-Forward Simulation .............. SHIPPED
S10 AI Intelligence Layer ...................... SHIPPED
S11 Live Launch Chain .......................... IN_REVIEW (current)
S12 Real-Money Trading ......................... FORBIDDEN
```

---

## 3. Milestone index (full mapping table)

### S0 — Core & Safety Foundation

| Milestone | Name | Legacy code | Status |
| --- | --- | --- | --- |
| M01 | Safety Foundation (five locked safety flags) | Phase 1 | CLOSED |
| M02 | Event Sourcing + Database Set | Phase 2 | CLOSED |
| M03 | Exchange Gateway (read-only abstract) | Phase 3 | CLOSED |
| M04 | Market Data Buffer | Phase 4 | CLOSED |

### S1 — Market Structure, Signals & Risk

| Milestone | Name | Legacy code | Status |
| --- | --- | --- | --- |
| M05 | Regime + Universe + Liquidity | Phase 5 | CLOSED |
| M06 | Pre-Anomaly + Anomaly + Confirmation + Manipulation | Phase 6 | CLOSED |
| M07 | Risk Engine + No-Trade Gate + Account Tier | Phase 7 | CLOSED |
| M08 | Capital Flow Engine | Phase 8 | CLOSED |

### S2 — Learning-Ready Data

| Milestone | Name | Legacy code | Status |
| --- | --- | --- | --- |
| M09 | Learning-Ready Data Contract + Test Data Export | Phase 8.5 | CLOSED |

### S3 — Execution

| Milestone | Name | Legacy code | Status |
| --- | --- | --- | --- |
| M10 | Execution FSM + Reconciliation | Phase 9 | CLOSED |

### S4 — Operator Intelligence

| Milestone | Name | Legacy code | Status |
| --- | --- | --- | --- |
| M11 | Replay Engine substrate | Phase 10A | CLOSED |
| M12 | Reflection + Replay (read-only) | Phase 10B | CLOSED |
| M13 | LLM Guarded Interpreter (receive-only) | Phase 10C | CLOSED |
| M14 | Telegram Outbound + Export Commands | Phase 10D | CLOSED |

### S5 — Cloud Paper Operations

| Milestone | Name | Legacy code | Status |
| --- | --- | --- | --- |
| M15 | Cloud Paper Acceptance | Phase 11B | CLOSED |
| M16 | Cloud Paper — High-Frequency observation | Phase 11B-HF | CLOSED |

### S6 — Real Public Market Data

| Milestone | Name | Legacy code | Status |
| --- | --- | --- | --- |
| M17 | Public Market Read-Only Ingestion | Phase 11C | CLOSED |
| M18 | REST Rate-Limit Governor & 418 Protection | Phase 11C.1A | CLOSED |
| M19 | WS-First All-Market Radar + SymbolUniverse | Phase 11C.1B | CLOSED |

### S7 — Adaptive Discovery & Strategy Selector

| Milestone | Name | Legacy code | Status |
| --- | --- | --- | --- |
| M20 | Adaptive Candidate / Regime / Strategy Selector Contracts | Phase 11C.1C-A | CLOSED |
| M21 | Adaptive Candidate Runtime Calibration & Early Tail Discovery | Phase 11C.1C-B | CLOSED |
| M22 | MFE/MAE Label Queue Runtime & Tail Outcome Tracking | Phase 11C.1C-C-A | CLOSED |
| M23 | Strategy Validation Lab + Cluster Exposure Control | Phase 11C.1C-C-B-A | CLOSED |
| M24 | Strategy Validation Dataset Builder & Quality Gate | Phase 11C.1C-C-B-B-A | CLOSED |

### S8 — Discovery Quality, Alpha Evidence & Audit

> Umbrella legacy code: `Phase 11C.1C-C-B-B-B` ("Alpha Evidence Program").

| Milestone | Name | Legacy code | Status |
| --- | --- | --- | --- |
| M25 | Paper Alpha Gate | 11C.1C-C-B-B-B-A | CLOSED |
| M26 | Regime & Cluster Cohort Evidence Pack | 11C.1C-C-B-B-B-B | CLOSED |
| M27 | Long-Window Cohort Stability & Sample Sufficiency | 11C.1C-C-B-B-B-C | CLOSED |
| M28 | Mover Capture Recall & Missed-Tail Coverage Audit | 11C.1C-C-B-B-B-D | CLOSED |
| M29 | Historical 60D Mover Coverage Backfill | 11C.1C-C-B-B-B-D-A | CLOSED |
| M30 | Post-Discovery Outcome Metrics | 11C.1C-C-B-B-B-D-B | PARTIAL (toolchain accepted; price-path data incomplete) |
| M31 | Historical Price Path / Kline-Path Adapter | 11C.1C-C-B-B-B-D-B.1 | PARTIAL (daily-bucket only) |
| M32 | Reject-to-Outcome Attribution | 11C.1C-C-B-B-B-D-C-A | SHIPPED |
| M33 | Severe Missed Tail Triage (RAVEUSDT / STOUSDT root-cause) | 11C.1C-C-B-B-B-D-C-B | IN_REVIEW |
| M34 | Discovery Quality Scorecard | 11C.1C-C-B-B-B-D-D | IN_REVIEW |
| M35 | Block B Integrated Evidence Checkpoint | 11C.1C-C-B-B-B-D-E | IN_REVIEW |
| M36 | Replay Extension for 11C Adaptive Events | 11C.1C-C-B-B-B-E-A | SHIPPED |
| M37 | Reflection Extension for 11C Adaptive Events | 11C.1C-C-B-B-B-E-B | SHIPPED |
| M38 | Evidence Contract Baseline | 11C.1C-C-B-B-B-E-C | SHIPPED |
| M39 | Block C Integrated Checkpoint | 11C.1C-C-B-B-B-E-D | IN_REVIEW |

### S9 — Blind Walk-Forward Simulation

> Umbrella legacy code: `Phase 11C.1D-D` ("Strict Blind Walk-Forward
> Sim-Live Constitution").

| Milestone | Name | Legacy code | Status |
| --- | --- | --- | --- |
| M40 | Paper Shadow Strategy Validation | 11C.1D-B | SHIPPED |
| M41 | Risk / Execution / Capital Safety Matrix | 11C.1D-C | SHIPPED |
| M42 | Strict Blind Walk-Forward Sim-Live Constitution (umbrella) | 11C.1D-D | SHIPPED |
| M43 | Simulation Clock & Time-Wall Guard | 11C.1D-D-A | SHIPPED |
| M44 | Historical Market Store | 11C.1D-D-B | SHIPPED |
| M45 | Replay Feed Provider | 11C.1D-D-C | SHIPPED |
| M46 | Mock Exchange Pessimistic Fill Model | 11C.1D-D-D | SHIPPED |
| M47 | Simulated Capital Flow & Trade Ledger | 11C.1D-D-E | SHIPPED |
| M48 | Telegram Sandbox Outbox | 11C.1D-D-F | SHIPPED |
| M49 | Blind Walk-Forward Runner | 11C.1D-D-G | SHIPPED |
| M50 | Historical Data Ingestion Backfill | 11C.1D-D-H | SHIPPED |
| M51 | Blind Runner ↔ Historical Store Glue | 11C.1D-D-I | SHIPPED |

### S10 — AI Intelligence Layer (no trade authority)

| Milestone | Name | Legacy code | Status |
| --- | --- | --- | --- |
| M52 | AI Evidence Bundle Builder | Phase AI-1 | SHIPPED |
| M53 | Truth Layer / Evidence Citation Contract | Phase AI-2 | SHIPPED |
| M54 | Reality Check Layer | Phase AI-3 | SHIPPED |
| M55 | AI Intelligence Output Schema + DeepSeek Offline Sandbox | Phase AI-4 | SHIPPED |
| M56 | Operator Briefing + Evidence Compression | Phase AI-5 | SHIPPED |
| M57 | AI Replay / Reflection Integration | Phase AI-6 | SHIPPED |
| M58 | AI Integrated Checkpoint | Phase AI-CHECKPOINT | SHIPPED |

### S11 — Live Launch Chain (gated; default-safe)

| Milestone | Name | Legacy code | Status |
| --- | --- | --- | --- |
| M60 | Live Foundation (path isolation + mode guard + capital ladder + leverage gate) | PR110 | IN_REVIEW |
| M61 | API Integration Pack (Binance + Telegram + DeepSeek health/permission) | PR111 | IN_REVIEW |
| M62 | Live Capital / Risk / Funding-Aware PnL / 10U Profile | PR112 | IN_REVIEW |
| M63 | Live Execution Gateway (15-point gate) | PR113 | IN_REVIEW |
| M64 | Telegram Operator Console + Live Funding Attribution | PR114 | IN_REVIEW |
| M65 | DeepSeek Live Intelligence (intelligence-only) | PR115 | IN_REVIEW |
| M66 | 10U LIVE_LIMITED Launch Pack | PR116 | IN_REVIEW |
| M67 | Full-System Single-Altcoin Live Sandbox Audit *(current head)* | PR117 | IN_REVIEW |

> Note: `M59` is intentionally reserved as the boundary between the AI
> layer (S10) and the live chain (S11); no work is assigned to it.

### S12 — Real-Money Trading

| Milestone | Name | Legacy code | Status |
| --- | --- | --- | --- |
| M68 | Real money / live trading | Phase 12 | **FORBIDDEN** |

> `M68` is reachable **only** through the Spec §41 Go/No-Go checklist,
> which has not been initiated. No `S11` milestone (incl. `M67`)
> authorises it.

---

## 4. Reverse lookup (legacy code → milestone)

For quickly translating an old docstring / event / commit message.

| Legacy code | Milestone |
| --- | --- |
| Phase 1 … 11C | M01–M17 (linear, in order) |
| Phase 11C.1A | M18 |
| Phase 11C.1B | M19 |
| Phase 11C.1C-A / -B | M20 / M21 |
| Phase 11C.1C-C-A | M22 |
| Phase 11C.1C-C-B-A / -B-B-A | M23 / M24 |
| Phase 11C.1C-C-B-B-B-A … -B-C | M25–M27 |
| Phase 11C.1C-C-B-B-B-D … -D-E | M28–M35 |
| Phase 11C.1C-C-B-B-B-E-A … -E-D | M36–M39 |
| Phase 11C.1D-B / -C / -D / -D-A … -D-I | M40 / M41 / M42 / M43–M51 |
| Phase AI-1 … AI-CHECKPOINT | M52–M58 |
| PR110 … PR117 | M60–M67 |
| Phase 12 | M68 |

---

## 5. Conventions for future milestones

To stop the fractal-naming problem from recurring:

1. **New work takes the next free `M##`.** Never append another
   `-A`/`-B` suffix to an existing milestone code.
2. **Give it a readable name first**, the legacy code (if any) second.
3. **Add the row here** (in the right stage) in the same change that
   ships it, and set its status.
4. **`PHASE_GATE.md` stays the formal gate ledger;** this file stays the
   human-readable index. Keep them consistent.
