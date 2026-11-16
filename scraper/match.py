"""Recognise fruit & vegetables in Dutch product names and group them.

Each store names products differently ("QUALITÉ SUISSE Jonagold appels" vs
"AH Elstar appels 1 kg"). We map every name to a canonical product using a
vocabulary of Dutch words, matched on whole words so that e.g. "appelsap"
or "appeltaart" are *not* treated as apples.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

# canonical name -> (category, [words/phrases as they appear in names])
# Longer phrases are matched first, so "zoete aardappel" wins over "aardappel".
PRODUCE: dict[str, tuple[str, list[str]]] = {
    # --- fruit ---
    "Appels": ("fruit", ["appel", "appels", "elstar", "jonagold", "jonagored", "goudrenet",
                          "pink lady", "granny smith", "kanzi", "junami", "braeburn", "gala", "fuji",
                          "evelina", "tasty red", "red prince", "rode boskoop"]),
    "Peren": ("fruit", ["peer", "peren", "conference", "doyenne", "gieser wildeman", "stoofperen"]),
    "Bananen": ("fruit", ["banaan", "bananen"]),
    "Sinaasappels": ("fruit", ["sinaasappel", "sinaasappels", "handsinaasappels", "perssinaasappels"]),
    "Mandarijnen": ("fruit", ["mandarijn", "mandarijnen", "clementine", "clementines", "nectarijn mandarijn"]),
    "Citroenen": ("fruit", ["citroen", "citroenen"]),
    "Limoenen": ("fruit", ["limoen", "limoenen"]),
    "Grapefruit": ("fruit", ["grapefruit", "grapefruits"]),
    "Druiven": ("fruit", ["druif", "druiven"]),
    "Aardbeien": ("fruit", ["aardbei", "aardbeien"]),
    "Blauwe bessen": ("fruit", ["blauwe bessen", "blauwebessen", "bosbessen"]),
    "Frambozen": ("fruit", ["framboos", "frambozen"]),
    "Bramen": ("fruit", ["braam", "bramen"]),
    "Kiwi's": ("fruit", ["kiwi", "kiwis", "kiwi's", "kiwi gold"]),
    "Mango": ("fruit", ["mango", "mango's", "mangos"]),
    "Ananas": ("fruit", ["ananas"]),
    "Meloen": ("fruit", ["meloen", "meloenen", "watermeloen", "galiameloen", "cantaloupe"]),
    "Avocado": ("fruit", ["avocado", "avocado's", "avocados"]),
    "Granaatappel": ("fruit", ["granaatappel", "granaatappels"]),
    "Perziken & nectarines": ("fruit", ["perzik", "perziken", "nectarine", "nectarines", "nectarijn", "nectarijnen"]),
    "Pruimen": ("fruit", ["pruim", "pruimen"]),
    "Kersen": ("fruit", ["kers", "kersen"]),
    "Passievrucht": ("fruit", ["passievrucht", "passievruchten"]),
    "Kaki": ("fruit", ["kaki", "sharonfruit", "persimmon"]),
    # --- groente ---
    "Zoete aardappels": ("groente", ["zoete aardappel", "zoete aardappels", "zoete aardappelen", "bataat"]),
    "Aardappels": ("groente", ["aardappel", "aardappels", "aardappelen", "krieltjes", "kruimige aardappelen"]),
    "Tomaten": ("groente", ["tomaat", "tomaten", "cherrytomaten", "snoeptomaten", "trostomaten", "romatomaten"]),
    "Komkommer": ("groente", ["komkommer", "komkommers", "minikomkommers"]),
    "Paprika": ("groente", ["paprika", "paprika's", "paprikas", "puntpaprika", "puntpaprika's"]),
    "Uien": ("groente", ["ui", "uien", "rode uien", "sjalot", "sjalotten", "bosui"]),
    "Knoflook": ("groente", ["knoflook"]),
    "Wortels": ("groente", ["wortel", "wortels", "wortelen", "winterpeen", "peen", "bospeen", "worteltjes"]),
    "Broccoli": ("groente", ["broccoli", "broccolini"]),
    "Bloemkool": ("groente", ["bloemkool"]),
    "Spruiten": ("groente", ["spruiten", "spruitjes"]),
    "Boerenkool": ("groente", ["boerenkool"]),
    "Rode kool": ("groente", ["rode kool", "rodekool"]),
    "Witte kool": ("groente", ["witte kool", "wittekool", "spitskool", "savooiekool", "chinese kool"]),
    "Witlof": ("groente", ["witlof"]),
    "Prei": ("groente", ["prei"]),
    "Courgette": ("groente", ["courgette", "courgettes"]),
    "Aubergine": ("groente", ["aubergine", "aubergines"]),
    "Champignons": ("groente", ["champignon", "champignons", "kastanjechampignons", "paddenstoelen"]),
    "Pompoen": ("groente", ["pompoen", "flespompoen", "butternut", "hokkaido"]),
    "Sla": ("groente", ["sla", "ijsbergsla", "kropsla", "rucola", "veldsla", "romaine", "little gem", "slamix"]),
    "Spinazie": ("groente", ["spinazie"]),
    "Sperziebonen": ("groente", ["sperziebonen", "boontjes", "snijbonen", "haricots verts"]),
    "Asperges": ("groente", ["asperge", "asperges"]),
    "Mais": ("groente", ["maiskolf", "maiskolven", "suikermais"]),
    "Bieten": ("groente", ["biet", "bieten", "rode bieten"]),
    "Selderij": ("groente", ["selderij", "bleekselderij", "knolselderij"]),
    "Venkel": ("groente", ["venkel"]),
    "Radijs": ("groente", ["radijs", "radijsjes"]),
    "Pastinaak": ("groente", ["pastinaak"]),
    "Peultjes": ("groente", ["peultjes", "sugar snaps"]),
}

# Words that mean the product is processed, not fresh produce.
EXCLUDE = {
    "sap", "taart", "taartje", "chips", "jam", "saus", "soep", "smoothie", "siroop",
    "moes", "compote", "gebak", "cake", "vlaai", "vlaaitje", "koek", "koeken", "yoghurt",
    "kwark", "ijs", "drank", "limonade", "thee", "bier", "wijn", "gedroogd", "gedroogde",
    "chutney", "pizza", "kaas", "frites", "patat", "puree", "olie", "azijn", "snoep",
    "donut", "shampoo", "zeep", "kaars", "geur", "plant", "conifeer", "zaad", "zaden",
    "pencee", "stroop", "mix voor", "bakmix", "diepvries",
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("’", "'")
    return " " + re.sub(r"[^a-z0-9']+", " ", text).strip() + " "


_PHRASES: list[tuple[str, str]] = sorted(
    ((f" {_norm(p).strip()} ", canon) for canon, (_, ps) in PRODUCE.items() for p in ps),
    key=lambda x: -len(x[0]),
)
_EXCLUDE_NORM = [f" {_norm(w).strip()} " for w in EXCLUDE]
_EXCLUDE_LONG = [_norm(w).strip() for w in EXCLUDE if " " not in w and len(w) >= 4]


def classify(name: str) -> Optional[tuple[str, str]]:
    """Return (canonical_product, category) or None if not fresh produce."""
    n = _norm(name)
    if any(w in n for w in _EXCLUDE_NORM):
        return None
    # compound words: "kruimelvlaaitje", "appeltaart", "tomatensoep"
    tokens = n.split()
    if any(len(w) >= 4 and w in t for t in tokens for w in _EXCLUDE_LONG):
        return None
    for phrase, canon in _PHRASES:
        if phrase in n:
            return canon, PRODUCE[canon][0]
    return None


def variety(name: str, product: str) -> Optional[str]:
    """Best-effort variety/brand hint (e.g. "Jonagold") for display."""
    n = _norm(name)
    for p in PRODUCE[product][1]:
        p_n = f" {_norm(p).strip()} "
        if p_n in n and p_n.strip() not in (product.lower(), product.lower().rstrip("s")):
            if p_n.strip() not in {"appel", "appels", "peer", "peren", "banaan", "bananen"}:
                return p.title()
    return None
