"""
The 4 investigation tools available to the Groq-powered investigation agent
(/api/investigate), plus their JSON-schema definitions for function calling.

Each function takes an entity_id and returns a plain dict (JSON-serializable)
straight from DuckDB. These are also the functions logged verbatim into the
evidence_log so the frontend can show "why" a claim was made.

Queries the real shared schema (Pipeline 1's taxpayer_lifecycle/listings/
entity_links, Pipeline 2's documents) rather than a separate mock `entities`
table - see db.py's module docstring for why.
"""

import json
from datetime import datetime, timedelta

import db


def rechercher_entite(query: str) -> dict:
    """Find dossiers by business name without requiring a foreign identifier."""
    query = (query or "").strip()
    if not query:
        return {"matches": [], "count": 0}
    rows = db.run(
        """
        SELECT tl.entity_id, l.business_name AS name, l.location_text AS location,
               tl.status, tl.status_updated_at
        FROM taxpayer_lifecycle tl
        JOIN listings l ON l.listing_id = tl.listing_id
        WHERE lower(l.business_name) LIKE lower(?)
        ORDER BY tl.status_updated_at DESC
        LIMIT 10
        """,
        [f"%{query}%"],
    )
    for row in rows:
        row["status_updated_at"] = str(row["status_updated_at"])
    return {"matches": rows, "count": len(rows)}


def detections_recentes(days: int = 7, limit: int = 10) -> dict:
    """Return recent detected businesses for a natural follow-up discussion."""
    days = max(1, min(int(days), 30))
    limit = max(1, min(int(limit), 25))
    since = datetime.now() - timedelta(days=days)
    rows = db.run(
        """
        SELECT l.business_name AS name, l.location_text AS location,
               tl.status, tl.status_updated_at AS detected_at, tl.notes
        FROM taxpayer_lifecycle tl
        JOIN listings l ON l.listing_id = tl.listing_id
        WHERE tl.status = 'Detecte' AND tl.status_updated_at >= ?
        ORDER BY tl.status_updated_at DESC
        LIMIT ?
        """,
        [since, limit],
    )
    for row in rows:
        row["detected_at"] = str(row["detected_at"])
    return {"period_days": days, "detections": rows, "count": len(rows)}


def consulter_entite(entity_id: str) -> dict:
    """Basic entity info + match score + lifecycle state.

    `match_score` (0-100) is Pipeline 1's name/phone correspondence score,
    not a calibrated fraud-risk score - it's the closest existing internal
    signal (a low score means no credible match was found in the fiscal
    registry, i.e. likely undeclared), surfaced honestly under its real name
    rather than relabeled as something more precise than it is.
    """
    rows = db.run(
        """
        SELECT tl.entity_id, l.business_name AS name, l.phone, l.location_text AS address,
               tl.status AS lifecycle_state, tl.match_score, tl.notes, l.detected_date AS created_at
        FROM taxpayer_lifecycle tl
        JOIN listings l ON l.listing_id = tl.listing_id
        WHERE tl.entity_id = ?
        """,
        [entity_id],
    )
    if not rows:
        return {"error": f"Entite '{entity_id}' introuvable"}
    row = rows[0]
    row["created_at"] = str(row["created_at"])
    return row


def entites_liees(entity_id: str) -> dict:
    """Other entities sharing a phone number or address with this one."""
    rows = db.run(
        """
        SELECT el.link_id, el.shared_attribute AS link_type, el.link_score,
               CASE WHEN el.entity_id_a = ? THEN el.entity_id_b ELSE el.entity_id_a END AS linked_entity_id,
               l.business_name AS linked_entity_name,
               tl.status AS linked_entity_state,
               tl.match_score AS linked_entity_match_score
        FROM entity_links el
        JOIN taxpayer_lifecycle tl
          ON tl.entity_id = CASE WHEN el.entity_id_a = ? THEN el.entity_id_b ELSE el.entity_id_a END
        JOIN listings l ON l.listing_id = tl.listing_id
        WHERE el.entity_id_a = ? OR el.entity_id_b = ?
        """,
        [entity_id, entity_id, entity_id, entity_id],
    )
    return {"entity_id": entity_id, "linked_entities": rows, "count": len(rows)}


def historique_declaration(entity_id: str) -> dict:
    """Declaration history for this entity, including gaps (missing/late filings)."""
    rows = db.run(
        """
        SELECT declaration_id, period, declaration_type, amount_declared,
               date_filed, status
        FROM declarations
        WHERE entity_id = ?
        ORDER BY period
        """,
        [entity_id],
    )
    for r in rows:
        r["date_filed"] = str(r["date_filed"]) if r["date_filed"] is not None else None

    gaps = [r for r in rows if r["status"] in ("manquante", "en_retard")]
    return {
        "entity_id": entity_id,
        "declarations": rows,
        "gap_count": len(gaps),
        "gaps": gaps,
    }


def verification_integrite(entity_id: str) -> dict:
    """Document integrity/coherence flags for this entity's submitted documents.

    Reads Pipeline 2's real `documents` table. That table doesn't classify a
    `doc_type` or store a single boolean flag/reason the way the original
    mock schema did, so both are derived here: doc_type falls back to the
    submitted filename, and a document counts as flagged if either its
    integrity score took a hit or any risk rule fired on it.
    """
    rows = db.run(
        """
        SELECT document_id, file_metadata, integrity_score, integrity_flags,
               risk_flags, composite_score, submitted_date
        FROM documents
        WHERE entity_id = ?
        ORDER BY submitted_date
        """,
        [entity_id],
    )

    documents = []
    for r in rows:
        meta = json.loads(r["file_metadata"]) if r["file_metadata"] else {}
        integrity_flags = json.loads(r["integrity_flags"]) if r["integrity_flags"] else []
        risk_flags = json.loads(r["risk_flags"]) if r["risk_flags"] else []
        all_flags = integrity_flags + risk_flags
        documents.append({
            "document_id": r["document_id"],
            "doc_type": meta.get("filename", "document"),
            "integrity_flag": len(all_flags) > 0,
            "flag_reason": ", ".join(all_flags) if all_flags else None,
            "composite_score": r["composite_score"],
            "submitted_at": str(r["submitted_date"]),
        })

    flagged = [d for d in documents if d["integrity_flag"]]
    return {
        "entity_id": entity_id,
        "documents": documents,
        "flagged_count": len(flagged),
        "flagged_documents": flagged,
    }


TOOL_REGISTRY = {
    "rechercher_entite": rechercher_entite,
    "detections_recentes": detections_recentes,
    "consulter_entite": consulter_entite,
    "entites_liees": entites_liees,
    "historique_declaration": historique_declaration,
    "verification_integrite": verification_integrite,
}


TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "rechercher_entite",
            "description": "Recherche un dossier tunisien par nom d'entreprise ou d'activité. Ne demande pas de SIREN ou SIRET.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Nom ou partie du nom de l'entreprise"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detections_recentes",
            "description": "Liste les entreprises detectees recemment pour pouvoir les presenter et les discuter une par une.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Nombre de jours a regarder, entre 1 et 30"},
                    "limit": {"type": "integer", "description": "Nombre maximum de resultats, entre 1 et 25"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consulter_entite",
            "description": (
                "Consulte les informations de base d'une entite : identite, type, "
                "coordonnees, score de risque interne et etat du cycle de vie."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Identifiant de l'entite a consulter",
                    }
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "entites_liees",
            "description": (
                "Recherche les autres entites partageant un telephone ou une adresse "
                "avec l'entite donnee (reseau de liens)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Identifiant de l'entite dont on cherche les liens",
                    }
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "historique_declaration",
            "description": (
                "Recupere l'historique des declarations fiscales d'une entite et "
                "identifie les periodes manquantes ou en retard."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Identifiant de l'entite dont on veut l'historique",
                    }
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verification_integrite",
            "description": (
                "Verifie la coherence/integrite des documents soumis par une entite "
                "(factures, releves, etc.) et retourne les anomalies detectees."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Identifiant de l'entite dont on verifie les documents",
                    }
                },
                "required": ["entity_id"],
            },
        },
    },
]
