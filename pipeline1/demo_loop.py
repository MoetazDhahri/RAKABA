"""
Ordonnanceur de demo - RAKABA Pipeline 1 (F1.8, X2)

Lance des cycles de "scraping" synthetiques a intervalle regulier, de sorte que
le tableau kanban de l'interface Admin se remplisse ET progresse sous les yeux
du jury pendant la presentation. Pipeline 1 uniquement, donnees synthetiques
(cf. cahier des charges sections 11 / 16 / 19).

A chaque tick :
  1. generate_scrape_batch(...)      -> un lot de signaux synthetiques (F1.1)
  2. ingestion via Pipeline 1        -> matching, creation d'entite, liaison, log
  3. progression de cycle de vie     -> quelques cartes avancent d'un etat (F1.5/F1.8)
  4. affichage des compteurs en direct

Placer ce fichier dans pipeline1/ (a cote de pipeline.py) puis :

    python -m pipeline1.demo_loop --fresh --interval 8 --batch-size 6
    python -m pipeline1.demo_loop --cycles 5 --seed 42        # deterministe
    python -m pipeline1.demo_loop --no-advance                # ingestion seule
    python -m pipeline1.demo_loop --once                      # un seul cycle puis stop
"""
from __future__ import annotations

import argparse
import random
import signal
import sys
import time
from datetime import datetime

import duckdb

from pipeline1 import db, data_generator, queries
from pipeline1.pipeline import LIFECYCLE_ORDER

# --- Point de couplage avec pipeline.py ------------------------------------
# demo_loop pilote ta pipeline.py existante. Ces DEUX fonctions sont le seul
# endroit ou il la touche : si tes noms de fonctions different, corrige ici.
from pipeline1 import pipeline as p1


def _ingest(conn: duckdb.DuckDBPyConnection, listings: list) -> None:
    """Ingere un lot de SyntheticListing (matching + cycle de vie + liaison + log)."""
    p1.ingest_listings(conn, listings)


def _transition(conn: duckdb.DuckDBPyConnection, entity_id: str, new_status: str) -> None:
    """Fait passer une entite a l'etat suivant via la machine a etats (F1.5),
    tracee comme une progression automatique (triggered_by='system')."""
    p1.transition_entity(conn, entity_id, new_status, triggered_by="system")
# ---------------------------------------------------------------------------


_STATUS_INDEX = {status: i for i, status in enumerate(LIFECYCLE_ORDER)}
_TERMINAL_STATUS = LIFECYCLE_ORDER[-1]


def _next_status(status: str) -> str | None:
    """Etat suivant dans l'ordre du cycle de vie, ou None si deja au dernier."""
    i = _STATUS_INDEX.get(status)
    if i is None or i >= len(LIFECYCLE_ORDER) - 1:
        return None
    return LIFECYCLE_ORDER[i + 1]


def seed_registry_if_empty(conn: duckdb.DuckDBPyConnection) -> int:
    """Charge le registre fiscal synthetique (F1.2) s'il est vide - le matching
    en a besoin des le premier cycle."""
    already = conn.execute("SELECT count(*) FROM registry").fetchone()[0]
    if already:
        return 0
    rows = data_generator.registry_rows()
    conn.executemany("INSERT INTO registry VALUES (?, ?, ?, ?, ?)", rows)
    return len(rows)


def advance_lifecycle(conn: duckdb.DuckDBPyConnection, rng: random.Random,
                      max_transitions: int = 3, advance_prob: float = 0.5) -> int:
    """Simule la progression descendante du cycle de vie (Detecte -> ... -> Confiance).

    En demo Pipeline 1 seul, les declencheurs reels (intention detectee par P3,
    controle de completude par P2) ne sont pas branches : on fait donc avancer
    quelques cartes par tick, en passant TOUJOURS par la machine a etats (F1.5),
    pour que le mouvement soit reel et trace, pas peint a l'ecran.
    """
    candidates = []
    for status in LIFECYCLE_ORDER[:-1]:  # tout sauf l'etat terminal
        for entity in queries.list_entities_by_status(conn, status):
            candidates.append(entity)

    rng.shuffle(candidates)
    moved = 0
    for entity in candidates:
        if moved >= max_transitions:
            break
        if rng.random() > advance_prob:
            continue
        nxt = _next_status(entity["status"])
        if nxt is None:
            continue
        _transition(conn, entity["entity_id"], nxt)
        moved += 1
    return moved


def render(conn: duckdb.DuckDBPyConnection, cycle: int, ingested: int, moved: int) -> None:
    """Affiche l'etat du board apres un tick (compteurs + repartition par colonne)."""
    counters = queries.dashboard_counters(conn)
    columns = queries.kanban_columns(conn)
    stamp = datetime.now().strftime("%H:%M:%S")

    print(f"\n[{stamp}] cycle {cycle}  (+{ingested} detectes, {moved} avances)")
    print("  " + " | ".join(f"{status}: {len(cards)}" for status, cards in columns.items()))
    print(f"  detectes aujourd'hui={counters['detected_today']}  "
          f"en regularisation={counters['in_regularization']}  "
          f"conformes={counters['compliant']}")


def run(args: argparse.Namespace) -> None:
    if args.fresh:
        conn = db.reset_database(args.db)
        print(f"DB reinitialisee -> {args.db}")
    else:
        conn = db.get_connection(args.db)

    loaded = seed_registry_if_empty(conn)
    if loaded:
        print(f"Registre charge : {loaded} fiches")

    stop = {"flag": False}

    def _handle_sigint(signum, frame):
        stop["flag"] = True
        print("\nArret demande, fin du cycle en cours...")

    signal.signal(signal.SIGINT, _handle_sigint)

    cycle = 0
    total_target = 1 if args.once else args.cycles  # 0 = illimite
    print(f"Demarrage : intervalle={args.interval}s  lot={args.batch_size}  "
          f"cycles={'∞' if total_target == 0 else total_target}")

    try:
        while not stop["flag"]:
            cycle += 1
            # Graine par cycle : varie a chaque tick tout en restant reproductible
            # si --seed est fourni (X2).
            batch_seed = None if args.seed is None else args.seed + cycle
            listings = data_generator.generate_scrape_batch(
                n=args.batch_size, seed=batch_seed, now=datetime.now()
            )
            _ingest(conn, listings)

            moved = 0
            if not args.no_advance:
                rng = random.Random(batch_seed)
                moved = advance_lifecycle(conn, rng, max_transitions=args.max_transitions)

            render(conn, cycle, len(listings), moved)

            if total_target and cycle >= total_target:
                break
            if not stop["flag"]:
                # Sommeil fractionne pour repondre vite au Ctrl+C
                slept = 0.0
                while slept < args.interval and not stop["flag"]:
                    time.sleep(min(0.25, args.interval - slept))
                    slept += 0.25
    finally:
        conn.close()
        print(f"\nTermine apres {cycle} cycle(s).")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Ordonnanceur de demo RAKABA Pipeline 1")
    ap.add_argument("--interval", type=float, default=8.0, help="secondes entre deux cycles")
    ap.add_argument("--batch-size", type=int, default=6, help="signaux generes par cycle (F1.1)")
    ap.add_argument("--cycles", type=int, default=0, help="nombre de cycles (0 = illimite)")
    ap.add_argument("--once", action="store_true", help="un seul cycle puis arret")
    ap.add_argument("--fresh", action="store_true", help="reinitialise la DB avant de demarrer (X2)")
    ap.add_argument("--no-advance", action="store_true", help="ingerer sans faire progresser le cycle de vie")
    ap.add_argument("--max-transitions", type=int, default=3, help="cartes avancees au maximum par cycle")
    ap.add_argument("--seed", type=int, default=None, help="graine de base -> demo reproductible")
    ap.add_argument("--db", default=str(db.DEFAULT_DB_PATH), help="chemin du fichier DuckDB")
    return ap


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        run(args)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
