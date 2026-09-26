import { useEffect, useMemo, useRef, useState } from "react";
import { TUNISIA_PATHS, TUNISIA_VIEWBOX } from "../data/tunisiaPaths";

const RISK_COLOR = {
  eleve: "#bc141f",
  moyen: "#e8963a",
  faible: "#279a63",
  non_evalue: "#98a2b3",
  traite: "#132130",
  none: "#dbe2ee",
};

function dominantCategory(region) {
  if (!region || region.total === 0) return "none";
  const entries = [
    ["eleve", region.eleve],
    ["moyen", region.moyen],
    ["traite", region.traite],
    ["faible", region.faible],
    ["non_evalue", region.non_evalue],
  ];
  entries.sort((a, b) => b[1] - a[1]);
  return entries[0][1] > 0 ? entries[0][0] : "none";
}

export default function MapPanel({ regions, onRegionSelect, selectedRegionId }) {
  const [zoom, setZoom] = useState(1);
  const [hoverGid, setHoverGid] = useState(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const [centroids, setCentroids] = useState({});
  const pathRefs = useRef({});
  const holderRef = useRef(null);

  const regionByGid = useMemo(() => {
    const map = {};
    for (const r of regions || []) map[r.governorate_id] = r;
    return map;
  }, [regions]);

  useEffect(() => {
    const next = {};
    for (const gov of TUNISIA_PATHS) {
      // Governorates split across multiple path fragments (nabeul, sfax,
      // tunis) - center the count badge on the LARGEST fragment's bbox, not
      // just the first one, or it can land on a small sliver outside the
      // main visible shape.
      let best = null;
      for (const el of pathRefs.current[gov.id] || []) {
        if (!el) continue;
        const bbox = el.getBBox();
        const area = bbox.width * bbox.height;
        if (!best || area > best.area) {
          best = { area, x: bbox.x + bbox.width / 2, y: bbox.y + bbox.height / 2 };
        }
      }
      if (best) next[gov.id] = { x: best.x, y: best.y };
    }
    setCentroids(next);
  }, []);

  function handleMouseMove(e) {
    const rect = holderRef.current.getBoundingClientRect();
    setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  }

  const hoverRegion = hoverGid ? regionByGid[hoverGid] : null;

  return (
    <div className="panel map-panel">
      <div className="panel-header">
        <h2>Répartition des entités et niveaux de risque</h2>
        <div className="map-controls">
          <button type="button" className="chip-btn" onClick={() => setZoom((z) => Math.min(2.4, z + 0.25))} title="Zoomer">+</button>
          <button type="button" className="chip-btn" onClick={() => setZoom((z) => Math.max(0.6, z - 0.25))} title="Dézoomer">–</button>
          <button type="button" className="chip-btn" onClick={() => setZoom(1)} title="Réinitialiser">⤾</button>
        </div>
      </div>

      <div className="map-wrap">
        <div
          className="map-svg-holder"
          ref={holderRef}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoverGid(null)}
        >
          <svg viewBox={TUNISIA_VIEWBOX} style={{ transform: `scale(${zoom})` }}>
            {TUNISIA_PATHS.map((gov) => {
              const region = regionByGid[gov.id];
              const category = dominantCategory(region);
              return gov.d.map((d, i) => (
                <path
                  key={`${gov.id}-${i}`}
                  ref={(el) => {
                    if (!pathRefs.current[gov.id]) pathRefs.current[gov.id] = [];
                    pathRefs.current[gov.id][i] = el;
                  }}
                  className={`gov-path ${selectedRegionId === gov.id ? "is-selected" : ""}`}
                  d={d}
                  fill={RISK_COLOR[category]}
                  onMouseEnter={() => setHoverGid(gov.id)}
                  onClick={() => onRegionSelect?.(region || { governorate_id: gov.id, governorate_name: gov.id, total: 0 })}
                />
              ));
            })}
            {TUNISIA_PATHS.map((gov) => {
              const region = regionByGid[gov.id];
              const c = centroids[gov.id];
              if (!region || region.total === 0 || !c) return null;
              const r = Math.min(22, 9 + Math.sqrt(region.total) * 3.2);
              return (
                <g key={`badge-${gov.id}`} style={{ pointerEvents: "none" }}>
                  <circle cx={c.x} cy={c.y} r={r} fill={RISK_COLOR[dominantCategory(region)]} stroke="white" strokeWidth="2" opacity="0.95" />
                  <text x={c.x} y={c.y} textAnchor="middle" dominantBaseline="central" fontSize={r > 14 ? 13 : 11} fontWeight="700" fill="white">
                    {region.total}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        {hoverRegion && (
          <div
            className="map-tooltip"
            style={{ left: mousePos.x + 14, top: mousePos.y + 10 }}
          >
            <strong>{hoverRegion.governorate_name}</strong><br />
            {hoverRegion.total} entité{hoverRegion.total > 1 ? "s" : ""}<br />
            {hoverRegion.eleve > 0 && <>Risque élevé : {hoverRegion.eleve}<br /></>}
            {hoverRegion.moyen > 0 && <>Risque moyen : {hoverRegion.moyen}<br /></>}
            {hoverRegion.faible > 0 && <>Risque faible : {hoverRegion.faible}<br /></>}
            {hoverRegion.non_evalue > 0 && <>Non évalué : {hoverRegion.non_evalue}<br /></>}
            {hoverRegion.traite > 0 && <>Traité : {hoverRegion.traite}</>}
          </div>
        )}
      </div>

      <p className="map-hint">Cliquez sur une région pour afficher ses nouvelles détections.</p>

      <div className="map-legend">
        <span><i className="dot dot-eleve" />Risque élevé</span>
        <span><i className="dot dot-moyen" />Risque moyen</span>
        <span><i className="dot dot-faible" />Risque faible</span>
        <span><i className="dot dot-none" />Non évalué</span>
        <span><i className="dot dot-traite" />Traité</span>
      </div>
    </div>
  );
}
