import { useEffect, useMemo, useRef, useState } from "react";

/**
 * Search-driven dossier picker: type to filter by name, phone, region, activity, or status.
 * from the filtered list. Replaces a plain <select> cramming 30+ entities
 * into one scroll list - each entity is found and chosen individually.
 */
export default function EntitySearchSelect({ entities, value, onChange, placeholder }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  const selected = (entities || []).find((e) => e.entity_id === value) || null;

  useEffect(() => {
    function handleClickOutside(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const filtered = useMemo(() => {
    const list = entities || [];
    const term = query.trim().toLowerCase();
    if (!term) return list.slice(0, 30);
    return list
      .filter((e) =>
        [e.business_name, e.phone, e.location_text, e.activity_description, e.source_platform, e.status, e.notes]
          .filter(Boolean)
          .some((v) => v.toLowerCase().includes(term))
      )
      .slice(0, 30);
  }, [entities, query]);

  function handlePick(entity) {
    onChange(entity.entity_id);
    setQuery("");
    setOpen(false);
  }

  return (
    <div className="entity-search" ref={rootRef}>
      {selected && !open ? (
        <button type="button" className="entity-search-chosen" onClick={() => setOpen(true)}>
          <span>{selected.business_name}</span>
          <span className="entity-search-change">Changer</span>
        </button>
      ) : (
        <>
          <input
            className="textinput"
            type="text"
            placeholder={placeholder || "Nom, téléphone, région, activité, statut…"}
            value={query}
            onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
            onFocus={() => setOpen(true)}
          />
          {open && (
            <div className="entity-search-dropdown">
              {filtered.length === 0 && <div className="entity-search-empty">Aucune entité trouvée.</div>}
              {filtered.map((e) => (
                <button type="button" className="entity-search-option" key={e.entity_id} onClick={() => handlePick(e)}>
                  <span className="entity-search-option-name">{e.business_name}</span>
                  <span className="entity-search-option-meta">{e.location_text?.split(",").pop()?.trim() || "Dossier disponible"}</span>
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
