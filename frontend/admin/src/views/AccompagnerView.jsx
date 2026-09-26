import { useEffect, useRef, useState } from "react";
import { api, useFetch } from "../api";
import EntitySearchSelect from "../components/EntitySearchSelect";
import FormattedText from "../components/FormattedText";
import AudioReplyControl from "../components/AudioReplyControl";
import { useInspector } from "../context/InspectorContext";

const CHAT_STORAGE_KEY = "rakaba_admin_chat_v1";
const MAX_STORED_MESSAGES = 60;

function loadStoredMessages() {
  try {
    const raw = localStorage.getItem(CHAT_STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveStoredMessages(messages) {
  try {
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(messages.slice(-MAX_STORED_MESSAGES)));
  } catch {
    /* localStorage unavailable (private browsing, quota) - memory just won't persist */
  }
}

function ChatTab() {
  const { inspectorId } = useInspector();
  const { data: entities } = useFetch("/pipeline1/entities");
  const [messages, setMessages] = useState(loadStoredMessages);
  const [conversationId] = useState(() => {
    const existing = localStorage.getItem("rakaba_admin_conversation_id");
    if (existing) return existing;
    const created = crypto.randomUUID();
    localStorage.setItem("rakaba_admin_conversation_id", created);
    return created;
  });
  const [input, setInput] = useState("");
  const [selectedEntityId, setSelectedEntityId] = useState("");
  const [file, setFile] = useState(null);
  const [sending, setSending] = useState(false);
  const [recording, setRecording] = useState(false);
  const [voiceError, setVoiceError] = useState(null);
  const scrollRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
    saveStoredMessages(messages);
  }, [messages]);

  function historyPayload() {
    return messages.map((m) => ({ role: m.role, content: m.content }));
  }

  async function handleSend(nextText = input) {
    const text = nextText.trim();
    if (!text || sending) return;
    const history = historyPayload();
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setSending(true);
    try {
      const result = await api.postJSON("/api/chat/admin", {
        inspector_id: inspectorId,
        message: text,
        conversation_history: history,
        conversation_id: conversationId,
      });
      setMessages((prev) => [...prev, { role: "assistant", content: result.reply }]);
    } catch (err) {
      setMessages((prev) => [...prev, { role: "assistant", content: `Erreur : ${err.message}` }]);
    } finally {
      setSending(false);
    }
  }

  async function handleFileUpload() {
    if (!file || !selectedEntityId || sending) return;
    setSending(true);
    try {
      const form = new FormData();
      form.append("entity_id", selectedEntityId);
      form.append("montant", "0");
      form.append("nb_transactions", "0");
      form.append("activite_declaree", "0");
      form.append("declared_date", new Date().toISOString().slice(0, 10));
      form.append("file", file);
      await api.postForm("/pipeline2/documents/upload-file", form);
      const selected = entities?.find((entity) => entity.entity_id === selectedEntityId);
      const history = historyPayload();
      setMessages((prev) => [...prev, { role: "user", content: `Document partage : ${file.name}` }]);
      const message = `Le document ${file.name} vient d'etre ajoute pour ${selected?.business_name || "ce dossier"}. Analyse-le et explique-moi les points importants.`;
      setFile(null);
      const result = await api.postJSON("/api/chat/admin", {
        inspector_id: inspectorId,
        message,
        conversation_history: history,
        conversation_id: conversationId,
      });
      setMessages((prev) => [...prev, { role: "assistant", content: result.reply }]);
    } catch (err) {
      setMessages((prev) => [...prev, { role: "assistant", content: `Je n'ai pas pu analyser ce document : ${err.message}` }]);
    } finally {
      setSending(false);
    }
  }

  async function startRecording() {
    setVoiceError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      audioChunksRef.current = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType || "audio/webm" });
        sendVoiceMessage(blob);
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch (err) {
      setVoiceError("Microphone inaccessible : " + err.message);
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  }

  async function sendVoiceMessage(blob) {
    setSending(true);
    setVoiceError(null);
    const history = historyPayload();
    try {
      const form = new FormData();
      form.append("inspector_id", inspectorId);
      form.append("conversation_history", JSON.stringify(history));
      form.append("conversation_id", conversationId);
      form.append("audio", blob, "message.webm");
      const result = await api.postForm("/api/voice/chat/admin", form);

      if (result.error) {
        setVoiceError(result.error);
        return;
      }

      setMessages((prev) => [...prev, { role: "user", content: result.transcript || "(audio)" }]);
      const audioUrl = result.audio_base64 ? `data:audio/${result.audio_format || "mp3"};base64,${result.audio_base64}` : null;
      setMessages((prev) => [...prev, { role: "assistant", content: result.reply, audioUrl }]);
    } catch (err) {
      setVoiceError(err.message);
    } finally {
      setSending(false);
    }
  }

  function clearHistory() {
    setMessages([]);
    saveStoredMessages([]);
  }

  return (
    <div>
      <div className="chat-toolbar">
          <label className="chat-attach-btn" title="Ajouter un document">
            <span aria-hidden="true">＋</span>
            <input type="file" accept=".pdf,image/*" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          </label>
        <span className="drawer-subtitle">La conversation est mémorisée localement (persiste au rechargement).</span>
        {messages.length > 0 && <button className="btn btn-sm" type="button" onClick={clearHistory}>Effacer l'historique</button>}
      </div>
      <div className="chat-shell">
        <div className="chat-messages" ref={scrollRef}>
          {messages.length === 0 && (
            <div className="chat-welcome">
              <p className="drawer-subtitle">Parlez naturellement avec l’assistant. Il peut retrouver les dossiers récents, comparer les éléments et garder le fil de votre discussion.</p>
              <div className="chat-suggestions">
                {["Quelles sont les nouvelles détections ?", "Quels dossiers dois-je examiner en priorité ?", "Explique-moi les derniers documents analysés."].map((prompt) => <button type="button" key={prompt} onClick={() => handleSend(prompt)}>{prompt}</button>)}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`chat-bubble chat-bubble--${m.role === "user" ? "user" : "assistant"}`}>
              {m.role === "assistant" ? <FormattedText text={m.content} /> : m.content}
              {m.audioUrl && <AudioReplyControl audioUrl={m.audioUrl} />}
            </div>
          ))}
          {sending && <div className="chat-bubble chat-bubble--assistant">…</div>}
        </div>
        {voiceError && <p className="error-note" style={{ padding: "0 12px" }}>{voiceError}</p>}
        <div className="chat-input-bar">
          <button
            type="button"
            className={`mic-btn ${recording ? "mic-btn--active" : ""}`}
            onClick={recording ? stopRecording : startRecording}
            title={recording ? "Arrêter l'enregistrement" : "Parler à l'assistant"}
          >
            {recording ? "⏹" : "🎤"}
          </button>
          <textarea
            rows={2}
            placeholder={recording ? "Enregistrement en cours…" : "Écrire un message…"}
            value={input}
            disabled={recording}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
          />
          <button className="btn btn-primary" type="button" onClick={() => handleSend()} disabled={sending || recording || !input.trim()}>Envoyer</button>
        </div>
        {file && (
          <div className="chat-upload-row">
            <span>{file.name}</span>
            <select value={selectedEntityId} onChange={(e) => setSelectedEntityId(e.target.value)} aria-label="Dossier concerne">
              <option value="">Choisir le dossier</option>
              {(entities || []).map((entity) => <option key={entity.entity_id} value={entity.entity_id}>{entity.business_name}</option>)}
            </select>
            <button className="btn btn-primary" type="button" onClick={handleFileUpload} disabled={!selectedEntityId || sending}>Analyser</button>
          </div>
        )}
      </div>
    </div>
  );
}

function InvestigateTab({ initialEntityId }) {
  const { inspectorId } = useInspector();
  const { data: entities } = useFetch("/pipeline1/entities");
  const [selectedId, setSelectedId] = useState(initialEntityId || "");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (initialEntityId) setSelectedId(initialEntityId);
  }, [initialEntityId]);

  async function handleInvestigate() {
    if (!selectedId) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.postJSON("/api/investigate", { inspector_id: inspectorId, entity_id: selectedId });
      setResult(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <div className="entity-picker">
        <div className="form-row">
          <label>Entité à enquêter</label>
          <EntitySearchSelect entities={entities} value={selectedId} onChange={setSelectedId} />
        </div>
        <button className="btn btn-primary" type="button" disabled={!selectedId || running} onClick={handleInvestigate}>
          {running ? "Investigation en cours…" : "Enquêter"}
        </button>
      </div>

      {error && <p className="error-note" style={{ marginTop: 12 }}>{error}</p>}

      {result && (
        <div style={{ marginTop: 18, display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <div className="drawer-section-title" style={{ marginBottom: 8 }}>Analyse</div>
            <div className="report-box"><FormattedText text={result.report} /></div>
          </div>
        </div>
      )}
    </div>
  );
}

function EscalationsTab() {
  const { data, loading, error } = useFetch("/api/escalations");
  const escalations = data?.escalations || [];

  return (
    <div>
      {loading && <p className="loading-note">Chargement…</p>}
      {error && <p className="error-note">{error}</p>}
      {!loading && escalations.length === 0 && <p className="drawer-subtitle">Aucune question client escaladée pour le moment.</p>}
      {escalations.length > 0 && (
        <div className="journal-list">
          {escalations.map((esc) => (
            <div className="journal-row" key={esc.escalation_id}>
              <span className="journal-source journal-source--pipeline3">Demande à traiter</span>
              <div className="journal-desc">
                <div>{esc.message}</div>
                <div className="drawer-subtitle">Dossier associé</div>
              </div>
              <span className="journal-time">{new Date(esc.timestamp).toLocaleString("fr-FR")}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AccompagnerView({ initialEntityId, initialTab }) {
  const [tab, setTab] = useState(initialTab || "chat");

  useEffect(() => {
    if (initialTab) setTab(initialTab);
  }, [initialTab]);

  return (
    <div className="panel">
      <div className="view-header">
        <div>
          <h1>Assistant RAKABA</h1>
          <p className="subtitle">Discutez des dossiers tunisiens, des obligations fiscales et des prochaines actions à mener.</p>
        </div>
      </div>

      <div className="tabs" style={{ marginTop: 14 }}>
        <button className={`tab-btn ${tab === "chat" ? "active" : ""}`} type="button" onClick={() => setTab("chat")}>Assistant</button>
        <button className={`tab-btn ${tab === "investigate" ? "active" : ""}`} type="button" onClick={() => setTab("investigate")}>Analyse de dossier</button>
        <button className={`tab-btn ${tab === "escalations" ? "active" : ""}`} type="button" onClick={() => setTab("escalations")}>Questions escaladées</button>
      </div>

      {tab === "chat" && <ChatTab />}
      {tab === "investigate" && <InvestigateTab initialEntityId={initialEntityId} />}
      {tab === "escalations" && <EscalationsTab />}
    </div>
  );
}
