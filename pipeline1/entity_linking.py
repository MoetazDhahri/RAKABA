"""
Liaison d'entites (F1.6) - RAKABA Pipeline 1

Des entites distinctes partageant un meme telephone ou une meme adresse sont
regroupees automatiquement (cf. cahier des charges, section 4.1) - un meme
operateur non declare peut ainsi etre identifie meme s'il apparait sous
plusieurs noms commerciaux. Cette meme logique alimente le graphe du
Pipeline 2.

Regle deterministe, non-IA : le lien est cree des que deux entites partagent
un telephone ou une adresse normalises identiques.
"""
from __future__ import annotations

import itertools
import uuid
from collections import defaultdict

import duckdb

from pipeline1.matching_engine import normalize_name, normalize_phone

PHONE_LINK_SCORE = 100.0
ADDRESS_LINK_SCORE = 80.0  # une adresse partagee est un signal un peu moins fiable qu'un telephone exact


def _existing_link_pairs(conn: duckdb.DuckDBPyConnection) -> set[frozenset[str]]:
    rows = conn.execute("SELECT entity_id_a, entity_id_b FROM entity_links").fetchall()
    return {frozenset((a, b)) for a, b in rows}


def refresh_entity_links(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    """Scans every active entity, groups by shared phone/address, and inserts
    any new pairwise link. Safe to call repeatedly (idempotent)."""
    rows = conn.execute(
        """
        SELECT tl.entity_id, l.phone, l.location_text
        FROM taxpayer_lifecycle tl
        JOIN listings l ON l.listing_id = tl.listing_id
        """
    ).fetchall()

    by_phone: dict[str, list[str]] = defaultdict(list)
    by_address: dict[str, list[str]] = defaultdict(list)
    for entity_id, phone, address in rows:
        phone_key = normalize_phone(phone)
        if phone_key:
            by_phone[phone_key].append(entity_id)
        address_key = normalize_name(address)
        if address_key:
            by_address[address_key].append(entity_id)

    existing_pairs = _existing_link_pairs(conn)
    new_links: list[dict] = []

    for grouping, attribute, score in (
        (by_phone, "phone", PHONE_LINK_SCORE),
        (by_address, "address", ADDRESS_LINK_SCORE),
    ):
        for entity_ids in grouping.values():
            if len(entity_ids) < 2:
                continue
            for entity_a, entity_b in itertools.combinations(sorted(set(entity_ids)), 2):
                pair_key = frozenset((entity_a, entity_b))
                if pair_key in existing_pairs:
                    continue
                existing_pairs.add(pair_key)
                new_links.append({
                    "link_id": f"LNK-{uuid.uuid4().hex[:8]}",
                    "entity_id_a": entity_a,
                    "entity_id_b": entity_b,
                    "shared_attribute": attribute,
                    "link_score": score,
                })

    if new_links:
        conn.executemany(
            "INSERT INTO entity_links VALUES (?, ?, ?, ?, ?)",
            [(l["link_id"], l["entity_id_a"], l["entity_id_b"], l["shared_attribute"], l["link_score"])
             for l in new_links],
        )
    return new_links


def get_related_entities(conn: duckdb.DuckDBPyConnection, entity_id: str) -> list[dict]:
    """Used by Pipeline 3's investigation agent (get_related_entities tool)."""
    rows = conn.execute(
        """
        SELECT el.entity_id_a, el.entity_id_b, el.shared_attribute, el.link_score,
               l.business_name
        FROM entity_links el
        JOIN taxpayer_lifecycle tl
          ON tl.entity_id = CASE WHEN el.entity_id_a = ? THEN el.entity_id_b ELSE el.entity_id_a END
        JOIN listings l ON l.listing_id = tl.listing_id
        WHERE el.entity_id_a = ? OR el.entity_id_b = ?
        """,
        [entity_id, entity_id, entity_id],
    ).fetchall()
    related = []
    for a, b, attribute, score, business_name in rows:
        other = b if a == entity_id else a
        related.append({"entity_id": other, "business_name": business_name, "shared_attribute": attribute, "link_score": score})
    return related
