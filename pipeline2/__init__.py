"""
pipeline2 — Module de détection/vérification fiscale (RAKABA).

Point d'entrée pour l'intégration dans l'application FastAPI principale.

Usage dans main.py :
    from pipeline2 import pipeline2_router, startup_pipeline2
    app.include_router(pipeline2_router)
    app.add_event_handler("startup", startup_pipeline2)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def startup_pipeline2() -> None:
    """
    Initialise la Pipeline 2 au démarrage de l'application :
      1. Crée les tables DB si absentes
      2. Entraîne l'Isolation Forest sur les données synthétiques
      3. Tente d'entraîner le GNN (optionnel — ne bloque pas si échec)
    """
    from .database        import init_db
    from .anomaly         import train_isolation_forest
    from .synthetic_data  import generate_synthetic_documents, get_entity_history
    from .gnn             import train_gnn, is_gnn_available
    from .graph           import build_graph, EntityLink

    # 1 — Base de données
    init_db()
    logger.info("Pipeline 2: tables DB initialisées.")

    # 2 — Isolation Forest (F2.3)
    docs = generate_synthetic_documents(n=500, seed=42)
    historical_lookup = {
        eid: get_entity_history(eid, docs)
        for eid in {d["entity_id"] for d in docs}
    }
    train_isolation_forest(docs, historical_lookup)
    logger.info("Pipeline 2: Isolation Forest prêt.")

    # 3 — GNN (F2.7) — optionnel
    links = []
    for doc in docs:
        if doc.get("_anomaly_types") and "linked_entity_transaction" in doc["_anomaly_types"]:
            pass  # liens synthétiques déjà dans les données
    try:
        # Graphe minimal pour le warm-up du GNN
        import networkx as nx
        G = nx.Graph()
        for doc in docs[:50]:
            G.add_node(doc["entity_id"])
        G.add_edges_from([
            (docs[i]["entity_id"], docs[i+1]["entity_id"])
            for i in range(0, min(20, len(docs)-1), 2)
        ])
        train_gnn(G)
        if is_gnn_available():
            logger.info("Pipeline 2: GNN entraîné et disponible.")
        else:
            logger.info("Pipeline 2: GNN non disponible (PyG absent ou graphe insuffisant).")
    except Exception as exc:
        logger.warning("Pipeline 2: initialisation GNN ignorée : %s", exc)


# Export du router pour main.py
from .router import router as pipeline2_router

__all__ = ["pipeline2_router", "startup_pipeline2"]
