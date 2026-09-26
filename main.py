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
from fastapi.responses import HTMLResponse
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

    from pipeline1 import live_feed
    live_feed.start()


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


@app.get("/", tags=["System"], include_in_schema=False)
def landing() -> HTMLResponse:
    """Tiny portal picker - the two real interfaces (cahier des charges §14)
    are separate SPAs (/admin, /espace-client) with no shared router, so this
    just needs to be a couple of links, not a third app."""
    return HTMLResponse(
        """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RAKABA</title>
<style>
/* Brand colors sampled from the RAKABA logo (navy + red). Light background,
   not dark: the logo itself is dark navy on transparent, so it needs a
   light backdrop to actually be visible. */
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#f5f7fb;color:#132130;font-family:'Segoe UI',sans-serif;padding:16px}
main{max-width:440px;text-align:center}
img.logo{height:120px;width:auto;display:block;margin:0 auto 18px;object-fit:contain}
p{color:#5b6472;margin:0 0 28px}
.links{display:flex;gap:14px;flex-wrap:wrap;justify-content:center}
a{display:block;flex:1;min-width:170px;padding:18px;border-radius:14px;
background:#ffffff;border:1px solid #e2e6ee;color:#132130;text-decoration:none;font-weight:600;
box-shadow:0 1px 2px rgba(19,33,48,0.05)}
a:hover{border-color:#bc141f}
small{display:block;margin-top:6px;font-weight:400;color:#5b6472}
</style></head><body><main>
<img class="logo" src="/admin/logo.png" alt="RAKABA — رقابة">
<p>Vigilance fiscale augmentée</p>
<div class="links">
<a href="/admin">Espace inspecteur<small>Détection, vérification, agent d'investigation</small></a>
<a href="/espace-client">Espace contribuable<small>Consulter mon dossier</small></a>
</div>
</main></body></html>"""
    )


# Interfaces React (build de production) - deux SPA distinctes, servies
# statiquement : /admin (inspecteur) et /espace-client (contribuable).
_ADMIN_DIST = Path(__file__).resolve().parent / "frontend" / "admin" / "dist"
if _ADMIN_DIST.exists():
    app.mount("/admin", StaticFiles(directory=str(_ADMIN_DIST), html=True), name="admin")

_CLIENT_DIST = Path(__file__).resolve().parent / "frontend" / "client" / "dist"
if _CLIENT_DIST.exists():
    app.mount("/espace-client", StaticFiles(directory=str(_CLIENT_DIST), html=True), name="espace-client")
