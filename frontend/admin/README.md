# RAKABA — Interface Admin (React)

Interface Admin d'Amira : vue d'ensemble (carte de Tunisie, KPI, alertes),
tableau kanban du cycle de vie (Pipeline 1), scoring documentaire et clusters
de fraude (Pipeline 2), chatbot interne + agent d'investigation (Pipeline 3),
et journal d'automatisation. Aucune donnée fictive côté frontend — tout vient
des endpoints réels du backend unifié (`main.py`, racine du dépôt).

## Développement

```bash
npm install
npm run dev
```

Ouvre sur `http://localhost:5173/admin/` (ou le prochain port libre). Le
serveur de dev Vite proxy `/pipeline1`, `/pipeline2` et `/api` vers
`http://localhost:8000` (voir `vite.config.js`) — **le backend FastAPI doit
tourner en parallèle** (`uvicorn main:app`, depuis la racine du dépôt) pour
que les appels réseau fonctionnent.

## Build de production

```bash
npm run build
```

Génère `dist/`, servi directement par le backend unifié sur `/admin` (voir
`main.py` — `StaticFiles` monté sur `frontend/admin/dist`). `dist/` n'est pas
versionné : lancer ce build après un `git clone` avant de démarrer
`uvicorn main:app` pour que `/admin` existe, sinon cette route est
simplement absente (pas d'erreur bruyante, juste rien monté).

## Structure

```
src/
├── App.jsx                    # routage entre vues (état local, pas de react-router)
├── api.js                     # fetch + hooks (useDashboardOverview, useFetch)
├── data/tunisiaPaths.js       # 24 gouvernorats (source: @svg-maps/tunisia, licence libre)
├── components/                # Vue d'ensemble : Sidebar, Topbar, KpiGrid, MapPanel,
│                               # RegionList, AlertList, EvolutionChart, DonutChart, RiskTable
└── views/
    ├── DecouvrirView.jsx      # Kanban (F1.7) + EntityDrawer (détail, F1.8 forçage manuel)
    ├── EntityDrawer.jsx       # Score F1.3, entités liées F1.6, documents P2, historique
    ├── VerifierView.jsx       # Upload fichier réel -> scoring F2.2-F2.5, clusters F2.6
    ├── AccompagnerView.jsx    # Chat admin, agent d'investigation (trace + rapport), escalades
    └── JournalView.jsx        # Journal d'automatisation cross-pipeline
```

« Détection », « Vérification » et « Investigations » dans la barre latérale
sont des alias de Découvrir/Vérifier/Accompagner (même donnée réelle, pas de
vue dupliquée) — voir `VIEW_ALIASES` dans `App.jsx`.

## Carte de Tunisie

Attribution région ↔ gouvernorat faite côté backend
(`pipeline1/dashboard.py::match_governorate`) par correspondance de mots-clés
sur l'adresse en texte libre — pas de géocodage réel, le schéma n'a pas de
colonne région structurée. Une adresse qui ne mentionne aucun gouvernorat par
son nom atterrit sous « non-attribué » plutôt que d'être devinée.

## Note de concurrence (important si vous touchez au backend)

Le premier passage de cette UI a révélé un vrai bug de concurrence : trois
pipelines partagent une seule connexion DuckDB (voir `pipeline1/db.py`), et
une connexion DuckDB n'est pas sûre pour un accès concurrent multi-thread.
FastAPI exécute les routes synchrones dans un pool de threads, donc plusieurs
requêtes simultanées du frontend (ce qui arrive à chaque chargement de page)
pouvaient renvoyer des résultats corrompus par intermittence. Fixé avec un
verrou (`pipeline1.db.LOCK`) partagé par les trois pipelines, tenu pendant
toute la durée de chaque requête. Si vous ajoutez un nouvel endpoint FastAPI
qui touche la base partagée, sa dépendance `get_db()` doit acquérir ce même
verrou — copier le pattern de `pipeline1/router.py` ou `pipeline2/database.py`.
