import duckdb

from pipeline2.router import _find_document_candidates


def test_document_intake_suggests_business_by_filename_without_exposing_internal_reference():
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE taxpayer_lifecycle (entity_id VARCHAR, listing_id VARCHAR)")
    conn.execute("CREATE TABLE listings (listing_id VARCHAR, business_name VARCHAR, location_text VARCHAR)")
    conn.execute("INSERT INTO taxpayer_lifecycle VALUES ('internal-1', 'listing-1')")
    conn.execute("INSERT INTO listings VALUES ('listing-1', 'Atelier Nour', 'Tunis')")

    candidates = _find_document_candidates(conn, "facture_atelier_nour.pdf", "")

    assert candidates[0]["business_name"] == "Atelier Nour"
    assert candidates[0]["confidence"] >= 0.8
    assert "matricule" not in candidates[0]
