import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline1.matching_engine import (
    MatchAction,
    MatchInterpretation,
    find_best_match,
    match_listing_to_registry_entry,
)


def test_reliable_match_exact_phone_and_name():
    result = match_listing_to_registry_entry(
        listing_id="L1",
        listing_name="Boutique Rima",
        listing_phone="+216 22 345 678",
        matricule_fiscal="MF001",
        registered_name="Boutique Rima",
        registered_phone="22345678",
    )
    assert result.composite_score >= 80
    assert result.interpretation == MatchInterpretation.RELIABLE
    assert result.action == MatchAction.NO_ACTION


def test_ambiguous_match_phone_only():
    # Same phone, very different name -> phone contributes 60, name contributes little
    result = match_listing_to_registry_entry(
        listing_id="L2",
        listing_name="Vente en ligne",
        listing_phone="98765432",
        matricule_fiscal="MF002",
        registered_name="Ste Alpha Distribution",
        registered_phone="98765432",
    )
    assert 40 <= result.composite_score < 80
    assert result.interpretation == MatchInterpretation.AMBIGUOUS
    assert result.action == MatchAction.FLAG_FOR_REVIEW


def test_no_credible_match():
    result = match_listing_to_registry_entry(
        listing_id="L3",
        listing_name="Snack Youssef",
        listing_phone="11111111",
        matricule_fiscal="MF003",
        registered_name="Cabinet Comptable Zied",
        registered_phone="22222222",
    )
    assert result.composite_score < 40
    assert result.interpretation == MatchInterpretation.NO_MATCH
    assert result.action == MatchAction.CREATE_ENTITY


def test_phone_normalization_ignores_formatting():
    result = match_listing_to_registry_entry(
        listing_id="L4",
        listing_name="Cafe Le Petit",
        listing_phone="(+216) 20-111-222",
        matricule_fiscal="MF004",
        registered_name="Cafe Le Petit",
        registered_phone="20111222",
    )
    assert result.phone_score == 100.0


def test_find_best_match_picks_highest_score():
    registry = [
        {"matricule_fiscal": "MF010", "registered_name": "Autre Commerce", "phone": "10000000"},
        {"matricule_fiscal": "MF011", "registered_name": "Boutique Rima", "phone": "22345678"},
    ]
    best = find_best_match(
        listing_id="L5",
        listing_name="Boutique Rima Store",
        listing_phone="22345678",
        registry=registry,
    )
    assert best.matricule_fiscal == "MF011"


def test_find_best_match_empty_registry_returns_none():
    assert find_best_match("L6", "X", "00000000", []) is None
