const SEGMENTS = [
  { key: "decouvrir", label: "Découvrir", color: "#132130" },
  { key: "verifier", label: "Vérifier", color: "#e8963a" },
  { key: "accompagner", label: "Accompagner", color: "#279a63" },
];

const SIZE = 150;
const STROKE = 20;
const RADIUS = (SIZE - STROKE) / 2;
const CIRC = 2 * Math.PI * RADIUS;

export default function DonutChart({ distribution }) {
  if (!distribution) return null;

  const total = SEGMENTS.reduce((sum, s) => sum + (distribution[s.key] || 0), 0);
  let offset = 0;

  return (
    <>
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} width="150" height="150">
        <circle cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} fill="none" stroke="#eef1f6" strokeWidth={STROKE} />
        {total > 0 && SEGMENTS.map((s) => {
          const value = distribution[s.key] || 0;
          const frac = value / total;
          const dash = frac * CIRC;
          const el = (
            <circle
              key={s.key}
              cx={SIZE / 2}
              cy={SIZE / 2}
              r={RADIUS}
              fill="none"
              stroke={s.color}
              strokeWidth={STROKE}
              strokeDasharray={`${dash} ${CIRC - dash}`}
              strokeDashoffset={-offset}
              transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
              strokeLinecap={frac > 0 && frac < 1 ? "butt" : "round"}
            />
          );
          offset += dash;
          return el;
        })}
        <text x={SIZE / 2} y={SIZE / 2 - 6} textAnchor="middle" fontSize="22" fontWeight="800" fill="#16213a">{total}</text>
        <text x={SIZE / 2} y={SIZE / 2 + 14} textAnchor="middle" fontSize="10.5" fill="#98a2b3">éléments</text>
      </svg>
      <div className="donut-legend">
        {SEGMENTS.map((s) => (
          <div className="donut-legend-row" key={s.key}>
            <span className="donut-legend-key">
              <span className="donut-legend-swatch" style={{ background: s.color }} />
              {s.label}
            </span>
            <span>{distribution[s.key] || 0}{total > 0 ? ` (${Math.round(((distribution[s.key] || 0) / total) * 100)}%)` : ""}</span>
          </div>
        ))}
      </div>
    </>
  );
}
