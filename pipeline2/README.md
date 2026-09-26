# RAKABA — Pipeline 2 : Vérifier

> Plateforme de détection, vérification et accompagnement fiscal — module de scoring documentaire.

---

## Vue d'ensemble

La **Pipeline 2** est le moteur de vérification de RAKABA. Pour chaque document fiscal soumis, elle produit un **score composite explicable** selon 3 axes indépendants, et construit un **graphe de relations** entre entités pour détecter la fraude coordonnée.

```
document entrant
      │
      ▼
┌─────────────┐   ┌──────────────────┐   ┌─────────────────┐
│ F2.2        │   │ F2.3             │   │ F2.4            │
│ Intégrité   │   │ Isolation Forest │   │ Règles métier   │
│ (détermin.) │   │ (scikit-learn)   │   │ (explicites)    │
└──────┬──────┘   └────────┬─────────┘   └────────┬────────┘
       │                   │                       │
       └───────────────────▼───────────────────────┘
                           │
                    ┌──────▼──────┐
                    │ F2.5        │
                    │ Score       │
                    │ Composite   │
                    └──────┬──────┘
                           │
              ┌────────────▼────────────┐
              │ F2.6 Graphe NetworkX    │
              │ F2.7 GNN (optionnel)    │
              └─────────────────────────┘
```

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| API | FastAPI + Uvicorn |
| Base de données | DuckDB (partagée avec Pipelines 1 et 3, `rakaba.duckdb`) |
| Détection d'anomalies | scikit-learn (Isolation Forest) |
| Graphe de relations | NetworkX |
| GNN (optionnel) | PyTorch Geometric (GraphSAGE) |
| Sérialisation | Pydantic v2 |
| Runtime | Python 3.11+ |

> Mis à jour lors de l'unification des trois pipelines : ce module ciblait
> initialement SQLite/SQLAlchemy sur son propre fichier ; il utilise
> désormais le même DuckDB partagé que Pipelines 1 et 3, avec le schéma
> canonique défini dans `pipeline1/db.py`. `router.py` lit/écrit directement
> via SQL (plus d'ORM), et le graphe (`entity_graph_nodes/edges`) est
> reconstruit à la volée depuis la table `entity_links` réelle de Pipeline 1
> à chaque appel à `/graph/entity/*` ou `/graph/clusters`.

---

## Arborescence

```
pipeline2/
├── __init__.py            # startup_pipeline2() + export router
├── models.py              # EdgeType (enum) — plus d'ORM, tables dans pipeline1/db.py
├── schemas.py             # Pydantic : I/O avec explicabilité complète
├── database.py            # Connexion DuckDB partagée (singleton), init_db
├── synthetic_data.py      # F2.1 — Générateur de données synthétiques
├── integrity.py           # F2.2 — Vérification d'intégrité (déterministe)
├── anomaly.py             # F2.3 — Isolation Forest
├── risk_rules.py          # F2.4 — Règles de schéma à risque
├── scoring.py             # F2.5 — Orchestrateur score composite
├── graph.py               # F2.6 — Graphe NetworkX + conversion en lignes DuckDB
├── gnn.py                 # F2.7 — GNN optionnel (GraphSAGE)
└── router.py              # Endpoints FastAPI (lecture/écriture DuckDB directe)
```

(`main.py`, `requirements.txt` restent à la racine du dépôt.)

---

## Installation

```bash
# Cloner le dépôt
git clone https://github.com/MoetazDhahri/RAKABA.git
cd RAKABA

# Installer les dépendances
pip install -r requirements.txt

# (Optionnel) GNN — nécessite PyTorch
pip install torch torch-geometric
```

---

## Démarrage

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Au démarrage, l'application :
1. Ouvre `rakaba.duckdb` et crée les tables du schéma partagé si elles n'existent pas
2. Entraîne l'Isolation Forest sur 500 documents synthétiques (seed=42)
3. Tente d'entraîner le GNN — silencieusement ignoré si PyTorch Geometric est absent
4. Monte aussi le router Pipeline 3 (`/api/chat/*`, `/api/investigate`, `/api/escalations`) —
   ce `main.py` est le backend unifié des deux pipelines (voir README racine)

**Swagger UI** : [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Endpoints

| Méthode | Route | Description |
|---------|-------|-------------|
| `POST` | `/pipeline2/documents/upload` | Soumettre un document et déclencher le scoring |
| `GET` | `/pipeline2/documents/{document_id}` | Score détaillé (3 axes + explications) |
| `GET` | `/pipeline2/entities/{entity_id}/documents` | Tous les documents d'une entité |
| `GET` | `/pipeline2/graph/entity/{entity_id}` | Sous-graphe centré sur une entité |
| `GET` | `/pipeline2/graph/clusters` | Clusters de fraude détectés |
| `POST` | `/pipeline2/documents/{document_id}/rescan` | Relancer le scoring |
| `GET` | `/health` | Statut du service |

---

## Exemple d'appel

```bash
curl -X POST http://localhost:8000/pipeline2/documents/upload \
  -H "Content-Type: application/json" \
  -d '{
    "entity_id": "entity-001",
    "file_metadata": {
      "created_at": "2024-03-01T10:00:00",
      "modified_at": "2024-05-10T14:30:00",
      "producer": "LibreOffice 7.5",
      "filename": "declaration_2024.pdf"
    },
    "montant": 500000.0,
    "nb_transactions": 3,
    "activite_declaree": 800000.0,
    "declared_date": "2024-03-31T00:00:00"
  }'
```

Réponse (document suspect) :

```json
{
  "document_id": "...",
  "composite_score": 0.6122,
  "integrity": {
    "score": 0.4,
    "flags": ["modified_after_declared_date", "document_altered_after_creation"]
  },
  "coherence": {
    "score": 0.19,
    "explanation": "Document fortement anormal selon l'Isolation Forest."
  },
  "risk": {
    "flags": ["clustering_montants_ronds"],
    "nb_flags": 1,
    "risk_score": 1.0
  },
  "formula_used": "0.4×integrity + 0.4×coherence + 0.2×(1 − 0.25×nb_risk_flags)",
  "gnn_anomaly_score": null
}
```

---

## Score composite

```
composite = 0.4 × (1 - integrity_score)
          + 0.4 × (1 - coherence_score)
          + 0.2 × (1 - 0.25 × nb_risk_flags)
```

- **0.0** → document sain
- **1.0** → document très suspect

Chaque score est toujours accompagné de ses flags/explications — jamais un chiffre seul.

---

## Modules détaillés

### F2.2 — Intégrité (déterministe)
Inspecte les métadonnées du fichier :
- `modified_after_declared_date` — le fichier a été modifié après la date de déclaration officielle
- `document_altered_after_creation` — `created_at ≠ modified_at`

Pénalité : `-0.3` par flag, score borné `[0, 1]`.

### F2.3 — Isolation Forest
- Features : montant normalisé, écart à l'historique, nb transactions, ratio montant/activité
- `contamination=0.08`, `random_state=42`
- Entraîné une fois au démarrage sur données synthétiques

### F2.4 — Règles de risque
- `clustering_montants_ronds` — >50% des montants sont des multiples de 1000
- `transactions_avec_entite_liee` — transactions avec une entité du même cluster (via module `entity_links` externe)

### F2.6 — Graphe NetworkX
- Liens par attribut partagé : téléphone, adresse, compte bancaire
- Détection de clusters via `nx.connected_components`

### F2.7 — GNN (optionnel)
GraphSAGE 2 couches. Si PyTorch Geometric n'est pas installé ou si l'entraînement échoue, `gnn_anomaly_score` retourne `None` sans jamais lever d'exception.

Entraîné au démarrage (`startup_pipeline2`) sur le **vrai** graphe reconstruit
depuis `entity_links` (Pipeline 1) s'il existe déjà assez de données (≥ 2
arêtes) ; sinon, sur un warm-up synthétique de secours — dans ce cas
`gnn_anomaly_score(entity_id)` renverra `None` pour toute vraie entité tant
que Pipeline 1 n'a pas tourné. **Pour un GNN utile en démo : lancer Pipeline
1 (`python -m pipeline1.pipeline`) avant de démarrer le backend unifié**, pas
après — l'entraînement ne se relance pas automatiquement en cours de route
(F2.7 reste un enrichissement optionnel, jamais un point de blocage : F2.3
Isolation Forest fonctionne dans tous les cas).

L'entraînement est auto-supervisé avec des pseudo-labels à zéro pour tous
les nœuds (cf. docstring de `gnn.py`) : sur un petit graphe, les scores
convergent vite vers ~0 pour tout le monde — un signal faible par
construction de cette méthode, pas un bug d'intégration.

---

## Intégration avec les autres Pipelines

```python
# Dans le main.py partagé
from pipeline2 import pipeline2_router, startup_pipeline2

app.include_router(pipeline2_router)
app.add_event_handler("startup", startup_pipeline2)
```

**Fonction pure pour Pipeline 3 (agent d'investigation) :**

```python
from pipeline2.router import check_document_integrity

result = check_document_integrity("entity-001")
# retourne le dernier score composite structuré de l'entité
```

---

## Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `DUCKDB_PATH` | `rakaba.duckdb` (racine du dépôt) | Chemin du fichier DuckDB partagé (même variable que Pipeline 3) |

---

## Auteurs

Projet développé dans le cadre d'un hackathon 24h.
