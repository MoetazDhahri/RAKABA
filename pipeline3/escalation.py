"""
Lightweight keyword/intent classifier for the client chatbot.

Runs BEFORE calling Groq so flagged messages never reach the LLM for a full
answer. Deliberately simple (substring matching, no LLM call) to keep this
fast and deterministic for a live demo.
"""

_SHARED_ACCOUNTS_FAMILY = [
    "compte partage", "compte commun", "famille", "mon frere", "ma soeur",
    "mon pere", "ma mere", "mon epoux", "mon epouse", "mon conjoint",
    "ma conjointe", "mon associe", "activite de mon frere", "activite de ma soeur",
]

_LINKED_ENTITIES = [
    "entreprise liee", "societe liee", "autre societe", "lie a", "liee a",
    "lie avec", "liee avec", "meme numero", "meme adresse", "meme telephone",
]

_LEGAL_RISK = [
    "si je ne declare pas", "que se passe-t-il si", "qu'est-ce qui se passe si",
    "risque si je ne", "sanction si", "amende si", "prison si", "peine si",
    "consequence si je ne", "consequences si je ne",
]

_INVESTIGATION_SUSPICION = [
    "enquete", "je suis soupconne", "on me soupconne", "vous me soupconnez",
    "suis-je soupconne", "suspecte", "accuse de fraude", "accusee de fraude",
    "vous m'accusez", "inspecteur me soupconne", "suis-je sous enquete",
    "dossier d'enquete",
]

_CATEGORIES = [
    ("comptes_partages_famille", _SHARED_ACCOUNTS_FAMILY),
    ("entites_liees", _LINKED_ENTITIES),
    ("risque_juridique", _LEGAL_RISK),
    ("enquete_soupcon", _INVESTIGATION_SUSPICION),
]


def _normalize(text: str) -> str:
    replacements = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a",
        "î": "i", "ï": "i",
        "ô": "o", "ö": "o",
        "ù": "u", "û": "u", "ü": "u",
        "ç": "c",
        "'": "'",
    }
    normalized = text.lower()
    for accented, plain in replacements.items():
        normalized = normalized.replace(accented, plain)
    return normalized


def classify(message: str):
    """
    Returns (should_escalate: bool, reason: str | None).
    reason is a short machine-readable category label for the escalations table.
    """
    normalized = _normalize(message or "")

    for reason, keywords in _CATEGORIES:
        for keyword in keywords:
            if keyword in normalized:
                return True, reason

    return False, None
