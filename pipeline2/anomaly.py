"""
pipeline2/anomaly.py
F2.3 — Détection d'anomalies par Isolation Forest (scikit-learn).

Features par document :
  1. montant_norm              — montant normalisé par l'activité déclarée
  2. ecart_montant_historique  — écart relatif au montant moyen historique de l'entité
  3. nb_transactions           — nombre de transactions dans la période
  4. ratio_montant_activite    — montant / activité déclarée

Paramètres fixes pour reproductibilité :
  contamination = 0.08
  random_state  = 42

Le modèle est entraîné une fois au démarrage (`train_isolation_forest`)
puis réutilisé en inférence (`coherence_score`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler

logger = logging.getLogger(__name__)

# Paramètres Isolation Forest
IF_CONTAMINATION  = 0.08
IF_RANDOM_STATE   = 42
IF_N_ESTIMATORS   = 100

# Singleton du modèle entraîné (+ scaler)
_model  : Optional[IsolationForest] = None
_scaler : Optional[MinMaxScaler]    = None

# Cache des scores bruts observés lors de l'entraînement
# (pour normaliser les scores d'inférence dans la même plage)
_train_score_min: float = -1.0
_train_score_max: float =  1.0


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def build_feature_vector(
    montant: float,
    nb_transactions: int,
    activite_declaree: float,
    historical_amounts: Sequence[float],
) -> np.ndarray:
    """
    Construit le vecteur de features [4 dimensions] d'un document.

    Paramètres
    ----------
    montant           : montant déclaré (MAD)
    nb_transactions   : nombre de transactions
    activite_declaree : CA/activité déclarée (MAD), doit être > 0
    historical_amounts: liste des montants passés de la même entité

    Retourne un ndarray shape (4,).
    """
    # Évite la division par zéro
    activite_safe = max(activite_declaree, 1.0)

    # Feature 1 : montant normalisé par l'activité
    montant_norm = montant / activite_safe

    # Feature 2 : écart relatif au montant historique moyen
    if historical_amounts:
        hist_mean = float(np.mean(historical_amounts))
        ecart = (montant - hist_mean) / max(hist_mean, 1.0)
    else:
        ecart = 0.0

    # Feature 3 : nombre de transactions (brut, l'IF normalise)
    nb_tx = float(nb_transactions)

    # Feature 4 : ratio montant / activité (redondant mais capte le rapport direct)
    ratio = montant / activite_safe

    return np.array([montant_norm, ecart, nb_tx, ratio], dtype=np.float64)


# ---------------------------------------------------------------------------
# Entraînement (appelé une fois au démarrage / seed)
# ---------------------------------------------------------------------------

def train_isolation_forest(
    documents: List[Dict[str, Any]],
    historical_lookup: Dict[str, List[float]],
) -> None:
    """
    Entraîne l'Isolation Forest sur le corpus fourni.
    Met à jour les singletons `_model` et `_scaler`.

    Paramètres
    ----------
    documents        : liste de dicts avec clés montant, nb_transactions,
                       activite_declaree, entity_id.
    historical_lookup: {entity_id: [montants historiques]}.

    Si le corpus est vide ou insuffisant, l'entraînement est annulé
    (le modèle reste None → inférence retournera 0.5 par défaut).
    """
    global _model, _scaler, _train_score_min, _train_score_max

    if len(documents) < 10:
        logger.warning(
            "F2.3: corpus trop petit (%d docs). Isolation Forest non entraîné.",
            len(documents),
        )
        return

    # Construire la matrice de features
    X_rows = []
    for doc in documents:
        hist = historical_lookup.get(doc.get("entity_id", ""), [])
        vec  = build_feature_vector(
            montant           = float(doc.get("montant", 0)),
            nb_transactions   = int(doc.get("nb_transactions", 1)),
            activite_declaree = float(doc.get("activite_declaree", 1)),
            historical_amounts= hist,
        )
        X_rows.append(vec)

    X = np.vstack(X_rows)

    # Normalisation MinMax (pour stabiliser l'IF)
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X)

    # Entraînement
    model = IsolationForest(
        n_estimators   = IF_N_ESTIMATORS,
        contamination  = IF_CONTAMINATION,
        random_state   = IF_RANDOM_STATE,
        n_jobs         = -1,
    )
    model.fit(X_scaled)

    # Calibrer la plage de normalisation sur les scores d'entraînement
    raw_scores = model.decision_function(X_scaled)
    _train_score_min = float(raw_scores.min())
    _train_score_max = float(raw_scores.max())

    _model  = model
    _scaler = scaler

    logger.info(
        "F2.3: Isolation Forest entraîné sur %d documents. "
        "Score range: [%.4f, %.4f]",
        len(documents), _train_score_min, _train_score_max,
    )


# ---------------------------------------------------------------------------
# Inférence
# ---------------------------------------------------------------------------

def coherence_score(
    montant: float,
    nb_transactions: int,
    activite_declaree: float,
    historical_amounts: Sequence[float],
) -> "CoherenceScoreResult":
    """
    Calcule le score de cohérence [0, 1] pour un document.

    Convention : 1.0 = parfaitement cohérent, 0.0 = très anormal.
    (L'Isolation Forest donne un score négatif pour les outliers,
     on l'inverse et normalise.)

    Si le modèle n'est pas entraîné, retourne 0.5 (neutre) avec explication.
    """
    if _model is None or _scaler is None:
        return CoherenceScoreResult(
            score        = 0.5,
            raw_if_score = None,
            explanation  = "Modèle Isolation Forest non disponible — score neutre appliqué.",
        )

    vec      = build_feature_vector(montant, nb_transactions, activite_declaree, historical_amounts)
    vec_2d   = vec.reshape(1, -1)
    vec_scaled = _scaler.transform(vec_2d)

    raw = float(_model.decision_function(vec_scaled)[0])

    # Normalisation vers [0, 1] :
    #   decision_function retourne des valeurs > 0 pour les inliers,
    #   < 0 pour les outliers.
    #   On mappe [score_min, score_max] → [0, 1] PUIS on inverse
    #   (score bas = anomalie).
    score_range = _train_score_max - _train_score_min
    if score_range < 1e-9:
        normalized = 0.5
    else:
        normalized = (raw - _train_score_min) / score_range

    # Inversion : 1 = sain, 0 = anormal
    coherence = float(np.clip(normalized, 0.0, 1.0))

    if coherence < 0.3:
        explanation = "Document fortement anormal selon l'Isolation Forest."
    elif coherence < 0.6:
        explanation = "Document légèrement déviant de la norme."
    else:
        explanation = "Document cohérent avec l'historique de l'entité."

    return CoherenceScoreResult(
        score        = round(coherence, 4),
        raw_if_score = round(raw, 6),
        explanation  = explanation,
    )


@dataclass
class CoherenceScoreResult:
    """Résultat de cohérence avec explication."""
    score        : float
    raw_if_score : Optional[float]
    explanation  : str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score"        : self.score,
            "raw_if_score" : self.raw_if_score,
            "explanation"  : self.explanation,
        }


def is_model_ready() -> bool:
    """Indique si l'Isolation Forest est entraîné et prêt."""
    return _model is not None and _scaler is not None
