"""
Moteur de correspondance floue (F1.3 / F1.4) - RAKABA Pipeline 1

Rapproche un signal public (listing) du registre fiscal via un score
composite : similarite du nom (fuzzy matching, 40%) + correspondance
exacte du telephone (60%, signal le plus fiable).

Regle metier (cahier des charges, section 4.1) :
    score >= 80         -> correspondance fiable, aucune action
    40 <= score < 80     -> ambigu, signale pour verification humaine
    score < 40           -> aucune correspondance credible, entite creee
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from rapidfuzz import fuzz

NAME_WEIGHT = 0.40
PHONE_WEIGHT = 0.60

RELIABLE_THRESHOLD = 80
AMBIGUOUS_THRESHOLD = 40


class MatchInterpretation(str, Enum):
    RELIABLE = "correspondance_fiable"
    AMBIGUOUS = "ambigu"
    NO_MATCH = "aucune_correspondance_credible"


class MatchAction(str, Enum):
    NO_ACTION = "aucune_action_deja_enregistre"
    FLAG_FOR_REVIEW = "signale_pour_verification_humaine"
    CREATE_ENTITY = "entite_creee_statut_detecte"


@dataclass(frozen=True)
class MatchResult:
    listing_id: str
    matricule_fiscal: str
    name_score: float
    phone_score: float
    composite_score: float
    interpretation: MatchInterpretation
    action: MatchAction


def normalize_phone(phone: str) -> str:
    """Keep digits only so formatting differences (spaces, +216, dashes) don't break exact match."""
    digits = re.sub(r"\D", "", phone or "")
    return digits[-8:] if len(digits) >= 8 else digits


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def score_name_similarity(listing_name: str, registered_name: str) -> float:
    """Fuzzy name similarity, 0-100, using rapidfuzz's token_sort_ratio
    (robust to word order and minor spelling drift, e.g. 'Café Rima' vs 'Rima Cafe')."""
    return fuzz.token_sort_ratio(normalize_name(listing_name), normalize_name(registered_name))


def score_phone_match(listing_phone: str, registered_phone: str) -> float:
    """Exact match after normalization: 100 if same number, 0 otherwise."""
    a, b = normalize_phone(listing_phone), normalize_phone(registered_phone)
    if not a or not b:
        return 0.0
    return 100.0 if a == b else 0.0


def compute_composite_score(name_score: float, phone_score: float) -> float:
    return round(NAME_WEIGHT * name_score + PHONE_WEIGHT * phone_score, 2)


def interpret_score(composite_score: float) -> tuple[MatchInterpretation, MatchAction]:
    if composite_score >= RELIABLE_THRESHOLD:
        return MatchInterpretation.RELIABLE, MatchAction.NO_ACTION
    if composite_score >= AMBIGUOUS_THRESHOLD:
        return MatchInterpretation.AMBIGUOUS, MatchAction.FLAG_FOR_REVIEW
    return MatchInterpretation.NO_MATCH, MatchAction.CREATE_ENTITY


def match_listing_to_registry_entry(
    listing_id: str,
    listing_name: str,
    listing_phone: str,
    matricule_fiscal: str,
    registered_name: str,
    registered_phone: str,
) -> MatchResult:
    name_score = score_name_similarity(listing_name, registered_name)
    phone_score = score_phone_match(listing_phone, registered_phone)
    composite = compute_composite_score(name_score, phone_score)
    interpretation, action = interpret_score(composite)
    return MatchResult(
        listing_id=listing_id,
        matricule_fiscal=matricule_fiscal,
        name_score=round(name_score, 2),
        phone_score=phone_score,
        composite_score=composite,
        interpretation=interpretation,
        action=action,
    )


def find_best_match(
    listing_id: str,
    listing_name: str,
    listing_phone: str,
    registry: list[dict],
) -> MatchResult | None:
    """Compare one listing against every registry entry, return the best-scoring match.

    `registry` entries are dicts with keys: matricule_fiscal, registered_name, phone.
    Returns None if the registry is empty.
    """
    best: MatchResult | None = None
    for entry in registry:
        result = match_listing_to_registry_entry(
            listing_id=listing_id,
            listing_name=listing_name,
            listing_phone=listing_phone,
            matricule_fiscal=entry["matricule_fiscal"],
            registered_name=entry["registered_name"],
            registered_phone=entry["phone"],
        )
        if best is None or result.composite_score > best.composite_score:
            best = result
    return best
