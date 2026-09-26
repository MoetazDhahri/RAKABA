import { useState } from "react";
import { api, useFetch } from "../api";

const STATUSES = ["Detecte", "Contacte", "En regularisation", "Conforme", "Contribuable de confiance"];
const STATUS_LABEL = {
  "Detecte": "Détecté",
  "Contacte": "Contacté",
  "En regularisation": "En régularisation",
  "Conforme": "Conforme",
  "Contribuable de confiance": "Contribuable de confiance",
};

function scoreColor(score) {
  if (score == null) return "#98a2b3";
  if (score >= 80) return "#279a63";
  if (score >= 40) return "#e8963a";
  return "#e0473f";
}

export default function EntityDrawer({ entityId, onClose, onInvestigate, onJumpTo }) {
  const { data: detail, error, loading, refetch } = useFetch(`/pipeline1/entities/${entityId}`, [entityId]);
  const { data: links } = useFetch(`/pipeline1/entities/${entityId}/links`, [entityId]);
  const { data: docs } = useFetch(`/pipeline2/entities/${entityId}/documents`, [entityId]);

  const [newStatus, setNewStatus] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  async function handleTransition() {
    if (!newStatus) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await api.postJSON(`/pipeline1/entities/${entityId}/transition`, { new_status: newStatus, note: note || null });
      setNote("");
      setNewStatus("");
      refetch();
    } catch (err) {
      setSubmitError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer-panel" onClick={(e) => e.stopPropagation()}>
        {loading && <p className="loading-note">Chargement…</p>}
        {error && <p className="error-note">{error}</p>}

        {detail && (
          <>
            <div className="drawer-header">
              <div>
                <div className="drawer-title">{detail.business_name}</div>
                <div className="drawer-subtitle">{detail.entity_id} · {STATUS_LABEL[detail.status] || detail.status}</div>
              </div>
              <button className="drawer-close" type="button" onClick={onClose}>&times;</button>
            </div>

            <div className="drawer-section">
              <div className="drawer-section-title">Correspondance registre (F1.3)</div>
              <div className="score-bar-row">
                <div className="score-bar-label"><span>Score de correspondance</span><strong>{detail.match_score?.toFixed(1) ?? "—"}</strong></div>
                <div className="score-bar-track">
                  <div className="score-bar-fill" style={{ width: `${Math.min(100, detail.match_score || 0)}%`, background: scoreColor(detail.match_score) }} />
                </div>
              </div>
              {detail.notes && <div className="drawer-subtitle">{detail.notes}</div>}
            </div>

            <div className="drawer-section">
              <div className="drawer-section-title">Coordonnées</div>
              <dl className="kv-grid">
                <div><dt>Téléphone</dt><dd>{detail.phone}</dd></div>
                <div><dt>Plateforme</dt><dd>{detail.source_platform}</dd></div>
                <div style={{ gridColumn: "1 / -1" }}><dt>Adresse</dt><dd>{detail.location_text}</dd></div>
                <div style={{ gridColumn: "1 / -1" }}><dt>Activité</dt><dd>{detail.activity_description}</dd></div>
              </dl>
            </div>

            {links && links.length > 0 && (
              <div className="drawer-section">
                <div className="drawer-section-title">Entités liées (F1.6)</div>
                <div className="chip-row">
                  {links.map((l) => (
                    <span key={l.entity_id} className="chip chip--link" onClick={() => onJumpTo(l.entity_id)}>
                      {l.entity_id} · {l.shared_attribute}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="drawer-section">
              <div className="drawer-section-title">Documents (Pipeline 2)</div>
              {!docs || docs.total === 0 ? (
                <p className="drawer-subtitle">Aucun document soumis pour le moment.</p>
              ) : (
                docs.documents.map((doc) => (
                  <div className="doc-card" key={doc.document_id}>
                    <div className="doc-card-head">
                      <span>{new Date(doc.submitted_date).toLocaleDateString("fr-FR")}</span>
                      <span
                        className="composite-pill"
                        style={{
                          background: doc.composite_score > 0.7 ? "var(--danger-light)" : doc.composite_score > 0.4 ? "var(--warning-light)" : "var(--success-light)",
                          color: doc.composite_score > 0.7 ? "var(--danger)" : doc.composite_score > 0.4 ? "#a56418" : "var(--success)",
                        }}
                      >
                        composite {doc.composite_score?.toFixed(2)}
                      </span>
                    </div>
                    <div className="score-bar-row">
                      <div className="score-bar-label"><span>Intégrité</span><span>{doc.integrity.score.toFixed(2)}</span></div>
                      <div className="score-bar-track"><div className="score-bar-fill" style={{ width: `${doc.integrity.score * 100}%`, background: "var(--primary)" }} /></div>
                    </div>
                    <div className="score-bar-row">
                      <div className="score-bar-label"><span>Cohérence</span><span>{doc.coherence.score.toFixed(2)}</span></div>
                      <div className="score-bar-track"><div className="score-bar-fill" style={{ width: `${doc.coherence.score * 100}%`, background: "var(--success)" }} /></div>
                    </div>
                    {(doc.integrity.flags.length > 0 || doc.risk.flags.length > 0) && (
                      <div className="chip-row">
                        {[...doc.integrity.flags, ...doc.risk.flags].map((f, i) => <span className="chip" key={i}>{f}</span>)}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

            {detail.history && detail.history.length > 0 && (
              <div className="drawer-section">
                <div className="drawer-section-title">Historique</div>
                <div className="timeline">
                  {detail.history.slice().reverse().map((h) => (
                    <div className="timeline-row" key={h.log_id}>
                      <span className={`timeline-dot ${h.triggered_by === "human" ? "timeline-dot--human" : ""}`} />
                      <div className="timeline-text">
                        {h.action_description}
                        <div className="timeline-meta">{new Date(h.timestamp).toLocaleString("fr-FR")} · {h.triggered_by === "human" ? "Manuel" : "Automatique"}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="drawer-section">
              <div className="drawer-section-title">Actions (F1.8)</div>
              <div className="form-row">
                <label htmlFor="new-status">Forcer le statut</label>
                <select id="new-status" className="select" value={newStatus} onChange={(e) => setNewStatus(e.target.value)}>
                  <option value="">— choisir —</option>
                  {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
                </select>
              </div>
              <div className="form-row">
                <label htmlFor="note">Note (optionnel)</label>
                <textarea id="note" className="textarea" value={note} onChange={(e) => setNote(e.target.value)} />
              </div>
              {submitError && <p className="error-note">{submitError}</p>}
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-primary" type="button" disabled={!newStatus || submitting} onClick={handleTransition}>
                  {submitting ? "…" : "Appliquer"}
                </button>
                <button className="btn" type="button" onClick={() => onInvestigate(entityId)}>Enquêter</button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
