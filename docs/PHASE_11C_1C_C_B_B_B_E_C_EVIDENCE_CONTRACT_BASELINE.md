# Phase 11C.1C-C-B-B-B-E-C — Evidence Contract Baseline v0

> **Status: IN_REVIEW (after this implementation PR; not `ACCEPTED`
> until maintainer review).**
> **Block:** Block C3 (Evidence Contract Baseline v0).
> **Predecessors:** Block A complete; Block B implementation chain
> complete; Block B Integrated Evidence Checkpoint =
> `PARTIAL_EVIDENCE` (advance allowed); Block C1 (Phase
> 11C.1C-C-B-B-B-E-A *Replay Extension for 11C Adaptive Events v0*)
> merged; Block C2 (Phase 11C.1C-C-B-B-B-E-B *Reflection Extension
> for 11C Adaptive Events v0*) merged.
> **Successor allowed by this phase:** Block C closeout
> (whole-block, **NOT** per-PR) **OR** AI Evidence Bundle
> preparation later. **No other phase is unlocked.**

## Purpose

The project's report / replay / reflection / discovery-quality /
post-discovery / severe-miss / reject-attribution surfaces have all
shipped a free-form `evidence_refs: tuple[str, ...]` field as their
provenance handle. Each surface has been free to use whatever string
shape it preferred. The Evidence Contract Baseline v0 introduces ONE
unified, paper / report / evidence-only `evidence_refs` contract so
every Block A / Block B output can be validated, audited, and
round-tripped through a single rule:

> **Any claim must be traceable to evidence; a claim that lacks
> evidence MUST be degraded, NEVER accepted as fact, and NEVER
> silently dropped.**

The baseline does **NOT** retrofit existing surfaces (that is
out-of-scope and explicitly forbidden in this phase). It ships the
contract and the validator so future PRs can consume / produce
contract-shaped evidence.

This is **NOT** AI. This phase does **NOT** wire in DeepSeek. This
phase does **NOT** make trading decisions. This phase does **NOT**
modify any runtime parameter. This phase does **NOT** unlock
Phase 12.

## Evidence reference format

The contract recognises a small, closed namespace vocabulary, all
shapes parsed by
`app.evidence.evidence_contract.parse_evidence_ref`:

| Namespace      | Shape                                | Example                                                                |
|----------------|--------------------------------------|------------------------------------------------------------------------|
| `event`        | `event:<EVENT_TYPE>:<event_id>`      | `event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_123`               |
| `symbol`       | `symbol:<SYMBOL>`                    | `symbol:RAVEUSDT`                                                      |
| `opportunity`  | `opportunity:<opportunity_id>`       | `opportunity:opp_123`                                                  |
| `scan_batch`   | `scan_batch:<scan_batch_id>`         | `scan_batch:batch_42`                                                  |
| `metric`       | `metric:<metric_name>:<window>`      | `metric:capture_rate:24h`                                              |
| `report`       | `report:<report_id>`                 | `report:block_b_integrated_evidence_report`                            |

Any other namespace is parsed into `EvidenceRefType.UNKNOWN` with a
warning attached, and is treated as **invalid for accept-as-fact
purposes**. The validator NEVER infers a ref it was not given.

## Public API

### Enums

* `EvidenceRefType` — closed namespace enum:
  `EVENT`, `SYMBOL`, `OPPORTUNITY`, `SCAN_BATCH`, `METRIC`,
  `REPORT`, `UNKNOWN`.
* `ClaimStatus` — closed claim-outcome enum:
  `ACCEPTED`, `DEGRADED_NO_EVIDENCE`,
  `REJECTED_INVALID_EVIDENCE`, `PARTIAL`, `INSUFFICIENT_EVIDENCE`.

### Value objects

* `EvidenceRef` — parsed evidence reference (`raw`, `ref_type`,
  `namespace`, `identifier`, `valid`, `warnings`).
* `EvidenceClaimInput` — caller-supplied claim (`claim_id`,
  `claim_type`, `text_or_label`, `evidence_refs`,
  `confidence_label`).
* `EvidenceClaim` — validated claim (preserves the input claim
  fields plus `parsed_refs`, `evidence_refs` (valid only),
  `confidence_label`, `degraded`, `degradation_reason`, `status`,
  `warnings`).
* `EvidenceContractResult` — aggregate result over many claims
  (`accepted_claim_count`, `degraded_claim_count`,
  `rejected_claim_count`, `partial_claim_count`,
  `missing_evidence_count`, `invalid_evidence_count`,
  `total_claim_count`, `overall_status`, `claims`, `warnings`,
  `auto_tuning_allowed=False`).

### Functions / classes

* `parse_evidence_ref(raw)` — total parser; every input produces
  an `EvidenceRef`.
* `EvidenceContractValidator.validate_claim(claim_input)` — single
  claim.
* `EvidenceContractValidator.validate(claims)` — many claims.
* `validate_claims(claims)` — convenience wrapper that uses a
  default validator.

## Claim validation rules

For every input claim:

1. The validator parses every supplied `raw` evidence-ref string.
2. A claim with **at least one valid** parsed ref AND no invalid
   refs is **accepted** (`status = ACCEPTED`). Its `evidence_refs`
   tuple preserves the valid raw strings in input order.
3. A claim with **no** evidence refs is **degraded** to
   `status = DEGRADED_NO_EVIDENCE`. The original `text_or_label`
   is preserved verbatim. `confidence_label` is forced to
   `insufficient_evidence`. `degraded = True`.
   `degradation_reason = "no_evidence_refs_supplied"`.
4. A claim whose every ref is invalid is **rejected** as
   `status = REJECTED_INVALID_EVIDENCE`. The claim is preserved.
   `degraded = True`.
   `degradation_reason = "all_evidence_refs_invalid"`. The invalid
   refs surface as warnings on the claim.
5. A claim with a mix of valid + invalid refs is recorded as
   `status = PARTIAL`. Valid refs are preserved on
   `claim.evidence_refs`. Invalid refs surface on
   `claim.parsed_refs` and `claim.warnings`.
   `degradation_reason = "partial_invalid_evidence_refs"`.
6. The validator NEVER infers a missing `evidence_refs`. It NEVER
   calls an LLM. It NEVER consults chat history. It NEVER mutates
   the input.

## Degradation rules

* No evidence supplied → `DEGRADED_NO_EVIDENCE` (the claim text /
  label is preserved; the claim is NOT silently dropped, but it is
  also NOT accepted as fact).
* Only invalid evidence supplied → `REJECTED_INVALID_EVIDENCE`
  (warnings preserved, no inference performed).
* Mixed valid + invalid → `PARTIAL` (valid refs preserved,
  warnings preserved, claim is descriptive only).
* Empty / `None` claim list → result `overall_status =
  INSUFFICIENT_EVIDENCE` with `warnings = ("no_claims_supplied",)`.

## Forbidden payload keys (recursively enforced)

`FORBIDDEN_EVIDENCE_PAYLOAD_KEYS` contains every direction /
sizing / risk / runtime-config-patch token. The recursive guard
`_assert_no_forbidden_keys_recursive` is invoked from every
`to_dict()` boundary so no forbidden key can be smuggled in.

The set covers (at minimum): `buy`, `sell`, `long`, `short`,
`direction`, `side`, `entry`, `exit`, `position_size`, `leverage`,
`stop`, `stop_loss`, `stop_price`, `target`, `target_price`,
`take_profit`, `risk_budget`, `order`, `order_type`,
`execution_command`, `runtime_config_patch`, `symbol_limit_patch`,
`threshold_patch`, `candidate_pool_patch`, `regime_weight_patch`.

## Event types

Three new descriptive event types are registered on
`app.core.events.EventType`:

* `EVIDENCE_CONTRACT_VALIDATED` — one
  `EvidenceContractResult` payload was assembled across many
  claims. Carries the aggregate counts + `overall_status` +
  `auto_tuning_allowed=False`.
* `EVIDENCE_CLAIM_DEGRADED` — one claim was degraded to
  `DEGRADED_NO_EVIDENCE` because no `evidence_refs` were
  supplied.
* `EVIDENCE_CLAIM_REJECTED` — one claim was rejected as
  `REJECTED_INVALID_EVIDENCE` because every supplied evidence
  ref failed to parse.

No trade-action / position / sizing / risk-budget event is added.

## Acceptance criteria

The implementation PR ships:

* `app/evidence/__init__.py` (new package).
* `app/evidence/evidence_contract.py` (new module).
* `app/core/events.py` — three new descriptive event types only
  (`EVIDENCE_CONTRACT_VALIDATED`, `EVIDENCE_CLAIM_DEGRADED`,
  `EVIDENCE_CLAIM_REJECTED`).
* `tests/unit/test_evidence_contract_baseline.py` — covers the
  brief's 10 numbered checks plus closed-vocabulary integrity
  and Mapping-input compatibility.
* `docs/PHASE_11C_1C_C_B_B_B_E_C_EVIDENCE_CONTRACT_BASELINE.md`
  — this design / acceptance doc.
* `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
  `docs/CHANGELOG.md` updates.

The phase is marked **IN_REVIEW** here. Maintainer-led review of
the implementation PR is the only path to **ACCEPTED**.

### Test-coverage map

| # | Brief check                                                                                               | Test(s)                                                                                                                                                                          |
|---|-----------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1 | valid event ref `event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_123` parses                           | `test_event_evidence_ref_parses_into_event_ref_type`, `test_event_evidence_ref_missing_event_id_is_invalid`                                                                      |
| 2 | valid `symbol:` / `opportunity:` / `report:` (and `scan_batch:` / `metric:`) refs parse                   | `test_symbol_evidence_ref_parses`, `test_opportunity_evidence_ref_parses`, `test_report_evidence_ref_parses`, `test_scan_batch_evidence_ref_parses`, `test_metric_evidence_ref_parses` |
| 3 | claim without refs is degraded, never accepted                                                            | `test_claim_without_evidence_refs_is_degraded_not_accepted`, `test_aggregate_overall_status_is_degraded_when_only_no_evidence_claims`                                            |
| 4 | invalid ref is rejected or degraded, never silently passed                                                | `test_invalid_evidence_ref_rejects_claim_when_only_invalid_refs`, `test_partial_invalid_evidence_ref_marks_claim_partial`, `test_invalid_unknown_namespace_does_not_pass_silently` |
| 5 | multiple valid refs preserved verbatim                                                                    | `test_multiple_valid_refs_are_preserved_in_order`                                                                                                                                |
| 6 | validator never invents refs                                                                              | `test_validator_does_not_invent_evidence_refs`, `test_validator_does_not_inject_extra_refs_on_partial`                                                                           |
| 7 | result summary counts correct                                                                             | `test_result_summary_counts_are_correct`, `test_empty_input_is_insufficient_evidence`, `test_none_input_is_insufficient_evidence`                                                |
| 8 | forbidden fields absent in every emitted payload                                                          | `test_forbidden_payload_keys_complete`, `test_emitted_payloads_contain_no_forbidden_keys`, `test_to_dict_hard_pins_auto_tuning_allowed_false`                                    |
| 9 | forbidden imports (no `app.risk` / `app.execution` / `app.exchanges` / `app.llm` / `app.telegram`)        | `test_evidence_contract_module_does_not_import_forbidden_modules`                                                                                                                |
| 10 | deterministic output on the same input                                                                   | `test_validator_output_is_deterministic`, `test_parse_evidence_ref_is_deterministic`                                                                                             |

## Safety boundary

* `mode = paper`
* `live_trading = False`
* `exchange_live_orders = False`
* `right_tail = False`
* `llm = False`
* `telegram_outbound_enabled = False`
* `binance_private_api_enabled = False`
* no Binance API key / secret
* no signed endpoint
* no private websocket
* no `listenKey`
* no real Telegram outbound
* no DeepSeek trade decision
* **Phase 12 = FORBIDDEN**
* **`auto_tuning_allowed = False`** on every emitted result;
  hard-pinned at the `to_dict` boundary.

## What this phase does NOT authorise

* This does **NOT** authorise live trading.
* This does **NOT** authorise auto-tuning.
* This does **NOT** use AI / DeepSeek.
* This does **NOT** modify any Risk / Execution / Exchange / LLM
  / Telegram / config file.
* This does **NOT** retrofit existing surfaces. Block A / Block B
  surfaces continue to ship `evidence_refs: tuple[str, ...]`
  fields exactly as they did before this phase.
* This does **NOT** close out cloud evidence — closeout is done
  per-block, not per-PR.
* This does **NOT** start Phase 12. **Phase 12 remains
  FORBIDDEN.**

## Successor allowed by this phase

A successful Phase 11C.1C-C-B-B-B-E-C only allows:

* the upcoming **Block C closeout** (whole-block, after all of
  C1 + C2 + C3 are merged and reviewed), OR
* the eventual **AI Evidence Bundle preparation** that will
  consume the contract's structured claims.

No other phase is unlocked. **Phase 12 remains FORBIDDEN.**

## Test commands

```
python -m pytest tests/unit/test_evidence_contract_baseline.py -q
python -m pytest tests/unit -q
```

The first command ships **31 PASSING** tests. The second command
reports **2711 PASSING** unit tests, 0 failures (was 2680 before
this phase; +31 from this phase).
