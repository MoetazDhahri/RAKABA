import { useState } from "react";
import { useFetch } from "../api";
import EntityDrawer from "./EntityDrawer";

const COLUMNS = [
  { key: "Detecte", label: "Détecté" },
  { key: "Contacte", label: "Contacté" },
  { key: "En regularisation", label: "En régularisation" },
  { key: "Conforme", label: "Conforme" },
  { key: "Contribuable de confiance", label: "Contribuable de confiance" },
];

export default function DecouvrirView({ onInvestigate }) {
  const { data, error, loading, refetch } = useFetch("/pipeline1/kanban");
  const [selectedEntity, setSelectedEntity] = useState(null);

  function handleInvestigate(entityId) {
    setSelectedEntity(null);
    onInvestigate(entityId);
  }

  return (
    <div className="panel">
      <div className="view-header">
        <div>
          <h1>Découvrir — Tableau de détection</h1>
          <p className="subtitle">Cycle de vie des entités détectées, de la première correspondance au statut de confiance.</p>
        </div>
        <button className="btn" type="button" onClick={refetch}>Actualiser</button>
      </div>

      {loading && <p className="loading-note">Chargement…</p>}
      {error && <p className="error-note">{error}</p>}

      {data && (
        <div className="kanban-board" style={{ marginTop: 16 }}>
          {COLUMNS.map((col) => {
            const cards = data[col.key] || [];
            return (
              <div className="kanban-column" key={col.key}>
                <div className="kanban-column-header">
                  <span>{col.label}</span>
                  <span className="kanban-count">{cards.length}</span>
                </div>
                <div className="kanban-cards">
                  {cards.length === 0 && <div className="kanban-empty">Aucune entité</div>}
                  {cards.map((card) => (
                    <div className="kanban-card" key={card.entity_id} onClick={() => setSelectedEntity(card.entity_id)}>
                      <div className="kanban-card-title">{card.business_name}</div>
                      <div className="kanban-card-meta">
                        <span>{card.location_text?.split(",").pop()?.trim()}</span>
                        <span>{card.match_score != null ? card.match_score.toFixed(0) : "—"}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {selectedEntity && (
        <EntityDrawer
          entityId={selectedEntity}
          onClose={() => { setSelectedEntity(null); refetch(); }}
          onInvestigate={handleInvestigate}
          onJumpTo={(id) => setSelectedEntity(id)}
        />
      )}
    </div>
  );
}
