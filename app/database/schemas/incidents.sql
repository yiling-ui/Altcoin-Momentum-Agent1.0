-- AMA-RT incidents.db schema (Phase 2 - Event Sourcing and Database)
--
-- Spec §38 (Incident Response Runbook). One row per opened incident.
-- A separate table `incident_log` records every state change of every
-- incident so that Reflection (Issue #10) can replay an incident without
-- pulling from events.db.
--
-- Phase 2 ships the schema. The incident dispatcher writer lands in
-- Issue #9 / Issue #10. Phase 2 must not insert here.

CREATE TABLE IF NOT EXISTS incidents (
    incident_id   TEXT PRIMARY KEY,
    level         TEXT NOT NULL,              -- P0 | P1 | P2 | P3
    title         TEXT NOT NULL,
    description   TEXT,
    source_module TEXT NOT NULL,
    symbol        TEXT,
    position_id   TEXT,
    opened_at     INTEGER NOT NULL,           -- ms
    resolved_at   INTEGER,
    resolution    TEXT,
    payload_json  TEXT NOT NULL DEFAULT '{}',
    created_at    INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER) * 1000)
);

CREATE INDEX IF NOT EXISTS idx_incidents_level     ON incidents(level);
CREATE INDEX IF NOT EXISTS idx_incidents_opened_at ON incidents(opened_at);
CREATE INDEX IF NOT EXISTS idx_incidents_symbol    ON incidents(symbol);

CREATE TABLE IF NOT EXISTS incident_log (
    log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id  TEXT NOT NULL,
    timestamp    INTEGER NOT NULL,
    state        TEXT NOT NULL,               -- 'opened' | 'updated' | 'resolved'
    note         TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (incident_id) REFERENCES incidents(incident_id)
);

CREATE INDEX IF NOT EXISTS idx_incident_log_incident_id ON incident_log(incident_id);
CREATE INDEX IF NOT EXISTS idx_incident_log_timestamp   ON incident_log(timestamp);
