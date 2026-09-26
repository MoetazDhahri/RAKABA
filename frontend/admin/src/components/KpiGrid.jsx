const CARDS = [
  {
    key: "total_detected",
    label: "Entités détectées",
    color: "primary",
    icon: (
      <>
        <circle cx="12" cy="8" r="4" />
        <path d="M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8" />
      </>
    ),
  },
  {
    key: "high_risk",
    label: "À risque élevé",
    color: "danger",
    icon: (
      <>
        <path d="M12 2 3 20h18L12 2z" />
        <path d="M12 10v4M12 17h.01" />
      </>
    ),
  },
  {
    key: "in_verification",
    label: "En cours de vérification",
    color: "warning",
    icon: (
      <>
        <rect x="5" y="3" width="14" height="18" rx="2" />
        <path d="M9 8h6M9 12h6M9 16h3" />
      </>
    ),
  },
  {
    key: "compliant",
    label: "En conformité",
    color: "success",
    icon: (
      <>
        <path d="M9 11l3 3L22 4" />
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
      </>
    ),
  },
];

export default function KpiGrid({ kpi }) {
  if (!kpi) return null;

  return (
    <section className="kpi-grid" aria-label="Indicateurs clés">
      {CARDS.map((card) => {
        const entry = kpi[card.key] || { value: 0, new_this_week: 0 };
        return (
          <div className="kpi-card" key={card.key}>
            <div className="kpi-top">
              <div className="kpi-icon" style={{ background: `var(--${card.color}-light)` }}>
                <svg viewBox="0 0 24 24" style={{ stroke: `var(--${card.color})` }}>{card.icon}</svg>
              </div>
              <div className="kpi-label">{card.label}</div>
            </div>
            <div className="kpi-value">{entry.value}</div>
            <div className={`kpi-trend ${entry.new_this_week === 0 ? "neutral" : ""}`}>
              {entry.new_this_week > 0 ? (
                <><strong>+{entry.new_this_week}</strong> cette semaine</>
              ) : (
                "Aucun changement cette semaine"
              )}
            </div>
          </div>
        );
      })}
    </section>
  );
}
