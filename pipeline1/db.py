"""
Couche de persistance DuckDB - RAKABA, schema partage (X1)

Base unique, partagee par les trois pipelines (cf. cahier des charges
section 12 et section 14 : "une seule base de donnees, trois pipelines
qui l'alimentent"). Ce module est le SEUL endroit ou le schema est defini -
Pipeline 2 (documents, entity_graph_nodes/edges) et Pipeline 3
(declarations, escalations) importent ce module plutot que de definir
leur propre schema, pour eviter exactement le genre de divergence
(moteurs de base differents, tables dupliquees sous des noms differents)
qui s'etait produite avant unification.

Note sur les colonnes JSON (file_metadata, risk_flags, integrity_flags,
feature_vector) : stockees en VARCHAR (JSON serialise en texte) plutot
qu'un type JSON natif DuckDB, pour rester simple a lire/ecrire depuis
Python (json.dumps/json.loads) sans dependre de fonctions SQL JSON
specifiques a DuckDB.
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
    # --- Pipeline 2 (Verifier) ---------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS documents (
        document_id      VARCHAR PRIMARY KEY,
        entity_id        VARCHAR NOT NULL,
        file_metadata    VARCHAR NOT NULL,
        integrity_score  DOUBLE,
        coherence_score  DOUBLE,
        risk_flags       VARCHAR NOT NULL,
        composite_score  DOUBLE,
        submitted_date   TIMESTAMP NOT NULL DEFAULT current_timestamp,
        integrity_flags  VARCHAR NOT NULL,
        risk_score_raw   DOUBLE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS entity_graph_nodes (
        node_id           VARCHAR PRIMARY KEY,
        feature_vector    VARCHAR NOT NULL,
        gnn_anomaly_score DOUBLE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS entity_graph_edges (
        edge_id   VARCHAR PRIMARY KEY,
        node_a    VARCHAR NOT NULL,
        node_b    VARCHAR NOT NULL,
        edge_type VARCHAR NOT NULL,
        weight    DOUBLE NOT NULL DEFAULT 1.0
    );
    """,
    # --- Pipeline 3 (Accompagner) -------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS declarations (
        declaration_id    VARCHAR PRIMARY KEY,
        entity_id         VARCHAR NOT NULL,
        period            VARCHAR NOT NULL,
        declaration_type  VARCHAR NOT NULL,
        amount_declared   DOUBLE,
        date_filed        DATE,
        status            VARCHAR NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS escalations (
        escalation_id VARCHAR PRIMARY KEY,
        entity_id     VARCHAR,
        message       VARCHAR NOT NULL,
        timestamp     TIMESTAMP NOT NULL DEFAULT current_timestamp,
        reason        VARCHAR
    );
    """,
]

_ALL_TABLES = (
    "entity_graph_edges", "entity_graph_nodes", "documents",
    "escalations", "declarations",
    "entity_links", "taxpayer_lifecycle", "listings", "registry", "automation_log",
)


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(str(db_path))
    init_schema(conn)
    return conn


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    for statement in SCHEMA_STATEMENTS:
        conn.execute(statement)


def reset_database(db_path: Path | str = DEFAULT_DB_PATH) -> duckdb.DuckDBPyConnection:
    """Drops every RAKABA table (all 3 pipelines) and recreates them empty. Used by the seed script (X2)."""
    conn = duckdb.connect(str(db_path))
    for table in _ALL_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table};")
    conn.execute("DROP SEQUENCE IF EXISTS listing_id_seq;")
    init_schema(conn)
    return conn
