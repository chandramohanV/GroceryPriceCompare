"""Recognise supermarket products in Dutch product names and group them.

Covers fruit, vegetables, meat, fish, dairy & eggs, cereals and coffee. Each
store names products differently ("QUALITÉ SUISSE Jonagold appels" vs
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
PRODUCTS: dict[str, tuple[str, list[str]]] = {
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
    # --- vlees ---
    "Gehakt": ("vlees", ["gehakt", "rundergehakt", "varkensgehakt", "half om half gehakt",
                         "kipgehakt", "gehaktballen", "slavink", "slavinken"]),
    "Kipfilet": ("vlees", ["kipfilet", "kipfilets", "kippenfilet", "kipfiletreepjes", "kipreepjes",
                           "kipschnitzel", "kipschnitzels"]),
    "Kippendijen": ("vlees", ["kipdij", "kipdijen", "kipdijfilet", "kippendijen", "dijfilet"]),
    "Kippenpoten": ("vlees", ["kippenpoten", "kippenbouten", "drumsticks", "kipdrumsticks",
                              "kipkluifjes", "scharrelkipkluifjes", "kippenvleugels", "kipvleugels"]),
    "Hele kip": ("vlees", ["hele kip", "braadkip"]),
    "Rundvlees": ("vlees", ["rundvlees", "biefstuk", "biefstukken", "entrecote", "ribeye",
                            "ossenhaas", "sukade", "riblappen", "runderlappen", "stoofvlees",
                            "rosbief", "tartaar", "tartaartjes"]),
    "Varkensvlees": ("vlees", ["varkensvlees", "varkenshaas", "varkensfilet", "karbonade",
                               "karbonades", "speklappen", "hamlappen", "procureur",
                               "varkenshaasjes", "schnitzel", "schnitzels", "spareribs"]),
    "Spek": ("vlees", ["spek", "spekjes", "spekblokjes", "spekreepjes", "ontbijtspek", "bacon"]),
    "Worst": ("vlees", ["worst", "worstjes", "rookworst", "braadworst", "braadworstjes",
                        "knakworst", "knakworstjes", "chipolata", "saucijzen"]),
    "Vleeswaren": ("vlees", ["vleeswaren", "ham", "achterham", "beenham", "schouderham", "salami",
                             "filet americain", "cervelaat", "boterhamworst", "leverworst",
                             "fricandeau", "rookvlees", "pastrami"]),
    "Hamburgers": ("vlees", ["hamburger", "hamburgers", "runderburger", "runderburgers"]),
    "Lamsvlees": ("vlees", ["lamsvlees", "lamsrack", "lamsrackjes", "lamskoteletten", "lamsbout"]),
    # --- vis ---
    "Zalm": ("vis", ["zalm", "zalmfilet", "zalmfilets", "zalmmoten", "gerookte zalm", "zalmsnippers"]),
    "Kabeljauw": ("vis", ["kabeljauw", "kabeljauwfilet", "kabeljauwfilets", "kabeljauwburgers",
                          "skrei"]),
    "Witvis": ("vis", ["witvis", "witvisfilet", "koolvis", "koolvisfilet", "pangasius", "tilapia",
                       "schol", "scholfilet", "wijting", "heek", "pollak", "tongfilet"]),
    "Garnalen": ("vis", ["garnalen", "garnaal", "noordzeegarnalen", "gamba", "gambas", "gamba's",
                         "scampi", "scampi's"]),
    "Tonijn": ("vis", ["tonijn", "tonijnsteak", "tonijnsteaks", "tonijnstukken"]),
    "Haring & makreel": ("vis", ["haring", "haringen", "maatjes", "maatjesharing", "zure haring",
                                 "rolmops", "makreel", "makreelfilet"]),
    "Vissticks": ("vis", ["vissticks", "visstick", "lekkerbekje", "lekkerbekjes", "kibbeling",
                          "visburgers"]),
    "Mosselen": ("vis", ["mosselen", "mossel"]),
    # --- zuivel & eieren ---
    "Melk": ("zuivel", ["melk", "halfvolle melk", "volle melk", "magere melk", "karnemelk",
                        "lactosevrije melk", "houdbare melk"]),
    "Yoghurt": ("zuivel", ["yoghurt", "griekse yoghurt", "turkse yoghurt", "skyr", "yoghurtdrank"]),
    "Kwark": ("zuivel", ["kwark", "magere kwark", "volle kwark"]),
    "Vla & pudding": ("zuivel", ["vla", "vanillevla", "pudding", "griesmeelpudding", "toetje",
                                 "toetjes"]),
    "Kaas": ("zuivel", ["kaas", "goudse kaas", "goudse", "jong belegen", "belegen", "extra belegen",
                        "oude kaas", "gouda", "kaasplakken", "geraspte kaas", "mozzarella",
                        "burrata", "brie", "camembert", "feta", "parmezaan", "parmigiano", "mascarpone", "cheddar",
                        "geitenkaas", "leerdammer", "old amsterdam", "roomkaas", "smeerkaas"]),
    "Boter": ("zuivel", ["boter", "roomboter", "grasboter", "halvarine", "margarine"]),
    "Room": ("zuivel", ["room", "slagroom", "kookroom", "zure room", "creme fraiche"]),
    "Eieren": ("zuivel", ["ei", "eieren", "scharreleieren", "vrije uitloop eieren", "kippeneieren",
                          "biologische eieren"]),
    # --- ontbijtgranen ---
    "Havermout": ("granen", ["havermout", "havervlokken", "brinta", "porridge"]),
    "Muesli & granola": ("granen", ["muesli", "granola", "cruesli", "crunchy muesli"]),
    "Cornflakes & cereals": ("granen", ["cornflakes", "ontbijtgranen", "cereals", "special k",
                                        "cheerios", "chocapic", "frosties", "rice krispies",
                                        "coco pops", "smacks"]),
    # --- koffie ---
    "Koffie": ("koffie", ["koffie", "filterkoffie", "snelfilterkoffie", "gemalen koffie",
                          "oploskoffie", "instant koffie"]),
    "Koffiebonen": ("koffie", ["koffiebonen", "espressobonen", "hele bonen"]),
    "Koffiecups & pads": ("koffie", ["koffiecups", "koffiecapsules", "koffiepads", "capsules",
                                     "cups", "pads", "nespresso", "dolce gusto", "senseo"]),
}

CATEGORIES = ("fruit", "groente", "vlees", "vis", "zuivel", "granen", "koffie")

# Words that mean the product is something else (a pastry, a meal, a non-food
# item), whatever category it would otherwise match.
EXCLUDE_ALWAYS = {
    "taart", "taartje", "gebak", "cake", "vlaai", "vlaaitje", "koek", "koeken", "donut",
    "chips", "snoep", "chocolade", "pizza", "soep", "saus", "croissant", "tosti", "wrap",
    "wraps", "broodje", "broodjes", "maaltijd", "shampoo", "zeep", "kaars", "geur", "plant",
    "conifeer", "zaad", "zaden", "pencee", "hondenvoer", "kattenvoer", "hond", "honden",
    "kat", "katten", "spray", "reiniger", "bowl", "staaf",
}
_EXCLUDE_PRODUCE = {
    "sap", "jam", "smoothie", "siroop", "moes", "compote", "yoghurt", "kwark", "ijs", "drank",
    "limonade", "thee", "bier", "wijn", "gedroogd", "gedroogde", "chutney", "kaas", "frites",
    "patat", "puree", "olie", "azijn", "stroop", "mix voor", "bakmix", "diepvries",
    "perensap", "olijven", "fruitcocktail", "piccalilly",
}
_EXCLUDE_NOT_ANIMAL = {
    "vega", "vegan", "vegetarisch", "vegetarische", "plantaardig", "plantaardige", "salade",
}
# Ready-made meat products: cold cuts, filled schnitzels, potato dishes
_EXCLUDE_PREPARED_MEAT = {"gebraden", "cordon", "aardappel"}
# Extra exclusions per category, on top of EXCLUDE_ALWAYS.
EXCLUDE_BY_CATEGORY: dict[str, set[str]] = {
    "fruit": _EXCLUDE_PRODUCE,
    "groente": _EXCLUDE_PRODUCE,
    "vlees": _EXCLUDE_NOT_ANIMAL | _EXCLUDE_PREPARED_MEAT,
    "vis": _EXCLUDE_NOT_ANIMAL,
    "zuivel": _EXCLUDE_NOT_ANIMAL | {"ijs", "choco"},
    "granen": {"reep", "repen", "yoghurt"},
    "koffie": {"ijs", "likeur", "apparaat", "machine", "mok", "beker", "filters"},
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("’", "'")
    return " " + re.sub(r"[^a-z0-9']+", " ", text).strip() + " "


_PHRASES: list[tuple[str, str]] = sorted(
    ((f" {_norm(p).strip()} ", canon) for canon, (_, ps) in PRODUCTS.items() for p in ps),
    key=lambda x: -len(x[0]),
)


def _has_excluded_word(normalized_name: str, words: set[str]) -> bool:
    """True if the name contains an excluded word, also inside compounds
    such as "kruimelvlaaitje", "appeltaart" or "tomatensoep"."""
    if any(f" {_norm(w).strip()} " in normalized_name for w in words):
        return True
    long_words = [_norm(w).strip() for w in words if " " not in w and len(w) >= 4]
    return any(w in token for token in normalized_name.split() for w in long_words)


def classify(name: str) -> Optional[tuple[str, str]]:
    """Return (canonical_product, category), or None if it isn't a product we compare."""
    n = _norm(name)
    product = next((canon for phrase, canon in _PHRASES if phrase in n), None)
    if product is None:
        return None
    category = PRODUCTS[product][0]
    if _has_excluded_word(n, EXCLUDE_ALWAYS | EXCLUDE_BY_CATEGORY[category]):
        return None
    return product, category


def variety(name: str, product: str) -> Optional[str]:
    """Best-effort variety/brand hint (e.g. "Jonagold") for display."""
    n = _norm(name)
    for p in PRODUCTS[product][1]:
        p_n = f" {_norm(p).strip()} "
        if p_n in n and p_n.strip() not in (product.lower(), product.lower().rstrip("s")):
            if p_n.strip() not in {"appel", "appels", "peer", "peren", "banaan", "bananen"}:
                return p.title()
    return None
