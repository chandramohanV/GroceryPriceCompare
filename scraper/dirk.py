"""Dirk NL offers scraper.

dirk.nl is a Nuxt site: the offers page embeds its offers in ``__NUXT_DATA__``
(decoded by ``devalue.py``), so one plain HTTP request is enough. An offer can
cover several products ("Kesbeke tafelzuren": three jars); the pack size and
picture come from the offer's products. Dirk's offer week runs Wednesday to Tuesday.
"""
from __future__ import annotations

import re
from typing import Optional

from .devalue import payload_from_html
from .models import Offer
from .web import fetch_page

LABEL = "Dirk"
BASE = "https://www.dirk.nl"
OFFERS_URL = f"{BASE}/aanbiedingen"
IMAGE_BASE = "https://web-fileserver.dirk.nl/"
OFFERS_KEY = "offers-currentOffers"
# "ACTIE_" marks every offer; anything else before the "_" (e.g. "VR, ZA & ZO") is worth showing
_PLAIN_OFFER_SIGN = "ACTIE"


class DirkPageChanged(RuntimeError):
    """The page no longer has the embedded offers data this scraper reads."""


def raw_offers(page: str) -> list[dict]:
    """The offer objects in the page, each once (an offer can be shown in several sections)."""
    try:
        sections = payload_from_html(page)["data"][OFFERS_KEY]
        offers = [offer for section in sections for offer in section["currentOffers"]]
    except (KeyError, TypeError, ValueError) as e:
        raise DirkPageChanged(f"Dirk offers data has an unexpected shape ({e!r}); "
                              "update scraper/dirk.py") from e
    unique = {}
    for offer in offers:
        unique.setdefault(offer.get("offerId"), offer)
    return list(unique.values())


def product_links(page: str) -> dict[int, str]:
    """Product id -> product page, from the links on the offers page."""
    return {int(product_id): BASE + path
            for path, product_id in re.findall(r'href="(/boodschappen/[^"]*/(\d+))"', page)}


def _products(offer: dict) -> list[dict]:
    """The product information of an offer's products (some offers list none)."""
    return [p["productInformation"] for p in offer.get("products") or []
            if p and p.get("productInformation")]


def _shared_packaging(products: list[dict]) -> Optional[str]:
    """The pack size when every product in the offer has the same one."""
    sizes = {p.get("packaging") for p in products}
    return sizes.pop() if len(sizes) == 1 else None


def _note(sign: Optional[str]) -> Optional[str]:
    label = (sign or "").split("_")[0].strip()
    return None if not label or label.upper() == _PLAIN_OFFER_SIGN else label


def _date(timestamp: Optional[str]) -> Optional[str]:
    return timestamp[:10] if timestamp else None


def _prices(offer: dict) -> tuple[Optional[float], Optional[float]]:
    """Offer and regular price (0 means "not shown").

    With a single product, its own prices are used: they belong to its pack size,
    while the offer's headline price can be for a different pack (witlof: €0.99
    on the offer, €1.98 for the 1 kg product).
    """
    entries = [p for p in offer.get("products") or [] if p]
    source = entries[0] if len(entries) == 1 and entries[0].get("offerPrice") else offer
    return source.get("offerPrice") or None, source.get("normalPrice") or None


def parse_offer(offer: dict, links: dict[int, str]) -> Offer:
    products = _products(offer)
    only = products[0] if len(products) == 1 else None
    price, normal = _prices(offer)
    note = _note(offer.get("textPriceSign"))
    return Offer(
        store="dirk",
        id=str(offer.get("offerId")),
        name=(offer.get("headerText") or "").strip(),
        image=IMAGE_BASE + only["image"] if only and only.get("image") else None,
        url=(links.get(only.get("productId")) if only else None) or OFFERS_URL,
        price=price,
        old_price=normal if normal and price and normal > price else None,
        quantity_text=_shared_packaging(products),
        valid_from=_date(offer.get("startDate")),
        valid_to=_date(offer.get("endDate")),
        extras={"note": note} if note else {},
    )


def parse_html(page: str) -> list[Offer]:
    links = product_links(page)
    return [parse_offer(offer, links) for offer in raw_offers(page)]


def scrape() -> list[Offer]:
    return parse_html(fetch_page(OFFERS_URL))
