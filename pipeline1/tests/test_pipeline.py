import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from pipeline1 import db, entity_linking, pipeline
from pipeline1.data_generator import SyntheticListing
from pipeline1.matching_engine import MatchAction


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    pipeline.ensure_registry_seeded(connection)
    yield connection
    connection.close()


def _listing(listing_id, name, phone, address="Rue Test, Tunis") -> SyntheticListing:
    return SyntheticListing(
        listing_id=listing_id, business_name=name, phone=phone, location_text=address,
        activity_description="Test", source_platform="Test", detected_date=datetime.now(),
        scenario="TEST",
    )


def test_reliable_match_creates_no_entity(conn):
    result = pipeline.process_new_listing(
        conn, _listing("L-R1", "Boutique Amira Mode", "22345678"),
    )
    assert result["created"] is False
    assert result["match"].action == MatchAction.NO_ACTION
    assert conn.execute("SELECT count(*) FROM taxpayer_lifecycle").fetchone()[0] == 0


def test_ambiguous_match_creates_flagged_entity(conn):
    result = pipeline.process_new_listing(
        conn, _listing("L-A1", "Vente Rapide Inconnue", "22345678"),  # phone of Boutique Amira Mode
    )
    assert result["created"] is True
    assert "verification humaine" in conn.execute(
        "SELECT notes FROM taxpayer_lifecycle WHERE entity_id = ?", [result["entity_id"]]
    ).fetchone()[0]


def test_unknown_listing_creates_detected_entity(conn):
    result = pipeline.process_new_listing(
        conn, _listing("L-U1", "Business Totalement Inconnu", "11119999"),
    )
    assert result["created"] is True
    assert result["status"] == pipeline.STATUS_DETECTED


def test_run_scrape_cycle_is_deterministic_with_seed(conn):
    summary_a = pipeline.run_scrape_cycle(conn, n=10, seed=7)
    assert summary_a["listings_processed"] == 10
    assert summary_a["entities_created"] > 0

    conn2 = db.get_connection(":memory:")
    pipeline.ensure_registry_seeded(conn2)
    summary_b = pipeline.run_scrape_cycle(conn2, n=10, seed=7)
    assert summary_a["entities_created"] == summary_b["entities_created"]
    assert summary_a["new_links"] == summary_b["new_links"]
    conn2.close()


def test_entity_linking_groups_shared_phone(conn):
    pipeline.process_new_listing(conn, _listing("L-G1", "Enseigne Un", "33334444", address="Rue A, Tunis"))
    pipeline.process_new_listing(conn, _listing("L-G2", "Enseigne Deux", "33334444", address="Rue B, Sfax"))
    pipeline.process_new_listing(conn, _listing("L-G3", "Enseigne Trois", "55556666", address="Rue C, Sousse"))

    new_links = entity_linking.refresh_entity_links(conn)
    assert len(new_links) == 1
    assert new_links[0]["shared_attribute"] == "phone"

    # idempotent: calling again finds nothing new
    assert entity_linking.refresh_entity_links(conn) == []


def test_get_related_entities_returns_linked_partners(conn):
    r1 = pipeline.process_new_listing(conn, _listing("L-H1", "Enseigne A", "77778888"))
    r2 = pipeline.process_new_listing(conn, _listing("L-H2", "Enseigne B", "77778888"))
    entity_linking.refresh_entity_links(conn)

    related = entity_linking.get_related_entities(conn, r1["entity_id"])
    assert len(related) == 1
    assert related[0]["entity_id"] == r2["entity_id"]


def test_force_transition_updates_status_and_logs(conn):
    result = pipeline.process_new_listing(conn, _listing("L-F1", "Cas Force", "12121212"))
    pipeline.force_transition(conn, result["entity_id"], pipeline.STATUS_CONTACTED, note="Contact manuel par Amira")

    row = conn.execute(
        "SELECT status, notes FROM taxpayer_lifecycle WHERE entity_id = ?", [result["entity_id"]]
    ).fetchone()
    assert row[0] == pipeline.STATUS_CONTACTED
    assert row[1] == "Contact manuel par Amira"

    log_entry = conn.execute(
        "SELECT triggered_by FROM automation_log WHERE entity_id = ? ORDER BY timestamp DESC LIMIT 1",
        [result["entity_id"]],
    ).fetchone()
    assert log_entry[0] == "human"


def test_force_transition_rejects_unknown_status(conn):
    result = pipeline.process_new_listing(conn, _listing("L-F2", "Cas Invalide", "34343434"))
    with pytest.raises(ValueError):
        pipeline.force_transition(conn, result["entity_id"], "Statut Inexistant")
