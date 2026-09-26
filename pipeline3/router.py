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
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parent / ".env")

import handlers

router = APIRouter(tags=["Pipeline 3 — Accompagner"])


class ClientChatIn(BaseModel):
    entity_id: str
    message: str
    conversation_history: List[Dict[str, Any]] = []


class AdminChatIn(BaseModel):
    inspector_id: str
    message: str
    conversation_history: List[Dict[str, Any]] = []


class InvestigateIn(BaseModel):
    inspector_id: str
    entity_id: str


@router.post("/api/chat/client", summary="Chatbot contribuable (grounded, jamais accusateur)")
def chat_client(payload: ClientChatIn) -> JSONResponse:
    result, code = handlers.chat_client(payload.entity_id, payload.message, payload.conversation_history)
    return JSONResponse(content=result, status_code=code)


@router.post("/api/chat/admin", summary="Chatbot interne pour inspecteurs")
def chat_admin(payload: AdminChatIn) -> JSONResponse:
    result, code = handlers.chat_admin(payload.inspector_id, payload.message, payload.conversation_history)
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
    entity_id: str = Form(...),
    conversation_history: Optional[str] = Form(None, description="JSON-encoded list, optional"),
    audio: UploadFile = File(...),
) -> JSONResponse:
    result, code = handlers.voice_chat_client(
        entity_id, await audio.read(), _parse_conversation_history(conversation_history)
    )
    return JSONResponse(content=result, status_code=code)


@router.post("/api/voice/chat/admin", summary="Chatbot inspecteur, en voix (ElevenLabs STT+TTS)")
async def voice_chat_admin(
    inspector_id: str = Form(...),
    conversation_history: Optional[str] = Form(None, description="JSON-encoded list, optional"),
    audio: UploadFile = File(...),
) -> JSONResponse:
    result, code = handlers.voice_chat_admin(
        inspector_id, await audio.read(), _parse_conversation_history(conversation_history)
    )
    return JSONResponse(content=result, status_code=code)


@router.post("/api/investigate", summary="Agent d'investigation autonome (tool-calling)")
def investigate(payload: InvestigateIn) -> JSONResponse:
    result, code = handlers.investigate(payload.inspector_id, payload.entity_id)
    return JSONResponse(content=result, status_code=code)


@router.get("/api/escalations", summary="Journal des questions clients escaladees")
def list_escalations() -> JSONResponse:
    result, code = handlers.list_escalations()
    return JSONResponse(content=result, status_code=code)


def startup_pipeline3() -> None:
    """Ensures the shared schema/declarations seeding has run before serving."""
    import db
    db.get_connection()
