import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import AudioReplyControl from "./AudioReplyControl";

function chatKey(email) {
  return `rakaba_client_chat_${email}`;
}

function loadChat(email) {
  try {
    return JSON.parse(localStorage.getItem(chatKey(email)) || "[]");
  } catch {
    return [];
  }
}

function saveChat(email, messages) {
  try {
    localStorage.setItem(chatKey(email), JSON.stringify(messages.slice(-40)));
  } catch {
    /* conversation stays usable for this session even if it can't persist */
  }
}

function initials(name) {
  return (name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
}

function TopBar({ account, onLogout }) {
  return (
    <header className="client-topbar">
      <img className="client-topbar-logo" src={`${import.meta.env.BASE_URL}logo.png`} alt="RAKABA — رقابة" />
      {account && (
        <div className="client-topbar-account">
          <div className="client-topbar-avatar">{initials(account.name || account.email)}</div>
          <span className="client-topbar-name">{account.name || account.email}</span>
          <button type="button" className="logout-btn" onClick={onLogout}>Se déconnecter</button>
        </div>
      )}
    </header>
  );
}

function AuthScreen({ onLogin }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", business_name: "", phone: "" });
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setSearching(true);
    setError(null);
    try {
      const path = mode === "login" ? "/api/auth/client/login" : "/api/auth/client/register";
      const result = await api.postJSON(path, form);
      if (mode === "register") {
        setMode("login");
        setError("Compte créé. Connectez-vous pour accéder à votre dossier.");
      } else {
        onLogin(result);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="search-screen">
      <img className="brand-mark" src={`${import.meta.env.BASE_URL}logo.png`} alt="RAKABA — رقابة" />
      <h1>{mode === "login" ? "Bienvenue dans votre espace RAKABA" : "Créer votre espace RAKABA"}</h1>
      <p className="lead">Un espace privé pour vérifier vos obligations fiscales tunisiennes et échanger avec l’assistant.</p>

      <form className="auth-form" onSubmit={handleSubmit}>
        <input
          type="text"
          type="email"
          placeholder="Votre email"
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          autoFocus
        />
        <input type="password" placeholder="Mot de passe" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        {mode === "register" && <>
          <input type="text" placeholder="Nom exact de l’entreprise" value={form.business_name} onChange={(e) => setForm({ ...form, business_name: e.target.value })} />
          <input type="tel" placeholder="Téléphone déclaré" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
        </>}
        <button type="submit" disabled={searching || !form.email || !form.password}>
          {searching ? "Patientez…" : mode === "login" ? "Se connecter" : "Créer mon compte"}
        </button>
      </form>

      {error && <p className="error-text">{error}</p>}
      <button type="button" className="link-btn auth-switch" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}>{mode === "login" ? "Créer un compte contribuable" : "J’ai déjà un compte"}</button>
    </div>
  );
}

function ChatPanel({ email, businessName }) {
  const [messages, setMessages] = useState(() => loadChat(email));
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [recording, setRecording] = useState(false);
  const [voiceError, setVoiceError] = useState(null);
  const scrollRef = useRef(null);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);

  useEffect(() => {
    saveChat(email, messages);
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [email, messages]);

  function history() {
    return messages.map(({ role, content }) => ({ role, content }));
  }

  async function send(text) {
    if (!text.trim() || sending) return;
    const h = history();
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setSending(true);
    try {
      const result = await api.postJSON("/api/chat/client", {
        message: text,
        conversation_history: h,
      });
      setMessages((prev) => [...prev, { role: "assistant", content: result.reply, escalated: result.escalated }]);
    } catch (err) {
      setMessages((prev) => [...prev, { role: "assistant", content: `Une erreur est survenue : ${err.message}` }]);
    } finally {
      setSending(false);
    }
  }

  async function sendVoice(blob) {
    setSending(true);
    setVoiceError(null);
    try {
      const form = new FormData();
      form.append("conversation_history", JSON.stringify(history()));
      form.append("audio", blob, "message.webm");
      const result = await api.postForm("/api/voice/chat/client", form);
      if (result.error) throw new Error(result.error);
      setMessages((prev) => [
        ...prev,
        { role: "user", content: result.transcript || "Message vocal" },
        { role: "assistant", content: result.reply, escalated: result.escalated, audioUrl: result.audio_base64 ? `data:audio/${result.audio_format || "mp3"};base64,${result.audio_base64}` : null },
      ]);
    } catch (err) {
      setVoiceError(err.message);
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
    setVoiceError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        sendVoice(new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" }));
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch (err) {
      setVoiceError(`Microphone inaccessible : ${err.message}`);
    }
  }

  return (
    <div className="chat-panel">
      <div className="chat-messages" ref={scrollRef}>
        {messages.length === 0 && (
          <p className="empty-text">
            Posez une question sur votre dossier {businessName} : documents à fournir, statut actuel, prochaines étapes…
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble bubble--${m.role}`}>
            {m.content}
            {m.escalated && <span className="escalated-tag">Transmis à un inspecteur</span>}
            {m.audioUrl && <AudioReplyControl audioUrl={m.audioUrl} />}
          </div>
        ))}
        {sending && <div className="bubble bubble--assistant">…</div>}
      </div>
      {voiceError && <p className="error-text" style={{ padding: "0 16px" }}>{voiceError}</p>}
      <div className="chat-input-row">
        <button
          type="button"
          className={`mic-btn ${recording ? "mic-btn--active" : ""}`}
          onClick={toggleRecording}
          title={recording ? "Arrêter" : "Parler à l'assistant"}
        >
          {recording ? "⏹" : "🎤"}
        </button>
        <textarea
          rows={1}
          placeholder={recording ? "Enregistrement…" : "Écrire votre question…"}
          value={input}
          disabled={recording}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
        />
        <button type="button" className="send-btn" onClick={() => send(input)} disabled={sending || recording || !input.trim()}>
          Envoyer
        </button>
      </div>
    </div>
  );
}

function DossierScreen({ account }) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get("/api/client/dossier")
      .then((result) => { if (!cancelled) setStatus(result); })
      .catch((err) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, []);

  if (error) {
    return (
      <div className="dossier-screen">
        <p className="error-text">{error}</p>
      </div>
    );
  }

  return (
    <div className="dossier-screen">
      <div className="dossier-header">
        <div>
          <span className="eyebrow">Votre dossier</span>
          <h1>{status?.name || "Chargement…"}</h1>
        </div>
        {status && <span className="status-pill">{status.status_label}</span>}
      </div>
      {status && <ChatPanel email={account.email} businessName={status.name} />}
    </div>
  );
}

export default function App() {
  const [account, setAccount] = useState(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    api.get("/api/auth/client/me").then(setAccount).catch(() => {}).finally(() => setChecking(false));
  }, []);

  async function logout() {
    await api.postJSON("/api/auth/client/logout", {});
    setAccount(null);
  }

  if (checking) {
    return (
      <div className="shell">
        <TopBar account={null} onLogout={logout} />
        <div className="client-main"><p className="empty-text">Chargement de votre espace…</p></div>
      </div>
    );
  }

  return (
    <div className="shell">
      <TopBar account={account} onLogout={logout} />
      <div className="client-main">
        {account ? <DossierScreen account={account} /> : <AuthScreen onLogin={setAccount} />}
      </div>
    </div>
  );
}
