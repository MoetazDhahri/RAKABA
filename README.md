# RAKABA

**رقابة — la vigilance fiscale, augmentée**

Plateforme intégrée de détection, vérification et accompagnement fiscal par IA.

Hackathon National « IA & Finances Publiques » — 25 & 26 septembre 2026, ESB El Ghazala
Équipe : **Moetaz** · **Choch** · **Khalil**

## Le problème

Une part significative de l'activité économique tunisienne échappe au radar
fiscal (secteur informel ≈ 35% du PIB) et, parmi les contribuables déjà
enregistrés au régime forfaitaire, près de 60% ne déposent plus leurs
déclarations. Chaque signal — une annonce en ligne, un document douteux, une
déclaration incohérente — est aujourd'hui traité isolément, sans mémoire ni
suivi dans le temps.

## La solution : trois pipelines reliés

| Pipeline | Rôle | Défis | Propriétaire | Détails |
|---|---|---|---|---|
| **1 — Découvrir** | Détecte les activités non déclarées par recoupement de signaux publics avec le registre fiscal, et suit chaque entité à travers un cycle de vie de régularisation | T11, T4 | Moetaz | [`pipeline1/README.md`](pipeline1/README.md) |
| **2 — Vérifier** | Score chaque document soumis (intégrité, cohérence, schéma à risque) et relie les entités dans un graphe pour détecter la fraude organisée | T6, T3, T16 | Khalil | [`pipeline2/README.md`](pipeline2/README.md) |
| **3 — Accompagner** | Chatbot fiscal + agent d'investigation autonome (tool-calling) qui enquête sur une entité flaguée et rédige un rapport pour l'inspecteur | T9, T14 | Choch | [`pipeline3/README.md`](pipeline3/README.md) |

Le principe directeur du cahier des charges (§14) : une seule base de données
partagée, trois pipelines qui l'alimentent, deux interfaces pour la
consulter — une pour l'inspecteur (Amira, dense et analytique), une pour le
contribuable (Youssef, simple et bienveillante, jamais accusatrice).

## État d'avancement

- ✅ **Pipeline 1 — Découvrir** (Moetaz) : complet. Moteur de correspondance
  floue, schéma DuckDB, générateur de signaux synthétiques, machine à états
  du cycle de vie, liaison d'entités, API de lecture, ordonnanceur de démo,
  19 tests.
- ✅ **Pipeline 2 — Vérifier** (Khalil) : complet côté logique de scoring
  (intégrité, Isolation Forest, règles de risque, graphe, GNN optionnel),
  exposé via son propre service FastAPI.
- ✅ **Pipeline 3 — Accompagner** (Choch) : chatbot + agent d'investigation
  (tool-calling), backend DuckDB avec seeding de secours autonome.

### ⚠️ Point d'intégration à résoudre avant la démo unifiée

Les trois pipelines ont été développés en parallèle contre des hypothèses de
persistance différentes — à trancher en équipe avant d'assembler la démo
finale (cf. §14, "une seule base de données") :

| Pipeline | Moteur | Fichier | Table pivot |
|---|---|---|---|
| 1 | DuckDB (driver natif) | `rakaba.duckdb` | `taxpayer_lifecycle` |
| 2 | SQLAlchemy ORM sur **SQLite** | `rakaba.db` | `documents` (FK logique non contrainte vers l'entité) |
| 3 | DuckDB (driver natif) | `rakaba.duckdb` | attend une table `entities` |

Deux écarts à résoudre : (a) Pipeline 2 cible un moteur différent (SQLite)
de Pipelines 1 et 3 (DuckDB) ; (b) même entre 1 et 3, le nom de la table
pivot diffère (`taxpayer_lifecycle` vs `entities`). `entity_links` est en
revanche déjà cohérent entre les trois. Rien de bloquant individuellement —
chaque pipeline tourne et teste en autonomie — mais la clé "une seule base
partagée" (X1) n'est pas encore vraie tant que ce n'est pas aligné.

## Stack technique

- **Correspondance floue (P1)** : `rapidfuzz`
- **Persistance (P1, P3)** : DuckDB — fichier local, zéro configuration
- **Persistance (P2)** : SQLite via SQLAlchemy *(à réconcilier, voir ci-dessus)*
- **Détection d'anomalie (P2)** : `scikit-learn` (Isolation Forest)
- **Graphe et GNN (P2)** : `NetworkX`, PyTorch Geometric (GraphSAGE, optionnel)
- **Backend (P2)** : FastAPI + Uvicorn
- **IA conversationnelle et agent (P3)** : Claude (API Anthropic), tool-use
- **Frontend** : React ou HTML/JS selon le temps disponible

Aucune donnée réelle : toutes les données (annonces, registre, documents)
sont synthétiques, par choix de conception — conformité à la loi organique
n° 2004-63 et aucune tentative d'accès à un système réel de l'administration.

## Démarrer

```bash
git clone https://github.com/MoetazDhahri/RAKABA.git
cd RAKABA

# Pipeline 1
pip install -r pipeline1/requirements.txt
python -m pipeline1.pipeline          # un cycle automatisé
python -m pipeline1.demo_loop --fresh --interval 8   # mode démo en continu
python -m pytest pipeline1/tests -v   # tests

# Pipeline 2 (service FastAPI indépendant pour l'instant, voir pipeline2/README.md)
# note : requirements.txt et main.py sont a la racine du depot (structure de Khalil)
pip install -r requirements.txt
uvicorn main:app --reload

# Pipeline 3 (voir pipeline3/README.md)
pip install -r pipeline3/requirements.txt
```

Chaque pipeline documente ses propres détails, règles de scoring et points
d'intégration dans son `README.md`.
