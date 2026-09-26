import { useState } from "react";
import { api } from "../api";

export default function Login({ onLogin }) {
  const [inspectorId, setInspectorId] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    const id = inspectorId.trim().toLowerCase();
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.postJSON("/api/auth/inspector", { inspector_id: id });
      onLogin(result);
    } catch (err) {
      setError(err.message || "Identifiant non reconnu.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-shell">
      <form className="login-card" onSubmit={handleSubmit}>
        <img className="login-logo" src={`${import.meta.env.BASE_URL}logo.png`} alt="RAKABA — رقابة" />
        <p className="login-subtitle">Espace inspecteur</p>
        <label className="login-label" htmlFor="inspector-id">Identifiant inspecteur</label>
        <input
          id="inspector-id"
          className="textinput"
          type="text"
          autoFocus
          placeholder="ex. amira"
          value={inspectorId}
          onChange={(e) => setInspectorId(e.target.value)}
        />
        {error && <p className="error-note">{error}</p>}
        <button className="btn btn-primary login-submit" type="submit" disabled={loading || !inspectorId.trim()}>
          {loading ? "Connexion…" : "Se connecter"}
        </button>
        <p className="login-hint">Accès démo réservé aux inspecteurs RAKABA enregistrés.</p>
      </form>
    </div>
  );
}
