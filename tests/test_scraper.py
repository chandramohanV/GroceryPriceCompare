from pathlib import Path

import pytest

from scraper import ah, lidl
from scraper.match import classify
from scraper.models import Offer
from scraper.normalize import deal_factor, enrich, multi_price, parse_quantity
from scraper.run import compare, prepare

FIXTURE = Path(__file__).parent / "fixtures" / "lidl_sample.html"


# ---------- normalize ----------
@pytest.mark.parametrize("text,expected", [
    ("1500 g", (1.5, "kg")),
    ("Per 500 g", (0.5, "kg")),
    ("1 kg", (1.0, "kg")),
    ("1,5 kilo", (1.5, "kg")),
    ("2 x 150 g", (0.3, "kg")),
    ("750 ml", (0.75, "l")),
    ("1 Stk.", (1.0, "stuk")),
    ("Per stuk", (1.0, "stuk")),
    ("6 stuks", (6.0, "stuk")),
    ("per kilo", (1.0, "kg")),
    ("Kiwi gold", (None, None)),
    ("Jonagold appels", (None, None)),
    (None, (None, None)),
])
def test_parse_quantity(text, expected):
    assert parse_quantity(text) == expected


@pytest.mark.parametrize("deal,factor", [
    ("1+1 gratis", 0.5),
    ("2+1 gratis", 2 / 3),
    ("2e halve prijs", 0.75),
    ("-45%", 1.0),
    (None, 1.0),
])
def test_deal_factor(deal, factor):
    assert deal_factor(deal) == pytest.approx(factor)


def test_multi_price():
    assert multi_price("2 voor 5,00") == (2, 5.0)
    assert multi_price("3 voor €4") == (3, 4.0)
    assert multi_price("25% korting") is None


def test_enrich_ah_one_plus_one():
    o = enrich(Offer(store="ah", id="x", name="AH Elstar appels", price=2.49,
                     deal_text="1+1 gratis", quantity_text="1 kg"),
               price_already_discounted=False)
    assert o.effective_price == pytest.approx(1.25, abs=0.01)
    assert o.unit_price == pytest.approx(1.25, abs=0.01)


def test_enrich_percent_not_double_counted():
    o = enrich(Offer(store="ah", id="x", name="Mango", price=1.00, old_price=1.50,
                     deal_text="25% korting", quantity_text="per stuk"),
               price_already_discounted=True)
    assert o.effective_price == 1.00


# ---------- match ----------
@pytest.mark.parametrize("name,product", [
    ("QUALITÉ SUISSE Jonagold appels", "Appels"),
    ("AH Elstar appels 1 kg", "Appels"),
    ("Conference peren", "Peren"),
    ("Zoete aardappels", "Zoete aardappels"),
    ("AH Kruimige aardappelen 3 kg", "Aardappels"),
    ("Bio flespompoen", "Pompoen"),
    ("Kiwi gold", "Kiwi's"),
    ("AH Cherrytomaten", "Tomaten"),
    ("Appelsap", None),
    ("AH Appeltaart", None),
    ("Aardbei kruimelvlaaitje", None),
    ("Stoofperencake", None),
    ("Vierkante donut", None),
])
def test_classify(name, product):
    hit = classify(name)
    assert (hit[0] if hit else None) == product


# ---------- lidl parser on real page sample ----------
def test_lidl_parse_fixture():
    offers = lidl.parse_html(FIXTURE.read_text(encoding="utf-8"))
    names = {o.name for o in offers}
    assert "Mango" in names
    assert "Vierkante donut" not in names  # not fruit/veg category
    mango = next(o for o in offers if o.name == "Mango")
    assert mango.price == 1.79
    assert mango.member_price == 0.99
    assert mango.member_label == "met Lidl Plus"
    assert mango.deal_text == "-45%"
    assert mango.image.startswith("https://")
    assert mango.url.startswith("https://www.lidl.nl/p/")
    assert mango.valid_from <= mango.valid_to
    sweet = next(o for o in offers if o.name == "Zoete aardappels")
    assert sweet.price is None and sweet.member_price == 0.99  # Lidl Plus only


def test_prepare_drops_pastry_and_computes_unit_price():
    offers = prepare(lidl.parse_html(FIXTURE.read_text(encoding="utf-8")))
    names = {o.name for o in offers}
    assert "Aardbei kruimelvlaaitje" not in names
    apples = next(o for o in offers if o.product == "Appels")
    assert apples.qty_unit == "kg" and apples.unit_price == pytest.approx(0.99, abs=0.01)
    assert apples.deal_text is None  # "Zak 1,5 kilo" is not a discount


# ---------- comparison ----------
def test_compare_picks_cheapest_per_kg():
    offers = [
        Offer(store="lidl", id="1", name="Jonagold appels", price=1.49, quantity_text="1500 g"),
        Offer(store="ah", id="2", name="AH Elstar appels", price=2.49, deal_text="1+1 gratis",
              quantity_text="1 kg"),
    ]
    rows = compare(prepare(offers))
    assert len(rows) == 1
    row = rows[0]
    assert row["product"] == "Appels" and row["unit"] == "kg"
    assert row["best"]["store"] == "lidl"
    assert row["stores"] == ["ah", "lidl"]
    assert row["saving_pct"] == 21  # 0.99 vs 1.25 per kg


# ---------- AH card parsing (synthetic card text) ----------
def test_ah_card_to_offer():
    card = {
        "href": "/bonus/groep/123456",
        "title": "AH Elstar appels",
        "text": "AH Elstar appels 1 kg 2.99 2.49 1+1 gratis",
        "img": "https://static.ah.nl/x.jpg",
    }
    o = ah.card_to_offer(card)
    assert o.name == "AH Elstar appels"
    assert o.deal_text == "1+1 gratis"
    assert o.quantity_text == "1 kg"
    assert o.price == 2.49 and o.old_price == 2.99
    assert o.url == "https://www.ah.nl/bonus/groep/123456"
