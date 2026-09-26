"""
pipeline1/dashboard.py - Aggregated read-only data for the Admin "Vue
d'ensemble" dashboard. Nothing here writes; everything is derived from
listings/taxpayer_lifecycle (Pipeline 1), documents (Pipeline 2), and
automation_log (transverse).

Region attribution (`match_governorate`) is a best-effort keyword match of
Tunisia's 24 governorate names against free-text addresses - the schema has
no structured region column, so this is a heuristic, not geocoding. An
address that doesn't mention a governorate by name lands under
"non-attribue" rather than being silently dropped or guessed.

Every number here is computed from what's actually in the database. Where
the UI mockup this was built from showed a fabricated week-over-week
percentage ("+12%"), this module reports an honest "new in the last 7 days"
count instead - there's no historical snapshot table to compute a real
percentage change against, and inventing one would violate the project's
own explicability principle (cf. cahier des charges §19).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import duckdb

# ---------------------------------------------------------------------------
# Region matching
# ---------------------------------------------------------------------------

GOVERNORATES: Dict[str, str] = {
    "tunis": "Tunis", "ariana": "Ariana", "ben-arous": "Ben Arous", "manouba": "Manouba",
    "nabeul": "Nabeul", "zaghouan": "Zaghouan", "bizerte": "Bizerte", "beja": "Béja",
    "jendouba": "Jendouba", "kef": "Le Kef", "siliana": "Siliana", "kairouan": "Kairouan",
    "kasserine": "Kasserine", "sidi-bouzid": "Sidi Bouzid", "sousse": "Sousse",
    "monastir": "Monastir", "mahdia": "Mahdia", "sfax": "Sfax", "gafsa": "Gafsa",
    "tozeur": "Tozeur", "kebili": "Kébili", "gabes": "Gabès", "mednine": "Médenine",
    "tataouine": "Tataouine",
}

_SEARCH_KEYS: Dict[str, List[str]] = {
    "tunis": ["tunis"], "ariana": ["ariana"], "ben-arous": ["ben arous", "benarous"],
    "manouba": ["manouba", "mannouba"], "nabeul": ["nabeul"], "zaghouan": ["zaghouan"],
    "bizerte": ["bizerte"], "beja": ["beja"], "jendouba": ["jendouba"], "kef": ["kef"],
    "siliana": ["siliana"], "kairouan": ["kairouan"], "kasserine": ["kasserine"],
    "sidi-bouzid": ["sidi bouzid"], "sousse": ["sousse"], "monastir": ["monastir"],
    "mahdia": ["mahdia"], "sfax": ["sfax"], "gafsa": ["gafsa"], "tozeur": ["tozeur"],
    "kebili": ["kebili"], "gabes": ["gabes"], "mednine": ["mednine", "medenine"],
    "tataouine": ["tataouine"],
}

_ACCENTS = str.maketrans("éèêëàâäîïôöùûüç", "eeeeaaaiioouuuc")


def _normalize(text: Optional[str]) -> str:
    return (text or "").lower().translate(_ACCENTS)


def match_governorate(address_text: Optional[str]) -> Optional[str]:
    """Best-effort match of a free-text address to a governorate id, or None."""
    normalized = _normalize(address_text)
    if not normalized:
        return None
    for gid, keys in _SEARCH_KEYS.items():
        for key in keys:
            if key in normalized:
                return gid
    return None


def _risk_level(score: Optional[float]) -> str:
    if score is None:
        return "inconnu"
    if score > 0.7:
        return "eleve"
    if score > 0.4:
        return "moyen"
    return "faible"


# ---------------------------------------------------------------------------
# Shared queries
# ---------------------------------------------------------------------------

def _entities(conn: duckdb.DuckDBPyConnection) -> List[tuple]:
    """(entity_id, status, status_updated_at, business_name, location_text, match_score)"""
    return conn.execute(
        """
        SELECT tl.entity_id, tl.status, tl.status_updated_at, l.business_name,
               l.location_text, tl.match_score
        FROM taxpayer_lifecycle tl
        JOIN listings l ON l.listing_id = tl.listing_id
        """
    ).fetchall()


def _max_document_scores(conn: duckdb.DuckDBPyConnection) -> Dict[str, float]:
    rows = conn.execute(
        "SELECT entity_id, MAX(composite_score) FROM documents GROUP BY entity_id"
    ).fetchall()
    return {eid: score for eid, score in rows if score is not None}


ACCOMPAGNEMENT_STATUSES = ("Contacte", "En regularisation", "Conforme", "Contribuable de confiance")
CONFORME_STATUSES = ("Conforme", "Contribuable de confiance")


# ---------------------------------------------------------------------------
# KPI summary
# ---------------------------------------------------------------------------

def kpi_summary(conn: duckdb.DuckDBPyConnection) -> Dict[str, Any]:
    entities = _entities(conn)
    max_scores = _max_document_scores(conn)
    week_ago = datetime.now() - timedelta(days=7)

    total = len(entities)
    high_risk = 0
    in_verification = 0
    compliant = 0
    new_total = new_high_risk = new_in_verification = new_compliant = 0

    for entity_id, status, status_updated_at, _name, _loc, _match in entities:
        is_recent = status_updated_at is not None and status_updated_at >= week_ago
        score = max_scores.get(entity_id)
        is_high_risk = score is not None and score > 0.7
        is_in_verification = status in ("Contacte", "En regularisation")
        is_compliant = status in CONFORME_STATUSES

        new_total += is_recent
        if is_high_risk:
            high_risk += 1
            new_high_risk += is_recent
        if is_in_verification:
            in_verification += 1
            new_in_verification += is_recent
        if is_compliant:
            compliant += 1
            new_compliant += is_recent

    return {
        "total_detected": {"value": total, "new_this_week": new_total},
        "high_risk": {"value": high_risk, "new_this_week": new_high_risk},
        "in_verification": {"value": in_verification, "new_this_week": new_in_verification},
        "compliant": {"value": compliant, "new_this_week": new_compliant},
    }


# ---------------------------------------------------------------------------
# Region breakdown (for the map + "Centres / régions" list)
# ---------------------------------------------------------------------------

def region_breakdown(conn: duckdb.DuckDBPyConnection) -> List[Dict[str, Any]]:
    entities = _entities(conn)
    max_scores = _max_document_scores(conn)
    buckets: Dict[str, Dict[str, int]] = {}

    for entity_id, status, _updated, _name, location_text, _match in entities:
        gid = match_governorate(location_text) or "non-attribue"
        bucket = buckets.setdefault(gid, {"total": 0, "eleve": 0, "moyen": 0, "faible": 0, "non_evalue": 0, "traite": 0})
        bucket["total"] += 1
        if status in CONFORME_STATUSES:
            bucket["traite"] += 1
        else:
            level = _risk_level(max_scores.get(entity_id))
            bucket[level if level in ("eleve", "moyen", "faible") else "non_evalue"] += 1

    result = [
        {
            "governorate_id": gid,
            "governorate_name": GOVERNORATES.get(gid, "Non attribué"),
            **counts,
        }
        for gid, counts in buckets.items()
    ]
    result.sort(key=lambda r: r["total"], reverse=True)
    return result


# ---------------------------------------------------------------------------
# Alerts feed
# ---------------------------------------------------------------------------

def _classify_log_entry(description: str) -> Optional[tuple]:
    """(alert_type, severity) for a log line worth surfacing as an alert, else None."""
    d = description.lower()
    if "liees par" in d or "liee par" in d:
        return ("reseau_fraude", "danger")
    if "ambigue" in d or "ambigue" in d:
        return ("declaration_incoherente", "warning")
    if "aucune correspondance credible" in d:
        return ("activite_non_declaree", "info")
    return None


_ALERT_LABELS = {
    "reseau_fraude": "Réseau d’entités liées détecté",
    "declaration_incoherente": "Déclaration incohérente",
    "activite_non_declaree": "Activité non déclarée détectée",
    "document_suspect": "Document à examiner",
}


def _relative_time(ts: datetime) -> str:
    delta = datetime.now() - ts
    hours = delta.total_seconds() / 3600
    if hours < 1:
        return f"Il y a {max(1, int(delta.total_seconds() / 60))} min"
    if hours < 24:
        return f"Il y a {int(hours)}h"
    return f"Il y a {int(hours / 24)}j"


def alerts_feed(conn: duckdb.DuckDBPyConnection, limit: int = 10) -> List[Dict[str, Any]]:
    log_rows = conn.execute(
        """
        SELECT al.entity_id, al.action_description, al.timestamp, l.business_name, l.location_text
        FROM automation_log al
        LEFT JOIN taxpayer_lifecycle tl ON tl.entity_id = al.entity_id
        LEFT JOIN listings l ON l.listing_id = tl.listing_id
        ORDER BY al.timestamp DESC
        LIMIT 200
        """
    ).fetchall()

    alerts: List[Dict[str, Any]] = []
    for entity_id, description, ts, name, location in log_rows:
        classified = _classify_log_entry(description)
        if classified is None:
            continue
        alert_type, severity = classified
        gid = match_governorate(location)
        alerts.append({
            "type": alert_type,
            "severity": severity,
            "title": _ALERT_LABELS[alert_type],
            "entity_name": name,
            "region": GOVERNORATES.get(gid) if gid else None,
            "timestamp": ts.isoformat(),
            "relative_time": _relative_time(ts),
        })

    doc_rows = conn.execute(
        """
        SELECT d.composite_score, d.submitted_date, l.business_name, l.location_text
        FROM documents d
        JOIN taxpayer_lifecycle tl ON tl.entity_id = d.entity_id
        JOIN listings l ON l.listing_id = tl.listing_id
        WHERE d.composite_score > 0.6
        ORDER BY d.submitted_date DESC
        LIMIT 50
        """
    ).fetchall()
    for score, ts, name, location in doc_rows:
        gid = match_governorate(location)
        alerts.append({
            "type": "document_suspect",
            "severity": "danger" if score > 0.75 else "warning",
            "title": _ALERT_LABELS["document_suspect"],
            "entity_name": name,
            "region": GOVERNORATES.get(gid) if gid else None,
            "timestamp": ts.isoformat(),
            "relative_time": _relative_time(ts),
        })

    alerts.sort(key=lambda a: a["timestamp"], reverse=True)
    return alerts[:limit]


# ---------------------------------------------------------------------------
# Evolution des détections (line chart)
# ---------------------------------------------------------------------------

def detection_evolution(conn: duckdb.DuckDBPyConnection, days: int = 7) -> List[Dict[str, Any]]:
    start = date.today() - timedelta(days=days - 1)
    rows = conn.execute(
        "SELECT CAST(detected_date AS DATE) AS d, count(*) FROM listings "
        "WHERE CAST(detected_date AS DATE) >= ? GROUP BY d",
        [start],
    ).fetchall()
    counts = {r[0]: r[1] for r in rows}
    return [
        {"date": (start + timedelta(days=i)).isoformat(), "count": counts.get(start + timedelta(days=i), 0)}
        for i in range(days)
    ]


# ---------------------------------------------------------------------------
# Répartition par pipeline (donut)
# ---------------------------------------------------------------------------

def pipeline_distribution(conn: duckdb.DuckDBPyConnection) -> Dict[str, int]:
    """Real counts per pipeline's own output table - not a partition of one
    total (an entity can count in more than one bucket, e.g. detected AND
    verified), matching what each pipeline actually produced."""
    decouvrir = conn.execute("SELECT count(*) FROM taxpayer_lifecycle").fetchone()[0]
    verifier = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
    placeholders = ", ".join("?" for _ in ACCOMPAGNEMENT_STATUSES)
    accompagner = conn.execute(
        f"SELECT count(*) FROM taxpayer_lifecycle WHERE status IN ({placeholders})",
        list(ACCOMPAGNEMENT_STATUSES),
    ).fetchone()[0]
    return {"decouvrir": decouvrir, "verifier": verifier, "accompagner": accompagner}


# ---------------------------------------------------------------------------
# Top entités à risque
# ---------------------------------------------------------------------------

def top_risk_entities(conn: duckdb.DuckDBPyConnection, limit: int = 5) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT tl.entity_id, l.business_name, tl.status, l.location_text, tl.match_score,
               (SELECT MAX(composite_score) FROM documents d WHERE d.entity_id = tl.entity_id) AS max_score
        FROM taxpayer_lifecycle tl
        JOIN listings l ON l.listing_id = tl.listing_id
        ORDER BY max_score DESC NULLS LAST, tl.match_score ASC
        LIMIT ?
        """,
        [limit],
    ).fetchall()

    result = []
    for entity_id, name, status, location, match_score, max_score in rows:
        gid = match_governorate(location)
        result.append({
            "entity_id": entity_id,
            "name": name,
            "status": status,
            "region": GOVERNORATES.get(gid, "—") if gid else "—",
            "risk_level": _risk_level(max_score),
            "score": max_score,
        })
    return result


# ---------------------------------------------------------------------------
# Combined payload for the dashboard's single fetch
# ---------------------------------------------------------------------------

def overview(conn: duckdb.DuckDBPyConnection) -> Dict[str, Any]:
    return {
        "kpi": kpi_summary(conn),
        "regions": region_breakdown(conn),
        "alerts": alerts_feed(conn),
        "evolution": detection_evolution(conn),
        "pipeline_distribution": pipeline_distribution(conn),
        "top_risk_entities": top_risk_entities(conn),
    }
