import { useState } from "react";
import { api, useFetch } from "../api";

export default function VerifierView() {
  const { data: entities } = useFetch("/pipeline1/entities");
  const { data: clusters, refetch: refetchClusters } = useFetch("/pipeline2/graph/clusters");

  const [selectedId, setSelectedId] = useState("");
  const { data: docs, refetch: refetchDocs } = useFetch(
    selectedId ? `/pipeline2/entities/${selectedId}/documents` : null,
    [selectedId]
  );

  const [file, setFile] = useState(null);
  const [montant, setMontant] = useState("5000");
  const [nbTransactions, setNbTransactions] = useState("3");
  const [activite, setActivite] = useState("8000");
  const [declaredDate, setDeclaredDate] = useState(new Date().toISOString().slice(0, 10));
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [lastResult, setLastResult] = useState(null);

  async function handleUpload(e) {
    e.preventDefault();
    if (!selectedId || !file) return;
    setUploading(true);
    setUploadError(null);
    setLastResult(null);
    try {
      const form = new FormData();
      form.append("entity_id", selectedId);
      form.append("montant", montant);
      form.append("nb_transactions", nbTransactions);
      form.append("activite_declaree", activite);
      form.append("declared_date", declaredDate);
      form.append("file", file);
      const result = await api.postForm("/pipeline2/documents/upload-file", form);
      setLastResult(result);
      refetchDocs();
      refetchClusters();
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="panel">
        <div className="view-header">
          <div>
            <h1>Vérifier — Scoring documentaire</h1>
            <p className="subtitle">Soumettre un document réel (PDF/image) pour une entité et consulter ses scores F2.2 à F2.5.</p>
          </div>
        </div>

        <div className="entity-picker" style={{ marginTop: 14 }}>
          <div className="form-row">
            <label htmlFor="entity-select">Entité</label>
            <select id="entity-select" className="select" value={selectedId} onChange={(e) => setSelectedId(e.target.value)}>
              <option value="">— sélectionner une entité —</option>
              {(entities || []).map((e) => (
                <option key={e.entity_id} value={e.entity_id}>{e.business_name} ({e.entity_id})</option>
              ))}
            </select>
          </div>
        </div>

        {selectedId && (
          <form onSubmit={handleUpload} style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="entity-picker">
              <div className="form-row">
                <label>Montant (DT)</label>
                <input className="textinput" type="number" value={montant} onChange={(e) => setMontant(e.target.value)} />
              </div>
              <div className="form-row">
                <label>Nb. transactions</label>
                <input className="textinput" type="number" value={nbTransactions} onChange={(e) => setNbTransactions(e.target.value)} />
              </div>
              <div className="form-row">
                <label>Activité déclarée (DT)</label>
                <input className="textinput" type="number" value={activite} onChange={(e) => setActivite(e.target.value)} />
              </div>
              <div className="form-row">
                <label>Date de déclaration</label>
                <input className="textinput" type="date" value={declaredDate} onChange={(e) => setDeclaredDate(e.target.value)} />
              </div>
              <div className="form-row">
                <label>Fichier (PDF/image)</label>
                <input type="file" accept=".pdf,image/*" onChange={(e) => setFile(e.target.files[0])} />
              </div>
              <button className="btn btn-primary" type="submit" disabled={!file || uploading}>
                {uploading ? "Analyse en cours…" : "Soumettre et scorer"}
              </button>
            </div>
            {uploadError && <p className="error-note">{uploadError}</p>}
          </form>
        )}

        {lastResult && (
          <div className="doc-card" style={{ marginTop: 14 }}>
            <div className="doc-card-head">
              <span>Résultat du scoring</span>
              <span
                className="composite-pill"
                style={{
                  background: lastResult.composite_score > 0.7 ? "var(--danger-light)" : lastResult.composite_score > 0.4 ? "var(--warning-light)" : "var(--success-light)",
                  color: lastResult.composite_score > 0.7 ? "var(--danger)" : lastResult.composite_score > 0.4 ? "#a56418" : "var(--success)",
                }}
              >
                composite {lastResult.composite_score?.toFixed(2)}
              </span>
            </div>
            <div className="chip-row">
              {[...lastResult.integrity.flags, ...lastResult.risk.flags].map((f, i) => <span className="chip" key={i}>{f}</span>)}
              {lastResult.integrity.flags.length === 0 && lastResult.risk.flags.length === 0 && <span className="chip">Aucun flag</span>}
            </div>
            {lastResult.content_forensics?.ela?.regions?.length > 0 && (
              <p className="drawer-subtitle">
                Analyse ELA : {lastResult.content_forensics.ela.regions.length} région(s) candidate(s) détectée(s) — à examiner visuellement, pas un verdict automatique.
              </p>
            )}
            {lastResult.content_forensics?.pdf_structure?.edited_after_finalization && (
              <p className="error-note">⚠ Ce PDF a été édité après sa finalisation (mises à jour incrémentales détectées).</p>
            )}
          </div>
        )}

        {selectedId && docs && (
          <div style={{ marginTop: 16 }}>
            <div className="drawer-section-title">Historique des documents de cette entité</div>
            {docs.total === 0 ? (
              <p className="drawer-subtitle">Aucun document soumis pour le moment.</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                {docs.documents.map((doc) => (
                  <div className="doc-card" key={doc.document_id}>
                    <div className="doc-card-head">
                      <span>{new Date(doc.submitted_date).toLocaleString("fr-FR")}</span>
                      <span className="composite-pill" style={{ background: "var(--bg)" }}>composite {doc.composite_score?.toFixed(2)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="panel">
        <div className="panel-header"><h2>Clusters de fraude en réseau (F2.6)</h2></div>
        {(!clusters || clusters.length === 0) ? (
          <p className="drawer-subtitle">Aucun cluster détecté — les entités ne partagent pas de téléphone/adresse pour le moment.</p>
        ) : (
          <div className="cluster-grid">
            {clusters.map((c) => (
              <div className="cluster-card" key={c.cluster_id}>
                <div className="cluster-head">
                  <span>Cluster #{c.cluster_id}</span>
                  <span className={`badge badge-${c.risk_level === "high" ? "eleve" : c.risk_level === "medium" ? "moyen" : "faible"}`}>
                    {c.risk_level === "high" ? "Élevé" : c.risk_level === "medium" ? "Moyen" : "Faible"}
                  </span>
                </div>
                <div className="chip-row">
                  {c.entity_ids.map((id) => <span className="chip" key={id}>{id}</span>)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
