export default function RegionList({ regions }) {
  const top = (regions || []).slice(0, 6);

  return (
    <div className="panel">
      <div className="panel-header"><h2>Centres / régions</h2></div>
      {top.length === 0 ? (
        <div className="empty-state">Aucune entité détectée pour le moment.</div>
      ) : (
        <ul className="region-list">
          {top.map((r) => (
            <li className="region-row" key={r.governorate_id}>
              <span className="region-name">
                <span className={`dot dot-${r.eleve > 0 ? "eleve" : r.moyen > 0 ? "moyen" : r.traite > 0 ? "traite" : "faible"}`} />
                {r.governorate_name}
              </span>
              <span>
                <span className="region-count">{r.total}</span>{" "}
                <span className="region-sub">entité{r.total > 1 ? "s" : ""}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
