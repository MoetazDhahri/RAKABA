const WIDTH = 320;
const HEIGHT = 130;
const PAD_X = 8;
const PAD_TOP = 12;
const PAD_BOTTOM = 22;

function formatDay(iso) {
  const d = new Date(iso + "T00:00:00");
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function EvolutionChart({ evolution }) {
  if (!evolution || evolution.length === 0) {
    return <div className="empty-state">Pas encore de données.</div>;
  }

  const max = Math.max(1, ...evolution.map((e) => e.count));
  const innerW = WIDTH - PAD_X * 2;
  const innerH = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const step = evolution.length > 1 ? innerW / (evolution.length - 1) : 0;

  const points = evolution.map((e, i) => {
    const x = PAD_X + step * i;
    const y = PAD_TOP + innerH - (e.count / max) * innerH;
    return { x, y, ...e };
  });

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L ${points[points.length - 1].x.toFixed(1)} ${PAD_TOP + innerH} L ${points[0].x.toFixed(1)} ${PAD_TOP + innerH} Z`;

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} width="100%" height={HEIGHT} role="img" aria-label="Évolution des détections sur 7 jours">
      <defs>
        <linearGradient id="evoFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#2d5fdb" stopOpacity="0.22" />
          <stop offset="100%" stopColor="#2d5fdb" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill="url(#evoFill)" />
      <path d={linePath} fill="none" stroke="#2d5fdb" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      {points.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="3.2" fill="#2d5fdb" stroke="white" strokeWidth="1.2" />
      ))}
      {points.map((p, i) => (
        <text key={`t-${i}`} x={p.x} y={HEIGHT - 4} textAnchor="middle" fontSize="9.5" fill="#98a2b3">
          {formatDay(p.date)}
        </text>
      ))}
    </svg>
  );
}
