import { useEffect, useRef, useState } from "react";
import { api, useFetch } from "../api";
import EntitySearchSelect from "../components/EntitySearchSelect";
import FormattedText from "../components/FormattedText";
import AudioReplyControl from "../components/AudioReplyControl";
import { documentRiskLabel, humanRiskFlag } from "../utils/presentation";
import { useInspector } from "../context/InspectorContext";

const CHAT_KEY = "rakaba_dossier_chat_v1";
const MAX_FILE_BYTES = 15 * 1024 * 1024;

function loadDiscussion(entityId) {
  try {
    return JSON.parse(localStorage.getItem(`${CHAT_KEY}_${entityId}`) || "[]");
  } catch {
    return [];
  }
}

function saveDiscussion(entityId, messages) {
  try {
    localStorage.setItem(`${CHAT_KEY}_${entityId}`, JSON.stringify(messages.slice(-40)));
  } catch {
    // The conversation remains usable for the current session.
  }
}

function DossierDiscussion({ entityId, businessName }) {
  const { inspectorId } = useInspector();
  const [messages, setMessages] = useState(() => loadDiscussion(entityId));
  const [conversationId] = useState(() => {
    const key = `${CHAT_KEY}_conversation_${entityId}`;
    const existing = localStorage.getItem(key);
    if (existing) return existing;
    const created = crypto.randomUUID();
    localStorage.setItem(key, created);
    return created;
  });
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [recording, setRecording] = useState(false);
  const [voiceError, setVoiceError] = useState(null);
  const recorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  useEffect(() => saveDiscussion(entityId, messages), [entityId, messages]);

  async function sendMessage() {
    const text = input.trim();
    if (!text || sending) return;
    const history = messages.map(({ role, content }) => ({ role, content }));
    setMessages((current) => [...current, { role: "user", content: text }]);
    setInput("");
    setSending(true);
    try {
      const result = await api.postJSON("/api/chat/admin", {
        inspector_id: inspectorId,
        message: text,
        conversation_history: history,
        context_entity_id: entityId,
        conversation_id: conversationId,
      });
      setMessages((current) => [...current, { role: "assistant", content: result.reply }]);
    } catch (error) {
      setMessages((current) => [...current, { role: "assistant", content: `Je n'ai pas pu répondre : ${error.message}` }]);
    } finally {
      setSending(false);
    }
  }

  async function sendVoice(blob) {
    setSending(true);
    setVoiceError(null);
    try {
      const form = new FormData();
      form.append("inspector_id", inspectorId);
      form.append("context_entity_id", entityId);
      form.append("conversation_id", conversationId);
      form.append("conversation_history", JSON.stringify(messages.map(({ role, content }) => ({ role, content }))));
      form.append("audio", blob, "message.webm");
      const result = await api.postForm("/api/voice/chat/admin", form);
      if (result.error) throw new Error(result.error);
      const audioUrl = result.audio_base64 ? `data:audio/${result.audio_format || "mp3"};base64,${result.audio_base64}` : null;
      setMessages((current) => [...current, { role: "user", content: result.transcript || "Message vocal" }, { role: "assistant", content: result.reply, audioUrl }]);
    } catch (error) {
      setVoiceError(error.message);
    } finally {
      setSending(false);
    }
  }

  async function toggleRecording() {
    if (recording) {
      recorderRef.current?.stop();
      setRecording(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      audioChunksRef.current = [];
      recorder.ondataavailable = (event) => { if (event.data.size > 0) audioChunksRef.current.push(event.data); };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        sendVoice(new Blob(audioChunksRef.current, { type: recorder.mimeType || "audio/webm" }));
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch (error) {
      setVoiceError(`Microphone inaccessible : ${error.message}`);
    }
  }

  return (
    <section className="dossier-chat">
      <div className="panel-header">
        <div>
          <h2>Discussion avec l’assistant</h2>
          <p className="helper-text">Posez une question sur {businessName}. L’assistant garde le fil de cette analyse.</p>
        </div>
        <span className="assistant-status"><i className="dot dot-online" />Dossier actif</span>
      </div>
      <div className="dossier-chat-messages">
        {messages.length === 0 && <p className="empty-state">Demandez pourquoi cette suite est proposée, ce qu’il faut vérifier ensuite ou quelles informations manquent.</p>}
        {messages.map((message, index) => <div key={index} className={`chat-bubble chat-bubble--${message.role === "user" ? "user" : "assistant"}`}>{message.role === "assistant" ? <FormattedText text={message.content} /> : message.content}{message.audioUrl && <AudioReplyControl audioUrl={message.audioUrl} />}</div>)}
        {sending && <div className="chat-bubble chat-bubble--assistant">Je relis les éléments du dossier…</div>}
      </div>
      <div className="dossier-chat-input">
        <textarea rows={2} value={input} placeholder="Poursuivre la discussion…" onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendMessage(); } }} />
        <button className={`mic-btn ${recording ? "mic-btn--active" : ""}`} type="button" onClick={toggleRecording} title={recording ? "Arrêter l’enregistrement" : "Parler à l’assistant"}>{recording ? "⏹" : "🎤"}</button>
        <button className="btn btn-primary" type="button" onClick={sendMessage} disabled={!input.trim() || sending}>Envoyer</button>
      </div>
      {voiceError && <p className="error-note">{voiceError}</p>}
    </section>
  );
}

function DecisionPanel({ analysis, onFollowUp, actionMessage, actionBusy }) {
  const decision = analysis?.decision;
  if (!decision) return null;
  return (
    <div className="decision-panel">
      <div className="decision-heading">
        <div><span className="eyebrow">Avis de l’assistant</span><h2>{decision.recommendation}</h2></div>
        <span className="confidence-pill">Confiance : {decision.confidence}</span>
      </div>
      <div className="decision-grid">
        <div><h3>Ce qui soutient cet avis</h3><ul>{decision.arguments.map((argument, index) => <li key={index}>{argument}</li>)}</ul></div>
        <div><h3>Suite proposée</h3><ul>{decision.next_actions.map((action, index) => <li key={index}>{action}</li>)}</ul></div>
      </div>
      <p className="helper-text">Cet avis aide à prioriser le travail. La décision finale reste à l’inspecteur.</p>
      <div className="decision-actions">
        <button className="btn btn-primary" type="button" onClick={onFollowUp} disabled={actionBusy}>{actionBusy ? "Mise à jour…" : "Mettre le dossier en suivi"}</button>
        {actionMessage && <span className="helper-text">{actionMessage}</span>}
      </div>
    </div>
  );
}

export default function VerifierView() {
  const { inspectorId } = useInspector();
  const { data: entities } = useFetch("/pipeline1/entities");
  const { data: clusters } = useFetch("/pipeline2/graph/clusters");
  const [file, setFile] = useState(null);
  const [intake, setIntake] = useState(null);
  const [selectedId, setSelectedId] = useState("");
  const [montant, setMontant] = useState("");
  const [nbTransactions, setNbTransactions] = useState("");
  const [activite, setActivite] = useState("");
  const [declaredDate, setDeclaredDate] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [lastResult, setLastResult] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [actionMessage, setActionMessage] = useState(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const selectedEntity = (entities || []).find((entity) => entity.entity_id === selectedId);
  const { data: docs } = useFetch(selectedId ? `/pipeline2/entities/${selectedId}/documents` : null, [selectedId]);

  function selectFile(candidate) {
    if (!candidate) return;
    const isPdf = candidate.type === "application/pdf" || candidate.name.toLowerCase().endsWith(".pdf");
    const isImage = candidate.type.startsWith("image/");
    if (!isPdf && !isImage) {
      setError("Choisissez un fichier PDF ou une image.");
      return;
    }
    if (candidate.size > MAX_FILE_BYTES) {
      setError("Le fichier est trop volumineux. La taille maximale est de 15 Mo.");
      return;
    }
    setFile(candidate);
    setError(null);
    setIntake(null);
    setSelectedId("");
  }

  async function prepareDocument(event) {
    event.preventDefault();
    if (!file || uploading) return;
    setUploading(true);
    setError(null);
    setIntake(null);
    setLastResult(null);
    setAnalysis(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await api.postForm("/pipeline2/documents/intake", form);
      setIntake(result);
      if (result.candidates?.length === 1 && !result.requires_confirmation) setSelectedId(result.candidates[0].entity_id);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setUploading(false);
    }
  }

  async function analyzeDocument(event) {
    event.preventDefault();
    if (!selectedId || !file || uploading) return;
    if (!montant || !nbTransactions || !activite || !declaredDate) {
      setError("Complétez les quatre paramètres pour obtenir une analyse fiable.");
      return;
    }
    setUploading(true);
    setError(null);
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
      try {
        const dossierAnalysis = await api.postJSON("/api/investigate", { inspector_id: inspectorId, entity_id: selectedId, document_id: result.document_id });
        setAnalysis(dossierAnalysis);
      } catch (analysisError) {
        setError(`Le document est enregistré, mais l’avis détaillé n’a pas pu être généré : ${analysisError.message}`);
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setUploading(false);
    }
  }

  async function moveToFollowUp() {
    if (!selectedId || actionBusy) return;
    setActionBusy(true);
    setActionMessage(null);
    try {
      await api.postJSON(`/pipeline1/entities/${selectedId}/transition`, {
        new_status: "En regularisation",
        note: "Suivi recommandé après analyse documentaire.",
      });
      setActionMessage("Le dossier est maintenant en suivi.");
    } catch (requestError) {
      setActionMessage(`La mise à jour a échoué : ${requestError.message}`);
    } finally {
      setActionBusy(false);
    }
  }

  return (
    <div className="verifier-layout">
      <section className="panel verifier-intake">
        <div className="view-header"><div><span className="eyebrow">Vérifier</span><h1>Comprendre un document, décider de la suite</h1><p className="subtitle">Déposez d’abord votre PDF ou votre image. RAKABA cherchera le dossier correspondant et vous guidera ensuite.</p></div></div>
        <form className={`upload-dropzone ${isDragging ? "is-dragging" : ""}`} onSubmit={prepareDocument} onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }} onDragLeave={() => setIsDragging(false)} onDrop={(event) => { event.preventDefault(); setIsDragging(false); selectFile(event.dataTransfer.files?.[0]); }}>
          <div className="upload-icon" aria-hidden="true">↑</div>
          <strong>{file ? file.name : "Déposez un document à analyser"}</strong>
          <span>PDF ou image · vous pourrez confirmer le dossier ensuite</span>
          <label className="btn" htmlFor="document-file">Choisir un fichier</label>
          <input id="document-file" type="file" accept=".pdf,image/*" onChange={(event) => selectFile(event.target.files?.[0])} />
          <button className="btn btn-primary" type="submit" disabled={!file || uploading}>{uploading ? "Lecture du document…" : "Préparer l’analyse"}</button>
        </form>

        {intake && <div className="intake-result"><div className="panel-header"><div><h2>Document reconnu</h2><p className="helper-text">{intake.text_detected ? "Du texte exploitable a été trouvé dans le fichier." : "Aucun texte exploitable n’a été trouvé ; choisissez le dossier manuellement."}</p></div><span className="muted-tag">{intake.filename}</span></div>{intake.candidates?.length > 0 ? <div className="candidate-list">{intake.candidates.map((candidate) => <button type="button" className={`candidate-row ${selectedId === candidate.entity_id ? "selected" : ""}`} key={candidate.entity_id} onClick={() => setSelectedId(candidate.entity_id)}><span><strong>{candidate.business_name}</strong><small>{candidate.location || "Localisation inconnue"}</small></span><span className="candidate-confidence">{Math.round(candidate.confidence * 100)}% de correspondance</span></button>)}</div> : <p className="empty-state">Aucun dossier n’a pu être proposé automatiquement.</p>}<div className="form-row intake-manual-choice"><label>Dossier à analyser</label><EntitySearchSelect entities={entities} value={selectedId} onChange={setSelectedId} placeholder="Rechercher une entreprise…" /></div></div>}

        {intake && selectedId && <form className="analysis-form" onSubmit={analyzeDocument}><div className="selected-dossier"><span className="eyebrow">Dossier sélectionné</span><strong>{selectedEntity?.business_name || "Dossier choisi"}</strong></div><details open><summary>Paramètres complémentaires <span>Ils améliorent la précision de l’analyse</span></summary><div className="parameter-grid"><label>Montant déclaré (DT)<input className="textinput" type="number" min="0" value={montant} onChange={(event) => setMontant(event.target.value)} /><small>Montant indiqué sur le document.</small></label><label>Nombre de transactions<input className="textinput" type="number" min="0" value={nbTransactions} onChange={(event) => setNbTransactions(event.target.value)} /><small>Sur la période concernée.</small></label><label>Activité déclarée (DT)<input className="textinput" type="number" min="0" value={activite} onChange={(event) => setActivite(event.target.value)} /><small>Chiffre déclaré pour comparaison.</small></label><label>Date de déclaration<input className="textinput" type="date" value={declaredDate} onChange={(event) => setDeclaredDate(event.target.value)} /><small>Date officielle de dépôt.</small></label></div></details><button className="btn btn-primary" type="submit" disabled={uploading}>{uploading ? "Analyse approfondie…" : "Lancer l’analyse complète"}</button></form>}
        {error && <p className="error-note">{error}</p>}
      </section>

      {lastResult && <section className="analysis-layout"><div className="panel analysis-summary"><div className="panel-header"><div><span className="eyebrow">Résultat</span><h2>Ce que le document nous dit</h2></div><span className="risk-badge">{documentRiskLabel(lastResult.composite_score)}</span></div><div className="analysis-metrics"><div><span>Intégrité</span><strong>{Math.round(lastResult.integrity.score * 100)}%</strong><small>État du fichier</small></div><div><span>Cohérence</span><strong>{Math.round(lastResult.coherence.score * 100)}%</strong><small>Avec les données connues</small></div><div><span>Points à examiner</span><strong>{lastResult.integrity.flags.length + lastResult.risk.flags.length}</strong><small>Pas un verdict automatique</small></div></div><div className="chip-row">{[...lastResult.integrity.flags, ...lastResult.risk.flags].map((flag, index) => <span className="chip" key={index}>{humanRiskFlag(flag)}</span>)}{lastResult.integrity.flags.length === 0 && lastResult.risk.flags.length === 0 && <span className="chip">Aucun point prioritaire</span>}</div></div><DecisionPanel analysis={analysis} onFollowUp={moveToFollowUp} actionMessage={actionMessage} actionBusy={actionBusy} />{analysis?.report && <div className="panel report-panel"><span className="eyebrow">Synthèse</span><h2>Lecture du dossier</h2><FormattedText text={analysis.report} /></div>}<DossierDiscussion entityId={selectedId} businessName={selectedEntity?.business_name || "ce dossier"} />{docs?.total > 0 && <div className="panel"><div className="panel-header"><h2>Documents précédemment analysés</h2><span className="muted-tag">{docs.total}</span></div><p className="helper-text">Les analyses précédentes restent disponibles dans le dossier de l’entreprise.</p></div>}</section>}

      <section className="panel"><div className="panel-header"><div><span className="eyebrow">Contexte</span><h2>Réseaux d’entités liées</h2></div></div>{(!clusters || clusters.length === 0) ? <p className="empty-state">Aucun lien partagé n’a été détecté pour le moment.</p> : <div className="cluster-grid">{clusters.map((cluster) => <div className="cluster-card" key={cluster.cluster_id}><div className="cluster-head"><strong>Réseau {cluster.cluster_id}</strong><span className="muted-tag">{cluster.size} entités</span></div><div className="chip-row">{cluster.entity_ids.map((id) => <span className="chip" key={id}>{(entities || []).find((entity) => entity.entity_id === id)?.business_name || "Entité liée"}</span>)}</div></div>)}</div>}</section>
    </div>
  );
}
