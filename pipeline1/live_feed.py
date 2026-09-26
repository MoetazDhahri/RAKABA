"""
pipeline1/live_feed.py — In-process background feed for the unified backend.

Without this, `uvicorn main:app` serves a perfectly correct but frozen
snapshot: the Admin dashboard's "Évolution des détections" chart and
"Dernières alertes" panel only ever reflect whatever was in the DB the
moment the server started, because the only thing that ever adds fresh
listings/automation_log rows is `pipeline1/demo_loop.py` — a SEPARATE
process nobody runs alongside the server by default. A jury watching the
live demo would see a chart pinned flat at zero and a notification bell
that never changes.

This reuses demo_loop.py's own ingest/advance-lifecycle functions (not a
parallel reimplementation) and runs them on a daemon thread from the
FastAPI app's own startup event, so `uvicorn main:app` alone is enough to
keep the dashboard visibly alive - exactly what demo_loop.py already does
standalone, just wired into the same process instead of a second one.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from datetime import datetime

from pipeline1 import data_generator, db
from pipeline1 import pipeline as p1
from pipeline1.demo_loop import advance_lifecycle, seed_registry_if_empty

logger = logging.getLogger(__name__)

_started = False
_started_lock = threading.Lock()


def _tick(rng: random.Random) -> None:
    with db.LOCK:
        conn = db.get_connection()
        listings = data_generator.generate_scrape_batch(n=rng.randint(2, 4), now=datetime.now())
        p1.ingest_listings(conn, listings)
        advance_lifecycle(conn, rng, max_transitions=2)


def _run(interval_seconds: float) -> None:
    rng = random.Random()
    with db.LOCK:
        seed_registry_if_empty(db.get_connection())
    while True:
        try:
            _tick(rng)
        except Exception:
            logger.exception("live_feed: tick failed, will retry next interval")
        time.sleep(interval_seconds)


def start(interval_seconds: float = 14.0) -> None:
    """Idempotent: safe to call from startup even if invoked more than once."""
    global _started
    with _started_lock:
        if _started:
            return
        _started = True
    thread = threading.Thread(target=_run, args=(interval_seconds,), daemon=True, name="rakaba-live-feed")
    thread.start()
    logger.info("Pipeline 1: flux automatique demarre (nouveau lot toutes les %ss).", interval_seconds)
