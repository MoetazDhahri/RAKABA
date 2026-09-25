"""
pipeline2/router.py
Endpoints FastAPI — Pipeline 2 : Vérifier.

Routes :
  POST   /documents/upload                — scoring complet d'un nouveau document
  GET    /documents/{document_id}         — détail du score (3 axes + explications)
  GET    /entities/{entity_id}/documents  — liste des documents d'une entité
  GET    /graph/entity/{entity_id}        — nœuds/arêtes liés à une entité
  GET    /graph/clusters                  — clusters détectés
  POST   /documents/{document_id}/rescan  — relance du scoring

Fonction Python pure (hors HTTP) :
  check_document_integrity(entity_id) → dict
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .database  import get_db
from .graph     import (
    EntityLink,
    build_graph, detect_clusters, get_entity_subgraph, graph_to_db_objects,
)
from .gnn       import gnn_anomaly_score, is_gnn_available
from .models    import Document, EntityGraphEdge, EntityGraphNode
from .schemas   import (
    CoherenceDetail, DocumentIn, DocumentListOut,
    EdgeTypeEnum, EntityGraphOut, GraphClusterOut,
    GraphEdgeOut, GraphNodeOut,
    IntegrityDetail, RescanOut, RiskDetail, ScoreOut,
)
from .scoring   import score_document, CompositeScore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline2", tags=["Pipeline 2 — Vérifier"])


# ---------------------------------------------------------------------------
# Helpers de conversion ORM → Pydantic
# ---------------------------------------------------------------------------

def _orm_document_to_score_out(doc: Document) -> ScoreOut:
    """Convertit un objet ORM Document en ScoreOut Pydantic."""
    risk_flags  = doc.risk_flags or []
    nb_flags    = len(risk_flags)

    return ScoreOut(
        document_id    = doc.document_id,
        entity_id      = doc.entity_id,
        submitted_date = doc.submitted_date,
        integrity = IntegrityDetail(
            score = doc.integrity_score or 0.5,
            flags = doc.integrity_flags or [],
        ),
        coherence = CoherenceDetail(
            score        = doc.coherence_score or 0.5,
            raw_if_score = None,
            explanation  = "Score chargé depuis la base de données.",
        ),
        risk = RiskDetail(
            flags      = risk_flags,
            nb_flags   = nb_flags,
            risk_score = float(nb_flags),
        ),
        composite_score   = doc.composite_score or 0.0,
        gnn_anomaly_score = gnn_anomaly_score(doc.entity_id),
    )


def _composite_to_score_out(cs: CompositeScore) -> ScoreOut:
    """Convertit un CompositeScore (scoring.py) en ScoreOut Pydantic."""
    return ScoreOut(
        document_id    = cs.document_id,
        entity_id      = cs.entity_id,
        submitted_date = cs.submitted_date,
        integrity = IntegrityDetail(
            score = cs.integrity.score,
            flags = cs.integrity.flags,
        ),
        coherence = CoherenceDetail(
            score        = cs.coherence.score,
            raw_if_score = cs.coherence.raw_if_score,
            explanation  = cs.coherence.explanation,
        ),
        risk = RiskDetail(
            flags      = cs.risk.flags,
            nb_flags   = cs.risk.nb_flags,
            risk_score = cs.risk.risk_score,
        ),
        composite_score   = cs.composite_score,
        gnn_anomaly_score = cs.gnn_anomaly_score,
    )


def _persist_composite_score(
    cs: CompositeScore,
    file_metadata: Dict[str, Any],
    db: Session,
) -> Document:
    """Crée ou met à jour un objet Document en base."""
    doc = Document(
        document_id     = cs.document_id,
        entity_id       = cs.entity_id,
        file_metadata   = file_metadata,
        integrity_score = cs.integrity.score,
        coherence_score = cs.coherence.score,
        risk_flags      = cs.risk.flags,
        composite_score = cs.composite_score,
        submitted_date  = cs.submitted_date,
        integrity_flags = cs.integrity.flags,
        risk_score_raw  = cs.risk.risk_score,
    )
    # db.merge() retourne l'instance persistée — utiliser cette référence
    merged = db.merge(doc)
    db.commit()
    db.refresh(merged)
    return merged


def _get_entity_historical_amounts(entity_id: str, db: Session) -> List[float]:
    """Récupère l'historique des montants d'une entité depuis la base."""
    docs = db.query(Document).filter(Document.entity_id == entity_id).all()
    # On extrait le montant depuis file_metadata si disponible, sinon on utilise
    # composite_score comme proxy (les montants bruts ne sont pas persistés séparément).
    # En production, ajouter une colonne `montant` dans Document.
    amounts = []
    for d in docs:
        meta = d.file_metadata or {}
        if "montant" in meta:
            amounts.append(float(meta["montant"]))
    return amounts


# ---------------------------------------------------------------------------
# POST /documents/upload
# ---------------------------------------------------------------------------

@router.post(
    "/documents/upload",
    response_model=ScoreOut,
    status_code=status.HTTP_201_CREATED,
    summary="Soumettre un document et déclencher le scoring complet",
)
def upload_document(payload: DocumentIn, db: Session = Depends(get_db)) -> ScoreOut:
    """
    Reçoit un document fiscal, déclenche le pipeline de scoring complet
    (F2.2 + F2.3 + F2.4 + F2.5) et persiste le résultat.
    """
    doc_id = str(uuid.uuid4())

    # Historique des montants de l'entité (pour F2.3)
    historical = _get_entity_historical_amounts(payload.entity_id, db)
    # Inclure le montant courant dans l'historique pour les règles F2.4
    all_amounts = historical + [payload.montant]

    file_meta_dict = payload.file_metadata.model_dump(mode="json")

    cs = score_document(
        entity_id         = payload.entity_id,
        file_metadata     = file_meta_dict,
        declared_date     = payload.declared_date,
        montant           = payload.montant,
        nb_transactions   = payload.nb_transactions,
        activite_declaree = payload.activite_declaree,
        historical_amounts= all_amounts,
        document_id       = doc_id,
    )

    # Enrichissement GNN si disponible
    cs.gnn_anomaly_score = gnn_anomaly_score(payload.entity_id)

    _persist_composite_score(cs, file_meta_dict, db)

    logger.info("Document %s uploadé et scoré (entity=%s).", doc_id, payload.entity_id)
    return _composite_to_score_out(cs)


# ---------------------------------------------------------------------------
# GET /documents/{document_id}
# ---------------------------------------------------------------------------

@router.get(
    "/documents/{document_id}",
    response_model=ScoreOut,
    summary="Récupérer le score détaillé d'un document",
)
def get_document_score(document_id: str, db: Session = Depends(get_db)) -> ScoreOut:
    """
    Retourne le détail du score d'un document (3 axes + explications).
    Jamais uniquement le chiffre global.
    """
    doc = db.query(Document).filter(Document.document_id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id!r} introuvable.",
        )
    return _orm_document_to_score_out(doc)


# ---------------------------------------------------------------------------
# GET /entities/{entity_id}/documents
# ---------------------------------------------------------------------------

@router.get(
    "/entities/{entity_id}/documents",
    response_model=DocumentListOut,
    summary="Lister tous les documents d'une entité",
)
def list_entity_documents(entity_id: str, db: Session = Depends(get_db)) -> DocumentListOut:
    """Liste tous les documents soumis par une entité, du plus récent au plus ancien."""
    docs = (
        db.query(Document)
        .filter(Document.entity_id == entity_id)
        .order_by(Document.submitted_date.desc())
        .all()
    )
    return DocumentListOut(
        entity_id = entity_id,
        total     = len(docs),
        documents = [_orm_document_to_score_out(d) for d in docs],
    )


# ---------------------------------------------------------------------------
# GET /graph/entity/{entity_id}
# ---------------------------------------------------------------------------

@router.get(
    "/graph/entity/{entity_id}",
    response_model=EntityGraphOut,
    summary="Sous-graphe centré sur une entité",
)
def get_entity_graph(entity_id: str, db: Session = Depends(get_db)) -> EntityGraphOut:
    """
    Retourne les nœuds et arêtes directement liés à une entité.
    Construit le graphe depuis les tables entity_graph_nodes/edges.
    """
    # Récupérer les arêtes impliquant l'entité
    edges_a = db.query(EntityGraphEdge).filter(EntityGraphEdge.node_a == entity_id).all()
    edges_b = db.query(EntityGraphEdge).filter(EntityGraphEdge.node_b == entity_id).all()
    all_edges = edges_a + edges_b

    # Collecter les node_ids voisins
    neighbor_ids = {entity_id}
    for e in all_edges:
        neighbor_ids.add(e.node_a)
        neighbor_ids.add(e.node_b)

    # Récupérer les nœuds
    nodes_orm = (
        db.query(EntityGraphNode)
        .filter(EntityGraphNode.node_id.in_(neighbor_ids))
        .all()
    )

    nodes_out = [
        GraphNodeOut(
            node_id           = n.node_id,
            feature_vector    = n.feature_vector or [],
            gnn_anomaly_score = gnn_anomaly_score(n.node_id),
        )
        for n in nodes_orm
    ]

    edges_out = [
        GraphEdgeOut(
            edge_id   = e.edge_id,
            node_a    = e.node_a,
            node_b    = e.node_b,
            edge_type = EdgeTypeEnum(e.edge_type.value),
            weight    = e.weight,
        )
        for e in all_edges
    ]

    return EntityGraphOut(entity_id=entity_id, nodes=nodes_out, edges=edges_out)


# ---------------------------------------------------------------------------
# GET /graph/clusters
# ---------------------------------------------------------------------------

@router.get(
    "/graph/clusters",
    response_model=List[GraphClusterOut],
    summary="Clusters d'entités détectés dans le graphe",
)
def get_clusters(db: Session = Depends(get_db)) -> List[GraphClusterOut]:
    """
    Détecte et retourne les clusters (composantes connexes) du graphe complet.
    Indique le niveau de risque si au moins un nœud du cluster a un score > 0.7.
    """
    # Charger toutes les arêtes et reconstruire le graphe NetworkX
    all_edges_orm = db.query(EntityGraphEdge).all()
    links = [
        EntityLink(
            entity_id_a      = e.node_a,
            entity_id_b      = e.node_b,
            shared_attribute = e.edge_type.value,
            link_score       = e.weight,
            edge_type        = e.edge_type.value,
        )
        for e in all_edges_orm
    ]

    if not links:
        return []

    G        = build_graph(links)
    clusters = detect_clusters(G, min_size=2)

    # Évaluer le risque par cluster : high si max(composite_score) > 0.7
    result = []
    for cluster in clusters:
        docs_in_cluster = (
            db.query(Document)
            .filter(Document.entity_id.in_(cluster.entity_ids))
            .all()
        )
        max_score = max(
            (d.composite_score or 0.0 for d in docs_in_cluster), default=0.0
        )
        risk_level = "high" if max_score > 0.7 else ("medium" if max_score > 0.4 else "low")

        result.append(GraphClusterOut(
            cluster_id = cluster.cluster_id,
            entity_ids = cluster.entity_ids,
            size       = cluster.size,
            risk_level = risk_level,
        ))

    return result


# ---------------------------------------------------------------------------
# POST /documents/{document_id}/rescan
# ---------------------------------------------------------------------------

@router.post(
    "/documents/{document_id}/rescan",
    response_model=RescanOut,
    summary="Relancer le scoring complet d'un document existant",
)
def rescan_document(document_id: str, db: Session = Depends(get_db)) -> RescanOut:
    """
    Relit le document depuis la base, relance le pipeline de scoring complet,
    et met à jour les scores persistés.
    """
    doc = db.query(Document).filter(Document.document_id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id!r} introuvable.",
        )

    file_meta = doc.file_metadata or {}
    historical = _get_entity_historical_amounts(doc.entity_id, db)

    # Reconstruire les paramètres de scoring depuis les métadonnées
    montant           = float(file_meta.get("montant", 0.0))
    nb_transactions   = int(file_meta.get("nb_transactions", 1))
    activite_declaree = float(file_meta.get("activite_declaree", 1.0))
    declared_date_raw = file_meta.get("declared_date") or doc.submitted_date.isoformat()

    try:
        from .integrity import _parse_dt
        declared_date = _parse_dt(declared_date_raw) or doc.submitted_date
    except Exception:
        declared_date = doc.submitted_date

    cs = score_document(
        entity_id         = doc.entity_id,
        file_metadata     = file_meta,
        declared_date     = declared_date,
        montant           = montant,
        nb_transactions   = nb_transactions,
        activite_declaree = activite_declaree,
        historical_amounts= historical,
        document_id       = document_id,
        submitted_date    = doc.submitted_date,
    )
    cs.gnn_anomaly_score = gnn_anomaly_score(doc.entity_id)

    _persist_composite_score(cs, file_meta, db)

    logger.info("Document %s re-scanné.", document_id)
    return RescanOut(
        document_id = document_id,
        new_score   = _composite_to_score_out(cs),
    )


# ---------------------------------------------------------------------------
# Fonction Python pure — pour l'agent d'investigation (Pipeline 3)
# ---------------------------------------------------------------------------

def check_document_integrity(entity_id: str) -> dict:
    """
    Retourne le détail structuré du dernier score composite de l'entité.

    Utilisée directement par les autres pipelines (pas d'HTTP).
    Crée sa propre session SQLAlchemy.

    Retourne un dict vide si l'entité n'a aucun document.
    """
    from .database import SessionLocal

    db  = SessionLocal()
    try:
        doc = (
            db.query(Document)
            .filter(Document.entity_id == entity_id)
            .order_by(Document.submitted_date.desc())
            .first()
        )
        if not doc:
            return {}

        score_out = _orm_document_to_score_out(doc)
        return score_out.model_dump(mode="json")
    except Exception as exc:
        logger.error(
            "check_document_integrity: erreur pour entity_id=%s : %s", entity_id, exc
        )
        return {}
    finally:
        db.close()
