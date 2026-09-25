"""
DuckDB connection + mock data seeding for RAKABA Pipeline 3.

A teammate owns the real schema/connection (`rakaba.duckdb` with tables
`entities`, `declarations`, `documents`, `entity_links`). This module will
open that file as-is if it already contains those tables. If the file does
not exist yet, or is missing tables, it creates them and seeds realistic
fake Tunisian data so this backend is runnable standalone.

To plug in the real database: just point DUCKDB_PATH (env var) at the real
`rakaba.duckdb` file. As long as it has the four tables above (plus this
module will add `escalations` if missing), everything else works unchanged.
"""

import os
import threading
from datetime import datetime, timedelta

import duckdb

DB_PATH = os.environ.get("DUCKDB_PATH", "rakaba.duckdb")

_conn = None
_lock = threading.RLock()  # reentrant: run()/execute() hold it while calling get_connection()

REQUIRED_TABLES = {"entities", "declarations", "documents", "entity_links"}


def get_connection():
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                _conn = duckdb.connect(DB_PATH)
                _ensure_schema(_conn)
    return _conn


def run(query, params=None):
    """Thread-safe query execution returning list-of-dict rows."""
    with _lock:
        conn = get_connection()
        cur = conn.execute(query, params or [])
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def execute(query, params=None):
    """Thread-safe write execution (no result rows expected)."""
    with _lock:
        conn = get_connection()
        conn.execute(query, params or [])


def _existing_tables(conn):
    rows = conn.execute("SELECT table_name FROM information_schema.tables").fetchall()
    return {r[0] for r in rows}


def _ensure_schema(conn):
    existing = _existing_tables(conn)

    if not REQUIRED_TABLES.issubset(existing):
        _create_core_tables(conn)
        _seed_mock_data(conn)

    if "escalations" not in existing:
        conn.execute(
            """
            CREATE TABLE escalations (
                escalation_id VARCHAR PRIMARY KEY,
                entity_id VARCHAR,
                message VARCHAR,
                timestamp TIMESTAMP,
                reason VARCHAR
            )
            """
        )


def _create_core_tables(conn):
    conn.execute("DROP TABLE IF EXISTS entity_links")
    conn.execute("DROP TABLE IF EXISTS documents")
    conn.execute("DROP TABLE IF EXISTS declarations")
    conn.execute("DROP TABLE IF EXISTS entities")

    conn.execute(
        """
        CREATE TABLE entities (
            entity_id VARCHAR PRIMARY KEY,
            name VARCHAR,
            entity_type VARCHAR,      -- 'personne_physique' | 'personne_morale'
            phone VARCHAR,
            address VARCHAR,
            lifecycle_state VARCHAR,  -- Detecte | Contacte | En regularisation | Conforme | Contribuable de confiance
            risk_score INTEGER,       -- 0-100, internal only, never shown to clients
            created_at TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE declarations (
            declaration_id VARCHAR PRIMARY KEY,
            entity_id VARCHAR,
            period VARCHAR,           -- e.g. '2024-Q4'
            declaration_type VARCHAR, -- e.g. 'TVA', 'IRPP', 'IS'
            amount_declared DOUBLE,
            date_filed DATE,          -- NULL if missing/never filed
            status VARCHAR            -- 'deposee' | 'en_retard' | 'manquante'
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE documents (
            document_id VARCHAR PRIMARY KEY,
            entity_id VARCHAR,
            doc_type VARCHAR,
            integrity_flag BOOLEAN,
            flag_reason VARCHAR,
            submitted_at TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE entity_links (
            link_id VARCHAR PRIMARY KEY,
            entity_id_a VARCHAR,
            entity_id_b VARCHAR,
            link_type VARCHAR,   -- 'telephone_partage' | 'adresse_partagee'
            shared_value VARCHAR
        )
        """
    )


def _seed_mock_data(conn):
    now = datetime.now()

    entities = [
        (
            "E-1001", "Sfax Textiles SARL", "personne_morale",
            "+216 74 220 118", "Route de Tunis, Km 4, Sfax",
            "Contribuable de confiance", 12, now - timedelta(days=900),
        ),
        (
            "E-1002", "Youssef Ben Ali", "personne_physique",
            "+216 22 314 590", "Rue Ibn Khaldoun, Ariana",
            "En regularisation", 45, now - timedelta(days=400),
        ),
        (
            "E-1003", "Manel Trading Co", "personne_morale",
            "+216 71 556 432", "Avenue Habib Bourguiba, Tunis",
            "Detecte", 78, now - timedelta(days=60),
        ),
        (
            "E-1004", "Karim Freres Import Export", "personne_morale",
            "+216 98 765 432", "Zone Industrielle, Sousse",
            "Contacte", 65, now - timedelta(days=200),
        ),
        (
            "E-1005", "Nabil Karim Consulting", "personne_physique",
            "+216 98 765 432", "Rue de Marseille, Sousse",
            "Detecte", 70, now - timedelta(days=45),
        ),
        (
            "E-1006", "Tunis Auto Pieces", "personne_morale",
            "+216 71 908 213", "Rue de la Kasbah, Tunis",
            "Conforme", 20, now - timedelta(days=1200),
        ),
    ]
    conn.executemany(
        """
        INSERT INTO entities
        (entity_id, name, entity_type, phone, address, lifecycle_state, risk_score, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        entities,
    )

    declarations = [
        ("D-1", "E-1001", "2024-Q3", "TVA", 45210.0, now - timedelta(days=200), "deposee"),
        ("D-2", "E-1001", "2024-Q4", "TVA", 47890.0, now - timedelta(days=110), "deposee"),
        ("D-3", "E-1002", "2024-Q3", "IRPP", 3200.0, now - timedelta(days=205), "deposee"),
        ("D-4", "E-1002", "2024-Q4", "IRPP", None, None, "manquante"),
        ("D-5", "E-1003", "2024-Q2", "IS", 12000.0, now - timedelta(days=290), "deposee"),
        ("D-6", "E-1003", "2024-Q3", "IS", None, None, "manquante"),
        ("D-7", "E-1003", "2024-Q4", "IS", None, None, "manquante"),
        ("D-8", "E-1004", "2024-Q3", "TVA", 8900.0, now - timedelta(days=150), "en_retard"),
        ("D-9", "E-1004", "2024-Q4", "TVA", 9100.0, now - timedelta(days=95), "deposee"),
        ("D-10", "E-1005", "2024-Q4", "IRPP", None, None, "manquante"),
        ("D-11", "E-1006", "2024-Q3", "TVA", 15400.0, now - timedelta(days=180), "deposee"),
        ("D-12", "E-1006", "2024-Q4", "TVA", 16020.0, now - timedelta(days=90), "deposee"),
    ]
    conn.executemany(
        """
        INSERT INTO declarations
        (declaration_id, entity_id, period, declaration_type, amount_declared, date_filed, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        declarations,
    )

    documents = [
        ("DOC-1", "E-1001", "facture", False, None, now - timedelta(days=200)),
        ("DOC-2", "E-1002", "releve_bancaire", False, None, now - timedelta(days=205)),
        (
            "DOC-3", "E-1003", "facture", True,
            "Montants incoherents entre facture et bon de livraison (ecart de 34%)",
            now - timedelta(days=290),
        ),
        (
            "DOC-4", "E-1005", "facture", True,
            "Numero de facture duplique detecte sur deux declarations distinctes",
            now - timedelta(days=40),
        ),
        ("DOC-5", "E-1006", "facture", False, None, now - timedelta(days=180)),
    ]
    conn.executemany(
        """
        INSERT INTO documents
        (document_id, entity_id, doc_type, integrity_flag, flag_reason, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        documents,
    )

    entity_links = [
        (
            "L-1", "E-1004", "E-1005", "telephone_partage", "+216 98 765 432",
        ),
    ]
    conn.executemany(
        """
        INSERT INTO entity_links
        (link_id, entity_id_a, entity_id_b, link_type, shared_value)
        VALUES (?, ?, ?, ?, ?)
        """,
        entity_links,
    )
