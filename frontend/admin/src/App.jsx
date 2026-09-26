import { useMemo, useState } from "react";
import { useDashboardOverview } from "./api";
import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";
import KpiGrid from "./components/KpiGrid";
import MapPanel from "./components/MapPanel";
import RegionList from "./components/RegionList";
import AlertList from "./components/AlertList";
import EvolutionChart from "./components/EvolutionChart";
import DonutChart from "./components/DonutChart";
import RiskTable from "./components/RiskTable";
import DecouvrirView from "./views/DecouvrirView";
import VerifierView from "./views/VerifierView";
import AccompagnerView from "./views/AccompagnerView";
import JournalView from "./views/JournalView";

// Sidebar item id -> (view component key, tab). "Détection" is the same
// underlying pipeline as "Découvrir", "Vérification" the same as "Vérifier",
// "Investigations" is Accompagner's investigation-agent tab specifically -
// aliased rather than duplicated, since they're the same real backend data.
const VIEW_ALIASES = {
  overview: "overview",
  decouvrir: "decouvrir",
  detection: "decouvrir",
  verifier: "verifier",
  verification: "verifier",
  accompagner: "accompagner",
  investigations: "investigations",
  journal: "journal",
};

function OverviewView({ data, error, loading, searchTerm }) {
  const filteredEntities = useMemo(() => {
    const entities = data?.top_risk_entities || [];
    const term = searchTerm.trim().toLowerCase();
    if (!term) return entities;
    return entities.filter((e) =>
      [e.name, e.region, e.status].filter(Boolean).some((v) => v.toLowerCase().includes(term))
    );
  }, [data, searchTerm]);

  return (
    <>
      {error && !data && (
        <div className="stub-banner">Impossible de charger les données : {error}. Le backend tourne-t-il (uvicorn main:app) ?</div>
      )}

      <KpiGrid kpi={data?.kpi} />

      <section className="grid-2col">
        <MapPanel regions={data?.regions} />
        <div className="side-col">
          <RegionList regions={data?.regions} />
          <AlertList alerts={data?.alerts} />
        </div>
      </section>

      <section className="grid-3col">
        <div className="panel">
          <div className="panel-header"><h2>Évolution des détections</h2><span className="muted-tag">7 jours</span></div>
          <div className="chart-holder"><EvolutionChart evolution={data?.evolution} /></div>
        </div>
        <div className="panel">
          <div className="panel-header"><h2>Répartition par pipeline</h2></div>
          <div className="chart-holder chart-holder--center"><DonutChart distribution={data?.pipeline_distribution} /></div>
        </div>
        <div className="panel">
          <div className="panel-header"><h2>Top entités à risque</h2></div>
          <table className="risk-table">
            <thead><tr><th>Entité</th><th>Région</th><th>Niveau</th><th>Statut</th></tr></thead>
            <RiskTable entities={filteredEntities} />
          </table>
        </div>
      </section>

      <footer className="foot-note">
        {loading ? "Chargement…" : "RAKABA — données synthétiques, aucune information réelle ou confidentielle. Rafraîchi automatiquement toutes les 15s."}
      </footer>
    </>
  );
}

export default function App() {
  const { data, error, loading } = useDashboardOverview();
  const [activeView, setActiveView] = useState("overview");
  const [searchTerm, setSearchTerm] = useState("");
  const [investigateEntityId, setInvestigateEntityId] = useState(null);

  const resolvedView = VIEW_ALIASES[activeView] || "overview";

  function handleNavigate(view) {
    setActiveView(view);
    if (view !== "investigations") setInvestigateEntityId(null);
  }

  function handleInvestigate(entityId) {
    setInvestigateEntityId(entityId);
    setActiveView("investigations");
  }

  const titles = {
    overview: { title: "Carte des entités — Tunisie", subtitle: "Visualisez les activités détectées, les entités à risque et leur statut de traitement." },
    decouvrir: { title: "Découvrir", subtitle: "Détection et cycle de vie des entités." },
    verifier: { title: "Vérifier", subtitle: "Scoring documentaire et graphe de fraude." },
    accompagner: { title: "Accompagner", subtitle: "Chatbot, investigation et suivi." },
    investigations: { title: "Accompagner", subtitle: "Chatbot, investigation et suivi." },
    journal: { title: "Journal d'automatisation", subtitle: "Historique de toutes les actions du système." },
  };
  const header = titles[resolvedView] || titles.overview;

  return (
    <div className="shell">
      <Sidebar activeView={activeView} onNavigate={handleNavigate} />

      <main className="main">
        <Topbar
          title={header.title}
          subtitle={header.subtitle}
          alertCount={data?.alerts?.length || 0}
          searchTerm={searchTerm}
          onSearchChange={setSearchTerm}
        />

        {resolvedView === "overview" && <OverviewView data={data} error={error} loading={loading} searchTerm={searchTerm} />}
        {resolvedView === "decouvrir" && <DecouvrirView onInvestigate={handleInvestigate} />}
        {resolvedView === "verifier" && <VerifierView />}
        {resolvedView === "accompagner" && <AccompagnerView />}
        {resolvedView === "investigations" && <AccompagnerView initialEntityId={investigateEntityId} initialTab="investigate" />}
        {resolvedView === "journal" && <JournalView />}
      </main>
    </div>
  );
}
