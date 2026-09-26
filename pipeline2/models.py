"""
pipeline2/models.py
Constantes partagees pour la Pipeline 2 — Verifier.

Les tables (documents, entity_graph_nodes, entity_graph_edges) sont
definies dans pipeline1/db.py (schema partage). Ce module ne contient plus
d'ORM : router.py et graph.py lisent/ecrivent directement via SQL sur la
connexion DuckDB partagee (pipeline2/database.py), et manipulent des dicts
plutot que des objets mappes.
"""

from __future__ import annotations

from enum import Enum as PyEnum


class EdgeType(PyEnum):
    """Types de liens partages entre entites (cf. entity_links.shared_attribute)."""
    phone        = "phone"
    address      = "address"
    bank_account = "bank_account"
