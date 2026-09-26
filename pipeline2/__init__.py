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
      3. Entraîne le GNN (optionnel) — sur le vrai graphe (entity_links de
         Pipeline 1) si assez de données existent déjà, sinon sur un warm-up
         synthétique de secours (le modèle existe quand même en démo isolée,
         mais gnn_anomaly_score() ne renverra rien pour de vraies entités
         tant que Pipeline 1 n'a pas tourné et que ce démarrage n'a pas été
         relancé).
    """
    from .database        import init_db, get_connection
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

    # 3 — GNN (F2.7) — optionnel, jamais bloquant
    trained = False
    try:
        conn = get_connection()
        from .router import _sync_graph_from_entity_links
        _sync_graph_from_entity_links(conn)
        edge_rows = conn.execute(
            "SELECT node_a, node_b, edge_type, weight FROM entity_graph_edges"
        ).fetchall()
        if len(edge_rows) >= 2:
            real_links = [
                EntityLink(entity_id_a=a, entity_id_b=b, shared_attribute=et,
                           link_score=w, edge_type=et)
                for (a, b, et, w) in edge_rows
            ]
            trained = train_gnn(build_graph(real_links))
    except Exception as exc:
        logger.warning("Pipeline 2: construction du graphe reel pour le GNN ignoree : %s", exc)

    if trained:
        source = "graphe reel (entity_links de Pipeline 1)"
    else:
        # Warm-up synthetique de secours : garantit qu'un modele existe meme
        # sans donnees Pipeline 1 (demo isolee de P2), mais gnn_anomaly_score
        # ne trouvera aucune vraie entite dans ce graphe.
        import networkx as nx
        G = nx.Graph()
        for doc in docs[:50]:
            G.add_node(doc["entity_id"])
        G.add_edges_from([
            (docs[i]["entity_id"], docs[i + 1]["entity_id"])
            for i in range(0, min(20, len(docs) - 1), 2)
        ])
        train_gnn(G)
        source = "warm-up synthetique (aucune donnee Pipeline 1 disponible)"

    if is_gnn_available():
        logger.info("Pipeline 2: GNN entraine et disponible (%s).", source)
    else:
        logger.info("Pipeline 2: GNN non disponible (PyG absent ou graphe insuffisant).")


# Export du router pour main.py
from .router import router as pipeline2_router

__all__ = ["pipeline2_router", "startup_pipeline2"]
