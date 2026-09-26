"""
Generateur de signaux synthetiques (F1.1) + registre fiscal synthetique (F1.2)
RAKABA Pipeline 1

Simule un flux de "scraping" de reseaux sociaux / annonces en ligne. Aucune
donnee reelle n'est utilisee (cf. cahier des charges, section 16 et 19) - le
scraping reel est explicitement hors scope (section 11, "Won't have").

Trois scenarios sont deliberement plantes dans chaque lot genere, pour donner
au moteur de correspondance (matching_engine.py) et a la liaison d'entites
(F1.6) une structure a demontrer :

  - RELIABLE : nom + telephone tres proches d'une fiche du registre  -> score >= 80
  - AMBIGUOUS: meme telephone, nom tres different                    -> 40 <= score < 80
  - UNKNOWN  : aucun rapprochement credible avec le registre          -> score < 40
  - LINKED   : plusieurs UNKNOWN partageant un meme telephone/adresse
               (un meme operateur non declare sous plusieurs enseignes)
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------------------
# Registre fiscal (F1.2) - fixe, pour que les demos soient reproductibles
# ---------------------------------------------------------------------------

REGISTRY_SEED: list[dict] = [
    {"matricule_fiscal": "MF-1001", "registered_name": "Boutique Amira Mode", "phone": "22345678",
     "registered_address": "Avenue Habib Bourguiba, Tunis", "registration_date": date(2019, 3, 12)},
    {"matricule_fiscal": "MF-1002", "registered_name": "Cafe Central Sousse", "phone": "98765432",
     "registered_address": "Rue de la Corniche, Sousse", "registration_date": date(2020, 6, 1)},
    {"matricule_fiscal": "MF-1003", "registered_name": "Salon Coiffure Yasmine", "phone": "55123456",
     "registered_address": "Rue Ibn Khaldoun, Sfax", "registration_date": date(2018, 11, 20)},
    {"matricule_fiscal": "MF-1004", "registered_name": "Atelier Menuiserie Karim", "phone": "20987654",
     "registered_address": "Zone Industrielle, Ariana", "registration_date": date(2021, 1, 15)},
    {"matricule_fiscal": "MF-1005", "registered_name": "Superette El Baraka", "phone": "50112233",
     "registered_address": "Avenue de la Liberte, Bizerte", "registration_date": date(2017, 9, 5)},
    {"matricule_fiscal": "MF-1006", "registered_name": "Patisserie Douceur Orientale", "phone": "27445566",
     "registered_address": "Rue de Marseille, Tunis", "registration_date": date(2022, 2, 28)},
    {"matricule_fiscal": "MF-1007", "registered_name": "Garage Mecanique Nabil", "phone": "90556677",
     "registered_address": "Route de Gabes, Sfax", "registration_date": date(2016, 5, 10)},
    {"matricule_fiscal": "MF-1008", "registered_name": "Cabinet Comptable Zied Trabelsi", "phone": "24778899",
     "registered_address": "Avenue Mohamed V, Tunis", "registration_date": date(2015, 7, 1)},
    {"matricule_fiscal": "MF-1009", "registered_name": "Fleuriste Le Jardin", "phone": "58223344",
     "registered_address": "Rue de la Kasbah, Kairouan", "registration_date": date(2020, 10, 18)},
    {"matricule_fiscal": "MF-1010", "registered_name": "Boucherie Chez Slim", "phone": "29667788",
     "registered_address": "Avenue Farhat Hached, Monastir", "registration_date": date(2019, 4, 22)},
    {"matricule_fiscal": "MF-1011", "registered_name": "Studio Photo Lumiere", "phone": "52334455",
     "registered_address": "Rue Charles de Gaulle, Tunis", "registration_date": date(2021, 8, 9)},
    {"matricule_fiscal": "MF-1012", "registered_name": "Librairie Savoir", "phone": "97889900",
     "registered_address": "Avenue de Paris, Sfax", "registration_date": date(2014, 12, 3)},
]

# ---------------------------------------------------------------------------
# Vocabulaire pour les entites "inconnues" (jamais dans le registre)
# ---------------------------------------------------------------------------

_UNKNOWN_BUSINESS_NAMES = [
    "Vente Vetements en Ligne", "Snack Rapide Youssef", "Pressing Express",
    "Location Voitures Sans Chauffeur", "Cours Particuliers Maths", "Traiteur Fait Maison",
    "Bijoux Fantaisie Chic", "Reparation Telephones Pro", "Decoration Evenementielle",
    "Elevage Volaille Bio", "Import Cosmetiques Turquie", "Artisanat Poterie Nabeul",
]

_CITIES = ["Tunis", "Sfax", "Sousse", "Bizerte", "Ariana", "Monastir", "Kairouan", "Gabes", "Nabeul"]
_STREET_WORDS = ["Rue", "Avenue", "Impasse"]
_STREET_NAMES = ["des Oliviers", "de la Republique", "El Manar", "des Roses", "du Stade", "de la Gare"]
_PLATFORMS = ["Facebook Marketplace", "Instagram", "TikTok Shop", "Annonce Tayara", "Groupe WhatsApp public"]

_NAME_DRIFT_SUFFIXES = [" Store", " Officiel", " Tunisie", ""]


@dataclass
class SyntheticListing:
    listing_id: str
    business_name: str
    phone: str
    location_text: str
    activity_description: str
    source_platform: str
    detected_date: datetime
    scenario: str  # for test/debug visibility only, not persisted


def _random_new_phone(rng: random.Random, used: set[str]) -> str:
    while True:
        prefix = rng.choice(["2", "4", "5", "9"])
        candidate = prefix + "".join(rng.choice("0123456789") for _ in range(7))
        if candidate not in used:
            used.add(candidate)
            return candidate


def _random_address(rng: random.Random) -> str:
    return f"{rng.choice(_STREET_WORDS)} {rng.choice(_STREET_NAMES)}, {rng.choice(_CITIES)}"


def _drift_name(rng: random.Random, name: str) -> str:
    """Introduce a plausible spelling/format drift so exact-string matching would fail
    but fuzzy matching succeeds (cf. section 16.1)."""
    variants = [
        name.upper(),
        name.replace(" ", "  "),
        " ".join(reversed(name.split())),
        name + rng.choice(_NAME_DRIFT_SUFFIXES),
        name.replace("e", "é") if "e" in name else name,
    ]
    return rng.choice(variants)


def _format_phone_variant(rng: random.Random, phone: str) -> str:
    style = rng.choice(["plain", "spaced", "intl"])
    if style == "spaced":
        return f"{phone[:2]} {phone[2:5]} {phone[5:]}"
    if style == "intl":
        return f"+216 {phone[:2]} {phone[2:5]} {phone[5:]}"
    return phone


def _make_listing(rng: random.Random, scenario: str, business_name: str, phone: str,
                   location_text: str, base_date: datetime, used_ids: set[str]) -> SyntheticListing:
    listing_id = f"LST-{uuid.uuid4().hex[:8]}"
    while listing_id in used_ids:
        listing_id = f"LST-{uuid.uuid4().hex[:8]}"
    used_ids.add(listing_id)
    return SyntheticListing(
        listing_id=listing_id,
        business_name=business_name,
        phone=phone,
        location_text=location_text,
        activity_description=rng.choice([
            "Vente de produits via reseaux sociaux", "Service a domicile", "Commerce de detail",
            "Prestation artisanale", "Restauration rapide",
        ]),
        source_platform=rng.choice(_PLATFORMS),
        detected_date=base_date - timedelta(days=rng.randint(0, 30), hours=rng.randint(0, 23)),
        scenario=scenario,
    )


def generate_scrape_batch(
    n: int = 12,
    seed: int | None = None,
    now: datetime | None = None,
) -> list[SyntheticListing]:
    """Simule un lot de signaux "scrapes" (F1.1). Deterministe si `seed` est fourni,
    ce qui permet des cycles d'automatisation reproductibles (X2)."""
    rng = random.Random(seed)
    now = now or datetime.now()
    used_ids: set[str] = set()
    used_phones: set[str] = set()
    listings: list[SyntheticListing] = []

    # 1) Cas RELIABLE (score >= 80) : nom proche + meme telephone
    for entry in rng.sample(REGISTRY_SEED, k=min(2, n)):
        listings.append(_make_listing(
            rng, "RELIABLE",
            business_name=_drift_name(rng, entry["registered_name"]),
            phone=_format_phone_variant(rng, entry["phone"]),
            location_text=entry["registered_address"],
            base_date=now, used_ids=used_ids,
        ))
        used_phones.add(entry["phone"])

    # 2) Cas AMBIGUOUS (40-79) : meme telephone, nom sans rapport
    for entry in rng.sample(REGISTRY_SEED, k=min(2, n)):
        if len(listings) >= n:
            break
        listings.append(_make_listing(
            rng, "AMBIGUOUS",
            business_name=rng.choice(_UNKNOWN_BUSINESS_NAMES),
            phone=_format_phone_variant(rng, entry["phone"]),
            location_text=_random_address(rng),
            base_date=now, used_ids=used_ids,
        ))
        used_phones.add(entry["phone"])

    # 3) Groupe LINKED : 3-5 annonces sous des noms differents, meme telephone
    #    ou meme adresse -> un seul operateur non declare (F1.6 / graphe P2).
    if len(listings) < n:
        shared_phone = _random_new_phone(rng, used_phones)
        shared_address = _random_address(rng)
        link_by_phone = rng.random() < 0.5
        group_size = min(rng.randint(3, 5), n - len(listings))
        for _ in range(group_size):
            listings.append(_make_listing(
                rng, "LINKED",
                business_name=rng.choice(_UNKNOWN_BUSINESS_NAMES),
                phone=shared_phone if link_by_phone else _random_new_phone(rng, used_phones),
                location_text=shared_address,
                base_date=now, used_ids=used_ids,
            ))

    # 4) Cas UNKNOWN (< 40) : remplissage, entites totalement nouvelles
    while len(listings) < n:
        listings.append(_make_listing(
            rng, "UNKNOWN",
            business_name=rng.choice(_UNKNOWN_BUSINESS_NAMES),
            phone=_random_new_phone(rng, used_phones),
            location_text=_random_address(rng),
            base_date=now, used_ids=used_ids,
        ))

    rng.shuffle(listings)
    return listings


def registry_rows() -> list[tuple]:
    return [
        (e["matricule_fiscal"], e["registered_name"], e["phone"], e["registered_address"], e["registration_date"])
        for e in REGISTRY_SEED
    ]
