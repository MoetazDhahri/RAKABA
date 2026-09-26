"""
pipeline2/schemas.py
Schémas Pydantic pour la Pipeline 2 — Vérifier.

Principes :
  - Chaque score est toujours accompagné de son explication (flags, détail).
  - Aucun chiffre global sans justification — exigence d'explicabilité.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums partagés
# ---------------------------------------------------------------------------

class EdgeTypeEnum(str, Enum):
    phone        = "phone"
    address      = "address"
    bank_account = "bank_account"


# ---------------------------------------------------------------------------
# Input : soumission d'un document
# ---------------------------------------------------------------------------

class FileMetadataIn(BaseModel):
    """Métadonnées extraites du fichier (PDF, XML…)."""
    created_at  : datetime
    modified_at : datetime
    producer    : Optional[str] = None   # ex. "LibreOffice 7.x"
    filename    : str


class DocumentIn(BaseModel):
    """Payload reçu à POST /documents/upload."""
    entity_id     : str = Field(..., description="Identifiant de l'entité fiscale (taxpayer_lifecycle FK)")
    file_metadata : FileMetadataIn
    # Données financières nécessaires aux features ML
    montant             : float = Field(..., ge=0, description="Montant déclaré (MAD)")
    nb_transactions     : int   = Field(..., ge=0, description="Nombre de transactions dans la période")
    activite_declaree   : float = Field(..., ge=0, description="CA/activité déclarée (MAD)")
    declared_date       : datetime = Field(..., description="Date de déclaration officielle")


# ---------------------------------------------------------------------------
# Sous-scores avec explications
# ---------------------------------------------------------------------------

class IntegrityDetail(BaseModel):
    """Résultat détaillé de F2.2."""
    score : float = Field(..., ge=0.0, le=1.0)
    flags : List[str] = Field(default_factory=list, description="Flags déclenchés (explicabilité)")


class CoherenceDetail(BaseModel):
    """Résultat détaillé de F2.3 (Isolation Forest)."""
    score         : float = Field(..., ge=0.0, le=1.0)
    raw_if_score  : Optional[float] = Field(None, description="Score brut decision_function avant normalisation")
    explanation   : str   = Field("", description="Texte court expliquant le score")


class RiskDetail(BaseModel):
    """Résultat détaillé de F2.4."""
    flags      : List[str] = Field(default_factory=list, description="Règles déclenchées")
    nb_flags   : int       = Field(0, ge=0)
    # Non plafonné par construction (risk_rules.evaluate_risk documente ce champ
    # comme = nb_flags brut) : scoring.py applique 0.25×nb_flags (capé à 1.0)
    # au moment du calcul du score composite, pas ici.
    risk_score : float     = Field(..., ge=0.0, description="Nombre de règles de risque déclenchées (brut, non normalisé)")


# ---------------------------------------------------------------------------
# Output principal : score composite
# ---------------------------------------------------------------------------

class ScoreOut(BaseModel):
    """
    Réponse complète après scoring d'un document.
    Chaque axe est explicité — jamais uniquement le chiffre global.
    """
    document_id     : str
    entity_id       : str
    submitted_date  : datetime

    # Scores par axe
    integrity  : IntegrityDetail
    coherence  : CoherenceDetail
    risk       : RiskDetail

    # Score composite
    composite_score : float = Field(..., ge=0.0, le=1.0,
                                    description="0 = sain, 1 = très suspect")
    formula_used    : str   = Field(
        "0.4×integrity + 0.4×coherence + 0.2×(1 − 0.25×nb_risk_flags)",
        description="Formule appliquée pour le score composite"
    )

    # GNN (optionnel)
    gnn_anomaly_score : Optional[float] = Field(
        None, description="Score GNN si disponible, None sinon"
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Graph schemas
# ---------------------------------------------------------------------------

class GraphNodeOut(BaseModel):
    node_id           : str
    feature_vector    : List[float] = Field(default_factory=list)
    gnn_anomaly_score : Optional[float] = None

    model_config = {"from_attributes": True}


class GraphEdgeOut(BaseModel):
    edge_id   : str
    node_a    : str
    node_b    : str
    edge_type : EdgeTypeEnum
    weight    : float

    model_config = {"from_attributes": True}


class GraphClusterOut(BaseModel):
    """Un cluster = composante connexe du graphe."""
    cluster_id  : int
    entity_ids  : List[str]
    size        : int
    risk_level  : str = Field(
        "", description="'high' si au moins un nœud a composite_score > 0.7"
    )


class EntityGraphOut(BaseModel):
    """Sous-graphe autour d'une entité donnée."""
    entity_id : str
    nodes     : List[GraphNodeOut]
    edges     : List[GraphEdgeOut]


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

class RescanOut(BaseModel):
    """Réponse à POST /documents/{document_id}/rescan."""
    document_id : str
    message     : str = "Rescan lancé avec succès."
    new_score   : ScoreOut


class DocumentListOut(BaseModel):
    entity_id   : str
    total       : int
    documents   : List[ScoreOut]
