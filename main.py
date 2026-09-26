"""
main.py — Application FastAPI RAKABA (point d'entrée unifié).

Un seul backend pour les Pipelines 2 et 3, conformément au cahier des
charges (section 14 : "un seul backend exposant deux interfaces"). Les deux
pipelines partagent le même fichier DuckDB (pipeline1/db.py définit le
schéma) ; les faire tourner comme deux process séparés (l'ancien
`pipeline3/app.py` en Flask à côté de cette app FastAPI) se heurterait au
verrou mono-écrivain de DuckDB sur ce fichier.

Pipeline 1 n'expose pas d'API HTTP à ce jour (son point d'entrée est le
script `python -m pipeline1.pipeline` / `pipeline1.demo_loop`) ; ses tables
sont lues directement par 2 et 3 via le fichier DuckDB partagé.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title       = "RAKABA — Plateforme de détection fiscale",
    description = "Pipeline 2 (vérification et scoring documentaire) + Pipeline 3 (chatbot et agent d'investigation)",
    version     = "1.0.0",
)


@app.on_event("startup")
async def on_startup() -> None:
    """Initialise toutes les pipelines au démarrage."""
    from pipeline2 import startup_pipeline2
    startup_pipeline2()

    from pipeline3.router import startup_pipeline3
    startup_pipeline3()


# Enregistrement des routers Pipeline 2 et Pipeline 3
from pipeline2 import pipeline2_router
app.include_router(pipeline2_router)

from pipeline3.router import router as pipeline3_router
app.include_router(pipeline3_router)


@app.get("/health", tags=["System"])
def health_check() -> dict:
    return {"status": "ok", "service": "RAKABA"}
