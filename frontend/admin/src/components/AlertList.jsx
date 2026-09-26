const SEVERITY_COLOR = {
  danger: "danger",
  warning: "warning",
  info: "info",
};

const TYPE_ICON = {
  reseau_fraude: <><path d="M12 2 3 20h18L12 2z" /><path d="M12 10v4M12 17h.01" /></>,
  declaration_incoherente: <><circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" /></>,
  activite_non_declaree: <><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></>,
  document_suspect: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 8h6M9 12h6M9 16h3" /></>,
};

export default function AlertList({ alerts }) {
  return (
    <div className="panel">
      <div className="panel-header"><h2>Dernières alertes</h2></div>
      {(!alerts || alerts.length === 0) ? (
        <div className="empty-state">Aucune alerte récente.</div>
      ) : (
        <ul className="alert-list">
          {alerts.map((a, i) => {
            const color = SEVERITY_COLOR[a.severity] || "info";
            return (
              <li className="alert-row" key={i}>
                <div className="alert-icon" style={{ background: `var(--${color}-light)` }}>
                  <svg viewBox="0 0 24 24" style={{ stroke: `var(--${color})` }}>{TYPE_ICON[a.type]}</svg>
                </div>
                <div>
                  <div className="alert-title">{a.title}</div>
                  <div className="alert-meta">
                    {a.region ? `Région ${a.region}` : "Région inconnue"}
                    {a.entity_name ? ` · ${a.entity_name}` : ""} · {a.relative_time}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
