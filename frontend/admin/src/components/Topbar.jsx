import { useEffect, useRef, useState } from "react";

const SEVERITY_DOT = { danger: "var(--danger)", warning: "var(--warning)", info: "var(--primary)" };

function initials(name) {
  return (name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
}

export default function Topbar({ title, subtitle, alerts, searchTerm, onSearchChange, inspectorName, onLogout }) {
  const [open, setOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const rootRef = useRef(null);
  const userRef = useRef(null);
  const list = alerts || [];

  useEffect(() => {
    function handleClickOutside(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
      if (userRef.current && !userRef.current.contains(e.target)) setUserMenuOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <header className="topbar">
      <div>
        <h1>{title}</h1>
        <p className="subtitle">{subtitle}</p>
      </div>
      <div className="topbar-actions">
        <div className="search-box">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></svg>
          <input
            type="text"
            placeholder="Rechercher une entité, un statut, une région…"
            value={searchTerm}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        </div>
        <div className="notif-root" ref={rootRef}>
          <button className="icon-btn" title="Notifications" type="button" onClick={() => setOpen((o) => !o)}>
            <svg viewBox="0 0 24 24"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></svg>
            {list.length > 0 && <span className="badge-dot">{list.length}</span>}
          </button>
          {open && (
            <div className="notif-dropdown">
              <div className="notif-dropdown-head">Dernières alertes</div>
              {list.length === 0 ? (
                <div className="notif-empty">Aucune alerte récente.</div>
              ) : (
                <div className="notif-list">
                  {list.map((a, i) => (
                    <div className="notif-row" key={i}>
                      <span className="notif-dot" style={{ background: SEVERITY_DOT[a.severity] || "var(--primary)" }} />
                      <div>
                        <div className="notif-title">{a.title}</div>
                        <div className="notif-meta">
                          {a.entity_name ? `${a.entity_name} · ` : ""}
                          {a.region ? `Région ${a.region} · ` : ""}
                          {a.relative_time}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        <div className="notif-root" ref={userRef}>
          <button type="button" className="user-chip" onClick={() => setUserMenuOpen((o) => !o)}>
            <div className="avatar avatar-sm">{initials(inspectorName)}</div>
            <span>{inspectorName || "Inspecteur"}</span>
          </button>
          {userMenuOpen && (
            <div className="notif-dropdown user-menu-dropdown">
              <button type="button" className="user-menu-item" onClick={onLogout}>Déconnexion</button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
