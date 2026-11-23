"""Translate Dutch offer text (product names, quantities, deals) into English.

Offline and dictionary based, so it is free, deterministic and testable. Words
that aren't in the glossary (brand and variety names such as "QUALITÉ SUISSE"
or "Jonagold") are kept as they are.

* ``translate_text("Bio flespompoen")``  -> "Organic butternut squash"
* ``translate_text("2e halve prijs")``   -> "2nd half price"
* ``product_name("Spruiten")``           -> "Brussels sprouts"
"""
from __future__ import annotations

import re
from typing import Optional

from .models import Offer

# Canonical product (keys of match.PRODUCTS) -> English display name.
PRODUCT_NAMES: dict[str, str] = {
    "Appels": "Apples", "Peren": "Pears", "Bananen": "Bananas", "Sinaasappels": "Oranges",
    "Mandarijnen": "Mandarins", "Citroenen": "Lemons", "Limoenen": "Limes",
    "Grapefruit": "Grapefruit", "Druiven": "Grapes", "Aardbeien": "Strawberries",
    "Blauwe bessen": "Blueberries", "Frambozen": "Raspberries", "Bramen": "Blackberries",
    "Kiwi's": "Kiwis", "Mango": "Mango", "Ananas": "Pineapple", "Meloen": "Melon",
    "Avocado": "Avocado", "Granaatappel": "Pomegranate",
    "Perziken & nectarines": "Peaches & nectarines", "Pruimen": "Plums", "Kersen": "Cherries",
    "Passievrucht": "Passion fruit", "Kaki": "Persimmon",
    "Zoete aardappels": "Sweet potatoes", "Aardappels": "Potatoes", "Tomaten": "Tomatoes",
    "Komkommer": "Cucumber", "Paprika": "Bell peppers", "Uien": "Onions", "Knoflook": "Garlic",
    "Wortels": "Carrots", "Broccoli": "Broccoli", "Bloemkool": "Cauliflower",
    "Spruiten": "Brussels sprouts", "Boerenkool": "Kale", "Rode kool": "Red cabbage",
    "Witte kool": "White cabbage", "Witlof": "Chicory", "Prei": "Leek",
    "Courgette": "Courgette", "Aubergine": "Aubergine", "Champignons": "Mushrooms",
    "Pompoen": "Pumpkin", "Sla": "Lettuce", "Spinazie": "Spinach",
    "Sperziebonen": "Green beans", "Asperges": "Asparagus", "Mais": "Corn",
    "Bieten": "Beetroot", "Selderij": "Celery", "Venkel": "Fennel", "Radijs": "Radish",
    "Pastinaak": "Parsnip", "Peultjes": "Mangetout",
    "Gehakt": "Minced meat", "Kipfilet": "Chicken breast", "Kippendijen": "Chicken thighs",
    "Kippenpoten": "Chicken legs & wings", "Hele kip": "Whole chicken", "Rundvlees": "Beef",
    "Varkensvlees": "Pork", "Spek": "Bacon", "Worst": "Sausages", "Vleeswaren": "Cold cuts",
    "Hamburgers": "Burgers", "Lamsvlees": "Lamb",
    "Zalm": "Salmon", "Kabeljauw": "Cod", "Witvis": "White fish", "Garnalen": "Prawns",
    "Tonijn": "Tuna", "Haring & makreel": "Herring & mackerel", "Vissticks": "Fish fingers",
    "Mosselen": "Mussels",
    "Melk": "Milk", "Yoghurt": "Yoghurt", "Kwark": "Quark", "Vla & pudding": "Custard & pudding",
    "Kaas": "Cheese", "Boter": "Butter", "Room": "Cream", "Eieren": "Eggs",
    "Havermout": "Oats", "Muesli & granola": "Muesli & granola",
    "Cornflakes & cereals": "Cornflakes & cereals",
    "Koffie": "Coffee", "Koffiebonen": "Coffee beans", "Koffiecups & pads": "Coffee capsules & pads",
    "Diepvries friet & aardappel": "Frozen fries & potato", "Diepvries snacks": "Frozen snacks",
    "IJs": "Ice cream", "Diepvriespizza": "Frozen pizza", "Diepvriesmaaltijden": "Frozen meals",
    "Diepvries vlees & kip": "Frozen meat & chicken", "Diepvriesgroenten": "Frozen vegetables",
    "Diepvriesfruit": "Frozen fruit", "Diepvries vis": "Frozen fish",
}

# Dutch word or phrase (lowercase) -> English. Longer entries win over shorter ones.
GLOSSARY: dict[str, str] = {
    # fruit
    "appel": "apple", "appels": "apples", "peer": "pear", "peren": "pears",
    "stoofperen": "stewing pears", "banaan": "banana", "bananen": "bananas",
    "sinaasappel": "orange", "sinaasappels": "oranges", "handsinaasappels": "eating oranges",
    "perssinaasappels": "juicing oranges", "mandarijn": "mandarin", "mandarijnen": "mandarins",
    "citroen": "lemon", "citroenen": "lemons", "limoen": "lime", "limoenen": "limes",
    "druif": "grape", "druiven": "grapes", "pitloze": "seedless",
    "aardbei": "strawberry", "aardbeien": "strawberries", "blauwe bessen": "blueberries",
    "bosbessen": "blueberries", "framboos": "raspberry", "frambozen": "raspberries",
    "braam": "blackberry", "bramen": "blackberries", "ananas": "pineapple",
    "meloen": "melon", "meloenen": "melons", "watermeloen": "watermelon",
    "galiameloen": "galia melon", "granaatappel": "pomegranate", "granaatappels": "pomegranates",
    "perzik": "peach", "perziken": "peaches", "nectarijn": "nectarine", "nectarijnen": "nectarines",
    "pruim": "plum", "pruimen": "plums", "kers": "cherry", "kersen": "cherries",
    "passievrucht": "passion fruit", "passievruchten": "passion fruits", "kaki": "persimmon",
    # vegetables
    "aardappel": "potato", "aardappels": "potatoes", "aardappelen": "potatoes",
    "krieltjes": "baby potatoes", "kruimige": "floury", "vastkokende": "waxy",
    "tomaat": "tomato", "tomaten": "tomatoes", "cherrytomaten": "cherry tomatoes",
    "snoeptomaten": "snack tomatoes", "trostomaten": "vine tomatoes", "romatomaten": "roma tomatoes",
    "komkommer": "cucumber", "komkommers": "cucumbers", "minikomkommers": "mini cucumbers",
    "paprika": "bell pepper", "paprika's": "bell peppers", "puntpaprika": "pointed pepper",
    "puntpaprika's": "pointed peppers", "ui": "onion", "uien": "onions", "sjalot": "shallot",
    "sjalotten": "shallots", "bosui": "spring onion", "knoflook": "garlic",
    "wortel": "carrot", "wortels": "carrots", "wortelen": "carrots", "worteltjes": "baby carrots",
    "winterpeen": "winter carrots", "peen": "carrots", "bospeen": "bunched carrots",
    "bloemkool": "cauliflower", "spruiten": "Brussels sprouts", "spruitjes": "Brussels sprouts",
    "boerenkool": "kale", "kool": "cabbage", "rodekool": "red cabbage", "wittekool": "white cabbage",
    "spitskool": "pointed cabbage", "savooiekool": "savoy cabbage", "witlof": "chicory",
    "prei": "leek", "champignon": "mushroom", "champignons": "mushrooms",
    "kastanjechampignons": "chestnut mushrooms", "paddenstoelen": "mushrooms",
    "pompoen": "pumpkin", "flespompoen": "butternut squash", "sla": "lettuce",
    "ijsbergsla": "iceberg lettuce", "kropsla": "butterhead lettuce", "veldsla": "lamb's lettuce",
    "slamix": "salad mix", "spinazie": "spinach", "sperziebonen": "green beans",
    "boontjes": "beans", "snijbonen": "runner beans", "asperge": "asparagus",
    "asperges": "asparagus", "maiskolf": "corn on the cob", "maiskolven": "corn cobs",
    "suikermais": "sweetcorn", "mais": "corn", "biet": "beetroot", "bieten": "beetroots",
    "selderij": "celery", "bleekselderij": "celery", "knolselderij": "celeriac",
    "venkel": "fennel", "radijs": "radish", "radijsjes": "radishes", "pastinaak": "parsnip",
    "peultjes": "mangetout",
    # meat
    "gehakt": "minced meat", "rundergehakt": "minced beef", "varkensgehakt": "minced pork",
    "kipgehakt": "minced chicken", "half om half gehakt": "mixed minced meat",
    "gehaktballen": "meatballs", "kip": "chicken", "kipfilet": "chicken breast",
    "kipfilets": "chicken breasts", "kipdijfilet": "chicken thigh fillet",
    "kippendijen": "chicken thighs", "kippenpoten": "chicken legs", "kipkluifjes": "chicken drumsticks",
    "scharrelkipkluifjes": "free-range chicken drumsticks", "kippenvleugels": "chicken wings",
    "scharrel": "free-range", "rundvlees": "beef", "biefstuk": "steak", "ossenhaas": "beef tenderloin",
    "riblappen": "braising steak", "stoofvlees": "stewing beef", "varkensvlees": "pork",
    "varkenshaas": "pork tenderloin", "karbonade": "pork chop", "karbonades": "pork chops",
    "speklappen": "pork belly slices", "spek": "bacon", "spekreepjes": "bacon strips",
    "spekblokjes": "bacon cubes", "ontbijtspek": "breakfast bacon", "gerookte": "smoked",
    "gerookt": "smoked", "worst": "sausage", "worstjes": "sausages", "rookworst": "smoked sausage",
    "braadworst": "frying sausage", "vleeswaren": "cold cuts",
    "achterham": "cooked ham", "lamsvlees": "lamb", "mager": "lean", "magere": "lean",
    # fish
    "vis": "fish", "zalm": "salmon", "zalmfilet": "salmon fillet", "zalmfilets": "salmon fillets",
    "kabeljauw": "cod", "kabeljauwfilet": "cod fillet", "kabeljauwburgers": "cod burgers",
    "koolvis": "coley", "schol": "plaice", "garnalen": "prawns", "tonijn": "tuna",
    "haring": "herring", "makreel": "mackerel", "vissticks": "fish fingers",
    "mosselen": "mussels", "op huid": "skin-on",
    # dairy and eggs
    "melk": "milk", "halfvolle": "semi-skimmed", "volle": "full-fat", "karnemelk": "buttermilk",
    "griekse": "Greek", "kwark": "quark", "vla": "custard", "kaas": "cheese",
    "goudse": "Gouda", "jong belegen": "young matured", "belegen": "matured", "oude": "old",
    "oud": "aged", "plakken": "slices", "geraspte": "grated", "boter": "butter",
    "roomboter": "butter", "room": "cream", "slagroom": "whipping cream", "kookroom": "cooking cream",
    "ei": "egg", "eieren": "eggs", "scharreleieren": "free-range eggs",
    "vrije uitloop": "free-range", "van de versafdeling": "from the fresh counter",
    # cereals and coffee
    "havermout": "oats", "havervlokken": "oat flakes", "ontbijtgranen": "breakfast cereal",
    "koffie": "coffee", "koffiebonen": "coffee beans", "gemalen": "ground",
    "filterkoffie": "filter coffee", "snelfilterkoffie": "filter coffee", "koffiepads": "coffee pads",
    "koffiecups": "coffee capsules", "bonen": "beans",
    # descriptors
    "rode": "red", "rood": "red", "witte": "white", "wit": "white", "groene": "green",
    "groen": "green", "gele": "yellow", "geel": "yellow", "blauwe": "blue", "zwarte": "black",
    "zoete": "sweet", "zoet": "sweet", "bio": "organic", "biologisch": "organic",
    "biologische": "organic", "vers": "fresh", "verse": "fresh", "groot": "large",
    "grote": "large", "klein": "small", "kleine": "small", "rijp": "ripe",
    "eetrijp": "ready to eat", "hollandse": "Dutch", "nederlandse": "Dutch",
    "spaanse": "Spanish", "gesneden": "sliced", "gewassen": "washed",
    # packaging and quantities
    "voordeelverpakking": "value pack", "voordeelzak": "value bag", "zak": "bag",
    "zakje": "small bag", "bak": "tub", "bakje": "punnet", "doos": "box", "bos": "bunch",
    "bosje": "bunch", "krop": "head", "tros": "bunch", "trosje": "bunch", "stuk": "piece",
    "stuks": "pieces", "stk": "pc", "ca": "approx", "ongeveer": "about",
    # deals and labels
    "alle": "all", "met": "with", "zonder": "without", "en": "and", "gratis": "free", "halve": "half",
    "prijs": "price", "voor": "for", "korting": "off", "vanaf": "from", "alleen": "only",
}

_GLOSSARY_PATTERN = re.compile(
    r"(?<![\w'])("
    + "|".join(re.escape(w) for w in sorted(GLOSSARY, key=len, reverse=True))
    + r")(?![\w'])",
    re.IGNORECASE,
)
_DUTCH_ORDINAL = re.compile(r"\b(\d+)e\b")        # e.g. "2e halve prijs"
_DECIMAL_COMMA = re.compile(r"(\d),(\d)")          # e.g. "1,5 kilo"
_ENGLISH_SUFFIX = {1: "st", 2: "nd", 3: "rd"}

_OFFER_TEXT_FIELDS = ("name", "quantity_text", "member_label", "deal_text")


def product_name(product: str) -> str:
    """English name of a canonical product; the Dutch name if none is known."""
    return PRODUCT_NAMES.get(product, product)


def translate_text(text: Optional[str]) -> Optional[str]:
    """Translate Dutch grocery text word by word, keeping unknown words."""
    if not text:
        return text
    english = _DUTCH_ORDINAL.sub(_english_ordinal, text)
    english = _DECIMAL_COMMA.sub(r"\1.\2", english)
    return _GLOSSARY_PATTERN.sub(_translate_word, english)


def translate_offer(offer: Offer) -> dict[str, str]:
    """English versions of an offer's display texts, for the site's language toggle."""
    english = {field: translate_text(getattr(offer, field)) for field in _OFFER_TEXT_FIELDS}
    english["note"] = translate_text(offer.extras.get("note"))
    if offer.product:
        english["product"] = product_name(offer.product)
    return {field: text for field, text in english.items() if text}


def _english_ordinal(match: re.Match) -> str:
    number = int(match.group(1))
    suffix = "th" if 11 <= number % 100 <= 13 else _ENGLISH_SUFFIX.get(number % 10, "th")
    return f"{number}{suffix}"


def _translate_word(match: re.Match) -> str:
    dutch = match.group(1)
    return _match_case(dutch, GLOSSARY[dutch.lower()])


def _match_case(dutch: str, english: str) -> str:
    """Copy the capitalisation of the Dutch word: "BIO" -> "ORGANIC", "Zak" -> "Bag"."""
    if len(dutch) > 1 and dutch.isupper():
        return english.upper()
    if dutch[0].isupper():
        return english[0].upper() + english[1:]
    return english
