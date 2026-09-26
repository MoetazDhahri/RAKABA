const PIPELINE_ITEMS = [
  {
    id: "decouvrir",
    title: "Découvrir",
    subtitle: "Activités non déclarées",
    icon: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="M21 21l-4.3-4.3" />
      </>
    ),
  },
  {
    id: "verifier",
    title: "Vérifier",
    subtitle: "Documents & cohérence",
    icon: (
      <>
        <rect x="5" y="3" width="14" height="18" rx="2" />
        <path d="M9 8h6M9 12h6M9 16h3" />
      </>
    ),
  },
  {
    id: "accompagner",
    title: "Accompagner",
    subtitle: "Conformité & suivi",
    icon: (
      <>
        <path d="M12 2a5 5 0 1 1 0 10 5 5 0 0 1 0-10z" />
        <path d="M4 22c0-4.4 3.6-8 8-8s8 3.6 8 8" />
      </>
    ),
  },
];

const FEATURE_ITEMS = [
  { id: "detection", title: "Détection", icon: <><circle cx="12" cy="12" r="3" /><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z" /></> },
  { id: "verification", title: "Vérification", icon: <><path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" /></> },
  { id: "investigations", title: "Investigations", icon: <><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></> },
  { id: "journal", title: "Journal d'automatisation", icon: <><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></> },
];

function initials(name) {
  return (name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
}

export default function Sidebar({ activeView, onNavigate, inspectorName }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <img className="brand-logo" src={`${import.meta.env.BASE_URL}logo.png`} alt="RAKABA — رقابة" />
      </div>

      <div className="user-card">
        <div className="avatar">{initials(inspectorName)}</div>
        <div>
          <div className="user-name">{inspectorName || "Inspecteur"}</div>
          <div className="user-role"><span className="dot dot-online" />Inspecteur RAKABA</div>
        </div>
      </div>

      <nav className="nav">
        <a
          href="#"
          className={`nav-item ${activeView === "overview" ? "active" : ""}`}
          onClick={(e) => { e.preventDefault(); onNavigate("overview"); }}
        >
          <svg className="nav-icon" viewBox="0 0 24 24"><path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" /></svg>
          Vue d'ensemble
        </a>

        <div className="nav-group-label">Parcours métier</div>
        {PIPELINE_ITEMS.map((item) => (
          <a
            key={item.id}
            href="#"
            className="nav-item nav-item--stub"
            onClick={(e) => { e.preventDefault(); onNavigate(item.id); }}
          >
            <svg className="nav-icon" viewBox="0 0 24 24">{item.icon}</svg>
            <span className="nav-item-title">{item.title}<small>{item.subtitle}</small></span>
          </a>
        ))}

        <div className="nav-group-label">Outils</div>
        {FEATURE_ITEMS.map((item) => (
          <a
            key={item.id}
            href="#"
            className="nav-item nav-item--stub"
            onClick={(e) => { e.preventDefault(); onNavigate(item.id); }}
          >
            <svg className="nav-icon" viewBox="0 0 24 24">{item.icon}</svg>
            {item.title}
          </a>
        ))}
      </nav>

      <div className="sidebar-footer">
        <a href="#" className="nav-item nav-item--stub" onClick={(e) => e.preventDefault()}>
          <svg className="nav-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></svg>
          Paramètres
        </a>
        <a href="#" className="nav-item nav-item--stub" onClick={(e) => e.preventDefault()}>
          <svg className="nav-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" /><path d="M9.1 9a3 3 0 0 1 5.82 1c0 2-3 2-3 4M12 17h.01" /></svg>
          Aide
        </a>
      </div>
    </aside>
  );
}
