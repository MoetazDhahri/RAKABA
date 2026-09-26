# RAKABA — Pipeline 1 : Découvrir

Détection d'activités non déclarées par recoupement de signaux publics avec le
registre fiscal, et suivi du cycle de vie de régularisation. Cf. cahier des
charges §4.1, §9.1, §12, §15 (owner: Moetaz).

## Modules

| Fichier | Rôle | Sections du cahier des charges |
|---|---|---|
| `matching_engine.py` | Score composite nom (fuzzy, rapidfuzz) + téléphone (exact) | F1.3 |
| `db.py` | Schéma DuckDB (`listings`, `registry`, `taxpayer_lifecycle`, `entity_links`, `automation_log`) | X1 |
| `data_generator.py` | Générateur de signaux synthétiques + registre fiscal synthétique | F1.1, F1.2 |
| `entity_linking.py` | Regroupement d'entités par téléphone/adresse partagés | F1.6 |
| `pipeline.py` | Orchestration automatisée bout-en-bout + transitions manuelles/automatiques | F1.4, F1.5, F1.8, X2 |
| `queries.py` | Couche de lecture (kanban, compteurs, détail entité, journal) | F1.7 (data contract), UC-02, UC-07, UC-11 |
| `demo_loop.py` | Ordonnanceur de présentation : ingère et fait progresser des entités à intervalle régulier, pour que le tableau kanban évolue sous les yeux du jury sans action manuelle | F1.8, X2 (usage démo uniquement) |
| `tests/` | 19 tests (matching, cycle de vie, liaison, lecture) | — |

## Réel vs. simulé

- **Simulé, par choix de conception** (cf. §11 "Won't have", §16, §19) : `data_generator.py`
  ne scrape rien. Il génère des annonces fictives (noms, téléphones, adresses,
  plateformes) avec des écarts volontaires par rapport au registre — exactement
  ce qu'un vrai flux de signaux produirait, mais sans toucher à un compte, une
  plateforme ou une donnée personnelle réelle.
- **Réel / production-ready** : tout le reste. Le moteur de correspondance, le
  schéma DuckDB, la machine à états, la liaison d'entités et les requêtes de
  lecture sont la logique métier définitive — ils fonctionneraient à l'identique
  sur un flux de données réel et autorisé (cf. §20, feuille de route : Google
  Places API / Meta Graph API sous accord formel, pas de scraping).

## Bibliothèques

- [`rapidfuzz`](https://pypi.org/project/rapidfuzz/) — similarité de noms (F1.3)
- [`duckdb`](https://pypi.org/project/duckdb/) — persistance locale, zéro configuration (X1)
- [`pytest`](https://pypi.org/project/pytest/) — 19 tests couvrant matching, cycle de vie, liaison, lecture

## Installation et exécution

```bash
pip install -r requirements.txt

# Un cycle automatisé complet : génère 12 signaux, les traite tous,
# met à jour les liaisons d'entités, journalise chaque action.
python -m pipeline1.pipeline

# Tests
python -m pytest pipeline1/tests -v
```

La base est créée dans `rakaba.duckdb` à la racine du projet. Pour repartir
d'un état vide et reproductible (X2) :

```python
from pipeline1 import db
db.reset_database()
```

### Mode démo (présentation au jury)

`demo_loop.py` fait tourner le pipeline en continu : à chaque tick, il génère
un nouveau lot de signaux, les ingère (matching → création/skip d'entité →
liaison → log), puis fait avancer quelques entités d'un état dans leur cycle
de vie — le tout tracé dans `automation_log` avec le bon `triggered_by`
(`system` pour la progression automatique, `human` réservé au forçage manuel
d'Amira via `force_transition`).

```bash
# Repart d'une base vide, un signal toutes les 8s, arret manuel (Ctrl+C)
python -m pipeline1.demo_loop --fresh --interval 8 --batch-size 6

# Déterministe (même déroulé à chaque répétition), 5 cycles puis arrêt
python -m pipeline1.demo_loop --fresh --cycles 5 --seed 42

# Ingestion seule, sans faire progresser le cycle de vie
python -m pipeline1.demo_loop --fresh --no-advance

# Un seul cycle (utile pour un bouton "actualiser" côté UI plutôt qu'une boucle)
python -m pipeline1.demo_loop --once
```

## Règle de matching (§4.1)

Score composite = 40% similarité de nom (rapidfuzz, `token_sort_ratio`) + 60%
correspondance exacte de téléphone (normalisé, insensible au formatage/+216).

| Score | Interprétation | Action |
|---|---|---|
| ≥ 80 | Correspondance fiable | Aucune action — déjà enregistré |
| 40–79 | Ambigu | Entité créée, statut `Détecté`, note de vérification humaine |
| < 40 | Aucune correspondance crédible | Entité créée, statut `Détecté` |

## Cycle de vie (§4.1)

`Détecté → Contacté → En régularisation → Conforme → Contribuable de confiance`

`pipeline.transition_entity(conn, entity_id, new_status, triggered_by=...)`
est la fonction générique de transition — elle valide le statut, met à jour
`taxpayer_lifecycle`, et journalise avec le vrai déclencheur (`system` pour
une progression automatique, `human` pour un forçage). `force_transition()`
en est le raccourci réservé à Amira (F1.8) : toujours `triggered_by="human"`.

## API de référence

Ce que les autres pipelines/l'UI sont censés appeler :

| Fonction | Usage |
|---|---|
| `pipeline.run_scrape_cycle(conn, n, seed)` | Un cycle one-shot : génère `n` signaux et les ingère. Utilisé par le CLI et les tests. |
| `pipeline.ingest_listings(conn, listings)` | Ingère un lot de signaux déjà généré (matching → création/skip → liaison → log). Utilisé par `demo_loop.py`. |
| `pipeline.force_transition(conn, entity_id, new_status, note=None)` | Forçage manuel par Amira (F1.8). |
| `queries.kanban_columns(conn)` | Les 5 colonnes du tableau kanban (Écran 1), déjà groupées par statut. |
| `queries.dashboard_counters(conn)` | Compteurs d'en-tête : détectés aujourd'hui / en régularisation / conformes. |
| `queries.get_entity_detail(conn, entity_id)` | Détail complet d'une entité + son historique d'automatisation (Écran 2 / `lookup_entity`). |
| `queries.get_automation_log(conn, limit)` | Journal cross-pipeline le plus récent en premier (Écran 5). |
| `entity_linking.get_related_entities(conn, entity_id)` | Entités liées par téléphone/adresse partagés (`get_related_entities`). |

## Points d'intégration avec les autres pipelines

- **Pipeline 2 (Khalil)** : `entity_links` est la table partagée qui alimente
  son graphe de relations. Les identifiants d'entité (`entity_id`) et de
  registre (`matricule_fiscal`) doivent rester cohérents entre les deux jeux
  de données synthétiques (§16.1).
- **Pipeline 3 (Choch)** : `queries.get_entity_detail()` correspond à l'outil
  `lookup_entity` de l'agent d'investigation ; `entity_linking.get_related_entities()`
  correspond à `get_related_entities` ; `queries.get_entity_automation_log()`
  peut servir d'équivalent P1 à `get_declaration_history`.

## Ce qui n'est délibérément pas ici

Aucun scraping réel de réseaux sociaux (Instagram, Facebook, TikTok, Google
Maps) n'est implémenté ni prévu pour ce hackathon — c'est un choix de
conception explicite du cahier des charges (§11, §19), pas une limitation
technique. Voir §20 pour le chemin légitime d'ingestion réelle post-hackathon.
