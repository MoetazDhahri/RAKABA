import { useEffect, useMemo, useState } from "react";
import { useDashboardOverview, useFetch } from "./api";
import { InspectorProvider } from "./context/InspectorContext";
import Login from "./components/Login";
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

const INSPECTOR_STORAGE_KEY = "rakaba_inspector";

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

function OverviewView({ data, error, loading, searchTerm, selectedRegion, onRegionSelect }) {
  const regionId = selectedRegion?.governorate_id || "";
  const { data: regionEntities, loading: regionLoading } = useFetch(
    regionId ? `/pipeline1/entities?status_filter=Detecte&location_filter=${encodeURIComponent(regionId)}` : null,
    [regionId]
  );
  const filteredEntities = useMemo(() => {
    let entities = data?.top_risk_entities || [];
    if (selectedRegion) {
      entities = entities.filter((e) => e.region === selectedRegion.governorate_name);
    }
    const term = searchTerm.trim().toLowerCase();
    if (!term) return entities;
    return entities.filter((e) =>
      [e.name, e.region, e.status].filter(Boolean).some((v) => v.toLowerCase().includes(term))
    );
  }, [data, searchTerm, selectedRegion]);

  return (
    <>
      {error && !data && (
        <div className="stub-banner">Impossible de charger les données : {error}. Le backend tourne-t-il (uvicorn main:app) ?</div>
      )}

      <KpiGrid kpi={data?.kpi} />

      <section className="grid-2col">
        <MapPanel regions={data?.regions} onRegionSelect={onRegionSelect} selectedRegionId={selectedRegion?.governorate_id} />
        <div className="side-col">
          <RegionList regions={data?.regions} />
          <AlertList alerts={data?.alerts} />
        </div>
      </section>

      {selectedRegion && (
        <section className="panel region-detections">
          <div className="panel-header">
            <div><span className="eyebrow">Région sélectionnée</span><h2>Nouvelles détections — {selectedRegion.governorate_name}</h2></div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span className="muted-tag">{regionLoading ? "Chargement…" : `${regionEntities?.length || 0} dossier(s)`}</span>
              <button type="button" className="btn btn-sm" onClick={() => onRegionSelect(null)}>Réinitialiser</button>
            </div>
          </div>
          <p className="drawer-subtitle" style={{ margin: "0 0 10px" }}>Le tableau « Top entités à risque » ci-dessous est aussi filtré sur cette région.</p>
          {!regionLoading && (!regionEntities || regionEntities.length === 0) ? (
            <p className="empty-state">Aucune nouvelle détection dans cette région.</p>
          ) : (
            <div className="region-detection-list">
              {(regionEntities || []).map((entity) => (
                <div className="region-detection-row" key={entity.entity_id}>
                  <div><strong>{entity.business_name}</strong><span>{entity.location_text || "Localisation non précisée"}</span></div>
                  <div><span className="badge badge-status">À vérifier</span><small>{entity.status_updated_at ? new Date(entity.status_updated_at).toLocaleDateString("fr-FR") : "Date inconnue"}</small></div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      <section className="grid-3col">
        <div className="panel">
          <div className="panel-header"><h2>Évolution des détections</h2><span className="muted-tag">7 jours</span></div>
          <div className="chart-holder"><EvolutionChart evolution={data?.evolution} /></div>
        </div>
        <div className="panel">
          <div className="panel-header"><h2>Activité par parcours</h2></div>
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

function Dashboard({ inspector, onLogout }) {
  const { data, error, loading } = useDashboardOverview();
  const [activeView, setActiveView] = useState("overview");
  const [searchTerm, setSearchTerm] = useState("");
  const [investigateEntityId, setInvestigateEntityId] = useState(null);
  const [selectedRegion, setSelectedRegion] = useState(null);

  const resolvedView = VIEW_ALIASES[activeView] || "overview";

  function handleNavigate(view) {
    setActiveView(view);
    if (view !== "investigations") setInvestigateEntityId(null);
    if (view !== "overview") setSelectedRegion(null);
  }

  function handleInvestigate(entityId) {
    setInvestigateEntityId(entityId);
    setActiveView("investigations");
  }

  const titles = {
    overview: { title: "Carte des entités — Tunisie", subtitle: "Visualisez les activités détectées, les entités à risque et leur statut de traitement." },
    decouvrir: { title: "Découvrir", subtitle: "Détection et cycle de vie des entités." },
    verifier: { title: "Vérifier", subtitle: "Analyse documentaire et liens entre entités." },
    accompagner: { title: "Assistant RAKABA", subtitle: "Dossiers, obligations fiscales tunisiennes et prochaines actions." },
    investigations: { title: "Analyse de dossier", subtitle: "Éléments vérifiés et suite proposée." },
    journal: { title: "Journal des actions", subtitle: "Suivi des actions réalisées sur les dossiers." },
  };
  const header = titles[resolvedView] || titles.overview;

  return (
    <div className="shell">
      <Sidebar activeView={activeView} onNavigate={handleNavigate} inspectorName={inspector.displayName} />

      <main className="main">
        <Topbar
          title={header.title}
          subtitle={header.subtitle}
          alerts={data?.alerts}
          searchTerm={searchTerm}
          onSearchChange={setSearchTerm}
          inspectorName={inspector.displayName}
          onLogout={onLogout}
        />

        {resolvedView === "overview" && <OverviewView data={data} error={error} loading={loading} searchTerm={searchTerm} selectedRegion={selectedRegion} onRegionSelect={setSelectedRegion} />}
        {resolvedView === "decouvrir" && <DecouvrirView onInvestigate={handleInvestigate} />}
        {resolvedView === "verifier" && <VerifierView />}
        {resolvedView === "accompagner" && <AccompagnerView />}
        {resolvedView === "investigations" && <AccompagnerView initialEntityId={investigateEntityId} initialTab="investigate" />}
        {resolvedView === "journal" && <JournalView />}
      </main>
    </div>
  );
}

export default function App() {
  const [inspector, setInspector] = useState(null);
  const [checkedStorage, setCheckedStorage] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(INSPECTOR_STORAGE_KEY);
      if (raw) setInspector(JSON.parse(raw));
    } catch {
      /* ignore - fall back to the login screen */
    } finally {
      setCheckedStorage(true);
    }
  }, []);

  function handleLogin(result) {
    const value = { inspectorId: result.inspector_id, displayName: result.display_name };
    setInspector(value);
    try {
      localStorage.setItem(INSPECTOR_STORAGE_KEY, JSON.stringify(value));
    } catch {
      /* localStorage unavailable - session still works, just won't survive a reload */
    }
  }

  function handleLogout() {
    setInspector(null);
    try {
      localStorage.removeItem(INSPECTOR_STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }

  if (!checkedStorage) return null;
  if (!inspector) return <Login onLogin={handleLogin} />;

  return (
    <InspectorProvider value={{ ...inspector, logout: handleLogout }}>
      <Dashboard inspector={inspector} onLogout={handleLogout} />
    </InspectorProvider>
  );
}
