"""
pipeline2/integrity.py
F2.2 — Vérification d'intégrité documentaire (déterministe, SANS ML).

Logique :
  - Flag si modified_at > declared_date  → falsification post-déclaration
  - Flag si created_at != modified_at    → document altéré après création
  - Score = 1.0 - 0.3 × nb_flags, borné [0, 1]

Retourne toujours le score ET la liste des flags (explicabilité garantie).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# Pénalité par flag (configurable sans modifier la logique)
FLAG_PENALTY = 0.3
SCORE_MIN    = 0.0
SCORE_MAX    = 1.0


# ---------------------------------------------------------------------------
# Résultat structuré
# ---------------------------------------------------------------------------

@dataclass
class IntegrityResult:
    """
    Résultat d'intégrité avec score ET explications.
    Jamais un chiffre sans contexte.
    """
    score : float
    flags : List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"score": self.score, "flags": self.flags}


# ---------------------------------------------------------------------------
# Règles de flag
# ---------------------------------------------------------------------------

def _flag_modified_after_declared(
    modified_at: datetime, declared_date: datetime
) -> bool:
    """
    Vrai si le fichier a été modifié APRÈS la date de déclaration officielle.
    Cela suggère une falsification post-dépôt.
    """
    return modified_at > declared_date


def _flag_created_differs_from_modified(
    created_at: datetime, modified_at: datetime
) -> bool:
    """
    Vrai si la date de création diffère de la date de modification.
    Un document original ne devrait pas être réécrit.
    Tolérance : on compare à la seconde près.
    """
    return abs((modified_at - created_at).total_seconds()) > 1.0


# ---------------------------------------------------------------------------
# Fonction principale
# ---------------------------------------------------------------------------

def check_integrity(
    file_metadata: Dict[str, Any],
    declared_date: datetime,
    extra_flags: Optional[List[str]] = None,
) -> IntegrityResult:
    """
    Vérifie l'intégrité d'un document fiscal à partir de ses métadonnées.

    Paramètres
    ----------
    file_metadata : dict
        Doit contenir les clés : 'created_at', 'modified_at' (str ISO ou datetime).
        Pour un fichier réellement uploadé (F2.2 étendu, voir document_forensics.py),
        ces valeurs devraient venir de l'inspection du fichier lui-même
        (ex. métadonnées PDF réelles), pas d'une déclaration de l'appelant.
    declared_date : datetime
        Date officielle de déclaration.
    extra_flags : list[str], optionnel
        Flags déjà déterminés en amont par une analyse du fichier réel (ex.
        `pdf_edited_after_finalization` depuis document_forensics.py) - fusionnés
        tels quels, chacun comptant pour la même pénalité que les flags F2.2
        natifs.

    Retourne
    --------
    IntegrityResult avec score [0,1] et liste de flags.
    """
    flags: List[str] = list(extra_flags or [])

    # --- Parsing des dates (supporte str ISO ou datetime) ---
    created_at  = _parse_dt(file_metadata.get("created_at"))
    modified_at = _parse_dt(file_metadata.get("modified_at"))

    if created_at is None or modified_at is None:
        # Métadonnées manquantes → flag critique
        flags.append("metadata_dates_missing")
        score = max(SCORE_MIN, SCORE_MAX - FLAG_PENALTY * len(flags))
        return IntegrityResult(score=round(score, 4), flags=flags)

    # --- Règle 1 : modification postérieure à la déclaration ---
    if _flag_modified_after_declared(modified_at, declared_date):
        flags.append("modified_after_declared_date")

    # --- Règle 2 : created_at ≠ modified_at ---
    if _flag_created_differs_from_modified(created_at, modified_at):
        flags.append("document_altered_after_creation")

    # --- Calcul du score ---
    raw_score = SCORE_MAX - FLAG_PENALTY * len(flags)
    score     = round(max(SCORE_MIN, min(SCORE_MAX, raw_score)), 4)

    return IntegrityResult(score=score, flags=flags)


# ---------------------------------------------------------------------------
# Utilitaire de parsing
# ---------------------------------------------------------------------------

def _parse_dt(value: Any) -> datetime | None:
    """Convertit une valeur en datetime. Retourne None si impossible."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Supporte les formats ISO 8601 (avec ou sans timezone)
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value[:26], fmt[:len(value[:26])])
            except ValueError:
                continue
        # Fallback stdlib
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00").split("+")[0])
        except ValueError:
            return None
    return None
