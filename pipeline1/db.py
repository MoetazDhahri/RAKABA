"""
Couche de persistance DuckDB - RAKABA Pipeline 1 (X1)

Base unique, partagee (en local) par les trois pipelines. Ce module ne gere
que les tables dont Pipeline 1 est proprietaire (cf. cahier des charges
section 12) plus la table transverse automation_log.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "rakaba.duckdb"

SCHEMA_STATEMENTS = [
    """
    CREATE SEQUENCE IF NOT EXISTS listing_id_seq START 1;
    """,
    """
    CREATE TABLE IF NOT EXISTS listings (
        listing_id          VARCHAR PRIMARY KEY,
        business_name       VARCHAR NOT NULL,
        phone               VARCHAR NOT NULL,
        location_text       VARCHAR,
        activity_description VARCHAR,
        source_platform     VARCHAR,
        detected_date       TIMESTAMP NOT NULL DEFAULT current_timestamp
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS registry (
        matricule_fiscal    VARCHAR PRIMARY KEY,
        registered_name     VARCHAR NOT NULL,
        phone               VARCHAR NOT NULL,
        registered_address  VARCHAR,
        registration_date   DATE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS taxpayer_lifecycle (
        entity_id           VARCHAR PRIMARY KEY,
        listing_id          VARCHAR REFERENCES listings(listing_id),
        status              VARCHAR NOT NULL,
        status_updated_at   TIMESTAMP NOT NULL DEFAULT current_timestamp,
        match_score         DOUBLE,
        notes               VARCHAR
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS entity_links (
        link_id             VARCHAR PRIMARY KEY,
        entity_id_a         VARCHAR REFERENCES taxpayer_lifecycle(entity_id),
        entity_id_b         VARCHAR REFERENCES taxpayer_lifecycle(entity_id),
        shared_attribute    VARCHAR NOT NULL,
        link_score          DOUBLE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS automation_log (
        log_id              VARCHAR PRIMARY KEY,
        entity_id           VARCHAR,
        pipeline_source     VARCHAR NOT NULL,
        action_description  VARCHAR NOT NULL,
        timestamp           TIMESTAMP NOT NULL DEFAULT current_timestamp,
        triggered_by        VARCHAR NOT NULL
    );
    """,
]


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(str(db_path))
    init_schema(conn)
    return conn


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    for statement in SCHEMA_STATEMENTS:
        conn.execute(statement)


def reset_database(db_path: Path | str = DEFAULT_DB_PATH) -> duckdb.DuckDBPyConnection:
    """Drops every RAKABA P1 table and recreates them empty. Used by the seed script (X2)."""
    conn = duckdb.connect(str(db_path))
    for table in ("entity_links", "taxpayer_lifecycle", "listings", "registry", "automation_log"):
        conn.execute(f"DROP TABLE IF EXISTS {table};")
    conn.execute("DROP SEQUENCE IF EXISTS listing_id_seq;")
    init_schema(conn)
    return conn
