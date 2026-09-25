"""
pipeline2/scoring.py
F2.5 — Orchestrateur du score composite.

Formule :
    composite = 0.4 × integrity + 0.4 × coherence + 0.2 × (1 − 0.25 × nb_risk_flags)

Contrainte d'explicabilité :
  Retourne TOUJOURS un objet structuré avec les 3 sous-scores ET leurs
  explications. Jamais uniquement le chiffre global.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from .anomaly    import coherence_score, CoherenceScoreResult
from .integrity  import check_integrity, IntegrityResult
from .risk_rules import evaluate_risk, RiskResult

logger = logging.getLogger(__name__)

# Poids du score composite
W_INTEGRITY  = 0.4
W_COHERENCE  = 0.4
W_RISK       = 0.2

FORMULA_DESCRIPTION = (
    "composite = 0.4×integrity + 0.4×coherence + 0.2×(1 − 0.25×nb_risk_flags)"
)


# ---------------------------------------------------------------------------
# Résultat complet (indépendant de Pydantic pour pouvoir être utilisé
# par d'autres modules Python sans dépendance FastAPI)
# ---------------------------------------------------------------------------

@dataclass
class CompositeScore:
    """
    Score composite avec décomposition explicite de chaque axe.
    Cet objet est ce qui est persisté en base et renvoyé par l'API.
    """
    document_id     : str
    entity_id       : str
    submitted_date  : datetime

    integrity        : IntegrityResult
    coherence        : CoherenceScoreResult
    risk             : RiskResult

    composite_score  : float
    formula_used     : str = FORMULA_DESCRIPTION

    # GNN (optionnel, enrichissement post-scoring)
    gnn_anomaly_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id"      : self.document_id,
            "entity_id"        : self.entity_id,
            "submitted_date"   : self.submitted_date.isoformat(),
            "integrity"        : self.integrity.to_dict(),
            "coherence"        : self.coherence.to_dict(),
            "risk"             : self.risk.to_dict(),
            "composite_score"  : self.composite_score,
            "formula_used"     : self.formula_used,
            "gnn_anomaly_score": self.gnn_anomaly_score,
        }


# ---------------------------------------------------------------------------
# Calcul du score composite
# ---------------------------------------------------------------------------

def _compute_composite(
    integrity_score: float,
    coherence_score_val: float,
    nb_risk_flags: int,
) -> float:
    """
    Applique la formule pondérée et borne le résultat dans [0, 1].
    Convention : 0 = sain, 1 = très suspect.
    (integrity et coherence sont des scores de CONFIANCE [0→1=ok],
     on les inverse pour que composite soit un score de RISQUE.)
    """
    risk_component = max(0.0, 1.0 - 0.25 * nb_risk_flags)

    # Les scores integrity/coherence sont des scores de confiance :
    # 1 = sain → contribution faible au risque
    # On calcule le composite comme score de RISQUE :
    #   plus integrity et coherence sont bas, plus le risque monte
    raw = (
        W_INTEGRITY * (1.0 - integrity_score)
        + W_COHERENCE  * (1.0 - coherence_score_val)
        + W_RISK       * (1.0 - risk_component)
    )
    return round(max(0.0, min(1.0, raw)), 4)


# ---------------------------------------------------------------------------
# Fonction principale d'orchestration
# ---------------------------------------------------------------------------

def score_document(
    entity_id         : str,
    file_metadata     : Dict[str, Any],
    declared_date     : datetime,
    montant           : float,
    nb_transactions   : int,
    activite_declaree : float,
    historical_amounts: Sequence[float],
    document_id       : Optional[str] = None,
    submitted_date    : Optional[datetime] = None,
) -> CompositeScore:
    """
    Orchestre les 3 axes de scoring pour un document.

    Paramètres
    ----------
    entity_id          : ID de l'entité fiscale.
    file_metadata      : dict {created_at, modified_at, producer, filename}.
    declared_date      : date officielle de déclaration.
    montant            : montant déclaré (MAD).
    nb_transactions    : nombre de transactions dans la période.
    activite_declaree  : CA/activité déclarée (MAD).
    historical_amounts : historique des montants de l'entité (incluant le courant).
    document_id        : UUID str (généré si absent).
    submitted_date     : horodatage de soumission (UTC now si absent).

    Retourne
    --------
    CompositeScore avec tous les sous-scores et leurs explications.
    """
    doc_id  = document_id  or str(uuid.uuid4())
    sub_dt  = submitted_date or datetime.utcnow()

    # --- F2.2 : Intégrité ---
    integrity_result = check_integrity(file_metadata, declared_date)
    logger.debug("F2.2 integrity score=%.4f flags=%s", integrity_result.score, integrity_result.flags)

    # --- F2.3 : Cohérence (Isolation Forest) ---
    coherence_result = coherence_score(
        montant           = montant,
        nb_transactions   = nb_transactions,
        activite_declaree = activite_declaree,
        historical_amounts= historical_amounts,
    )
    logger.debug("F2.3 coherence score=%.4f raw=%.6f", coherence_result.score, coherence_result.raw_if_score or 0)

    # --- F2.4 : Règles de risque ---
    risk_result = evaluate_risk(
        entity_id       = entity_id,
        entity_montants = list(historical_amounts),
    )
    logger.debug("F2.4 risk flags=%s", risk_result.flags)

    # --- F2.5 : Score composite ---
    composite = _compute_composite(
        integrity_score     = integrity_result.score,
        coherence_score_val = coherence_result.score,
        nb_risk_flags       = risk_result.nb_flags,
    )

    logger.info(
        "Scoring document %s entity=%s → composite=%.4f",
        doc_id, entity_id, composite,
    )

    return CompositeScore(
        document_id    = doc_id,
        entity_id      = entity_id,
        submitted_date = sub_dt,
        integrity      = integrity_result,
        coherence      = coherence_result,
        risk           = risk_result,
        composite_score= composite,
    )
