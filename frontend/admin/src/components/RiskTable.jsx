const RISK_LABEL = { eleve: "Élevé", moyen: "Moyen", faible: "Faible", inconnu: "—" };

const STATUS_MAP = {
  "Detecte": { label: "À vérifier", cls: "" },
  "Contacte": { label: "Contacté", cls: "" },
  "En regularisation": { label: "En cours", cls: "badge-status--verif" },
  "Conforme": { label: "Traité", cls: "badge-status--traite" },
  "Contribuable de confiance": { label: "Traité", cls: "badge-status--traite" },
};

export default function RiskTable({ entities }) {
  if (!entities || entities.length === 0) {
    return <tbody><tr><td colSpan={4} className="empty-state">Aucune entité pour le moment.</td></tr></tbody>;
  }

  return (
    <tbody>
      {entities.map((e) => {
        const status = STATUS_MAP[e.status] || { label: e.status, cls: "" };
        return (
          <tr key={e.entity_id}>
            <td className="entity-name">{e.name}</td>
            <td>{e.region}</td>
            <td><span className={`badge badge-${e.risk_level}`}>{RISK_LABEL[e.risk_level]}</span></td>
            <td><span className={`badge badge-status ${status.cls}`}>{status.label}</span></td>
          </tr>
        );
      })}
    </tbody>
  );
}
