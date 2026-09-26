import duckdb

from pipeline2.router import _find_document_candidates


def _make_conn():
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE taxpayer_lifecycle (entity_id VARCHAR, listing_id VARCHAR)")
    conn.execute(
        "CREATE TABLE listings (listing_id VARCHAR, business_name VARCHAR, location_text VARCHAR, phone VARCHAR)"
    )
    return conn


def test_document_intake_suggests_business_by_filename_without_exposing_internal_reference():
    conn = _make_conn()
    conn.execute("INSERT INTO taxpayer_lifecycle VALUES ('internal-1', 'listing-1')")
    conn.execute("INSERT INTO listings VALUES ('listing-1', 'Atelier Nour', 'Tunis', '20123456')")

    candidates = _find_document_candidates(conn, "facture_atelier_nour.pdf", "")

    assert candidates[0]["business_name"] == "Atelier Nour"
    assert candidates[0]["confidence"] >= 0.8
    assert "matricule" not in candidates[0]


def test_document_intake_matches_on_phone_when_business_name_is_a_generic_label():
    """Informal/unregistered sellers get a generic category label as their business_name
    (see pipeline1/data_generator.py _UNKNOWN_BUSINESS_NAMES), so it will never appear
    verbatim on a real invoice. The phone number printed on the invoice should still let
    the document be matched to the right dossier."""
    conn = _make_conn()
    conn.execute("INSERT INTO taxpayer_lifecycle VALUES ('internal-1', 'listing-1')")
    conn.execute("INSERT INTO listings VALUES ('listing-1', 'Vente Vetements en Ligne', 'Sfax', '+216 20 12 34 56')")

    ocr_text = "FACTURE\nTel: 20-12-34-56\nMontant: 150 DT"
    candidates = _find_document_candidates(conn, "facture-resized.webp", ocr_text)

    assert len(candidates) == 1
    assert candidates[0]["business_name"] == "Vente Vetements en Ligne"
    assert candidates[0]["matched_on"] == ["telephone"]
    assert candidates[0]["confidence"] >= 0.8


def test_document_intake_falls_back_to_fuzzy_name_similarity():
    conn = _make_conn()
    conn.execute("INSERT INTO taxpayer_lifecycle VALUES ('internal-1', 'listing-1')")
    conn.execute("INSERT INTO listings VALUES ('listing-1', 'Pressing Rapide', 'Sousse', '20000000')")

    # OCR-mangled spelling (no substring containment either way) and an unrelated phone:
    # no exact token match, no phone match, but close enough to be useful.
    candidates = _find_document_candidates(conn, "facture.jpg", "pres5ing rapid3 - Sousse")

    assert len(candidates) == 1
    assert candidates[0]["matched_on"] == ["similarite_nom"]
    assert candidates[0]["confidence"] < 0.8


def test_document_intake_returns_no_candidate_when_nothing_matches():
    conn = _make_conn()
    conn.execute("INSERT INTO taxpayer_lifecycle VALUES ('internal-1', 'listing-1')")
    conn.execute("INSERT INTO listings VALUES ('listing-1', 'Vente Vetements en Ligne', 'Sfax', '20123456')")

    candidates = _find_document_candidates(conn, "IMG_0001.webp", "totalement sans rapport")

    assert candidates == []
