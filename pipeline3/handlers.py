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

Voice (voice_chat_client / voice_chat_admin) is a thin wrapper, not a
parallel path: audio in -> ElevenLabs speech-to-text -> the exact same
chat_client/chat_admin above -> ElevenLabs text-to-speech on the reply. Every
safety rule above still applies to a voice turn.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import db
import escalation
import prompts
import tools
import voice
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
ADMIN_SCOPE_REPLY = (
    "Je peux vous aider avec les dossiers RAKABA, les declarations, les documents, "
    "les liens entre entites et les indicateurs de risque. Je ne peux pas repondre "
    "aux questions de culture generale ou de football."
)
PRIVACY_REPLY = "Je ne peux pas partager cette information confidentielle."
CLIENT_SESSION_TTL_DAYS = 7
ADMIN_DOMAIN_TERMS = {
    "rakaba", "dossier", "entite", "entreprise", "declaration", "document",
    "registre", "fiscal", "impot", "risque", "score", "statut", "lien",
    "liee", "reseau", "analyse", "verification", "integrite", "coherence",
    "montant", "transaction", "activite", "inspecteur", "contribuable",
    "detection", "detections", "nouvelle", "nouvelles", "recent", "recente", "recentes",
    "anomalie", "fraude", "enquete", "historique", "fichier", "pdf",
}
OFF_TOPIC_TERMS = {"champions", "football", "sport", "météo", "meteo", "recette", "cinéma", "cinema"}


def _normalise_for_scope(message: str) -> str:
    normalized = unicodedata.normalize("NFD", message.lower())
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _is_admin_domain_question(message: str) -> bool:
    words = set(_normalise_for_scope(message).replace("'", " ").split())
    if words & OFF_TOPIC_TERMS:
        return False
    return True


def _protect_admin_reply(reply: str) -> str:
    normalized = _normalise_for_scope(reply)
    sensitive_terms = ("matricule", "identifiant fiscal", "numero de registre")
    return PRIVACY_REPLY if any(term in normalized for term in sensitive_terms) else reply


def _is_authorized_inspector(inspector_id: Optional[str]) -> bool:
    configured = os.environ.get("RAKABA_INSPECTORS", "amira")
    allowed = {value.strip() for value in configured.split(",") if value.strip()}
    return bool(inspector_id and inspector_id in allowed)


def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210_000)
    return f"{salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        candidate = _hash_password(password, bytes.fromhex(salt_hex)).split("$", 1)[1]
        return hmac.compare_digest(candidate, digest_hex)
    except (ValueError, TypeError):
        return False


def register_client(
    email: Optional[str],
    password: Optional[str],
    business_name: Optional[str],
    phone: Optional[str],
) -> Tuple[Dict[str, Any], int]:
    email = (email or "").strip().lower()
    business_name = (business_name or "").strip()
    phone = "".join(char for char in (phone or "") if char.isdigit())
    if not email or "@" not in email or len(password or "") < 8 or not business_name or len(phone) < 8:
        return {"error": "Renseignez un email, un mot de passe d'au moins 8 caractères, le nom de l'entreprise et le téléphone déclaré."}, 400

    existing = db.run("SELECT account_id FROM client_accounts WHERE email = ?", [email])
    if existing:
        return {"error": "Un compte existe déjà avec cet email."}, 409

    matches = db.run(
        """
        SELECT tl.entity_id, l.business_name, l.phone
        FROM taxpayer_lifecycle tl
        JOIN listings l ON l.listing_id = tl.listing_id
        WHERE lower(l.business_name) = lower(?) AND regexp_replace(l.phone, '[^0-9]', '', 'g') = ?
        """,
        [business_name, phone],
    )
    if len(matches) != 1:
        return {"error": "Nous ne trouvons pas un dossier unique avec ces informations. Vérifiez le nom et le téléphone déclaré."}, 404

    account_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO client_accounts (account_id, email, password_hash, entity_id) VALUES (?, ?, ?, ?)",
        [account_id, email, _hash_password(password), matches[0]["entity_id"]],
    )
    return {"email": email, "name": matches[0]["business_name"]}, 201


def login_client(email: Optional[str], password: Optional[str]) -> Tuple[Dict[str, Any], int]:
    email = (email or "").strip().lower()
    rows = db.run(
        "SELECT account_id, email, password_hash, entity_id FROM client_accounts WHERE email = ? AND active = TRUE",
        [email],
    )
    if not rows or not _verify_password(password or "", rows[0]["password_hash"]):
        return {"error": "Email ou mot de passe incorrect."}, 401

    token = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO client_sessions (session_id, account_id, token_hash, expires_at) VALUES (?, ?, ?, ?)",
        [str(uuid.uuid4()), rows[0]["account_id"], hashlib.sha256(token.encode()).hexdigest(), datetime.now(timezone.utc) + timedelta(days=CLIENT_SESSION_TTL_DAYS)],
    )
    entity = _fetch_client_safe_entity(rows[0]["entity_id"])
    return {"session_token": token, "email": email, "name": entity["name"] if entity else ""}, 200


def get_client_session(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    rows = db.run(
        """
        SELECT ca.account_id, ca.email, ca.entity_id, l.business_name AS name
        FROM client_sessions cs
        JOIN client_accounts ca ON ca.account_id = cs.account_id AND ca.active = TRUE
        JOIN taxpayer_lifecycle tl ON tl.entity_id = ca.entity_id
        JOIN listings l ON l.listing_id = tl.listing_id
        WHERE cs.token_hash = ? AND cs.expires_at > current_timestamp
        """,
        [hashlib.sha256(token.encode()).hexdigest()],
    )
    return rows[0] if rows else None


def logout_client(token: Optional[str]) -> None:
    if token:
        db.execute("DELETE FROM client_sessions WHERE token_hash = ?", [hashlib.sha256(token.encode()).hexdigest()])


def _load_conversation(conversation_id: Optional[str], inspector_id: str) -> list[dict[str, Any]]:
    if not conversation_id:
        return []
    rows = db.run(
        "SELECT messages FROM assistant_conversations WHERE conversation_id = ? AND inspector_id = ?",
        [conversation_id, inspector_id],
    )
    if not rows:
        return []
    try:
        parsed = json.loads(rows[0]["messages"])
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _save_conversation(
    conversation_id: Optional[str],
    inspector_id: str,
    context_entity_id: Optional[str],
    messages: list[dict[str, Any]],
) -> None:
    if not conversation_id:
        return
    # now() rather than current_timestamp: DuckDB's parser mis-binds the bare
    # `current_timestamp` keyword against the `excluded.*` references in an
    # ON CONFLICT DO UPDATE SET clause ("does not have a column named
    # 'current_timestamp'") the moment the same INSERT also provides it
    # positionally in VALUES(...) - reproduced directly against duckdb, not
    # just an assumption. now() is the same current-timestamp value without
    # tripping that parsing path.
    db.execute(
        """
        INSERT INTO assistant_conversations (conversation_id, inspector_id, context_entity_id, messages, updated_at)
        VALUES (?, ?, ?, ?, now())
        ON CONFLICT (conversation_id) DO UPDATE SET
            messages = excluded.messages,
            context_entity_id = excluded.context_entity_id,
            updated_at = now()
        """,
        [conversation_id, inspector_id, context_entity_id, json.dumps(messages[-60:])],
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
    context_entity_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], int]:
    if not inspector_id or not message:
        return {"error": "inspector_id et message sont requis"}, 400
    if not _is_authorized_inspector(inspector_id):
        return {"error": "Accès inspecteur refusé"}, 403

    effective_history = conversation_history or _load_conversation(conversation_id, inspector_id)
    scoped_message = message
    if context_entity_id:
        scoped_message = f"Dossier de référence interne {context_entity_id}. Ne cite jamais cette référence. Question : {message}"

    if not _is_admin_domain_question(scoped_message):
        _save_conversation(conversation_id, inspector_id, context_entity_id, effective_history + [{"role": "user", "content": message}, {"role": "assistant", "content": ADMIN_SCOPE_REPLY}])
        return {"reply": ADMIN_SCOPE_REPLY}, 200

    try:
        reply, _evidence_log = run_tool_calling_loop(
            prompts.ADMIN_SYSTEM_PROMPT,
            scoped_message,
            tools.TOOLS_SCHEMA,
            tools.TOOL_REGISTRY,
            conversation_history=effective_history,
        )
    except GroqAPIError as exc:
        return {"error": str(exc)}, 502

    protected_reply = _protect_admin_reply(reply)
    _save_conversation(conversation_id, inspector_id, context_entity_id, effective_history + [{"role": "user", "content": message}, {"role": "assistant", "content": protected_reply}])
    return {"reply": protected_reply}, 200


def _voice_reply(result: Dict[str, Any], code: int, transcript: str) -> Tuple[Dict[str, Any], int]:
    """Shared tail end of both voice handlers: attach the transcript, and
    synthesize audio for the reply if there is one. Synthesis failure
    degrades to a text-only response rather than losing the chat reply
    itself - the user still gets an answer, just not spoken."""
    result["transcript"] = transcript
    reply_text = result.get("reply")
    if code == 200 and reply_text:
        try:
            audio_bytes = voice.synthesize(reply_text)
            result["audio_base64"] = base64.b64encode(audio_bytes).decode("ascii")
            result["audio_format"] = "mp3"
        except voice.VoiceAPIError as exc:
            result["audio_error"] = str(exc)
    return result, code


def voice_chat_client(
    entity_id: Optional[str],
    audio_bytes: bytes,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Any], int]:
    """Same access control and escalation logic as chat_client - this only
    adds speech-to-text on the way in and text-to-speech on the way out."""
    try:
        transcript = voice.transcribe(audio_bytes)
    except voice.VoiceAPIError as exc:
        return {"error": str(exc)}, 502

    if not transcript.strip():
        return {"error": "Aucune parole detectee dans l'audio envoye"}, 400

    result, code = chat_client(entity_id, transcript, conversation_history)
    return _voice_reply(result, code, transcript)


def voice_chat_admin(
    inspector_id: Optional[str],
    audio_bytes: bytes,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    context_entity_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], int]:
    try:
        transcript = voice.transcribe(audio_bytes)
    except voice.VoiceAPIError as exc:
        return {"error": str(exc)}, 502

    if not transcript.strip():
        return {"error": "Aucune parole detectee dans l'audio envoye"}, 400

    result, code = chat_admin(inspector_id, transcript, conversation_history, context_entity_id, conversation_id)
    return _voice_reply(result, code, transcript)


def investigate(
    inspector_id: Optional[str],
    entity_id: Optional[str],
    document_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], int]:
    if not inspector_id or not entity_id:
        return {"error": "inspector_id et entity_id sont requis"}, 400
    if not _is_authorized_inspector(inspector_id):
        return {"error": "Accès inspecteur refusé"}, 403

    existing = db.run("SELECT entity_id FROM taxpayer_lifecycle WHERE entity_id = ?", [entity_id])
    if not existing:
        return {"error": f"Entite '{entity_id}' introuvable"}, 404

    user_message = f"Enquete sur l'entite {entity_id}."
    if document_id:
        user_message += f" Porte une attention particuliere au document {document_id}, qui vient d'etre analyse."

    try:
        report, evidence_log = run_tool_calling_loop(
            prompts.INVESTIGATION_SYSTEM_PROMPT,
            user_message,
            tools.TOOLS_SCHEMA,
            tools.TOOL_REGISTRY,
        )
    except GroqAPIError as exc:
        return {"error": str(exc)}, 502

    return {
        "report": report,
        "evidence_log": evidence_log,
        "decision": _build_investigation_decision(evidence_log, document_id),
    }, 200


def _build_investigation_decision(evidence_log: List[Dict[str, Any]], document_id: Optional[str] = None) -> Dict[str, Any]:
    """Turn tool evidence into a cautious, inspectable next-step recommendation."""
    arguments = []
    next_actions = []
    integrity = next((step["result"] for step in evidence_log if step["tool"] == "verification_integrite"), {})
    declarations = next((step["result"] for step in evidence_log if step["tool"] == "historique_declaration"), {})
    links = next((step["result"] for step in evidence_log if step["tool"] == "entites_liees"), {})

    if integrity.get("flagged_count", 0):
        arguments.append(f"{integrity['flagged_count']} document(s) présentent un point à examiner.")
        next_actions.append("Vérifier visuellement les documents concernés.")
    if declarations.get("gap_count", 0):
        arguments.append(f"{declarations['gap_count']} déclaration(s) sont manquantes ou en retard.")
        next_actions.append("Comparer les périodes concernées avec les justificatifs disponibles.")
    if links.get("count", 0):
        arguments.append(f"{links['count']} lien(s) avec d'autres entités ont été retrouvé(s).")
        next_actions.append("Examiner les liens avant toute décision définitive.")

    if arguments:
        recommendation = "Poursuivre la vérification"
        next_actions.insert(0, "Contacter l'entité pour obtenir les éléments manquants.")
    else:
        recommendation = "Aucun signal prioritaire"
        next_actions.append("Conserver le dossier sous surveillance normale.")

    if document_id:
        arguments.insert(0, "L’avis prend en compte le document qui vient d’être analysé, puis le contexte du dossier.")

    return {
        "recommendation": recommendation,
        "confidence": "Élevée" if len(arguments) >= 2 else "À confirmer",
        "document_id": document_id,
        "arguments": arguments or ["Aucun élément prioritaire n'a été relevé dans les données disponibles."],
        "next_actions": next_actions,
    }


def list_escalations() -> Tuple[Dict[str, Any], int]:
    rows = db.run(
        "SELECT escalation_id, entity_id, message, timestamp, reason FROM escalations ORDER BY timestamp DESC"
    )
    for r in rows:
        r["timestamp"] = str(r["timestamp"])
    return {"escalations": rows}, 200


# ---------------------------------------------------------------------------
# Inspector login (demo-grade: no password, just the allowlist already
# enforced by _is_authorized_inspector on every admin-facing call) and the
# taxpayer-facing "espace client" lookup - both new surfaces, same access
# rules that were already there for chat_admin/chat_client.
# ---------------------------------------------------------------------------

def login_inspector(inspector_id: Optional[str]) -> Tuple[Dict[str, Any], int]:
    inspector_id = (inspector_id or "").strip()
    if not inspector_id:
        return {"error": "Identifiant requis"}, 400
    if not _is_authorized_inspector(inspector_id):
        return {"error": f"Identifiant inspecteur '{inspector_id}' non reconnu"}, 403
    return {"inspector_id": inspector_id, "display_name": inspector_id.replace(".", " ").title()}, 200


def client_search(query: Optional[str]) -> Tuple[Dict[str, Any], int]:
    """Client-safe search by business name only - no match_score, phone,
    notes or lifecycle_state, unlike Pipeline 1's /pipeline1/entities (which
    is an inspector-only surface). A taxpayer can only ever see the same
    handful of columns chat_client itself is allowed to use."""
    query = (query or "").strip()
    if not query:
        return {"matches": []}, 200
    rows = db.run(
        """
        SELECT tl.entity_id, l.business_name AS name, l.location_text AS location
        FROM taxpayer_lifecycle tl
        JOIN listings l ON l.listing_id = tl.listing_id
        WHERE lower(l.business_name) LIKE lower(?)
        ORDER BY l.business_name
        LIMIT 15
        """,
        [f"%{query}%"],
    )
    return {"matches": rows}, 200


def client_status(entity_id: Optional[str]) -> Tuple[Dict[str, Any], int]:
    """Friendly, client-safe status for the espace client header - the same
    fields/labels chat_client itself is restricted to, exposed directly so
    the portal can show a status pill without spending a chat turn on it."""
    if not entity_id:
        return {"error": "entity_id requis"}, 400
    entity = _fetch_client_safe_entity(entity_id)
    if entity is None:
        return {"error": f"Dossier '{entity_id}' introuvable"}, 404
    return {
        "name": entity["name"],
        "status_label": _client_status_label(entity["lifecycle_state"]),
    }, 200
