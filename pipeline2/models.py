"""
pipeline2/models.py
ORM SQLAlchemy pour la Pipeline 2 — Vérifier.

Tables :
  - documents          : résultats de scoring par document
  - entity_graph_nodes : nœuds du graphe de relations
  - entity_graph_edges : arêtes du graphe de relations

La base SQLite est partagée avec les Pipelines 1 et 3.
Ce module ne recrée QUE les tables propres à la Pipeline 2.
"""

import json
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, String, Float, DateTime, JSON, ForeignKey,
    Enum, UniqueConstraint, Index
)
from sqlalchemy.orm import declarative_base

# Base partagée : à importer depuis le module racine si elle existe déjà,
# ou redéfinie ici pour l'autonomie de ce module.
Base = declarative_base()


class Document(Base):
    """
    Résultat de scoring d'un document fiscal soumis.
    entity_id est une FK logique vers `taxpayer_lifecycle` (Pipeline 1) ;
    la contrainte FK n'est pas enforced côté SQLite pour rester découplé.
    """
    __tablename__ = "documents"

    document_id     = Column(String, primary_key=True)           # UUID str
    entity_id       = Column(String, nullable=False, index=True)  # FK logique
    file_metadata   = Column(JSON, nullable=False, default=dict)  # {created_at, modified_at, producer, filename}
    integrity_score = Column(Float, nullable=True)                # [0, 1]
    coherence_score = Column(Float, nullable=True)                # [0, 1]
    risk_flags      = Column(JSON, nullable=False, default=list)  # liste de strings
    composite_score = Column(Float, nullable=True)                # [0, 1]
    submitted_date  = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Explicabilité : stocke aussi les sous-explications en JSON
    integrity_flags = Column(JSON, nullable=False, default=list)  # flags F2.2
    risk_score_raw  = Column(Float, nullable=True)                # score risque avant normalisation

    __table_args__ = (
        Index("ix_documents_entity_submitted", "entity_id", "submitted_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<Document id={self.document_id!r} "
            f"entity={self.entity_id!r} composite={self.composite_score}>"
        )


class EdgeType(PyEnum):
    """Types de liens partagés entre entités."""
    phone        = "phone"
    address      = "address"
    bank_account = "bank_account"


class EntityGraphNode(Base):
    """
    Nœud dans le graphe de relations inter-entités.
    node_id == entity_id.
    """
    __tablename__ = "entity_graph_nodes"

    node_id           = Column(String, primary_key=True)   # = entity_id
    feature_vector    = Column(JSON, nullable=False, default=list)  # vecteur numérique sérialisé
    gnn_anomaly_score = Column(Float, nullable=True)       # rempli par F2.7 si dispo

    def __repr__(self) -> str:
        return (
            f"<EntityGraphNode id={self.node_id!r} "
            f"gnn={self.gnn_anomaly_score}>"
        )


class EntityGraphEdge(Base):
    """
    Arête entre deux nœuds du graphe.
    Un lien représente un attribut partagé (téléphone, adresse, compte).
    """
    __tablename__ = "entity_graph_edges"

    edge_id   = Column(String, primary_key=True)  # UUID str
    node_a    = Column(String, ForeignKey("entity_graph_nodes.node_id"), nullable=False, index=True)
    node_b    = Column(String, ForeignKey("entity_graph_nodes.node_id"), nullable=False, index=True)
    edge_type = Column(Enum(EdgeType), nullable=False)
    weight    = Column(Float, nullable=False, default=1.0)

    __table_args__ = (
        UniqueConstraint("node_a", "node_b", "edge_type", name="uq_edge_nodes_type"),
        Index("ix_edge_node_b", "node_b"),
    )

    def __repr__(self) -> str:
        return (
            f"<EntityGraphEdge {self.node_a!r} --[{self.edge_type}]--> "
            f"{self.node_b!r} w={self.weight}>"
        )
