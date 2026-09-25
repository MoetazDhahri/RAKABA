"""
The 4 investigation tools available to the Grok-powered investigation agent
(/api/investigate), plus their JSON-schema definitions for function calling.

Each function takes an entity_id and returns a plain dict (JSON-serializable)
straight from DuckDB. These are also the functions logged verbatim into the
evidence_log so the frontend can show "why" a claim was made.
"""

import db


def consulter_entite(entity_id: str) -> dict:
    """Basic entity info + current risk score + lifecycle state."""
    rows = db.run(
        """
        SELECT entity_id, name, entity_type, phone, address,
               lifecycle_state, risk_score, created_at
        FROM entities
        WHERE entity_id = ?
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
        SELECT l.link_id, l.link_type, l.shared_value,
               CASE WHEN l.entity_id_a = ? THEN l.entity_id_b ELSE l.entity_id_a END AS linked_entity_id,
               e.name AS linked_entity_name,
               e.lifecycle_state AS linked_entity_state,
               e.risk_score AS linked_entity_risk_score
        FROM entity_links l
        JOIN entities e
          ON e.entity_id = CASE WHEN l.entity_id_a = ? THEN l.entity_id_b ELSE l.entity_id_a END
        WHERE l.entity_id_a = ? OR l.entity_id_b = ?
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
    """Document integrity/coherence flags for this entity's submitted documents."""
    rows = db.run(
        """
        SELECT document_id, doc_type, integrity_flag, flag_reason, submitted_at
        FROM documents
        WHERE entity_id = ?
        ORDER BY submitted_at
        """,
        [entity_id],
    )
    for r in rows:
        r["submitted_at"] = str(r["submitted_at"])

    flagged = [r for r in rows if r["integrity_flag"]]
    return {
        "entity_id": entity_id,
        "documents": rows,
        "flagged_count": len(flagged),
        "flagged_documents": flagged,
    }


TOOL_REGISTRY = {
    "consulter_entite": consulter_entite,
    "entites_liees": entites_liees,
    "historique_declaration": historique_declaration,
    "verification_integrite": verification_integrite,
}


TOOLS_SCHEMA = [
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
