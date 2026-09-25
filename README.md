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

| Pipeline | Rôle | Défis | Propriétaire |
|---|---|---|---|
| **1 — Découvrir** | Détecte les activités non déclarées par recoupement de signaux publics avec le registre fiscal, et suit chaque entité à travers un cycle de vie de régularisation | T11, T4 | Moetaz |
| **2 — Vérifier** | Score chaque document soumis (intégrité, cohérence, schéma à risque) et relie les entités dans un graphe pour détecter la fraude organisée | T6, T3, T16 | Khalil |
| **3 — Accompagner** | Chatbot fiscal + agent d'investigation autonome (tool-calling) qui enquête sur une entité flaguée et rédige un rapport pour l'inspecteur | T9, T14 | Choch |

Une seule base de données partagée (DuckDB), trois pipelines qui l'alimentent,
deux interfaces pour la consulter — une pour l'inspecteur (Amira, dense et
analytique), une pour le contribuable (Youssef, simple et bienveillante,
jamais accusatrice).

## État d'avancement

- ✅ **Pipeline 1 — Découvrir** : complet (branche [`gafsi's-work`](../../tree/gafsi's-work)).
  Moteur de correspondance floue, schéma DuckDB, générateur de signaux
  synthétiques, machine à états du cycle de vie, liaison d'entités, API de
  lecture, ordonnanceur de démo, 19 tests. Voir [`pipeline1/README.md`](pipeline1/README.md).
- ⏳ **Pipeline 2 — Vérifier** : à venir (Khalil).
- ⏳ **Pipeline 3 — Accompagner** : à venir (Choch).

## Stack technique

- **Correspondance floue (P1)** : `rapidfuzz`
- **Détection d'anomalie (P2)** : `scikit-learn` (Isolation Forest)
- **Graphe et GNN (P2)** : `NetworkX`, PyTorch Geometric
- **Base de données** : DuckDB — fichier local unique, zéro configuration, partagé par les trois pipelines
- **Backend** : Python (FastAPI)
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
```

Détails complets, règles de scoring, cycle de vie et points d'intégration
entre pipelines : [`pipeline1/README.md`](pipeline1/README.md).
