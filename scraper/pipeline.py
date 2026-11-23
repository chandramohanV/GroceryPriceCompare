"""Turn scraped offers into the offers.json payload: classify, normalise, compare.

Pure functions only (no network, files or clock), so the same code runs in
``run.py`` and in the browser (Pyodide) when an AH bonus page is uploaded.
"""
from __future__ import annotations

from dataclasses import fields
from itertools import combinations
from datetime import date, datetime
from typing import Optional

from .match import classify, variety
from .models import Offer
from .normalize import enrich
from .translate import product_name, translate_offer

# Stores whose shelf price already includes a "-30%" style discount (AH shows the old price)
STORES_SHOWING_DISCOUNTED_PRICE = frozenset({"lidl", "aldi", "dirk", "jumbo"})


def prepare(offers: list[Offer]) -> list[Offer]:
    """Keep the offers we compare and fill in product, category and unit price."""
    kept = []
    for o in offers:
        hit = classify(o.name, o.is_frozen)
        if not hit:
            continue
        o.product, o.category = hit
        v = variety(o.name, o.product)
        if v:
            o.extras["variety"] = v
        enrich(o, price_already_discounted=(
            o.store in STORES_SHOWING_DISCOUNTED_PRICE or o.old_price is not None))
        kept.append(o)
    return kept


def _comparison_unit(items: list[Offer]) -> Optional[str]:
    """The most common unit within a group (kg beats stuk on ties)."""
    units = [o.qty_unit for o in items if o.unit_price is not None]
    return max(set(units), key=lambda u: (units.count(u), u == "kg")) if units else None


def _compare_group(product: str, items: list[Offer]) -> dict:
    unit = _comparison_unit(items)
    comparable = sorted((o for o in items if o.qty_unit == unit and o.unit_price is not None),
                        key=lambda o: o.unit_price)
    best = comparable[0] if comparable else None
    entry = {
        "product": product,
        "product_en": product_name(product),
        "category": items[0].category,
        "unit": unit,
        "stores": sorted({o.store for o in items}),
        # True only when at least two stores have a price in the same unit
        "compared": len({o.store for o in comparable}) > 1,
        "offer_ids": [f"{o.store}:{o.id}" for o in sorted(
            items, key=lambda o: (o.unit_price is None, o.unit_price or 0))],
        "best": None,
        "saving_pct": None,
    }
    if best:
        entry["best"] = {"store": best.store, "id": best.id, "unit_price": best.unit_price}
        others = [o for o in comparable if o.store != best.store]
        if others and others[0].unit_price:
            nxt = others[0].unit_price
            entry["saving_pct"] = round((nxt - best.unit_price) / nxt * 100)
    return entry


def compare(offers: list[Offer]) -> list[dict]:
    """Group offers per canonical product and pick the cheapest per unit."""
    groups: dict[str, list[Offer]] = {}
    for o in offers:
        groups.setdefault(o.product, []).append(o)
    result = [_compare_group(product, items) for product, items in groups.items()]
    # products sold by several stores first, then by category and name
    result.sort(key=lambda e: (-len(e["stores"]), e["category"], e["product"]))
    return result


# What a comparison concludes; the rest of an entry (product, offers) doesn't depend on the stores.
VERDICT_FIELDS = ("unit", "compared", "best", "saving_pct")


def store_set_key(stores) -> str:
    """Key of a store combination in ``verdicts_by_store_set``, e.g. "aldi,lidl"."""
    return ",".join(sorted(stores))


def verdicts_by_store_set(offers: list[Offer]) -> dict[str, dict[str, dict]]:
    """For every combination of stores: product -> verdict among only those stores.

    Lets the site show "best deal" for the stores a visitor picks without
    re-implementing the comparison in JavaScript.
    """
    stores = sorted({o.store for o in offers})
    result = {}
    for size in range(1, len(stores) + 1):
        for chosen in combinations(stores, size):
            entries = compare([o for o in offers if o.store in chosen])
            result[store_set_key(chosen)] = {
                e["product"]: {f: e[f] for f in VERDICT_FIELDS} for e in entries}
    return result


def build_payload(offers: list[Offer], status: dict, now: datetime) -> dict:
    """The offers.json document the site renders."""
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "stores": status,
        "offers": [
            {"key": f"{o.store}:{o.id}", **o.to_dict(), "en": translate_offer(o)}
            for o in offers
        ],
        "comparisons": compare(offers),
        "verdicts_by_store_set": verdicts_by_store_set(offers),
    }


def offers_from_dicts(items: list[dict]) -> list[Offer]:
    """Offers from saved JSON, ignoring fields the site adds (key, en)."""
    known_fields = {f.name for f in fields(Offer)}
    return [Offer(**{k: v for k, v in o.items() if k in known_fields}) for o in items]


def offers_from_payload(payload: dict) -> list[Offer]:
    """Offers from an earlier offers.json document."""
    return offers_from_dicts(payload.get("offers", []))


def still_valid(offers: list[Offer], store: str, today: date) -> list[Offer]:
    """A store's earlier offers whose offer week hasn't ended yet."""
    return [o for o in offers
            if o.store == store and o.valid_to and o.valid_to >= today.isoformat()]


def replace_store_offers(payload: dict, store: str, label: str,
                         scraped: list[Offer], now: datetime) -> dict:
    """A new payload where one store's offers are replaced by freshly scraped ones.

    Used by the upload form (AH) and the daily refresh (Lidl, Aldi, Dirk, Jumbo, AH): the other stores
    keep their status and those of their offers whose week hasn't ended.
    """
    kept = prepare(scraped)
    today = now.date().isoformat()
    others = [o for o in offers_from_payload(payload)
              if o.store != store and (o.valid_to is None or o.valid_to >= today)]
    status = {**payload.get("stores", {}),
              store: {"name": label, "ok": True, "scraped": len(scraped), "matched": len(kept)}}
    return build_payload(others + kept, status, now)
