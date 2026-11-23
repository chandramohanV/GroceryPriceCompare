"""Tests for AH's bonus offers from the app API (scraper/ah_api.py), with a fake transport instead of AH."""
import httpx
import pytest

from scraper import ah_api
from scraper.models import Offer
from scraper.pipeline import prepare

WEEK = ("2026-11-23", "2026-11-29")
IMAGES = [{"width": w, "height": w, "url": f"https://static.ah.nl/dam/product/x?rendition={w}"}
          for w in (800, 400, 200)]


def _product(webshop_id=1, title="AH Broccoli", size="500 g", current=0.99, shelf=1.35,
             mechanism="VOOR 0.99", labels=(), promotion="NATIONAL", is_bonus=True,
             category="Groente, aardappelen") -> dict:
    return {"webshopId": webshop_id, "title": title, "salesUnitSize": size, "images": IMAGES,
            "currentPrice": current, "priceBeforeBonus": shelf, "bonusMechanism": mechanism,
            "discountLabels": list(labels), "promotionType": promotion, "isBonus": is_bonus,
            "bonusStartDate": WEEK[0], "bonusEndDate": WEEK[1], "mainCategory": category}


def _one(**product) -> Offer:
    offer = ah_api.parse_product(_product(**product))
    assert offer is not None
    return offer


# ---------- parsing ----------
def test_fixed_price_bonus_becomes_an_offer():
    broccoli = _one()
    assert (broccoli.store, broccoli.id, broccoli.name) == ("ah", "1", "AH Broccoli")
    assert (broccoli.price, broccoli.old_price, broccoli.deal_text) == (0.99, 1.35, "voor 0.99")
    assert broccoli.quantity_text == "500 g"
    assert (broccoli.valid_from, broccoli.valid_to) == WEEK
    assert broccoli.url == "https://www.ah.nl/producten/product/wi1"
    assert broccoli.image == "https://static.ah.nl/dam/product/x?rendition=400"
    assert broccoli.is_frozen is False


@pytest.mark.parametrize("mechanism,deal,unit_price", [
    ("1 + 1 gratis", "1 + 1 gratis", 1.1),      # pay one of two: 2.20 / 2 per 1 kg
    ("2e Halve Prijs", "2e halve prijs", 1.65),  # 2.20 * 0.75
    ("2 voor 3.50", "2 voor 3.50", 1.75),        # the deal is the price
])
def test_deal_without_bonus_price_is_applied_once_to_the_shelf_price(mechanism, deal, unit_price):
    [offer] = prepare([_one(title="AH Appels", size="1 kg", current=None, shelf=2.20, mechanism=mechanism)])
    assert (offer.price, offer.old_price, offer.deal_text) == (2.20, None, deal)
    assert offer.unit_price == unit_price


def test_percentage_bonus_price_is_not_discounted_twice():
    [offer] = prepare([_one(title="Pink Lady Appels schaal", size="1 kg", current=2.62, shelf=3.49,
                            mechanism="25% korting")])
    assert offer.unit_price == 2.62


def test_weight_deal_is_priced_per_its_weight_not_per_pack():
    salmon = _one(title="AH Zalmfilet", size="ca. 310 g", current=2.59, shelf=9.99,
                  mechanism="100 GRAM VOOR 2.59",
                  labels=[{"code": "DISCOUNT_WEIGHT", "count": 100, "price": 2.59, "unit": "GRAM"}])
    assert (salmon.price, salmon.quantity_text, salmon.deal_text) == (2.59, "100 gram", "100 gram voor 2.59")
    assert salmon.old_price == 3.22  # 9.99 for 310 g, scaled to 100 g
    [prepared] = prepare([salmon])
    assert prepared.unit_price == 25.9


def test_weight_deal_without_a_pack_weight_has_no_old_price():
    offer = _one(size="per stuk", labels=[{"code": "DISCOUNT_WEIGHT", "count": 500, "price": 0.99}])
    assert (offer.price, offer.old_price, offer.quantity_text) == (0.99, None, "500 gram")


def test_frozen_aisle_marks_the_offer_frozen():
    assert _one(category="Diepvries").is_frozen is True


@pytest.mark.parametrize("product", [
    _product(is_bonus=False, promotion=None),   # regular price, no bonus
    _product(promotion="AHONLINE"),              # online-only package deal
    _product(promotion="PERPETUAL"),             # long-running, not this week's bonus
    _product(title="Lay's Paprika", category="Borrel, chips, snacks"),  # an aisle we never compare
    _product(title=""),
])
def test_non_in_store_bonus_products_are_skipped(product):
    assert ah_api.parse_product(product) is None


def test_offers_from_products_keeps_each_product_once():
    products = [_product(1), _product(1), _product(2, title="AH Mango"), _product(3, promotion="AHONLINE")]
    assert [o.id for o in ah_api.offers_from_products(products)] == ["1", "2"]


# ---------- fetching (fake transport) ----------
def _client(search_pages: list[dict], token_body=None, requests=None) -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        if request.url.path == ah_api.TOKEN_PATH:
            return httpx.Response(200, json={"access_token": "t0k"} if token_body is None else token_body)
        return httpx.Response(200, json=search_pages[int(request.url.params["page"])])
    return httpx.Client(transport=httpx.MockTransport(handle))


def _search_page(products: list[dict], total_pages: int) -> dict:
    return {"products": products, "page": {"totalPages": total_pages}}


def test_fetch_products_reads_every_page_with_the_anonymous_token():
    requests = []
    pages = [_search_page([_product(1)], 2), _search_page([_product(2)], 2)]
    products = ah_api.fetch_products(_client(pages, requests=requests))
    assert [p["webshopId"] for p in products] == [1, 2]
    searches = [r for r in requests if r.url.path == ah_api.SEARCH_PATH]
    assert [r.url.params["page"] for r in searches] == ["0", "1"]
    assert all(r.headers["Authorization"] == "Bearer t0k" for r in searches)


def test_fetch_products_stops_at_the_page_limit():
    pages = [_search_page([_product(i)], 10_000) for i in range(ah_api.MAX_PAGES + 1)]
    assert len(ah_api.fetch_products(_client(pages))) == ah_api.MAX_PAGES


def test_missing_token_is_reported_as_an_api_change():
    with pytest.raises(ah_api.AHApiChanged, match="access_token"):
        ah_api.fetch_products(_client([], token_body={}))


def test_unexpected_search_answer_is_reported_as_an_api_change():
    with pytest.raises(ah_api.AHApiChanged, match="products"):
        ah_api.fetch_products(_client([{"error": "gone"}]))


def test_http_error_is_raised():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403)))
    with pytest.raises(httpx.HTTPStatusError):
        ah_api.fetch_products(client)
