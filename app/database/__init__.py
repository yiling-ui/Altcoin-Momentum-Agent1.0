"""SQLite persistence layer for AMA-RT.

Phase 1 ships:
    - schema.sql with the events table
    - connection.py: SQLite WAL connection helper
    - repositories.py: EventRepository (append/list/replay)
    - migrations.py: applies schema.sql idempotently

Other databases listed in Spec §33.1 are deliberately deferred to
Issue #2 (Phase 2 - Event Sourcing and Database).
"""
