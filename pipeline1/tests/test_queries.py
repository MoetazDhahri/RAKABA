import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from pipeline1 import db, pipeline, queries
from pipeline1.data_generator import SyntheticListing


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


def test_kanban_columns_covers_all_statuses_and_places_new_entity(conn):
    pipeline.process_new_listing(conn, _listing("L-Q1", "Nouvelle Entite", "44445555"))

    columns = queries.kanban_columns(conn)
    assert set(columns.keys()) == set(pipeline.LIFECYCLE_ORDER)
    assert len(columns[pipeline.STATUS_DETECTED]) == 1
    assert columns[pipeline.STATUS_DETECTED][0]["business_name"] == "Nouvelle Entite"
    assert columns[pipeline.STATUS_CONTACTED] == []


def test_dashboard_counters_reflect_status_counts(conn):
    r1 = pipeline.process_new_listing(conn, _listing("L-Q2", "Entite Un", "66667777"))
    pipeline.process_new_listing(conn, _listing("L-Q3", "Entite Deux", "88889999"))
    pipeline.force_transition(conn, r1["entity_id"], pipeline.STATUS_IN_REGULARIZATION)

    counters = queries.dashboard_counters(conn)
    assert counters["in_regularization"] == 1
    assert counters["detected_today"] == 1  # only the one still in Detecte
    assert counters["compliant"] == 0


def test_get_entity_detail_includes_history(conn):
    result = pipeline.process_new_listing(conn, _listing("L-Q4", "Entite Detail", "10101010"))
    pipeline.force_transition(conn, result["entity_id"], pipeline.STATUS_CONTACTED, note="Contact initie")

    detail = queries.get_entity_detail(conn, result["entity_id"])
    assert detail["business_name"] == "Entite Detail"
    assert detail["status"] == pipeline.STATUS_CONTACTED
    assert len(detail["history"]) == 2  # creation log + forced transition log
    assert detail["history"][0]["triggered_by"] == "system"
    assert detail["history"][1]["triggered_by"] == "human"


def test_get_entity_detail_unknown_id_returns_none(conn):
    assert queries.get_entity_detail(conn, "ENT-does-not-exist") is None


def test_get_automation_log_orders_most_recent_first(conn):
    pipeline.process_new_listing(conn, _listing("L-Q5", "Entite Log 1", "20202020"))
    pipeline.process_new_listing(conn, _listing("L-Q6", "Entite Log 2", "30303030"))

    log = queries.get_automation_log(conn, limit=10)
    assert len(log) == 2
    assert log[0]["timestamp"] >= log[1]["timestamp"]
