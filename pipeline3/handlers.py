"""
Framework-agnostic route logic for RAKABA Pipeline 3.

Extracted from app.py so the same logic can be served two ways: standalone
via Flask (app.py, `cd pipeline3 && python app.py`) or mounted into the
unified FastAPI backend (router.py, included from the repo-root main.py).
Neither adapter duplicates this logic - both just parse their framework's
request shape, call these functions, and serialize (result_dict, status_code).

Access control is enforced here, not just in prompting:
- chat_client only ever reads client-safe columns (no match_score, raw
  lifecycle_state, or other entities' data) and translates the lifecycle
  state through a fixed mapping before it ever reaches the prompt.
- A keyword/intent classifier (escalation.py) runs before any Groq call and
  short-circuits sensitive questions straight to a fixed escalation reply.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import db
import escalation
import prompts
import tools
from groq_client import GroqAPIError, chat, run_tool_calling_loop

logger = logging.getLogger(__name__)

# Client-facing labels for internal lifecycle states. "Detecte" is intentionally
# absent: clients in that state see the generic "no active file" message and
# must never learn a detection state exists.
CLIENT_STATUS_LABELS = {
    "Contacte": "Signale",
    "En regularisation": "En cours",
    "Conforme": "Valide",
    "Contribuable de confiance": "Statut de confiance",
}
GENERIC_NO_FILE_LABEL = "Aucun dossier actif"

FIXED_ESCALATION_REPLY = (
    "Cette question necessite l'avis d'un inspecteur, votre demande a ete transmise."
)


def _client_status_label(lifecycle_state: str) -> str:
    return CLIENT_STATUS_LABELS.get(lifecycle_state, GENERIC_NO_FILE_LABEL)


def _fetch_client_safe_entity(entity_id: str):
    """Only the fields a client is ever allowed to see. No match_score, ever."""
    rows = db.run(
        """
        SELECT tl.entity_id, l.business_name AS name, tl.status AS lifecycle_state
        FROM taxpayer_lifecycle tl
        JOIN listings l ON l.listing_id = tl.listing_id
        WHERE tl.entity_id = ?
        """,
        [entity_id],
    )
    return rows[0] if rows else None


def _fetch_client_safe_declarations(entity_id: str):
    return db.run(
        """
        SELECT period, declaration_type, amount_declared, status
        FROM declarations
        WHERE entity_id = ?
        ORDER BY period
        """,
        [entity_id],
    )


def _fetch_client_safe_documents(entity_id: str):
    """Doc type isn't tracked by Pipeline 2's real schema, so it's derived
    from the submitted filename - never the internal score, ever."""
    rows = db.run(
        """
        SELECT file_metadata, submitted_date AS submitted_at
        FROM documents
        WHERE entity_id = ?
        ORDER BY submitted_date
        """,
        [entity_id],
    )
    out = []
    for r in rows:
        meta = json.loads(r["file_metadata"]) if r["file_metadata"] else {}
        out.append({
            "doc_type": meta.get("filename", "document"),
            "submitted_at": str(r["submitted_at"]),
        })
    return out


def _insert_escalation(entity_id: str, message: str, reason: str):
    db.execute(
        """
        INSERT INTO escalations (escalation_id, entity_id, message, timestamp, reason)
        VALUES (?, ?, ?, ?, ?)
        """,
        [str(uuid.uuid4()), entity_id, message, datetime.now(timezone.utc), reason],
    )


# ---------------------------------------------------------------------------
# Route handlers: (result_dict, http_status)
# ---------------------------------------------------------------------------

def chat_client(
    entity_id: Optional[str],
    message: Optional[str],
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Any], int]:
    if not entity_id or not message:
        return {"error": "entity_id et message sont requis"}, 400

    entity = _fetch_client_safe_entity(entity_id)
    if entity is None:
        return {"error": f"Entite '{entity_id}' introuvable"}, 404

    should_escalate, reason = escalation.classify(message)
    if should_escalate:
        try:
            _insert_escalation(entity_id, message, reason)
        except Exception as exc:
            logger.error("Failed to write escalation row: %s", exc)
        return {"reply": FIXED_ESCALATION_REPLY, "escalated": True}, 200

    declarations = _fetch_client_safe_declarations(entity_id)
    documents = _fetch_client_safe_documents(entity_id)
    status_label = _client_status_label(entity["lifecycle_state"])

    context = prompts.build_client_context(entity, status_label, declarations, documents)
    system_prompt = prompts.CLIENT_SYSTEM_PROMPT.format(context=context)

    try:
        reply = chat(system_prompt, conversation_history or [], message)
    except GroqAPIError as exc:
        return {"error": str(exc)}, 502

    return {"reply": reply, "escalated": False}, 200


def chat_admin(
    inspector_id: Optional[str],
    message: Optional[str],
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Any], int]:
    if not inspector_id or not message:
        return {"error": "inspector_id et message sont requis"}, 400

    try:
        reply = chat(prompts.ADMIN_SYSTEM_PROMPT, conversation_history or [], message)
    except GroqAPIError as exc:
        return {"error": str(exc)}, 502

    return {"reply": reply}, 200


def investigate(inspector_id: Optional[str], entity_id: Optional[str]) -> Tuple[Dict[str, Any], int]:
    if not inspector_id or not entity_id:
        return {"error": "inspector_id et entity_id sont requis"}, 400

    existing = db.run("SELECT entity_id FROM taxpayer_lifecycle WHERE entity_id = ?", [entity_id])
    if not existing:
        return {"error": f"Entite '{entity_id}' introuvable"}, 404

    user_message = f"Enquete sur l'entite {entity_id}."

    try:
        report, evidence_log = run_tool_calling_loop(
            prompts.INVESTIGATION_SYSTEM_PROMPT,
            user_message,
            tools.TOOLS_SCHEMA,
            tools.TOOL_REGISTRY,
        )
    except GroqAPIError as exc:
        return {"error": str(exc)}, 502

    return {"report": report, "evidence_log": evidence_log}, 200


def list_escalations() -> Tuple[Dict[str, Any], int]:
    rows = db.run(
        "SELECT escalation_id, entity_id, message, timestamp, reason FROM escalations ORDER BY timestamp DESC"
    )
    for r in rows:
        r["timestamp"] = str(r["timestamp"])
    return {"escalations": rows}, 200
