import { useFetch } from "../api";
import { pipelineLabel } from "../utils/presentation";

export default function JournalView() {
  const { data, error, loading, refetch } = useFetch("/pipeline1/automation-log?limit=150");

  return (
    <div className="panel">
      <div className="view-header">
        <div>
          <h1>Journal d'automatisation</h1>
          <p className="subtitle">Retrouvez les actions récentes et leur état d’avancement.</p>
        </div>
        <button className="btn" type="button" onClick={refetch}>Actualiser</button>
      </div>

      {loading && <p className="loading-note">Chargement…</p>}
      {error && <p className="error-note">{error}</p>}

      {data && (
        <div className="journal-list" style={{ marginTop: 14 }}>
          {data.length === 0 && <p className="drawer-subtitle">Aucune action enregistrée pour le moment.</p>}
          {data.map((entry) => (
            <div className="journal-row" key={entry.log_id}>
              <span className={`journal-source journal-source--${entry.pipeline_source}`}>{pipelineLabel(entry.pipeline_source)}</span>
              <div className="journal-desc">
                {entry.action_description}
                {entry.entity_id && <div className="drawer-subtitle">Dossier associé</div>}
              </div>
              <span className="journal-time">
                {new Date(entry.timestamp).toLocaleString("fr-FR")} · {entry.triggered_by === "human" ? "Manuel" : "Auto"}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
