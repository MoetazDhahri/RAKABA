import { useEffect, useRef, useState } from "react";
import { api, useFetch } from "../api";

function ChatTab() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  async function handleSend() {
    const text = input.trim();
    if (!text || sending) return;
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setSending(true);
    try {
      const result = await api.postJSON("/api/chat/admin", {
        inspector_id: "amira",
        message: text,
        conversation_history: history,
      });
      setMessages((prev) => [...prev, { role: "assistant", content: result.reply }]);
    } catch (err) {
      setMessages((prev) => [...prev, { role: "assistant", content: `Erreur : ${err.message}` }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="chat-shell">
      <div className="chat-messages" ref={scrollRef}>
        {messages.length === 0 && (
          <p className="drawer-subtitle">Posez une question à l'assistant interne (méthodologie, cycle de vie, terminologie RAKABA…).</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`chat-bubble chat-bubble--${m.role === "user" ? "user" : "assistant"}`}>{m.content}</div>
        ))}
        {sending && <div className="chat-bubble chat-bubble--assistant">…</div>}
      </div>
      <div className="chat-input-bar">
        <textarea
          rows={2}
          placeholder="Écrire un message…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
        />
        <button className="btn btn-primary" type="button" onClick={handleSend} disabled={sending || !input.trim()}>Envoyer</button>
      </div>
    </div>
  );
}

function InvestigateTab({ initialEntityId }) {
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
      const res = await api.postJSON("/api/investigate", { inspector_id: "amira", entity_id: selectedId });
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
          <select className="select" value={selectedId} onChange={(e) => setSelectedId(e.target.value)}>
            <option value="">— sélectionner —</option>
            {(entities || []).map((e) => (
              <option key={e.entity_id} value={e.entity_id}>{e.business_name} ({e.entity_id})</option>
            ))}
          </select>
        </div>
        <button className="btn btn-primary" type="button" disabled={!selectedId || running} onClick={handleInvestigate}>
          {running ? "Investigation en cours…" : "Enquêter"}
        </button>
      </div>

      {error && <p className="error-note" style={{ marginTop: 12 }}>{error}</p>}

      {result && (
        <div style={{ marginTop: 18, display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <div className="drawer-section-title" style={{ marginBottom: 8 }}>Trace de raisonnement ({result.evidence_log.length} outil{result.evidence_log.length > 1 ? "s" : ""} appelé{result.evidence_log.length > 1 ? "s" : ""})</div>
            <div className="trace-list">
              {result.evidence_log.map((step, i) => (
                <div className="trace-step" key={i}>
                  <div className="trace-step-head">
                    <span>🔧</span>{step.tool}
                  </div>
                  <div className="trace-step-args">Arguments : {JSON.stringify(step.arguments)}</div>
                  <div className="trace-step-result">{JSON.stringify(step.result, null, 2)}</div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="drawer-section-title" style={{ marginBottom: 8 }}>Rapport final</div>
            <div className="report-box">{result.report}</div>
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
              <span className="journal-source journal-source--pipeline3">{esc.reason}</span>
              <div className="journal-desc">
                <div>{esc.message}</div>
                <div className="drawer-subtitle">Entité {esc.entity_id}</div>
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
          <h1>Accompagner — Chatbot &amp; investigation</h1>
          <p className="subtitle">Assistant interne, agent d'investigation autonome, et questions clients escaladées.</p>
        </div>
      </div>

      <div className="tabs" style={{ marginTop: 14 }}>
        <button className={`tab-btn ${tab === "chat" ? "active" : ""}`} type="button" onClick={() => setTab("chat")}>Chat inspecteur</button>
        <button className={`tab-btn ${tab === "investigate" ? "active" : ""}`} type="button" onClick={() => setTab("investigate")}>Agent d'investigation</button>
        <button className={`tab-btn ${tab === "escalations" ? "active" : ""}`} type="button" onClick={() => setTab("escalations")}>Questions escaladées</button>
      </div>

      {tab === "chat" && <ChatTab />}
      {tab === "investigate" && <InvestigateTab initialEntityId={initialEntityId} />}
      {tab === "escalations" && <EscalationsTab />}
    </div>
  );
}
