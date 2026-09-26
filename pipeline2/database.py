"""
pipeline2/database.py
Connexion DuckDB partagee pour la Pipeline 2 (F2.5, F2.6).

Remplace l'ancien moteur SQLAlchemy/SQLite : la base partagee entre les
trois pipelines est un fichier DuckDB unique (cf. pipeline1/db.py, qui
definit le schema canonique — ce module ne fait qu'ouvrir une connexion
vers le meme fichier et s'assurer que ce schema existe).
"""

from __future__ import annotations

import os

import duckdb

from pipeline1 import db as shared_db

DB_PATH = os.environ.get("DUCKDB_PATH", str(shared_db.DEFAULT_DB_PATH))

_conn: duckdb.DuckDBPyConnection | None = None


def get_connection() -> duckdb.DuckDBPyConnection:
    """Connexion DuckDB partagee (singleton par process)."""
    global _conn
    if _conn is None:
        with shared_db.LOCK:
            if _conn is None:
                _conn = shared_db.get_connection(DB_PATH)
    return _conn


def get_db():
    """Dependance FastAPI : fournit la connexion DuckDB partagee. Le lock est
    tenu pour toute la duree de la requete (voir pipeline1/db.py LOCK) - sans
    ca, des requetes concurrentes du frontend Admin sur cette meme connexion
    provoquent des resultats intermittents corrompus, pas juste des erreurs
    visibles."""
    with shared_db.LOCK:
        yield get_connection()


def init_db() -> None:
    """Cree les tables du schema partage si elles n'existent pas encore.
    Appelee au demarrage de l'application (idempotent)."""
    get_connection()
