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

### ✅ Unification de la base de données (résolu)

Les trois pipelines avaient été développés en parallèle contre des
hypothèses de persistance différentes : Pipeline 2 sur SQLAlchemy/SQLite
(`rakaba.db`), Pipeline 1 et 3 sur DuckDB mais avec des tables pivot au nom
différent (`taxpayer_lifecycle` vs `entities`). Unifié : le schéma canonique
vit dans [`pipeline1/db.py`](pipeline1/db.py) et couvre les tables des trois
pipelines (`documents`, `entity_graph_nodes/edges` pour P2 ; `declarations`,
`escalations` pour P3). Pipeline 2 a été porté de SQLAlchemy vers ce DuckDB
partagé ; Pipeline 3 lit désormais `taxpayer_lifecycle`/`listings` au lieu
d'une table `entities` redondante. Un correctif important au passage :
l'ancien bootstrap de schéma de Pipeline 3 supprimait et recréait
`entity_links`/`documents` dès qu'une seule table lui manquait — ce qui
aurait effacé les données réelles de Pipeline 1 au premier lancement contre
le fichier partagé. Vérifié par un test d'intégration bout-en-bout (P1 crée
des entités et des liens réels → P2 les score et reconstruit son graphe
depuis `entity_links` → P3 les lit via `consulter_entite`/`entites_liees` —
rien n'est écrasé).

⚠️ **Reste à faire** : Pipeline 2 (FastAPI) et Pipeline 3 (Flask) sont deux
process séparés qui ouvriraient chacun `rakaba.duckdb` — DuckDB ne supporte
qu'un seul process écrivain à la fois sur un même fichier. Le cahier des
charges (§14) prévoit un seul backend ; les fusionner en un seul process
(monter le WSGI Flask de P3 dans l'app FastAPI de P2, par exemple) n'est pas
encore fait. Pour l'instant, ne pas lancer les deux services en même temps
contre le même fichier.

## Stack technique

- **Correspondance floue (P1)** : `rapidfuzz`
- **Persistance (P1, P2, P3)** : DuckDB partagé — fichier local unique, zéro configuration
- **Détection d'anomalie (P2)** : `scikit-learn` (Isolation Forest)
- **Graphe et GNN (P2)** : `NetworkX`, PyTorch Geometric (GraphSAGE, optionnel)
- **Backend (P2)** : FastAPI + Uvicorn
- **Backend (P3)** : Flask
- **IA conversationnelle et agent (P3)** : Grok (client compatible OpenAI), tool-use —
  note : le cahier des charges (§13) prévoyait Claude/API Anthropic ; le code
  actuel utilise Grok, à confirmer si c'est un choix définitif de l'équipe
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
