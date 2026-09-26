"""
Compatibility shim expected by pipeline2/risk_rules.py
(`from entity_links import has_linked_transactions`).

Without this module, F2.4's "transactions_avec_entite_liee" rule silently
degrades to always-False (by risk_rules.py's own design) because the import
fails. This module makes it resolve for real, against the shared
entity_links table Pipeline 1 owns (F1.6) — reusing Pipeline 2's own DuckDB
connection so we don't open a second connection to the same file.
"""

from __future__ import annotations

from pipeline1.entity_linking import get_related_entities


def has_linked_transactions(entity_id: str) -> bool:
    """True if this entity shares a phone/address with at least one other
    entity, per the real entity_links table (F1.6)."""
    from pipeline2.database import get_connection

    conn = get_connection()
    return len(get_related_entities(conn, entity_id)) > 0
