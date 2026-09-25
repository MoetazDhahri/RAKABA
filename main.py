"""
main.py — Application FastAPI RAKABA (point d'entrée).

Intègre la Pipeline 2. Les Pipelines 1 et 3 peuvent être ajoutés
en suivant le même pattern.
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
    description = "Pipeline 2 : Vérification et scoring documentaire",
    version     = "1.0.0",
)


@app.on_event("startup")
async def on_startup() -> None:
    """Initialise toutes les pipelines au démarrage."""
    from pipeline2 import startup_pipeline2
    startup_pipeline2()


# Enregistrement du router Pipeline 2
from pipeline2 import pipeline2_router
app.include_router(pipeline2_router)


@app.get("/health", tags=["System"])
def health_check() -> dict:
    return {"status": "ok", "service": "RAKABA"}
