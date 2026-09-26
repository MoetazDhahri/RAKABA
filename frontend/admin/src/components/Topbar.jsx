export default function Topbar({ title, subtitle, alertCount, searchTerm, onSearchChange }) {
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
        <button className="icon-btn" title="Notifications" type="button">
          <svg viewBox="0 0 24 24"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></svg>
          {alertCount > 0 && <span className="badge-dot">{alertCount}</span>}
        </button>
        <div className="user-chip">
          <div className="avatar avatar-sm">AB</div>
          <span>Amira Ben Salem</span>
        </div>
      </div>
    </header>
  );
}
