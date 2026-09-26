"""
RAKABA Pipeline 3 - Chatbot backend.

Two scopes, one engine:
- /api/chat/client   -> restricted, entity-scoped, escalation-aware chatbot
- /api/chat/admin    -> full-access Q&A chatbot for inspectors
- /api/investigate   -> autonomous tool-calling investigation agent
- /api/escalations   -> list flagged client questions for the admin dashboard

Access control is enforced in code (which columns are queried, which prompt
is used, which tools exist per role) - never left to LLM instruction alone.
"""

import json
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request

import db
import escalation
import prompts
import tools
from grok_client import GrokAPIError, chat, run_tool_calling_loop

load_dotenv()

app = Flask(__name__)

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


FIXED_ESCALATION_REPLY = (
    "Cette question necessite l'avis d'un inspecteur, votre demande a ete transmise."
)


@app.route("/api/chat/client", methods=["POST"])
def chat_client():
    body = request.get_json(silent=True) or {}
    entity_id = body.get("entity_id")
    message = body.get("message")
    conversation_history = body.get("conversation_history", [])

    if not entity_id or not message:
        return jsonify({"error": "entity_id et message sont requis"}), 400

    entity = _fetch_client_safe_entity(entity_id)
    if entity is None:
        return jsonify({"error": f"Entite '{entity_id}' introuvable"}), 404

    should_escalate, reason = escalation.classify(message)
    if should_escalate:
        try:
            _insert_escalation(entity_id, message, reason)
        except Exception as exc:
            app.logger.error("Failed to write escalation row: %s", exc)
        return jsonify({"reply": FIXED_ESCALATION_REPLY, "escalated": True})

    declarations = _fetch_client_safe_declarations(entity_id)
    documents = _fetch_client_safe_documents(entity_id)
    status_label = _client_status_label(entity["lifecycle_state"])

    context = prompts.build_client_context(entity, status_label, declarations, documents)
    system_prompt = prompts.CLIENT_SYSTEM_PROMPT.format(context=context)

    try:
        reply = chat(system_prompt, conversation_history, message)
    except GrokAPIError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify({"reply": reply, "escalated": False})


@app.route("/api/chat/admin", methods=["POST"])
def chat_admin():
    body = request.get_json(silent=True) or {}
    inspector_id = body.get("inspector_id")
    message = body.get("message")
    conversation_history = body.get("conversation_history", [])

    if not inspector_id or not message:
        return jsonify({"error": "inspector_id et message sont requis"}), 400

    try:
        reply = chat(prompts.ADMIN_SYSTEM_PROMPT, conversation_history, message)
    except GrokAPIError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify({"reply": reply})


@app.route("/api/investigate", methods=["POST"])
def investigate():
    body = request.get_json(silent=True) or {}
    inspector_id = body.get("inspector_id")
    entity_id = body.get("entity_id")

    if not inspector_id or not entity_id:
        return jsonify({"error": "inspector_id et entity_id sont requis"}), 400

    existing = db.run("SELECT entity_id FROM taxpayer_lifecycle WHERE entity_id = ?", [entity_id])
    if not existing:
        return jsonify({"error": f"Entite '{entity_id}' introuvable"}), 404

    user_message = f"Enquete sur l'entite {entity_id}."

    try:
        report, evidence_log = run_tool_calling_loop(
            prompts.INVESTIGATION_SYSTEM_PROMPT,
            user_message,
            tools.TOOLS_SCHEMA,
            tools.TOOL_REGISTRY,
        )
    except GrokAPIError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify({"report": report, "evidence_log": evidence_log})


@app.route("/api/escalations", methods=["GET"])
def list_escalations():
    rows = db.run(
        "SELECT escalation_id, entity_id, message, timestamp, reason FROM escalations ORDER BY timestamp DESC"
    )
    for r in rows:
        r["timestamp"] = str(r["timestamp"])
    return jsonify({"escalations": rows})


@app.errorhandler(404)
def not_found(_e):
    return jsonify({"error": "Route introuvable"}), 404


@app.errorhandler(500)
def server_error(e):
    app.logger.error("Unhandled error: %s", e)
    return jsonify({"error": "Erreur interne du serveur"}), 500


if __name__ == "__main__":
    db.get_connection()  # ensures schema + mock data exist before serving
    port = int(os.environ.get("FLASK_PORT", 5000))
    app.run(debug=True, port=port)
