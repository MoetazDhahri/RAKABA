"""
pipeline2/risk_rules.py
F2.4 — Règles de schéma à risque (logique explicite, SANS ML).

Règles implémentées :
  1. clustering_montants_ronds : >50% des montants de l'entité sont
     des multiples de 1000 → fraude à la déclaration simplifiée.
  2. transactions_avec_entite_liee : l'entité a des transactions avec
     une entité du même cluster (fraude coordonnée).

La fonction `has_linked_transactions` est importée depuis un module
externe (`entity_links`). En cas d'indisponibilité du module,
le flag est simplement ignoré (graceful degradation).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

logger = logging.getLogger(__name__)

# Seuil : proportion minimale de montants ronds pour lever le flag
ROUND_AMOUNT_THRESHOLD = 0.50

# Multiple de référence pour "montant rond suspect"
ROUND_MULTIPLE = 1000.0


# ---------------------------------------------------------------------------
# Import découplé du module externe entity_links
# ---------------------------------------------------------------------------

def _load_has_linked_transactions():
    """
    Tente d'importer has_linked_transactions depuis le module partagé.
    Retourne une lambda `None` en cas d'échec → flag ignoré.
    """
    try:
        from entity_links import has_linked_transactions  # module Pipeline 1 / partagé
        return has_linked_transactions
    except ImportError:
        logger.warning(
            "F2.4: module 'entity_links' introuvable. "
            "Le flag 'transactions_avec_entite_liee' sera désactivé."
        )
        return lambda entity_id: False  # dégradation gracieuse


_has_linked_transactions = _load_has_linked_transactions()


# ---------------------------------------------------------------------------
# Résultat structuré
# ---------------------------------------------------------------------------

@dataclass
class RiskResult:
    """
    Résultat des règles de risque avec liste des flags déclenchés.
    Jamais un score seul : les flags sont toujours visibles.
    """
    flags      : List[str] = field(default_factory=list)
    risk_score : float = 0.0   # composante risque normalisée [0, 1]

    @property
    def nb_flags(self) -> int:
        return len(self.flags)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flags"      : self.flags,
            "nb_flags"   : self.nb_flags,
            "risk_score" : self.risk_score,
        }


# ---------------------------------------------------------------------------
# Règle 1 : montants ronds suspects
# ---------------------------------------------------------------------------

def _is_round_amount(montant: float, multiple: float = ROUND_MULTIPLE) -> bool:
    """Retourne True si `montant` est un multiple exact de `multiple`."""
    if multiple <= 0:
        return False
    return abs(montant % multiple) < 1e-6


def check_round_amounts(
    entity_montants: Sequence[float],
) -> bool:
    """
    Retourne True si plus de ROUND_AMOUNT_THRESHOLD (50%) des montants
    de l'entité sont des multiples de 1000.

    Paramètres
    ----------
    entity_montants : historique complet des montants déclarés par l'entité.
    """
    if not entity_montants:
        return False

    n_round = sum(1 for m in entity_montants if _is_round_amount(m))
    proportion = n_round / len(entity_montants)
    return proportion > ROUND_AMOUNT_THRESHOLD


# ---------------------------------------------------------------------------
# Règle 2 : transactions avec entité liée (même cluster)
# ---------------------------------------------------------------------------

def check_linked_entity_transactions(entity_id: str) -> bool:
    """
    Vérifie si l'entité a des transactions avec une entité du même cluster.
    Délègue à `has_linked_transactions` du module externe.
    """
    try:
        return bool(_has_linked_transactions(entity_id))
    except Exception as exc:
        logger.warning(
            "F2.4: erreur lors de la vérification des liens pour %s : %s",
            entity_id, exc,
        )
        return False


# ---------------------------------------------------------------------------
# Fonction principale
# ---------------------------------------------------------------------------

def evaluate_risk(
    entity_id: str,
    entity_montants: Sequence[float],
) -> RiskResult:
    """
    Évalue les règles de risque pour un document/entité donnée.

    Paramètres
    ----------
    entity_id       : identifiant de l'entité fiscale.
    entity_montants : historique des montants de l'entité (inclut le document courant).

    Retourne
    --------
    RiskResult avec flags et risk_score.

    Score risque = nb_flags (non plafonné ; la formule composite
    dans scoring.py applique 0.25 × nb_flags, max utile ≈ 4 flags).
    """
    flags: List[str] = []

    # --- Règle 1 ---
    if check_round_amounts(entity_montants):
        flags.append("clustering_montants_ronds")

    # --- Règle 2 ---
    if check_linked_entity_transactions(entity_id):
        flags.append("transactions_avec_entite_liee")

    # risk_score brut = nombre de flags (utilisé par scoring.py)
    return RiskResult(flags=flags, risk_score=float(len(flags)))
