const RISK_FLAG_LABELS = {
  clustering_montants_ronds: "Montants répétitifs à examiner",
  transactions_avec_entite_liee: "Transactions avec une entité liée",
  pdf_edited_after_finalization: "Document modifié après finalisation",
  pasted_content_suspected: "Élément visuel à vérifier",
};

export function humanRiskFlag(flag) {
  return RISK_FLAG_LABELS[flag] || "Point à examiner";
}

export function documentRiskLabel(score) {
  if (score == null) return "Non évalué";
  if (score > 0.7) return "Élevé";
  if (score > 0.4) return "À examiner";
  return "Faible signal";
}

export function pipelineLabel(source) {
  return {
    pipeline1: "Détection",
    pipeline2: "Vérification",
    pipeline3: "Accompagnement",
  }[source] || "Plateforme";
}
