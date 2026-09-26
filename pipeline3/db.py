"""
DuckDB connection for RAKABA Pipeline 3.

Shares rakaba.duckdb with Pipelines 1 and 2, whose schema is defined once in
pipeline1/db.py (entities live in taxpayer_lifecycle + listings, documents
belong to Pipeline 2, entity_links to Pipeline 1). This module only owns
`declarations` and `escalations`, which are genuinely Pipeline 3's own
concept and aren't produced by the other two pipelines.

Earlier version of this file created and unconditionally DROPped its own
copies of `entities`/`documents`/`entity_links` whenever any one of its four
expected tables was missing - which would have silently wiped Pipeline 1's
real entity_links data the first time this ran against the shared file.
Fixed here: this module never creates or drops a table it doesn't own, and
never assumes a standalone `entities` table exists - entity data is read
through taxpayer_lifecycle/listings directly (see tools.py, app.py).
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

# This module is normally run with pipeline3/ as the working directory (flat
# `import db`/`import tools` style throughout this pipeline), but pipeline1 -
# which owns the shared schema - lives at the repo root. Make sure it's
# importable regardless of how app.py was launched.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pipeline1 import db as shared_db

DB_PATH = os.environ.get("DUCKDB_PATH", str(shared_db.DEFAULT_DB_PATH))

_conn = None
# The SAME lock object pipeline1/db.py and pipeline2/database.py use, not a
# separate one - all three pipelines can share one physical DuckDB connection
# object in the unified backend process, and a connection isn't safe for
# concurrent multi-threaded use. A lock private to this module would only
# serialize Pipeline 3's own queries against each other, not against
# Pipelines 1/2 hitting the same connection at the same time.
_lock = shared_db.LOCK


def get_connection():
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                _conn = shared_db.get_connection(DB_PATH)
                _seed_declarations_if_empty(_conn)
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


def _seed_declarations_if_empty(conn):
    """Seeds a handful of declarations against whatever real entities already
    exist in taxpayer_lifecycle (from Pipeline 1). If none exist yet (fresh
    DB, standalone run before Pipeline 1 has ingested anything), seeds
    nothing rather than inventing entities that don't belong to the shared
    schema - an empty declarations table is a safe, non-destructive default."""
    already = conn.execute("SELECT count(*) FROM declarations").fetchone()[0]
    if already:
        return

    entity_ids = [
        r[0] for r in conn.execute(
            "SELECT entity_id FROM taxpayer_lifecycle ORDER BY status_updated_at LIMIT 6"
        ).fetchall()
    ]
    if not entity_ids:
        return

    now = datetime.now()
    statuses = ["deposee", "deposee", "en_retard", "manquante"]
    types = ["TVA", "IRPP", "IS"]
    rows = []
    for i, entity_id in enumerate(entity_ids):
        for q, period in enumerate(["2024-Q3", "2024-Q4"]):
            status = statuses[(i + q) % len(statuses)]
            rows.append((
                f"D-{entity_id}-{period}",
                entity_id,
                period,
                types[i % len(types)],
                None if status == "manquante" else round(1000 + i * 733.5, 2),
                None if status == "manquante" else now - timedelta(days=90 * (2 - q)),
                status,
            ))

    conn.executemany(
        """
        INSERT INTO declarations
        (declaration_id, entity_id, period, declaration_type, amount_declared, date_filed, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
