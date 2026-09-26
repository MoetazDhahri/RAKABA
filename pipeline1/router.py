"""
pipeline1/router.py
FastAPI router — Pipeline 1 : Découvrir.

Pipeline 1's own entry point has always been script/CLI-based
(python -m pipeline1.pipeline / pipeline1.demo_loop) since nothing needed an
HTTP surface until the Admin dashboard did. This router exists to serve
that: reads (and the one write - manual transition, F1.8) over the same
shared DuckDB file Pipelines 2 and 3 already use, via pipeline1/db.py's
connection.
"""

from __future__ import annotations

from typing import Optional

import duckdb
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from pipeline1 import dashboard, db, entity_linking, pipeline, queries

router = APIRouter(prefix="/pipeline1", tags=["Pipeline 1 — Découvrir"])


def get_db():
    # Held for the whole request (yield-dependencies stay "open" until the
    # endpoint returns) - see pipeline1/db.py's LOCK docstring for why this
    # is necessary, not just cautious.
    with db.LOCK:
        yield db.get_connection()


@router.get("/dashboard/overview", summary="Donnees agregees pour la vue d'ensemble Admin")
def dashboard_overview(conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> dict:
    return dashboard.overview(conn)


@router.get("/kanban", summary="Colonnes du tableau kanban (5 etats du cycle de vie)")
def kanban(conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> dict:
    return queries.kanban_columns(conn)


@router.get("/lifecycle-statuses", summary="Les 5 statuts, dans l'ordre du cycle de vie")
def lifecycle_statuses() -> list:
    return pipeline.LIFECYCLE_ORDER


@router.get("/entities", summary="Liste des entites, filtrable par statut")
def list_entities(status_filter: Optional[str] = None, conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> list:
    return queries.list_entities_by_status(conn, status_filter)


@router.get("/entities/{entity_id}", summary="Detail d'une entite (score, historique)")
def entity_detail(entity_id: str, conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> dict:
    detail = queries.get_entity_detail(conn, entity_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Entite '{entity_id}' introuvable")
    return detail


@router.get("/entities/{entity_id}/links", summary="Entites liees (telephone/adresse partages, F1.6)")
def entity_links(entity_id: str, conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> list:
    return entity_linking.get_related_entities(conn, entity_id)


class TransitionIn(BaseModel):
    new_status: str
    note: Optional[str] = None


@router.post("/entities/{entity_id}/transition", summary="Forcage manuel d'une transition (F1.8, reserve a Amira)")
def force_transition(entity_id: str, payload: TransitionIn, conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> dict:
    existing = queries.get_entity_detail(conn, entity_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Entite '{entity_id}' introuvable")
    try:
        pipeline.force_transition(conn, entity_id, payload.new_status, note=payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return queries.get_entity_detail(conn, entity_id)


@router.get("/automation-log", summary="Journal d'automatisation cross-pipeline")
def automation_log(limit: int = 100, conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> list:
    return queries.get_automation_log(conn, limit=limit)
