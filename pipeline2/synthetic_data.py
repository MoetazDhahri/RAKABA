"""
pipeline2/synthetic_data.py
F2.1 — Générateur de documents fiscaux synthétiques.

Règles :
  - Reproductible via seed fixe (DEFAULT_SEED = 42).
  - Taux d'anomalie configurable (défaut 8 %).
  - Anomalies plantées :
      1. modified_at > declared_date  (falsification post-déclaration)
      2. Montants ronds suspects      (multiples de 1000)
      3. Transactions inter-cluster   (fraude coordonnée entre entités liées)
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

DEFAULT_SEED       = 42
DEFAULT_N          = 200
DEFAULT_ANOMALY_RATE = 0.08
N_CLUSTERS         = 5   # nombre de clusters d'entités liées


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def _random_date(rng: random.Random, start: datetime, end: datetime) -> datetime:
    delta = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randint(0, delta))


def _make_entity_clusters(n_entities: int, n_clusters: int, rng: random.Random) -> Dict[str, int]:
    """Assigne chaque entité à un cluster (index 0..n_clusters-1)."""
    entity_ids = [str(uuid.UUID(int=rng.getrandbits(128))) for _ in range(n_entities)]
    return {eid: rng.randint(0, n_clusters - 1) for eid in entity_ids}


# ---------------------------------------------------------------------------
# Générateur principal
# ---------------------------------------------------------------------------

def generate_synthetic_documents(
    n: int = DEFAULT_N,
    anomaly_rate: float = DEFAULT_ANOMALY_RATE,
    seed: int = DEFAULT_SEED,
) -> List[Dict[str, Any]]:
    """
    Génère `n` déclarations fiscales fictives.

    Retourne une liste de dicts compatibles avec DocumentIn :
      {
        document_id     : str (UUID),
        entity_id       : str (UUID),
        file_metadata   : {created_at, modified_at, producer, filename},
        montant         : float,
        nb_transactions : int,
        activite_declaree: float,
        declared_date   : datetime,
        _is_anomaly     : bool,          # méta, non persisté
        _anomaly_types  : List[str],     # méta, non persisté
      }
    """
    rng = random.Random(seed)

    # Plage de dates pour les déclarations (année fiscale courante)
    period_start = datetime(2024, 1, 1)
    period_end   = datetime(2024, 12, 31)

    # Créer un pool d'entités avec leurs clusters
    n_entities = max(10, n // 5)
    entity_cluster = _make_entity_clusters(n_entities, N_CLUSTERS, rng)
    entity_ids     = list(entity_cluster.keys())

    # Activité moyenne par entité (stable, seed-déterminé)
    entity_avg_activity = {
        eid: rng.uniform(50_000, 2_000_000) for eid in entity_ids
    }

    n_anomalies = int(n * anomaly_rate)
    anomaly_indices = set(rng.sample(range(n), n_anomalies))

    docs: List[Dict[str, Any]] = []

    for i in range(n):
        entity_id   = rng.choice(entity_ids)
        cluster_id  = entity_cluster[entity_id]
        is_anomaly  = i in anomaly_indices
        anomaly_types: List[str] = []

        declared_date = _random_date(rng, period_start, period_end)
        created_at    = declared_date - timedelta(days=rng.randint(1, 30))

        # Par défaut : modified_at == created_at (document non altéré)
        modified_at   = created_at

        # Montant normal : distribution log-normale autour de l'activité moyenne
        avg = entity_avg_activity[entity_id]
        montant = abs(rng.gauss(avg * 0.1, avg * 0.03))

        # Nombre de transactions : normal autour de 20
        nb_transactions = max(1, int(rng.gauss(20, 5)))

        # Activité déclarée
        activite_declaree = avg * rng.uniform(0.85, 1.15)

        # --- Planter les anomalies ---
        if is_anomaly:
            anomaly_choice = rng.random()

            # Anomalie 1 : modified_at APRÈS declared_date (falsification)
            if anomaly_choice < 0.4:
                modified_at = declared_date + timedelta(days=rng.randint(1, 60))
                anomaly_types.append("modified_after_declared")

            # Anomalie 2 : montant rond suspect (multiple de 1000)
            elif anomaly_choice < 0.75:
                montant = float(rng.randint(1, 500) * 1000)
                anomaly_types.append("round_amount_suspect")

            # Anomalie 3 : transaction inter-cluster (fraude coordonnée)
            else:
                # On choisit une entité du MÊME cluster
                same_cluster = [
                    eid for eid, cid in entity_cluster.items()
                    if cid == cluster_id and eid != entity_id
                ]
                if same_cluster:
                    anomaly_types.append("linked_entity_transaction")
                    # On marque aussi le montant comme rond pour renforcer le signal
                    montant = float(rng.randint(1, 200) * 1000)

        producer = rng.choice(["LibreOffice 7.5", "Microsoft Word 365", "Adobe Acrobat DC", "PDFCreator 4.x"])
        filename = f"declaration_{entity_id[:8]}_{declared_date.strftime('%Y%m')}.pdf"

        docs.append({
            "document_id"       : str(uuid.UUID(int=rng.getrandbits(128))),
            "entity_id"         : entity_id,
            "file_metadata"     : {
                "created_at"  : created_at.isoformat(),
                "modified_at" : modified_at.isoformat(),
                "producer"    : producer,
                "filename"    : filename,
            },
            "montant"           : round(montant, 2),
            "nb_transactions"   : nb_transactions,
            "activite_declaree" : round(activite_declaree, 2),
            "declared_date"     : declared_date.isoformat(),
            # Métadonnées internes (non persistées en DB)
            "_is_anomaly"       : is_anomaly,
            "_anomaly_types"    : anomaly_types,
            "_cluster_id"       : cluster_id,
        })

    return docs


def get_entity_history(
    entity_id: str,
    all_docs: List[Dict[str, Any]],
) -> List[float]:
    """
    Retourne l'historique des montants d'une entité à partir
    du dataset synthétique, pour le calcul de la feature
    'écart au montant moyen historique'.
    """
    return [d["montant"] for d in all_docs if d["entity_id"] == entity_id]


# ---------------------------------------------------------------------------
# Utilitaire CLI (pour visualiser rapidement)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    docs = generate_synthetic_documents(n=20, seed=42)
    anomalies = [d for d in docs if d["_is_anomaly"]]
    print(f"Générés : {len(docs)} documents, dont {len(anomalies)} anomalies")
    for a in anomalies:
        print(f"  [{a['document_id'][:8]}] {a['_anomaly_types']}  montant={a['montant']}")
