# Phase 8.5 — Telegram Export Contract (deferred to Issue #10)

This document captures the **future** Telegram integration for the
Phase 8.5 Test Data Export Service.

> **Phase 8.5 boundary:** the Telegram outbound bot is **NOT** shipped
> in Phase 8.5. There is no live Telegram client, no bot token, no
> outbound HTTP request, and no message of any kind sent off-host
> from this codebase. The `app.telegram` package remains a Phase 1
> in-process command-bus skeleton. This file is the contract that
> Issue #10 (LLM / Telegram outbound / Replay / Reflection) MUST
> honour when the real client is wired in.

## 1. Commands the Telegram Command Center MUST add (Issue #10)

The following commands extend the existing in-process command bus.
Each command produces a redacted `.zip` via the Phase 8.5
`TestDataExportService` and replies with two messages: a short text
summary, then the file as a `document` attachment.

| Command                              | Range          | Type filter      |
| ------------------------------------ | -------------- | ---------------- |
| `/export_test_data 24h`              | last 24 h      | `all`            |
| `/export_test_data 7d`               | last 7 d       | `all`            |
| `/export_test_data today`            | today UTC      | `all`            |
| `/export_rejections 24h`             | last 24 h      | `rejections`     |
| `/export_report today`               | today UTC      | `all` + summary  |
| `/export_learning_dataset 7d`        | last 7 d       | `learning`       |

The full set of allowed type filters is the Issue contract:
`all`, `events`, `opportunities`, `rejections`, `capital`, `state`,
`learning`. The full set of allowed range labels is `today`, `24h`,
`7d`, `range` (the last requires explicit start/end and is operator-
only — accept it via Telegram only after operator allow-list checks).

## 2. Behavioural contract

For every export command, Issue #10 MUST:

1. **Reply with a short text summary first.** The message is human-
   readable text built from `manifest.json` (event count, opportunity
   count, risk-rejected count, capital event count, time range,
   trading mode). Never paste the raw events into the chat.
2. **Generate the zip via `TestDataExportService.export(...)`.** The
   service is the single source of truth for redaction, manifest, and
   summary; Issue #10 MUST NOT re-implement any of those.
3. **Send the zip as a `document` / file attachment.** Use the
   Telegram bot API `sendDocument` method, NOT `sendMessage` with a
   chunked body. The chat window must remain readable.
4. **Refuse to dump raw `.jsonl` content into the chat window.** If
   the operator asks, reply with the file attachment instead.
5. **Honour the size cap.** Telegram's `sendDocument` accepts files
   up to ~50 MB. When the export exceeds the cap (the service raises
   `ExportError`):
   - Reply with a short error message that suggests the operator
     narrows the range (`24h` → `today`, `7d` → `24h`) or the type
     filter (`all` → a single shard).
   - **Do not** silently truncate. Do not split bytes mid-event.
   - Telegram-side fragmentation (uploading multiple smaller zips
     for the same window) is OPTIONAL; if implemented it MUST send
     one `manifest.json` per zip with a `chunk_index` / `chunk_total`
     pair so the consumer can stitch the dataset back together.
6. **Apply the redaction layer.** The service already applies
   `app.exports.redaction.redact` and runs
   `assert_no_forbidden_substrings` on every file before writing the
   zip. Issue #10 MUST NOT bypass either guard.
7. **Pin the message to a paper-mode banner.** Every export response
   MUST include `mode=paper` (or whatever `manifest.trading_mode`
   says) so the operator never confuses an export with a live-trading
   audit.
8. **Operator allow-list.** The `/export_*` family is restricted to
   the existing Telegram admin allow-list. Non-admin users get a
   single rejection message; the action is recorded as a
   `TELEGRAM_COMMAND_RECEIVED` event with the rejection reason.

## 3. Output bytes contract

For every Telegram-driven export the following MUST hold:

- The bytes attached to the chat are a `.zip` file produced by
  `TestDataExportService`, NOT a raw `.jsonl`, NOT a `.csv`.
- The `.zip` contains at minimum: `manifest.json`, `summary_report.md`,
  and the per-type `.jsonl` files described in
  [`app/exports/service.py`](../app/exports/service.py). The exact
  set depends on the type filter.
- `manifest.json.redaction_applied` is `true`.
- `manifest.json.trading_mode` is the live setting at export time;
  Phase 1 hard-locks it to `"paper"` until the Go/No-Go checklist
  (Spec §41) clears.
- No bytes attached to the chat may contain any of the substrings
  enumerated by `app.exports.redaction.forbidden_substrings()`. The
  service refuses to write the zip if any do.
- No path under `manifest.json.files` may name a `.csv` unless the
  operator explicitly asked for one and the export service was
  extended to produce it. CSV is OPTIONAL per the Issue contract;
  Phase 8.5 ships `.jsonl` only.

## 4. Phase 8.5 prohibitions (Issue #10 must keep them)

These are inherited from the Phase 1 / Phase 8.5 hard rules and may
not be loosened by the Telegram integration:

- **No outbound HTTP / WebSocket from `app/`.** The Phase 1 lock is
  enforced by `tests/unit/test_phase{3,4,5,6,7}_no_network.py` and
  Phase 8.5 adds `tests/unit/test_phase8_5_no_network.py` for the
  new packages.
- **No real API key in process memory.** Telegram's bot token MUST
  be loaded from a runtime secret store at request time and dropped
  from memory immediately after use; `BinanceClient` continues to
  refuse any credential.
- **No live trading triggered by an export command.** Export is
  read-only against `events.db`; it MUST NOT cause the Risk Engine,
  the Execution FSM, or the Capital Flow Engine to mutate any state.
- **No LLM in the export path.** Phase 8.5 forbids any LLM call;
  Issue #10 may add an LLM-summary command but MUST gate it with
  `llm_enabled=True` and route through the Risk Engine for any
  trade-impacting decision (Spec rule 7).
- **No raw operator content in `summary_report.md` or
  `manifest.json`.** Both files are produced by Phase 8.5 builders;
  Issue #10 MUST NOT splice in user-supplied text without first
  passing it through `redact(...)`.

## 5. Pseudo-code (Issue #10 reference)

```python
# Issue #10 - reference shape ONLY. Phase 8.5 does NOT ship this code.

def handle_export_test_data_command(cmd, *, service, send_text, send_document):
    # 1. operator allow-list
    if cmd.user_id not in admin_allow_list:
        send_text(cmd.chat_id, "⛔ /export_* is admin-only.")
        return
    # 2. parse range / type
    range_label, type_filter = _parse_export_args(cmd.args)
    # 3. run the export
    try:
        result = service.export(
            range_label=range_label,
            type_filter=type_filter,
        )
    except ExportError as exc:
        send_text(cmd.chat_id,
                  f"⚠️  Export refused: {exc}. "
                  f"Try a smaller range or a single type filter.")
        return
    # 4. short summary first
    send_text(cmd.chat_id, render_short_summary(result.manifest))
    # 5. attach the file (NOT the raw bytes inline)
    send_document(cmd.chat_id, path=result.zip_path,
                  caption=f"AMA-RT export {result.manifest.export_id} "
                          f"(mode={result.manifest.trading_mode}, "
                          f"redacted=True)")
```

## 6. Cross-references

- Phase 8.5 service implementation: [`app/exports/service.py`](../app/exports/service.py)
- Redaction primitives: [`app/exports/redaction.py`](../app/exports/redaction.py)
- Manifest shape: [`app/exports/manifest.py`](../app/exports/manifest.py)
- Summary builder: [`app/exports/summary.py`](../app/exports/summary.py)
- CLI counterpart of every Telegram command: `python -m scripts.export_test_data`
  (see [`scripts/export_test_data.py`](../scripts/export_test_data.py))
- Project safety lock: [`app/config/settings.py`](../app/config/settings.py)
  (`_apply_phase1_safety_lock`)
- Spec reference: [`docs/AMA_RT_V1_4_Production_Spec_Kiro.md`](AMA_RT_V1_4_Production_Spec_Kiro.md)
  §32 (Telegram Command Center) / §22 (LLM Guardrails)

— *Issue #8.5 / Phase 8.5 — Learning-Ready Data Contract + Test Data Export Contract*
