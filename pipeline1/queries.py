"""
Couche de lecture - RAKABA Pipeline 1 (F1.7 data contract, UC-02, UC-07, UC-11)

Expose les donnees dont l'interface Admin (kanban, detail d'entite, journal)
a besoin, sans rien imposer sur la presentation. Ces fonctions sont aussi ce
que l'agent d'investigation du Pipeline 3 appellera (lookup_entity,
get_declaration_history-equivalent) une fois branche.
"""
from __future__ import annotations

from datetime import date

import duckdb

from pipeline1.dashboard import match_governorate
from pipeline1.pipeline import (
    LIFECYCLE_ORDER,
    STATUS_COMPLIANT,
    STATUS_DETECTED,
    STATUS_IN_REGULARIZATION,
)


def list_entities_by_status(
    conn: duckdb.DuckDBPyConnection,
    status: str | None = None,
    search: str | None = None,
    location_filter: str | None = None,
) -> list[dict]:
    """Kanban cards (Ecran 1). One row per entity, with the listing info needed for the card.

    `location_filter` is a governorate id (e.g. "gabes", "sidi-bouzid" - the
    same ids the map/dashboard.region_breakdown uses), matched via the same
    match_governorate() heuristic rather than a raw ILIKE substring on the
    accented display name - otherwise a click on "Gabès"/"Béja"/"Kébili"/
    etc. would silently match nothing (ILIKE does not fold accents), and the
    result set here could disagree with the map's own bucket count for the
    same region.
    """
    query = """
        SELECT tl.entity_id, tl.status, tl.status_updated_at, tl.match_score, tl.notes,
               l.business_name, l.phone, l.location_text, l.source_platform, l.detected_date
        FROM taxpayer_lifecycle tl
        JOIN listings l ON l.listing_id = tl.listing_id
    """
    params = []
    filters = []
    if status is not None:
        filters.append("tl.status = ?")
        params.append(status)
    if search:
        filters.append(
            "(l.business_name ILIKE ? OR l.phone ILIKE ? OR l.location_text ILIKE ? "
            "OR l.activity_description ILIKE ? OR l.source_platform ILIKE ? "
            "OR tl.status ILIKE ? OR tl.notes ILIKE ?)"
        )
        params.extend([f"%{search}%"] * 7)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY tl.status_updated_at DESC"

    rows = conn.execute(query, params).fetchall()
    columns = ["entity_id", "status", "status_updated_at", "match_score", "notes",
               "business_name", "phone", "location_text", "source_platform", "detected_date"]
    entities = [dict(zip(columns, row)) for row in rows]
    if location_filter:
        entities = [e for e in entities if match_governorate(e["location_text"]) == location_filter]
    return entities


def kanban_columns(conn: duckdb.DuckDBPyConnection) -> dict[str, list[dict]]:
    """One entry per lifecycle status, in the fixed display order (Ecran 1)."""
    return {status: list_entities_by_status(conn, status) for status in LIFECYCLE_ORDER}


def dashboard_counters(conn: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Header counters (Ecran 1): detectes aujourd'hui, en regularisation, conformes."""
    today = date.today()
    detected_today = conn.execute(
        "SELECT count(*) FROM taxpayer_lifecycle WHERE status = ? AND CAST(status_updated_at AS DATE) = ?",
        [STATUS_DETECTED, today],
    ).fetchone()[0]
    in_regularization = conn.execute(
        "SELECT count(*) FROM taxpayer_lifecycle WHERE status = ?", [STATUS_IN_REGULARIZATION]
    ).fetchone()[0]
    compliant = conn.execute(
        "SELECT count(*) FROM taxpayer_lifecycle WHERE status = ?", [STATUS_COMPLIANT]
    ).fetchone()[0]
    return {
        "detected_today": detected_today,
        "in_regularization": in_regularization,
        "compliant": compliant,
    }


def get_entity_detail(conn: duckdb.DuckDBPyConnection, entity_id: str) -> dict | None:
    """Ecran 2 / UC-02 / lookup_entity for Pipeline 3's investigation agent.
    Full record: lifecycle status, originating listing, and its own automation history."""
    row = conn.execute(
        """
        SELECT tl.entity_id, tl.status, tl.status_updated_at, tl.match_score, tl.notes,
               l.listing_id, l.business_name, l.phone, l.location_text,
               l.activity_description, l.source_platform, l.detected_date
        FROM taxpayer_lifecycle tl
        JOIN listings l ON l.listing_id = tl.listing_id
        WHERE tl.entity_id = ?
        """,
        [entity_id],
    ).fetchone()
    if row is None:
        return None

    columns = ["entity_id", "status", "status_updated_at", "match_score", "notes",
               "listing_id", "business_name", "phone", "location_text",
               "activity_description", "source_platform", "detected_date"]
    detail = dict(zip(columns, row))
    detail["history"] = get_entity_automation_log(conn, entity_id)
    return detail


def get_entity_automation_log(conn: duckdb.DuckDBPyConnection, entity_id: str) -> list[dict]:
    """UC-11 (scoped to one entity) - also used as get_declaration_history's P1-side
    equivalent for the Pipeline 3 investigation agent: every automated/manual action
    RAKABA has taken for this entity, in order."""
    rows = conn.execute(
        """
        SELECT log_id, pipeline_source, action_description, timestamp, triggered_by
        FROM automation_log
        WHERE entity_id = ?
        ORDER BY timestamp ASC
        """,
        [entity_id],
    ).fetchall()
    columns = ["log_id", "pipeline_source", "action_description", "timestamp", "triggered_by"]
    return [dict(zip(columns, row)) for row in rows]


def get_automation_log(conn: duckdb.DuckDBPyConnection, limit: int = 100) -> list[dict]:
    """UC-11, Ecran 5 - the full cross-pipeline automation feed, most recent first."""
    rows = conn.execute(
        """
        SELECT log_id, entity_id, pipeline_source, action_description, timestamp, triggered_by
        FROM automation_log
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()
    columns = ["log_id", "entity_id", "pipeline_source", "action_description", "timestamp", "triggered_by"]
    return [dict(zip(columns, row)) for row in rows]
