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
- ✅ **Pipeline 2 — Vérifier** (Khalil) : logique de scoring complète
  (intégrité, Isolation Forest, règles de risque, graphe, GNN optionnel),
  plus une forensique de fichier réel (`/documents/upload-file`) : détection
  fiable d'édition post-finalisation d'un PDF, et analyse ELA pour repérer
  une signature/un cachet potentiellement collé (voir
  [`pipeline2/README.md`](pipeline2/README.md#f22-étendu--forensique-sur-fichier-réel-document_forensicspy)
  pour ce qui est fiable vs. simplement indicatif).
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

### ✅ Un seul backend (résolu)

Pipeline 2 (FastAPI) et Pipeline 3 (Flask) tournaient comme deux process
séparés, qui se seraient disputé le verrou mono-écrivain de DuckDB sur
`rakaba.duckdb`. Résolu : la logique de Pipeline 3 (`handlers.py`) est
maintenant servie par les deux — un adaptateur Flask (`pipeline3/app.py`,
toujours utilisable seul pour le dev) et un router FastAPI
(`pipeline3/router.py`) monté directement dans le `main.py` racine, à côté
du router Pipeline 2. `python -m uvicorn main:app` lance donc désormais tout
le backend (P2 + P3) en un seul process, un seul fichier DuckDB, comme le
prévoit le cahier des charges (§14). Vérifié de bout en bout : entité réelle
créée par Pipeline 1 → `/api/chat/client` classifie et escalade → visible
sur `/api/escalations` → `/api/investigate` gère correctement une entité
inconnue (404) — le tout dans le même process que les endpoints `/pipeline2/*`.

## Stack technique

- **Correspondance floue (P1)** : `rapidfuzz`
- **Persistance (P1, P2, P3)** : DuckDB partagé — fichier local unique, zéro configuration
- **Détection d'anomalie (P2)** : `scikit-learn` (Isolation Forest)
- **Graphe et GNN (P2)** : `NetworkX`, PyTorch Geometric (GraphSAGE, optionnel)
- **Backend unifié (P2 + P3)** : FastAPI + Uvicorn (`main.py`, racine du dépôt) —
  Pipeline 3 est aussi utilisable seule en Flask pour le développement
  (`pipeline3/app.py`), les deux servent la même logique (`pipeline3/handlers.py`)
- **IA conversationnelle et agent (P3)** : Groq (client compatible OpenAI), tool-use —
  note : le cahier des charges (§13) prévoyait Claude/API Anthropic ; le code
  actuel utilise Groq, à confirmer si c'est un choix définitif de l'équipe
- **Voix (P3)** : ElevenLabs (speech-to-text + text-to-speech), français/anglais/arabe —
  voir [`pipeline3/README.md`](pipeline3/README.md#voice-apivoicechatclient-apivoicechatadmin)
  pour ce qui fonctionne vraiment en dialecte tunisien (script arabe oui, transcription
  Arabizi non) et ce qui reste à valider
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

# Backend unifié : Pipeline 2 + Pipeline 3 dans le même process FastAPI
pip install -r requirements.txt
pip install -r pipeline3/requirements.txt
cp pipeline3/.env.example pipeline3/.env   # puis renseigner GROQ_API_KEY
uvicorn main:app --reload
# -> /pipeline2/*  (voir pipeline2/README.md)
# -> /api/chat/client, /api/chat/admin, /api/investigate, /api/escalations  (voir pipeline3/README.md)

# Pipeline 3 seule, en Flask (dev/tests indépendants, voir pipeline3/README.md)
cd pipeline3 && python app.py
```

Chaque pipeline documente ses propres détails, règles de scoring et points
d'intégration dans son `README.md`.
