"""
Orchestration automatisee - RAKABA Pipeline 1 (F1.4, F1.5, F1.8, X2)

Chaine complete, sans intervention manuelle :
    generer un lot de signaux "scrapes" (F1.1)
    -> les inserer dans DuckDB
    -> les rapprocher du registre fiscal (matching_engine, F1.3)
    -> creer/ignorer l'entite selon le score (F1.4)
    -> faire progresser la machine a etats (F1.5)
    -> relier les entites par telephone/adresse partages (F1.6)
    -> tracer chaque action dans automation_log (traçabilite, section 10)

Amira garde neanmoins un droit de forcage manuel sur toute transition
(F1.8) via `force_transition`.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime

import duckdb

from pipeline1 import db, entity_linking
from pipeline1.data_generator import SyntheticListing, generate_scrape_batch, registry_rows
from pipeline1.matching_engine import MatchAction, find_best_match

# Les 5 etats du cycle de vie (section 4.1)
STATUS_DETECTED = "Detecte"
STATUS_CONTACTED = "Contacte"
STATUS_IN_REGULARIZATION = "En regularisation"
STATUS_COMPLIANT = "Conforme"
STATUS_TRUSTED = "Contribuable de confiance"

LIFECYCLE_ORDER = [
    STATUS_DETECTED,
    STATUS_CONTACTED,
    STATUS_IN_REGULARIZATION,
    STATUS_COMPLIANT,
    STATUS_TRUSTED,
]


def ensure_registry_seeded(conn: duckdb.DuckDBPyConnection) -> None:
    count = conn.execute("SELECT count(*) FROM registry").fetchone()[0]
    if count == 0:
        conn.executemany(
            "INSERT INTO registry VALUES (?, ?, ?, ?, ?)",
            registry_rows(),
        )


def _log(conn: duckdb.DuckDBPyConnection, entity_id: str | None, action_description: str,
          triggered_by: str = "system", pipeline_source: str = "pipeline1") -> None:
    conn.execute(
        "INSERT INTO automation_log VALUES (?, ?, ?, ?, ?, ?)",
        [f"LOG-{uuid.uuid4().hex[:10]}", entity_id, pipeline_source, action_description,
         datetime.now(), triggered_by],
    )


def _load_registry(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    rows = conn.execute(
        "SELECT matricule_fiscal, registered_name, phone FROM registry"
    ).fetchall()
    return [{"matricule_fiscal": r[0], "registered_name": r[1], "phone": r[2]} for r in rows]


def process_new_listing(conn: duckdb.DuckDBPyConnection, listing: SyntheticListing) -> dict:
    """Ingests one signal end-to-end: insert -> match -> create/skip entity -> log.
    Returns a summary dict describing what happened (useful for the Admin UI / tests)."""
    conn.execute(
        "INSERT INTO listings VALUES (?, ?, ?, ?, ?, ?, ?)",
        [listing.listing_id, listing.business_name, listing.phone, listing.location_text,
         listing.activity_description, listing.source_platform, listing.detected_date],
    )

    registry = _load_registry(conn)
    best_match = find_best_match(
        listing_id=listing.listing_id,
        listing_name=listing.business_name,
        listing_phone=listing.phone,
        registry=registry,
    )

    if best_match is not None and best_match.action == MatchAction.NO_ACTION:
        _log(
            conn, None,
            f"Signal '{listing.business_name}' rapproche de {best_match.matricule_fiscal} "
            f"(score {best_match.composite_score}) - deja enregistre, aucune action.",
        )
        return {"listing_id": listing.listing_id, "entity_id": None, "status": None,
                "match": best_match, "created": False}

    entity_id = f"ENT-{uuid.uuid4().hex[:8]}"
    if best_match is not None and best_match.action == MatchAction.FLAG_FOR_REVIEW:
        notes = (f"Correspondance ambigue avec {best_match.matricule_fiscal} "
                 f"(score {best_match.composite_score}) - verification humaine requise.")
        match_score = best_match.composite_score
    else:
        notes = "Aucune correspondance credible dans le registre fiscal."
        match_score = best_match.composite_score if best_match else 0.0

    conn.execute(
        "INSERT INTO taxpayer_lifecycle VALUES (?, ?, ?, ?, ?, ?)",
        [entity_id, listing.listing_id, STATUS_DETECTED, datetime.now(), match_score, notes],
    )
    _log(conn, entity_id, f"Entite creee (statut Detecte) pour le signal '{listing.business_name}'. {notes}")

    return {"listing_id": listing.listing_id, "entity_id": entity_id, "status": STATUS_DETECTED,
            "match": best_match, "created": True}


def ingest_listings(conn: duckdb.DuckDBPyConnection, listings: list[SyntheticListing]) -> dict:
    """Traite un lot de signaux deja generes : insertion -> matching -> creation/skip
    d'entite -> liaison -> log. Ne genere rien elle-meme, contrairement a
    `run_scrape_cycle` - utile quand l'appelant (ex: demo_loop.py) veut controler
    lui-meme la generation du lot a chaque tick."""
    ensure_registry_seeded(conn)
    results = [process_new_listing(conn, listing) for listing in listings]

    new_links = entity_linking.refresh_entity_links(conn)
    for link in new_links:
        _log(
            conn, link["entity_id_a"],
            f"Entites liees par {link['shared_attribute']} partage avec {link['entity_id_b']} "
            f"(score {link['link_score']}).",
        )

    created = [r for r in results if r["created"]]
    return {
        "listings_processed": len(results),
        "entities_created": len(created),
        "auto_registered_no_action": len(results) - len(created),
        "new_links": len(new_links),
        "results": results,
    }


def run_scrape_cycle(conn: duckdb.DuckDBPyConnection, n: int = 12, seed: int | None = None) -> dict:
    """Un cycle complet et automatise : genere un lot de signaux puis les ingere.
    Point d'entree unique pour un run one-shot (CLI, tests)."""
    ensure_registry_seeded(conn)
    batch = generate_scrape_batch(n=n, seed=seed)
    return ingest_listings(conn, batch)


def transition_entity(conn: duckdb.DuckDBPyConnection, entity_id: str, new_status: str,
                       note: str | None = None, triggered_by: str = "system") -> None:
    """Transition generique du cycle de vie (F1.5), tracee avec le veritable
    declencheur : 'system' pour une progression automatique (section 4.3, ou le
    scheduler de demo_loop.py qui simule cette progression), 'human' pour un
    forcage manuel par Amira. `force_transition` est le raccourci reserve a Amira."""
    if new_status not in LIFECYCLE_ORDER:
        raise ValueError(f"Statut inconnu: {new_status}. Attendu un parmi {LIFECYCLE_ORDER}.")

    conn.execute(
        "UPDATE taxpayer_lifecycle SET status = ?, status_updated_at = ?, "
        "notes = COALESCE(?, notes) WHERE entity_id = ?",
        [new_status, datetime.now(), note, entity_id],
    )
    verb = "forcee manuellement" if triggered_by == "human" else "automatique"
    _log(conn, entity_id, f"Transition {verb} vers '{new_status}'."
         + (f" Note: {note}" if note else ""), triggered_by=triggered_by)


def force_transition(conn: duckdb.DuckDBPyConnection, entity_id: str, new_status: str,
                      note: str | None = None) -> None:
    """F1.8 - Amira garde a tout moment un droit de forcage manuel sur n'importe
    quelle transition du cycle de vie, quel que soit l'ordre normal des etats."""
    transition_entity(conn, entity_id, new_status, note=note, triggered_by="human")


def run_automated_flow(db_path=None, cycles: int = 1, listings_per_cycle: int = 12,
                        seed: int | None = None) -> list[dict]:
    """Point d'entree CLI/automatisation : `python -m pipeline1.pipeline`.
    Ouvre (ou cree) la base DuckDB et enchaine N cycles de scraping automatique."""
    conn = db.get_connection(db_path) if db_path else db.get_connection()
    summaries = []
    for i in range(cycles):
        cycle_seed = None if seed is None else seed + i
        summaries.append(run_scrape_cycle(conn, n=listings_per_cycle, seed=cycle_seed))
    conn.close()
    return summaries


if __name__ == "__main__":
    for summary in run_automated_flow(cycles=1, listings_per_cycle=12, seed=42):
        print(
            f"Traites: {summary['listings_processed']} | "
            f"Entites creees: {summary['entities_created']} | "
            f"Deja enregistres: {summary['auto_registered_no_action']} | "
            f"Nouvelles liaisons: {summary['new_links']}"
        )
