"""Albert Heijn bonus offers from AH's app API (the API behind the Albert Heijn app).

ah.nl/bonus refuses scripts (HTTP 403), but the app's product search answers with an anonymous
token, no account needed. Its bonus filter is ignored, so every search page is read and the
in-store bonus products (promotion type NATIONAL, as on ah.nl/bonus) are kept; online-only
package deals and aisles we never compare (drinks, snacks, sweets...) are skipped. The search
shows bonuses once their week has started, so this gives this week's offers; next week's still
come from the site's upload form.

This is an unofficial API: AH can change or close it at any time. A failure is reported by
the daily run, which then keeps the AH offers it saved earlier.
"""
from __future__ import annotations

from typing import Optional

from .models import Offer
from .normalize import parse_quantity

API = "https://api.ah.nl"
TOKEN_PATH = "/mobile-auth/v1/auth/token/anonymous"
SEARCH_PATH = "/mobile-services/product/search/v2"
CLIENT_ID = "appie"  # the app's public client id for anonymous tokens
APP_USER_AGENT = "Appie/8.22.3"
APPLICATION = "AHWEBSHOP"
PAGE_SIZE = 1000  # the most the search returns per page
# The search claims 10 pages but answers 400 from the 4th: it pages through 3,000 products at most.
# The bonus products rank high, so those hold this week's bonus.
PAGE_LIMIT_STATUS = 400
MAX_PAGES = 20  # guards against a page count that never ends
TIMEOUT_SECONDS = 30
PRODUCT_URL = "https://www.ah.nl/producten/product/wi{}"

IN_STORE_BONUS = "NATIONAL"
FROZEN_AISLE = "Diepvries"
# Aisles we never compare; their names fool the product matcher ("Amstel Radler citroen",
# "Lay's Paprika", "Knorr Cup-a-soup champignon", "Roomboter krakelingen").
SKIPPED_AISLES = frozenset({
    "Baby en kind", "Bakkerij", "Bier, wijn, aperitieven", "Borrel, chips, snacks",
    "Frisdrank, sappen, water", "Koek, snoep, chocolade", "Soepen, sauzen, kruiden, olie",
    "Drogisterij", "Huishouden", "Huisdier",
})
WEIGHT_DEAL = "DISCOUNT_WEIGHT"  # "100 GRAM VOOR 1.99": the price is per weight, not per pack
IMAGE_WIDTH = 400


class AHApiChanged(RuntimeError):
    """AH's app API answered, but not in the shape this module reads."""


def _image(product: dict) -> Optional[str]:
    images = product.get("images") or []
    preferred = [i for i in images if i.get("width") == IMAGE_WIDTH] or images
    return preferred[0].get("url") if preferred else None


def _weight_deal(product: dict) -> Optional[dict]:
    return next((label for label in product.get("discountLabels") or []
                 if label.get("code") == WEIGHT_DEAL and label.get("count") and label.get("price")), None)


def _per_weight_prices(product: dict, deal: dict) -> dict:
    """Price, old price and quantity for the deal's weight ("100 gram"), not the whole pack."""
    deal_quantity = f"{deal['count']} gram"
    deal_kg, _ = parse_quantity(deal_quantity)
    pack_kg, unit = parse_quantity(product.get("salesUnitSize"))
    old_pack_price = product.get("priceBeforeBonus")
    old_price = None
    if old_pack_price and deal_kg and pack_kg and unit == "kg":
        old_price = round(old_pack_price * deal_kg / pack_kg, 2)
    return {"price": deal["price"], "old_price": old_price, "quantity_text": deal_quantity}


def _prices(product: dict) -> dict:
    """Price, old price and quantity as the pipeline expects them.

    ``currentPrice`` is the bonus price already ("voor 0.99", "25% korting"). Deals such as
    "1+1 gratis" or "2 voor 3.50" have none: the shelf price goes in and the deal text is
    applied once by ``normalize.enrich``.
    """
    weight_deal = _weight_deal(product)
    if weight_deal:
        return _per_weight_prices(product, weight_deal)
    current, shelf = product.get("currentPrice"), product.get("priceBeforeBonus")
    if current is None:
        return {"price": shelf, "old_price": None, "quantity_text": product.get("salesUnitSize")}
    return {"price": current, "old_price": shelf, "quantity_text": product.get("salesUnitSize")}


def _is_compared_in_store_bonus(product: dict) -> bool:
    return (bool(product.get("isBonus")) and product.get("promotionType") == IN_STORE_BONUS
            and product.get("mainCategory") not in SKIPPED_AISLES)


def parse_product(product: dict) -> Optional[Offer]:
    """One in-store bonus product from an aisle we compare as an Offer, or None for anything else."""
    if not _is_compared_in_store_bonus(product) or not product.get("title"):
        return None
    mechanism = (product.get("bonusMechanism") or "").strip()
    return Offer(
        store="ah",
        id=str(product.get("webshopId")),
        name=product["title"].strip(),
        image=_image(product),
        url=PRODUCT_URL.format(product.get("webshopId")),
        deal_text=mechanism.lower() or None,
        valid_from=product.get("bonusStartDate"),
        valid_to=product.get("bonusEndDate"),
        is_frozen=product.get("mainCategory") == FROZEN_AISLE,
        **_prices(product),
    )


def offers_from_products(products: list[dict]) -> list[Offer]:
    """The in-store bonus offers among search results, each product once."""
    offers: list[Offer] = []
    seen: set[str] = set()
    for product in products:
        offer = parse_product(product)
        if offer and offer.id not in seen:
            seen.add(offer.id)
            offers.append(offer)
    return offers


def _anonymous_token(client) -> str:
    resp = client.post(API + TOKEN_PATH, json={"clientId": CLIENT_ID})
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise AHApiChanged("AH's token answer has no access_token; update scraper/ah_api.py")
    return token


def _search_page(client, token: str, page: int) -> Optional[dict]:
    """One search page, or None past the search's paging limit (only after the first page)."""
    resp = client.get(API + SEARCH_PATH, headers={"Authorization": f"Bearer {token}"},
                      params={"sortOn": "RELEVANCE", "size": PAGE_SIZE, "page": page})
    if page > 0 and resp.status_code == PAGE_LIMIT_STATUS:
        return None
    resp.raise_for_status()
    body = resp.json()
    if not isinstance(body.get("products"), list) or "page" not in body:
        raise AHApiChanged("AH's search answer has no products/page; update scraper/ah_api.py")
    return body


def fetch_products(client) -> list[dict]:
    """Every product of AH's search, page by page; ``client`` is an httpx.Client (or a fake)."""
    token = _anonymous_token(client)
    products: list[dict] = []
    page, pages = 0, 1
    while page < min(pages, MAX_PAGES):
        body = _search_page(client, token, page)
        if body is None:
            break
        products.extend(body["products"])
        pages = body["page"].get("totalPages") or 0
        page += 1
    return products


def scrape() -> list[Offer]:
    import httpx  # imported lazily so parsing/tests don't need it

    headers = {"User-Agent": APP_USER_AGENT, "x-application": APPLICATION}
    with httpx.Client(headers=headers, timeout=TIMEOUT_SECONDS) as client:
        return offers_from_products(fetch_products(client))
