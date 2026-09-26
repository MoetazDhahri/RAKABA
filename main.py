"""
main.py — Application FastAPI RAKABA (point d'entrée unifié).

Un seul backend pour les Pipelines 1, 2 et 3, conformément au cahier des
charges (section 14 : "un seul backend exposant deux interfaces"). Les trois
pipelines partagent le même fichier DuckDB (pipeline1/db.py définit le
schéma) ; les faire tourner comme des process séparés (l'ancien
`pipeline3/app.py` en Flask à côté de cette app FastAPI) se heurterait au
verrou mono-écrivain de DuckDB sur ce fichier.

Sert aussi l'interface Admin React (frontend/admin) sur /admin - le build de
production (`npm run build`, dossier dist/). En développement, lancer plutôt
`npm run dev` dans frontend/admin (proxy Vite vers ce backend) pour le hot
reload ; les deux ne servent pas la même chose mais tapent la même API.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title       = "RAKABA — Plateforme de détection fiscale",
    description = "Pipeline 1 (découverte) + Pipeline 2 (vérification) + Pipeline 3 (chatbot et agent d'investigation)",
    version     = "1.0.0",
)


@app.on_event("startup")
async def on_startup() -> None:
    """Initialise toutes les pipelines au démarrage."""
    from pipeline1 import db as shared_db
    shared_db.get_connection()

    from pipeline2 import startup_pipeline2
    startup_pipeline2()

    from pipeline3.router import startup_pipeline3
    startup_pipeline3()


# Enregistrement des routers Pipeline 1, 2 et Pipeline 3
from pipeline1.router import router as pipeline1_router
app.include_router(pipeline1_router)

from pipeline2 import pipeline2_router
app.include_router(pipeline2_router)

from pipeline3.router import router as pipeline3_router
app.include_router(pipeline3_router)


@app.get("/health", tags=["System"])
def health_check() -> dict:
    return {"status": "ok", "service": "RAKABA"}


# Interface Admin (React, build de production) - http://localhost:8000/admin
_ADMIN_DIST = Path(__file__).resolve().parent / "frontend" / "admin" / "dist"
if _ADMIN_DIST.exists():
    app.mount("/admin", StaticFiles(directory=str(_ADMIN_DIST), html=True), name="admin")
