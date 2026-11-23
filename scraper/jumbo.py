"""Jumbo NL offers scraper.

jumbo.com is a Nuxt site: /aanbiedingen/nu embeds every promotion of this offer
week, and from about Sunday also next week's, in ``__NUXT_DATA__`` (decoded by ``devalue.py``), the featured ones and
those grouped per aisle, so one plain HTTP request is enough. Jumbo publishes
promotions rather than shelf prices: the price or deal is a short tag such as
"voor 1,00", "2 voor 3,00" or "1+1 gratis", and the pack size is in the subtitle.
Jumbo's offer week runs Wednesday to Tuesday.
"""
from __future__ import annotations

import html
import re
from typing import Iterator, Optional

from .devalue import payload_from_html
from .models import Offer
from .web import fetch_page

LABEL = "Jumbo"
BASE = "https://www.jumbo.com"
OFFERS_URL = f"{BASE}/aanbiedingen/nu"
OFFERS_KEY = "nuTab"
# Jumbo's bot protection stalls requests whose User-Agent contains a URL (the
# shared one links to the project), so Jumbo gets the same name without the link.
USER_AGENT = "Mozilla/5.0 (compatible; GroceryPriceCompare/1.0)"

_NUM = r"(\d+(?:,\d{1,2})?)"
# "voor 1,00": the offer price of one pack
_PRICE_TAG_RE = re.compile(rf"^voor\s+€?\s*{_NUM}$", re.I)
# "1,99 per 500 gram" / "6,99 per kilo": a price for the stated amount
_PRICE_PER_RE = re.compile(rf"^€?\s*{_NUM}\s+(per\s+.+)$", re.I)
# "2,49": a bare price
_BARE_PRICE_RE = re.compile(rf"^€?\s*{_NUM}$")
# Deals normalize.py understands: "2 voor 3,00", "1+1 gratis", "2e halve prijs", "25% korting"
_DEAL_RE = re.compile(r"\d+\s+voor\s|\+\s*\d+\s*gratis|halve\s+prijs|%|\bkorting\b", re.I)
_LINE_BREAK_RE = re.compile(r"<br\s*/?>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


class JumboPageChanged(RuntimeError):
    """The page no longer has the embedded offers data this scraper reads."""


def _amount(text: str) -> float:
    return float(text.replace(",", "."))


def _runtimes(page: str) -> list[dict]:
    """The page's offer periods: this week's and, once Jumbo shows it, next week's ("Vanaf woensdag")."""
    try:
        runtimes = payload_from_html(page)["data"][OFFERS_KEY]["activeTab"]["runtimes"]
        if not isinstance(runtimes, list):
            raise TypeError("runtimes is not a list")
        return runtimes
    except (KeyError, TypeError, ValueError) as e:
        raise JumboPageChanged(f"Jumbo offers data has an unexpected shape ({e!r}); "
                               "update scraper/jumbo.py") from e


def _promotions_in(section: dict) -> Iterator[dict]:
    yield from section.get("promotions") or []
    for category in section.get("categories") or []:
        yield from category.get("promotions") or []


def raw_promotions(page: str) -> list[dict]:
    """The visible promotions of every offer period on the page, each once.

    A promotion can be both featured and listed under its aisle.
    """
    unique: dict[str, dict] = {}
    for runtime in _runtimes(page):
        for section in runtime.get("sections") or []:
            for promotion in _promotions_in(section):
                if promotion.get("id") and not promotion.get("hidden"):
                    unique.setdefault(promotion["id"], promotion)
    return list(unique.values())


def subtitle_text(subtitle: Optional[str]) -> Optional[str]:
    """The subtitle as plain text, its lines joined with " · " ("Alle zakken à 150 gram")."""
    if not subtitle:
        return None
    lines = (_TAG_RE.sub("", line) for line in _LINE_BREAK_RE.split(subtitle))
    cleaned = [" ".join(html.unescape(line).split()) for line in lines]
    return " · ".join(line for line in cleaned if line) or None


def _tag_fields(tags: list[str]) -> dict:
    """Price, pack size from the price, deal and note from a promotion's tags."""
    fields: dict = {"price": None, "quantity_text": None, "deal_text": None}
    notes = []
    for tag in tags:
        price = _PRICE_TAG_RE.match(tag) or _BARE_PRICE_RE.match(tag)
        price_per = _PRICE_PER_RE.match(tag)
        if price and fields["price"] is None:
            fields["price"] = _amount(price.group(1))
        elif price_per and fields["price"] is None:
            fields["price"] = _amount(price_per.group(1))
            fields["quantity_text"] = price_per.group(2)
        elif _DEAL_RE.search(tag) and fields["deal_text"] is None:
            fields["deal_text"] = tag
        else:
            notes.append(tag)  # e.g. "Alleen online", "OP=OP", "Alleen in de winkel"
    fields["note"] = " · ".join(notes) or None
    return fields


def _date(moment: Optional[dict]) -> Optional[str]:
    iso = (moment or {}).get("iso")
    return iso[:10] if iso else None


FROZEN_AISLE = "Diepvries"


def frozen_promotion_ids(page: str) -> set[str]:
    """Promotions listed in the frozen aisle (featured ones appear under their aisle too)."""
    return {promotion.get("id")
            for runtime in _runtimes(page) for section in runtime.get("sections") or []
            for category in section.get("categories") or [] if category.get("title") == FROZEN_AISLE
            for promotion in category.get("promotions") or []}


def parse_promotion(promotion: dict, is_frozen: bool = False) -> Offer:
    tags = [(tag.get("text") or "").strip() for tag in promotion.get("tags") or []]
    fields = _tag_fields([tag for tag in tags if tag])
    path = promotion.get("url")
    return Offer(
        store="jumbo",
        id=str(promotion["id"]),
        name=(promotion.get("title") or "").strip(),
        image=promotion.get("image"),
        url=BASE + path if path else OFFERS_URL,
        price=fields["price"],
        deal_text=fields["deal_text"],
        # a "per 500 gram" price states the amount it is for; otherwise the subtitle does
        quantity_text=fields["quantity_text"] or subtitle_text(promotion.get("subtitle")),
        valid_from=_date(promotion.get("start")),
        valid_to=_date(promotion.get("end")),
        is_frozen=is_frozen,
        extras={"note": fields["note"]} if fields["note"] else {},
    )


def parse_html(page: str) -> list[Offer]:
    frozen = frozen_promotion_ids(page)
    return [parse_promotion(promotion, promotion["id"] in frozen) for promotion in raw_promotions(page)]


def scrape() -> list[Offer]:
    return parse_html(fetch_page(OFFERS_URL, user_agent=USER_AGENT))
