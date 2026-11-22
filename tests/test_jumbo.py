"""Tests for the Jumbo offers scraper (scraper/jumbo.py)."""
import pytest

from nuxt_page import nuxt_page
from scraper import jumbo
from scraper.models import Offer
from scraper.normalize import enrich

WEEK = ("2026-11-18T00:01:00+01:00", "2026-11-24T23:59:59+01:00")


def _promotion(pid="3022475", title="Rode uien", subtitle="Net 1 kilo", tags=("voor 1,00",),
               hidden=False) -> dict:
    return {"id": pid, "title": title + " ", "subtitle": subtitle, "hidden": hidden,
            "image": f"https://www.jumbo.com/img/{pid}.png", "url": f"/aanbiedingen/x/{pid}",
            "start": {"iso": WEEK[0]}, "end": {"iso": WEEK[1]},
            "tags": [{"text": t} for t in tags]}


def _page(featured=(), aisles=(), runtimes=None) -> str:
    sections = [{"promotions": list(featured), "categories": []},
                {"promotions": [], "categories": [{"title": "Groente", "promotions": list(aisles)}]}]
    if runtimes is None:
        runtimes = [{"active": True, "sections": sections}]
    return nuxt_page({"data": {"nuTab": {"activeTab": {"runtimes": runtimes}}}})


def _one(**promotion) -> Offer:
    [offer] = jumbo.parse_html(_page(featured=[_promotion(**promotion)]))
    return offer


def test_price_tag_becomes_offer_price():
    onions = _one()
    assert onions.store == "jumbo" and onions.name == "Rode uien"
    assert (onions.price, onions.deal_text, onions.old_price) == (1.0, None, None)
    assert onions.quantity_text == "Net 1 kilo"
    assert onions.url == "https://www.jumbo.com/aanbiedingen/x/3022475"
    assert onions.image == "https://www.jumbo.com/img/3022475.png"
    assert (onions.valid_from, onions.valid_to) == ("2026-11-18", "2026-11-24")
    assert onions.extras == {}


def test_reads_featured_and_aisle_promotions_of_the_active_week_once():
    page = _page(featured=[_promotion("1")], aisles=[_promotion("1"), _promotion("2")])
    assert [o.id for o in jumbo.parse_html(page)] == ["1", "2"]


def test_reads_next_weeks_runtime_too():
    # Jumbo's page shows "Nu geldig" and, from about Sunday, "Vanaf woensdag"; weeks.py splits them.
    runtimes = [{"active": True, "sections": [{"promotions": [_promotion("1")]}]},
                {"active": True, "sections": [{"promotions": [_promotion("2"), _promotion("1")]}]}]
    assert [o.id for o in jumbo.parse_html(_page(runtimes=runtimes))] == ["1", "2"]


def test_runtime_without_sections_has_no_promotions():
    assert jumbo.parse_html(_page(runtimes=[{"active": False}])) == []


def test_skips_hidden_promotions():
    assert jumbo.parse_html(_page(aisles=[_promotion(hidden=True)])) == []


@pytest.mark.parametrize("tag", ["2 voor 3,00", "1+1 gratis", "2e halve prijs", "25% korting", "1,00 korting"])
def test_deal_tags_become_deal_text(tag):
    offer = _one(tags=(tag,))
    assert (offer.price, offer.deal_text) == (None, tag)


def test_multi_buy_deal_gives_a_comparable_price():
    leeks = enrich(_one(title="Prei", subtitle="Los, per stuk", tags=("2 voor 1,00",)))
    assert (leeks.effective_price, leeks.unit_price, leeks.qty_unit) == (0.5, 0.5, "stuk")


def test_price_per_amount_tag_sets_price_and_quantity():
    mince = _one(title="Rundergehakt", subtitle="Schaal 500 gram", tags=("6,99 per kilo",))
    assert (mince.price, mince.quantity_text) == (6.99, "per kilo")


def test_bare_price_tag():
    assert _one(tags=("2,49",)).price == 2.49


def test_other_tags_become_a_note():
    offer = _one(tags=("voor 1,00", "Alleen online", "OP=OP"))
    assert offer.price == 1.0 and offer.extras == {"note": "Alleen online · OP=OP"}


def test_promotion_without_tags_has_no_price():
    offer = _one(tags=())
    assert (offer.price, offer.deal_text, offer.extras) == (None, None, {})


def test_subtitle_html_becomes_plain_text():
    subtitle = "Per verpakking<br />M.u.v. Voordeelverpakkingen&nbsp;<br /><br />"
    assert jumbo.subtitle_text(subtitle) == "Per verpakking · M.u.v. Voordeelverpakkingen"
    assert jumbo.subtitle_text("<br />") is None
    assert jumbo.subtitle_text(None) is None


def test_promotion_without_url_links_to_offers_page():
    promotion = _promotion()
    promotion["url"] = None
    assert jumbo.parse_promotion(promotion).url == jumbo.OFFERS_URL


def test_scrape_downloads_offers_page_with_jumbos_user_agent(monkeypatch):
    requests = []

    def fake_fetch(url, user_agent):
        requests.append((url, user_agent))
        return _page(featured=[_promotion()])

    monkeypatch.setattr(jumbo, "fetch_page", fake_fetch)
    assert [o.name for o in jumbo.scrape()] == ["Rode uien"]
    assert requests == [(jumbo.OFFERS_URL, jumbo.USER_AGENT)]
    assert "http" not in jumbo.USER_AGENT


@pytest.mark.parametrize("state", [
    {"data": {}},
    {"data": {"nuTab": {"activeTab": {"runtimes": {"active": True}}}}},
])
def test_unexpected_page_shape_is_reported(state):
    with pytest.raises(jumbo.JumboPageChanged, match="update scraper/jumbo.py"):
        jumbo.parse_html(nuxt_page(state))
