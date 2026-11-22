"""Aldi NL offers scraper.

aldi.nl is a Next.js site: every offer page embeds its products as JSON in the
``__NEXT_DATA__`` script, so plain HTTP requests are enough (no browser needed).
Aldi has one page for this week and one for next week; both are read, and
``weeks.split_by_week`` later sorts the offers into this week and next week.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from .models import Offer
from .web import fetch_page

LABEL = "Aldi"
BASE = "https://www.aldi.nl"
OFFER_PAGES = (
    f"{BASE}/aanbiedingen.html",
    f"{BASE}/aanbiedingen-volgende-week.html",
)
OFFERS_REQUEST = "OFFER_GET"  # name of the page's API call that returns the offers

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
# "2 VOOR" / "5 VOOR": the price tag shows the price for that many packs
_MULTI_BUY_RE = re.compile(r"^(\d+)\s*VOOR$", re.I)
_IMAGE_TYPES = ("primary", "gallery")


class AldiPageChanged(RuntimeError):
    """The page no longer has the embedded offers data this scraper reads."""


def products_from_html(page: str) -> list[dict]:
    """The raw product objects embedded in one Aldi offers page."""
    match = _NEXT_DATA_RE.search(page)
    if not match:
        raise AldiPageChanged("no __NEXT_DATA__ script on the Aldi offers page")
    try:
        api_calls = json.loads(json.loads(match.group(1))["props"]["pageProps"]["apiData"])
        response = next(body["res"] for name, body in api_calls if name == OFFERS_REQUEST)
        return list(response["algoliaDataMap"].values())
    except (KeyError, TypeError, ValueError, StopIteration) as e:
        raise AldiPageChanged(f"Aldi offers data has an unexpected shape ({e!r}); "
                              "update scraper/aldi.py") from e


def _image(item: dict) -> Optional[str]:
    assets = item.get("assets") or []
    for kind in _IMAGE_TYPES:
        for asset in assets:
            if asset.get("type") == kind and asset.get("url"):
                return asset["url"]
    return None


def _validity(item: dict) -> tuple[Optional[str], Optional[str]]:
    promotions = item.get("promotionPrices") or [{}]
    first = promotions[0]
    return first.get("validFromLocalDate"), first.get("validUntilLocalDate")


def _price_fields(current: dict) -> dict:
    """Price, old price, deal and note from Aldi's price tag."""
    price = current.get("priceValue")
    old_price = (current.get("strikePrice") or {}).get("strikePriceValue")
    label = ((current.get("priceTagLabels") or {}).get("promoText1") or "").strip()

    multi_buy = _MULTI_BUY_RE.match(label)
    if multi_buy and price is not None:
        packs = int(multi_buy.group(1))
        return {
            "price": None,  # the tag price is for all packs; the deal text carries it
            "old_price": round(old_price / packs, 2) if old_price else None,
            "deal_text": f"{packs} voor {price:.2f}",
            "note": None,
        }
    is_discount = "%" in label
    return {
        "price": price,
        "old_price": old_price,
        "deal_text": label.lower() if is_discount else None,
        # e.g. "OP=OP" (while stocks last), "VANAF" (from-price), "v.a. za. 21.11."
        "note": label if label and not is_discount else None,
    }


def parse_item(item: dict) -> Optional[Offer]:
    """One Aldi product as an Offer, or None when it has no price (e.g. a teaser)."""
    current = item.get("currentPrice")
    if not current:
        return None
    prices = _price_fields(current)
    valid_from, valid_to = _validity(item)
    slug = item.get("productSlug")
    return Offer(
        store="aldi",
        id=str(item.get("objectID")),
        name=(item.get("name") or "").strip(),
        image=_image(item),
        url=f"{BASE}/product/{slug}.html" if slug else None,
        price=prices["price"],
        old_price=prices["old_price"],
        deal_text=prices["deal_text"],
        quantity_text=item.get("salesUnit"),
        valid_from=valid_from,
        valid_to=valid_to,
        extras={"note": prices["note"]} if prices["note"] else {},
    )


def parse_pages(pages: list[str]) -> list[Offer]:
    """Offers from all pages, each product once per offer period (it can be on offer both weeks)."""
    offers: list[Offer] = []
    seen: set[tuple[str, Optional[str]]] = set()
    for page in pages:
        for item in products_from_html(page):
            offer = parse_item(item)
            if offer is None or (offer.id, offer.valid_from) in seen:
                continue
            seen.add((offer.id, offer.valid_from))
            offers.append(offer)
    return offers


def scrape() -> list[Offer]:
    return parse_pages([fetch_page(url) for url in OFFER_PAGES])
