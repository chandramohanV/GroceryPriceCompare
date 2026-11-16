"""Lidl NL offers scraper.

The offers page embeds every product tile as JSON in a ``data-grid-data``
attribute, so a single plain HTTP request is enough (no browser needed).
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from .models import Offer

OFFERS_URL = "https://www.lidl.nl/c/store/aanbiedingen/a10008785"
BASE = "https://www.lidl.nl"
USER_AGENT = (
    "Mozilla/5.0 (compatible; GroceryPriceCompare/1.0; "
    "+https://github.com/chandramohanV/GroceryPriceCompare)"
)

_GRID_RE = re.compile(r'data-grid-data="([^"]*)"')
_TZ = ZoneInfo("Europe/Amsterdam")
# Only treat ribbon text as a "deal" if it describes a discount
_DEAL_WORDS = re.compile(r"%|gratis|halve prijs|voor\s*€?\s*\d", re.I)


def fetch_html(url: str = OFFERS_URL) -> str:
    import httpx  # imported lazily so parsing/tests don't need it

    resp = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "nl-NL,nl;q=0.9"},
        timeout=30,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def _iso_from_ts(ts) -> Optional[str]:
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=_TZ).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _iso_from_str(s) -> Optional[str]:
    if not s or s.startswith("2200"):  # Lidl uses 2200-01-01 for "no end date"
        return None
    return s[:10]


def _region_prices(item: dict) -> dict:
    regions = item.get("regionsPrices") or {}
    if not regions:
        return {}
    return regions.get("1") or next(iter(regions.values()))


def parse_item(item: dict) -> Offer:
    keyfacts = item.get("keyfacts") or {}
    region = _region_prices(item)
    current = region.get("currentPrice") or {}
    plus = (region.get("currentLidlPlusPrice") or {})
    plus_price = plus.get("price") or {}
    top = item.get("price") or {}

    price = current.get("price", top.get("price"))
    discount = current.get("discount") or top.get("discount") or {}
    old_price = discount.get("deletedPrice") or current.get("oldPrice") or top.get("oldPrice")

    member_price = plus_price.get("price")
    plus_discount = plus_price.get("discount") or {}
    if member_price is not None and old_price is None:
        old_price = plus_discount.get("deletedPrice") or plus_price.get("oldPrice")

    deal_text = (
        discount.get("discountText")
        or plus.get("highlightText")
        or plus_discount.get("discountText")
    )

    extras = {}
    if deal_text and not _DEAL_WORDS.search(deal_text):
        extras["note"] = deal_text
        deal_text = None

    packaging = (current.get("packaging") or top.get("packaging")
                 or plus_price.get("packaging") or {})

    valid_from = _iso_from_ts(item.get("storeStartDate")) or _iso_from_str(
        plus_price.get("startDate") or current.get("startDate"))
    valid_to = _iso_from_ts(item.get("storeEndDate")) or _iso_from_str(
        plus_price.get("endDate") or current.get("endDate"))

    url = item.get("canonicalUrl")
    if url and url.startswith("/"):
        url = BASE + url

    return Offer(
        store="lidl",
        id=str(item.get("productId") or item.get("itemId") or item.get("erpNumber")),
        name=(item.get("fullTitle") or item.get("title") or "").strip(" -"),
        image=item.get("image"),
        url=url,
        price=price,
        old_price=old_price,
        member_price=member_price,
        member_label=plus.get("lidlPlusText") if member_price is not None else None,
        deal_text=deal_text,
        quantity_text=packaging.get("text"),
        valid_from=valid_from,
        valid_to=valid_to,
        extras=extras,
    )


def is_fruit_or_veg(item: dict) -> bool:
    keyfacts = item.get("keyfacts") or {}
    path = keyfacts.get("wonCategoryPrimary") or ""
    return "Groenten & fruit" in path or item.get("category") == "F+V"


def parse_html(page: str, only_produce: bool = True) -> list[Offer]:
    offers: list[Offer] = []
    seen: set[str] = set()
    for raw in _GRID_RE.findall(page):
        try:
            item = json.loads(html.unescape(raw))
        except json.JSONDecodeError:
            continue
        if only_produce and not is_fruit_or_veg(item):
            continue
        offer = parse_item(item)
        if offer.id in seen:
            continue
        seen.add(offer.id)
        offers.append(offer)
    return offers


def scrape() -> list[Offer]:
    return parse_html(fetch_html())


def _cli(argv: Iterable[str]) -> None:  # pragma: no cover
    for o in scrape():
        print(json.dumps(o.to_dict(), ensure_ascii=False))


if __name__ == "__main__":  # pragma: no cover
    import sys

    _cli(sys.argv[1:])
