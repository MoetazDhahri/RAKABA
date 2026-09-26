"""
pipeline3/router.py
FastAPI router — Pipeline 3 : Accompagner.

Mounted into the unified backend (repo-root main.py) alongside Pipeline 2's
router, so the whole platform runs as one process against one DuckDB file -
per cahier des charges section 14 ("un seul backend exposant deux
interfaces"). Previously this pipeline only ran as a separate Flask process,
which would have raced Pipeline 2's FastAPI process for the same DuckDB
file's single-writer lock.

Thin adapter over handlers.py: builds the request/response shape FastAPI
expects, calls the same framework-agnostic handlers app.py (the standalone
Flask entry point) uses - one source of truth for the actual logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parent / ".env")

import handlers

router = APIRouter(tags=["Pipeline 3 — Accompagner"])


class ClientChatIn(BaseModel):
    entity_id: Optional[str] = None
    message: str
    conversation_history: List[Dict[str, Any]] = []


class AdminChatIn(BaseModel):
    inspector_id: str
    message: str
    conversation_history: List[Dict[str, Any]] = []
    context_entity_id: Optional[str] = None
    conversation_id: Optional[str] = None


class InvestigateIn(BaseModel):
    inspector_id: str
    entity_id: str
    document_id: Optional[str] = None


class ClientRegisterIn(BaseModel):
    email: str
    password: str
    business_name: str
    phone: str


class ClientLoginIn(BaseModel):
    email: str
    password: str


CLIENT_COOKIE = "rakaba_client_session"


def _client_session(request: Request) -> dict:
    session = handlers.get_client_session(request.cookies.get(CLIENT_COOKIE))
    if session is None:
        raise HTTPException(status_code=401, detail="Connexion contribuable requise")
    return session


@router.post("/api/auth/client/register", summary="Créer un compte contribuable")
def register_client(payload: ClientRegisterIn) -> JSONResponse:
    result, code = handlers.register_client(payload.email, payload.password, payload.business_name, payload.phone)
    return JSONResponse(content=result, status_code=code)


@router.post("/api/auth/client/login", summary="Connexion contribuable")
def login_client(payload: ClientLoginIn) -> JSONResponse:
    result, code = handlers.login_client(payload.email, payload.password)
    if code == 200:
        token = result.pop("session_token")
        response = JSONResponse(content=result, status_code=code)
        response.set_cookie(CLIENT_COOKIE, token, httponly=True, secure=False, samesite="lax", max_age=7 * 24 * 3600)
        return response
    return JSONResponse(content=result, status_code=code)


@router.get("/api/auth/client/me", summary="Compte contribuable connecté")
def client_me(request: Request) -> JSONResponse:
    session = _client_session(request)
    return JSONResponse(content={"email": session["email"], "name": session["name"]})


@router.get("/api/client/dossier", summary="Dossier du contribuable connecté")
def client_dossier(request: Request) -> JSONResponse:
    session = _client_session(request)
    result, code = handlers.client_status(session["entity_id"])
    return JSONResponse(content=result, status_code=code)


@router.post("/api/auth/client/logout", summary="Déconnexion contribuable")
def logout_client(request: Request) -> JSONResponse:
    handlers.logout_client(request.cookies.get(CLIENT_COOKIE))
    response = JSONResponse(content={"ok": True})
    response.delete_cookie(CLIENT_COOKIE)
    return response


@router.post("/api/chat/client", summary="Chatbot contribuable (grounded, jamais accusateur)")
def chat_client(payload: ClientChatIn, request: Request) -> JSONResponse:
    session = _client_session(request)
    if payload.entity_id and payload.entity_id != session["entity_id"]:
        raise HTTPException(status_code=403, detail="Ce dossier n'appartient pas à ce compte")
    result, code = handlers.chat_client(session["entity_id"], payload.message, payload.conversation_history)
    return JSONResponse(content=result, status_code=code)


@router.post("/api/chat/admin", summary="Chatbot interne pour inspecteurs")
def chat_admin(payload: AdminChatIn) -> JSONResponse:
    result, code = handlers.chat_admin(
        payload.inspector_id,
        payload.message,
        payload.conversation_history,
        payload.context_entity_id,
        payload.conversation_id,
    )
    return JSONResponse(content=result, status_code=code)


def _parse_conversation_history(raw: Optional[str]) -> list:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


@router.post("/api/voice/chat/client", summary="Chatbot contribuable, en voix (ElevenLabs STT+TTS)")
async def voice_chat_client(
    request: Request,
    entity_id: Optional[str] = Form(None),
    conversation_history: Optional[str] = Form(None, description="JSON-encoded list, optional"),
    audio: UploadFile = File(...),
) -> JSONResponse:
    session = _client_session(request)
    if entity_id and entity_id != session["entity_id"]:
        raise HTTPException(status_code=403, detail="Ce dossier n'appartient pas à ce compte")
    result, code = handlers.voice_chat_client(
        session["entity_id"], await audio.read(), _parse_conversation_history(conversation_history)
    )
    return JSONResponse(content=result, status_code=code)


@router.post("/api/voice/chat/admin", summary="Chatbot inspecteur, en voix (ElevenLabs STT+TTS)")
async def voice_chat_admin(
    inspector_id: str = Form(...),
    conversation_history: Optional[str] = Form(None, description="JSON-encoded list, optional"),
    context_entity_id: Optional[str] = Form(None),
    conversation_id: Optional[str] = Form(None),
    audio: UploadFile = File(...),
) -> JSONResponse:
    result, code = handlers.voice_chat_admin(
        inspector_id,
        await audio.read(),
        _parse_conversation_history(conversation_history),
        context_entity_id,
        conversation_id,
    )
    return JSONResponse(content=result, status_code=code)


@router.post("/api/investigate", summary="Agent d'investigation autonome (tool-calling)")
def investigate(payload: InvestigateIn) -> JSONResponse:
    result, code = handlers.investigate(payload.inspector_id, payload.entity_id, payload.document_id)
    return JSONResponse(content=result, status_code=code)


@router.get("/api/escalations", summary="Journal des questions clients escaladees")
def list_escalations() -> JSONResponse:
    result, code = handlers.list_escalations()
    return JSONResponse(content=result, status_code=code)


class InspectorLoginIn(BaseModel):
    inspector_id: str


@router.post("/api/auth/inspector", summary="Connexion inspecteur (liste blanche RAKABA_INSPECTORS, sans mot de passe)")
def login_inspector(payload: InspectorLoginIn) -> JSONResponse:
    result, code = handlers.login_inspector(payload.inspector_id)
    return JSONResponse(content=result, status_code=code)


@router.get("/api/client/search", summary="Recherche d'un dossier par nom d'entreprise (espace client, donnees limitees)")
def client_search(q: str = "") -> JSONResponse:
    result, code = handlers.client_search(q)
    return JSONResponse(content=result, status_code=code)


@router.get("/api/client/entities/{entity_id}", summary="Statut simplifie d'un dossier (espace client)")
def client_status(entity_id: str, request: Request) -> JSONResponse:
    session = _client_session(request)
    if entity_id != session["entity_id"]:
        raise HTTPException(status_code=403, detail="Ce dossier n'appartient pas à ce compte")
    result, code = handlers.client_status(session["entity_id"])
    return JSONResponse(content=result, status_code=code)


def startup_pipeline3() -> None:
    """Ensures the shared schema/declarations seeding has run before serving."""
    import db
    db.get_connection()
