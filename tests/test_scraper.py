import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from nuxt_page import devalue_encode, nuxt_page

from scraper import ah, aldi, devalue, dirk, lidl, publish, upload
from scraper.match import CATEGORIES, PRODUCTS, classify
from scraper.models import Offer
from scraper.normalize import deal_factor, enrich, multi_price, parse_quantity
from scraper.pipeline import (build_payload, compare, prepare, replace_store_offers, store_set_key,
                              verdicts_by_store_set)
from scraper.run import build_scrapers, run
from scraper.translate import PRODUCT_NAMES, translate_offer, translate_text

FIXTURE = Path(__file__).parent / "fixtures" / "lidl_sample.html"
AH_SAVED_PAGE = Path(__file__).parent / "fixtures" / "ah_saved_sample.html"
ALDI_FIXTURE = Path(__file__).parent / "fixtures" / "aldi_sample.html"
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


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


def test_enrich_multi_buy_without_shelf_price_uses_deal_price():
    o = enrich(Offer(store="ah", id="x", name="Chiquita bananen", deal_text="2 voor 3.50"),
               price_already_discounted=False)
    assert o.effective_price == 1.75


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
    # meat, fish, dairy & eggs, cereals, coffee
    ("- Half-om-half gehakt", "Gehakt"),
    ("Zwagerman Gerookte spekreepjes", "Spek"),
    ("AH Scharrelkipkluifjes", "Kippenpoten"),
    ("- Zalmfilet op huid", "Zalm"),
    ("Iglo vissticks", "Vissticks"),
    ("Milbona Gouda oud stuk", "Kaas"),
    ("AH Halfvolle melk", "Melk"),
    ("Scharreleieren 10 stuks", "Eieren"),
    ("Quaker havermout", "Havermout"),
    ("Bellarom Koffie rood", "Koffie"),
    ("Koffiebroodjes", None),           # pastry, not coffee
    ("Kaastwister", None),              # pastry, not cheese
    ("Alle Douwe Egberts ijskoffie", None),
    ("Alle Calvé pindakaas 350 gram", None),
    ("Vegetarisch gehakt", None),
    ("Appel yoghurt", "Yoghurt"),       # yoghurt with fruit is dairy, not apples
    # Aldi look-alikes
    ("3-in-1 powerspray citroen", None),            # cleaning spray
    ("Appel- of perensap", None),
    ("Olijven met kruiden of knoflook", None),
    ("Pokébowl kip, zalm of tonijn", None),         # ready meal
    ("Gehakt cordon bleus", None),
    ("Gebraden gehakt", None),                      # cold cut
    ("Aardappelschijfjes spek & ui", None),
    ("Choco met slagroom", None),
    ("Roomboter amandelstaaf", None),               # pastry
    ("Gemengd gehakt gekruid", "Gehakt"),
    # Dirk look-alikes
    ("Actimel drink aardbei", None),
    ("Bakker van der Akker Kaas-ui bollen", None),   # bread rolls
])
def test_classify(name, product):
    hit = classify(name)
    assert (hit[0] if hit else None) == product


def test_every_product_has_a_known_category():
    assert {category for category, _ in PRODUCTS.values()} == set(CATEGORIES)


# ---------- lidl parser on real page sample ----------
def test_lidl_parse_fixture():
    offers = lidl.parse_html(FIXTURE.read_text(encoding="utf-8"))
    names = {o.name for o in offers}
    assert "Mango" in names
    assert "Vierkante donut" not in names  # bakery aisle
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


@pytest.mark.parametrize("path,is_food", [
    ("Werelden van nood/Eten en dichtbij voedsel/Vlees & gevogelte/Varkensvlees", True),
    ("Werelden van nood/Eten en dichtbij voedsel/Koffie, thee & cacao", True),
    ("Werelden van nood/Eten en dichtbij voedsel/Dierbenodigdheden/Hondenvoer", False),
    ("Werelden van nood/Eten en dichtbij voedsel/Diepvriesvoeding/Diepvriespizza's & snacks",
     False),
    ("Werelden van nood/Wonen & Inrichting/Badkamer", False),
])
def test_lidl_keeps_food_aisles_only(path, is_food):
    assert lidl.is_grocery_food({"keyfacts": {"wonCategoryPrimary": path}}) is is_food


# ---------- aldi parser on real page sample ----------
def _aldi_offers() -> list[Offer]:
    return aldi.parse_pages([ALDI_FIXTURE.read_text(encoding="utf-8")])


def _aldi_page(*items: dict) -> str:
    """A minimal Aldi page embedding the given products."""
    api = [["OFFER_GET", {"res": {"algoliaDataMap": {i["objectID"]: i for i in items}}}]]
    next_data = {"props": {"pageProps": {"apiData": json.dumps(api)}}}
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script>'


def _aldi_item(object_id: str, valid_from: str, valid_to: str) -> dict:
    return {"objectID": object_id, "name": "Prei", "salesUnit": "Per stuk",
            "currentPrice": {"priceValue": 0.55},
            "promotionPrices": [{"validFromLocalDate": valid_from, "validUntilLocalDate": valid_to}]}


def test_aldi_parse_fixture():
    sprouts = next(o for o in _aldi_offers() if o.name == "Spruiten")
    assert sprouts.store == "aldi"
    assert sprouts.price == 0.99 and sprouts.old_price == 1.89
    assert sprouts.deal_text == "-47%"
    assert sprouts.quantity_text == "750 g"
    assert sprouts.image.startswith("https://")
    assert sprouts.url == "https://www.aldi.nl/product/spruiten-1219371.html"
    assert (sprouts.valid_from, sprouts.valid_to) == ("2026-11-16", "2026-11-22")


def test_aldi_multi_buy_price_moves_into_deal_text():
    skyr = next(o for o in _aldi_offers() if o.name == "High protein skyr")
    assert skyr.price is None
    assert skyr.deal_text == "2 voor 2.50"


def test_aldi_non_discount_label_is_a_note():
    item = _aldi_item("1", "2026-11-16", "2026-11-22")
    item["currentPrice"]["priceTagLabels"] = {"promoText1": "OP=OP"}
    [leek] = aldi.parse_pages([_aldi_page(item)])
    assert leek.deal_text is None
    assert leek.extras == {"note": "OP=OP"}


def test_aldi_product_without_label_has_no_deal_or_note():
    ham = next(o for o in _aldi_offers() if o.name == "Gegrilde beenham")
    assert ham.deal_text is None and ham.extras == {}


def test_aldi_skips_products_without_price():
    assert "Gyoza" not in {o.name for o in _aldi_offers()}


def test_aldi_keeps_both_weeks_and_each_product_once_per_week():
    this_week = _aldi_page(_aldi_item("1", "2026-11-16", "2026-11-22"))
    next_week = _aldi_page(_aldi_item("1", "2026-11-23", "2026-11-29"),
                           _aldi_item("2", "2026-11-23", "2026-11-29"))
    offers = aldi.parse_pages([this_week, next_week, next_week])
    assert [(o.id, o.valid_from) for o in offers] == [
        ("1", "2026-11-16"), ("1", "2026-11-23"), ("2", "2026-11-23")]


def test_aldi_page_without_offers_data_is_reported():
    with pytest.raises(aldi.AldiPageChanged):
        aldi.parse_pages(["<html>no data</html>"])


# ---------- Nuxt payload (scraper/devalue.py) ----------
def test_devalue_round_trip():
    value = {"a": [1, "x", None, {"b": 2.5}], "c": True}
    assert devalue.decode(devalue_encode(value)) == value


def test_devalue_unwraps_vue_state_and_dates():
    entries = [["ShallowReactive", 1], {"when": 2, "list": 3, "gone": -1}, ["Date", "2026-11-18"],
               ["Reactive", 4], [5], "item"]
    assert devalue.decode(entries) == {"when": "2026-11-18", "list": ["item"], "gone": None}


def test_devalue_keeps_shared_values_shared():
    shared = {"x": 1}
    entries = [{"first": 1, "second": 1}, {"x": 2}, 1]
    decoded = devalue.decode(entries)
    assert decoded["first"] is decoded["second"] and decoded["first"] == shared


def test_devalue_rejects_unknown_types():
    with pytest.raises(ValueError, match="BigInt"):
        devalue.decode([["BigInt", "1"]])


def test_devalue_page_without_payload():
    with pytest.raises(devalue.PayloadMissing):
        devalue.payload_from_html("<html></html>")


# ---------- dirk parser ----------
def _dirk_offer(offer_id=1, name="Hollandse spruiten", price=0.89, normal=1.89,
                sign="ACTIE_\n ", products=None) -> dict:
    return {"offerId": offer_id, "headerText": name + " ", "packaging": None,
            "offerPrice": price, "normalPrice": normal, "textPriceSign": sign,
            "startDate": "2026-11-18T00:00:00.000Z", "endDate": "2026-11-24T23:59:00.000Z",
            "products": products if products is not None else [None]}


def _dirk_product(product_id=4535, packaging="750 g", price=0.89, normal=1.89) -> dict:
    return {"productId": product_id, "offerPrice": price, "normalPrice": normal,
            "productInformation": {"productId": product_id, "headerText": "Spruiten",
                                   "packaging": packaging, "image": f"artikelen/{product_id}.png"}}


def _dirk_page(*sections: list, links: str = "") -> str:
    state = {"data": {"offers-currentOffers": [{"currentOffers": s} for s in sections]}}
    return nuxt_page(state, before=links)


def test_dirk_single_product_offer():
    link = '<a href="/boodschappen/groente/1%20de%20beste%20spruiten/4535">'
    page = _dirk_page([_dirk_offer(products=[_dirk_product()])], links=link)
    [sprouts] = dirk.parse_html(page)
    assert sprouts.store == "dirk" and sprouts.name == "Hollandse spruiten"
    assert (sprouts.price, sprouts.old_price) == (0.89, 1.89)
    assert sprouts.quantity_text == "750 g"
    assert sprouts.image == "https://web-fileserver.dirk.nl/artikelen/4535.png"
    assert sprouts.url == "https://www.dirk.nl/boodschappen/groente/1%20de%20beste%20spruiten/4535"
    assert (sprouts.valid_from, sprouts.valid_to) == ("2026-11-18", "2026-11-24")
    assert sprouts.extras == {}


def test_dirk_uses_product_price_that_belongs_to_its_pack():
    offer = _dirk_offer(name="Hollandse witlof", price=0.99, normal=1.15,
                        products=[_dirk_product(packaging="1 kg", price=1.98, normal=2.30)])
    [chicory] = dirk.parse_html(_dirk_page([offer]))
    assert (chicory.price, chicory.quantity_text) == (1.98, "1 kg")


def test_dirk_offer_with_several_pack_sizes_has_no_quantity():
    offer = _dirk_offer(products=[_dirk_product(1, "250 g"), _dirk_product(2, "500 g")])
    [mixed] = dirk.parse_html(_dirk_page([offer]))
    assert mixed.quantity_text is None and mixed.image is None
    assert mixed.price == 0.89  # the offer's own price
    assert mixed.url == "https://www.dirk.nl/aanbiedingen"


def test_dirk_offer_without_products_keeps_offer_price():
    [kiwis] = dirk.parse_html(_dirk_page([_dirk_offer(name="Groene kiwi's", price=3.49, normal=0)]))
    assert (kiwis.price, kiwis.old_price, kiwis.quantity_text) == (3.49, None, None)


def test_dirk_weekend_sign_is_a_note():
    [offer] = dirk.parse_html(_dirk_page([_dirk_offer(sign="VR, ZA & ZO_actie")]))
    assert offer.extras == {"note": "VR, ZA & ZO"}


def test_dirk_offer_in_two_sections_is_kept_once():
    offer = _dirk_offer()
    assert len(dirk.parse_html(_dirk_page([offer], [offer]))) == 1


def test_dirk_page_without_offers_data_is_reported():
    with pytest.raises(dirk.DirkPageChanged):
        dirk.parse_html("<html></html>")


def test_prepare_uses_aldi_shelf_price_as_discounted():
    sprouts = next(o for o in prepare(_aldi_offers()) if o.name == "Spruiten")
    assert sprouts.unit_price == pytest.approx(1.32, abs=0.01)  # 0.99 for 750 g, not 47% off again


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
    assert row["product_en"] == "Apples"


def test_compare_flags_group_without_a_second_price_as_not_compared():
    offers = [
        Offer(store="lidl", id="1", name="Jonagold appels", price=1.49, quantity_text="1500 g"),
        Offer(store="ah", id="2", name="Alle appels op schaal", deal_text="2e halve prijs"),
    ]
    row = compare(prepare(offers))[0]
    assert row["stores"] == ["ah", "lidl"]
    assert row["compared"] is False and row["saving_pct"] is None


def _three_store_apples() -> list[Offer]:
    return prepare([
        Offer(store="lidl", id="1", name="Jonagold appels", price=1.50, quantity_text="1 kg"),
        Offer(store="aldi", id="2", name="Elstar appels", price=2.00, quantity_text="1 kg"),
        Offer(store="dirk", id="3", name="Gala appels", price=3.00, quantity_text="1 kg"),
    ])


def test_verdicts_cover_every_store_combination():
    verdicts = verdicts_by_store_set(_three_store_apples())
    assert set(verdicts) == {"aldi", "dirk", "lidl", "aldi,dirk", "aldi,lidl", "dirk,lidl",
                             "aldi,dirk,lidl"}


def test_verdict_picks_best_among_chosen_stores_only():
    verdicts = verdicts_by_store_set(_three_store_apples())
    assert verdicts[store_set_key(["lidl", "dirk", "aldi"])]["Appels"]["best"]["store"] == "lidl"
    without_lidl = verdicts["aldi,dirk"]["Appels"]
    assert without_lidl["best"]["store"] == "aldi"
    assert without_lidl["saving_pct"] == 33  # €2 vs €3 per kg
    assert verdicts["dirk"]["Appels"]["compared"] is False  # one store: nothing to compare


def test_payload_includes_verdicts_by_store_set():
    payload = build_payload(_three_store_apples(), {}, NOW)
    assert payload["verdicts_by_store_set"]["aldi,dirk,lidl"]["Appels"]["unit"] == "kg"


def test_replace_store_offers_keeps_other_stores():
    lidl_offer = prepare([Offer(store="lidl", id="1", name="Mango", price=0.99,
                                quantity_text="1 Stk.")])[0]
    old_ah = prepare([Offer(store="ah", id="old", name="AH Prei", price=1.29)])[0]
    previous = {
        "stores": {"lidl": {"name": "Lidl", "ok": True}, "ah": {"name": "Albert Heijn", "ok": False}},
        "offers": [lidl_offer.to_dict(), old_ah.to_dict()],
    }
    fresh = [Offer(store="ah", id="new", name="AH Mandarijnen", price=1.29, quantity_text="1 kg"),
             Offer(store="ah", id="toy", name="Speelgoedauto", price=9.99)]
    payload = replace_store_offers(previous, "ah", "Albert Heijn", fresh, NOW)
    assert sorted(o["key"] for o in payload["offers"]) == ["ah:new", "lidl:1"]
    assert payload["stores"]["ah"] == {"name": "Albert Heijn", "ok": True, "scraped": 2,
                                       "matched": 1}
    assert payload["stores"]["lidl"]["ok"] is True
    assert payload["generated_at"] == "2026-11-17T12:00:00+00:00"


def test_upload_turns_cards_into_payload():
    cards = [{"href": "/producten/product/wi1/ah-witlof", "title": "AH Witlof",
              "text": "voor 1.49 AH Witlof 1.49 2.29 4 stuks"}]
    payload = json.loads(upload.import_ah_cards(json.dumps(cards), json.dumps({"offers": []})))
    assert [o["name"] for o in payload["offers"]] == ["AH Witlof"]
    assert payload["stores"]["ah"]["matched"] == 1


def test_upload_rejects_page_without_offers():
    with pytest.raises(ValueError, match="No AH bonus offers"):
        upload.import_ah_cards("[]", "{}")


# ---------- translate ----------
@pytest.mark.parametrize("dutch,english", [
    ("Conference peren", "Conference pears"),
    ("Bio flespompoen", "Organic butternut squash"),
    ("Zoete aardappels", "Sweet potatoes"),
    ("AH Kruimige aardappelen 3 kg", "AH Floury potatoes 3 kg"),
    ("BIO RODE UIEN", "ORGANIC RED ONIONS"),
    ("Blauwe bessen", "Blueberries"),
    ("Zak 1,5 kilo", "Bag 1.5 kilo"),
    ("met Lidl Plus", "with Lidl Plus"),
    ("1+1 gratis", "1+1 free"),
    ("2e halve prijs", "2nd half price"),
    ("2 voor 5,00", "2 for 5.00"),
    ("25% korting", "25% off"),
    ("QUALITÉ SUISSE Jonagold appels", "QUALITÉ SUISSE Jonagold apples"),
    ("Kiwi gold", "Kiwi gold"),
    ("Appelsap", "Appelsap"),  # unknown compound words stay untouched
    (None, None),
])
def test_translate_text(dutch, english):
    assert translate_text(dutch) == english


def test_every_product_has_an_english_name():
    assert set(PRODUCTS) <= set(PRODUCT_NAMES)


def test_translate_offer_keeps_only_filled_fields():
    offer = Offer(store="lidl", id="1", name="Spruiten", quantity_text="750 g",
                  member_label="met Lidl Plus", product="Spruiten")
    assert translate_offer(offer) == {
        "name": "Brussels sprouts",
        "quantity_text": "750 g",
        "member_label": "with Lidl Plus",
        "product": "Brussels sprouts",
    }


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


@pytest.mark.parametrize("text,price,old_price,deal", [
    # the deal amount is not a shelf price
    ("voor 1.49 AH Witlof 1.49 2.29 4 stuks", 1.49, 2.29, "voor 1.49"),
    ("2 voor 4.00 AH Ananas eetrijp 2.19 per stuk", 2.19, None, "2 voor 4.00"),
    ("€1 korting AH Scharrelkipkluifjes", None, None, "€1 korting"),
    ("100 gram 1.79 AH Stoofvlees 8.95 9.99 ca. 500 g", 8.95, 9.99, "100 gram 1.79"),
    ("voor 2.49 Alle Calvé pindakaas 350 gram 2.49 2.99", 2.49, 2.99, "voor 2.49"),
])
def test_ah_card_prices_ignore_deal_amount(text, price, old_price, deal):
    o = ah.card_to_offer({"href": "/bonus/groep/1", "title": "x", "text": text})
    assert (o.price, o.old_price, o.deal_text) == (price, old_price, deal)


def test_ah_card_quantity_ignores_price_per_weight_label():
    card = {"href": "/x/1", "title": "AH Stoofvlees",
            "text": "100 gram 1.79 AH Stoofvlees 8.95 9.99 ca. 500 g"}
    assert ah.card_to_offer(card).quantity_text == "500 g"


def test_ah_card_without_deal_or_price_is_a_banner():
    card = {"href": "/bonus/groep/2", "title": "Heerlijke koffie, voordelig gezet",
            "text": "Heerlijke koffie, voordelig gezet"}
    assert ah.card_to_offer(card) is None


def test_ah_card_id_drops_week_query():
    card = {"href": "/bonus/groep/832162?week=47", "title": "AH Prei", "text": "AH Prei 1.29"}
    assert ah.card_to_offer(card).id == "832162"


def test_ah_card_drops_local_image_from_saved_page():
    card = {"href": "/bonus/groep/1", "title": "AH Prei", "text": "AH Prei 1.29",
            "img": "Bonus_files/prei.jpg"}
    assert ah.card_to_offer(card).image is None


def test_ah_saved_page_import_is_offline_and_deduplicated():
    offers = ah.scrape_saved_page(AH_SAVED_PAGE)
    assert [o.name for o in offers] == ["AH Elstar appels", "AH Spruiten"]
    apples, sprouts = offers
    assert apples.deal_text == "1+1 gratis" and apples.image is None
    assert sprouts.image == "https://static.ah.nl/dam/product/spruiten.jpg"
    assert sprouts.price == 1.49 and sprouts.old_price == 1.99


def test_build_scrapers_uses_saved_ah_page_even_when_not_listed():
    scrapers = build_scrapers(["lidl"], AH_SAVED_PAGE)
    assert set(scrapers) == {"lidl", "ah"}
    assert scrapers["ah"][0] == "Albert Heijn"


# ---------- carrying over a blocked store's offers ----------
def _blocked() -> list[Offer]:
    raise ah.AHBlocked("ah.nl answered HTTP 403")


def _save_previous_ah_offer(out_dir: Path, valid_to: date) -> None:
    offer = prepare([Offer(store="ah", id="7", name="AH Spruiten", price=1.49,
                           quantity_text="500 g", valid_to=valid_to.isoformat())])[0]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "offers.json").write_text(
        json.dumps({"offers": [{"key": "ah:7", **offer.to_dict(), "en": {}}]}), encoding="utf-8")


def test_blocked_store_keeps_offers_until_its_week_ends(tmp_path):
    _save_previous_ah_offer(tmp_path, date.today() + timedelta(days=2))
    data = run({"ah": ("Albert Heijn", _blocked)}, tmp_path)
    assert data["stores"]["ah"]["ok"] is False
    assert data["stores"]["ah"]["carried_over"] == 1
    assert [o["name"] for o in data["offers"]] == ["AH Spruiten"]
    assert data["offers"][0]["en"]["name"] == "AH Brussels sprouts"


def test_blocked_store_drops_expired_offers(tmp_path):
    _save_previous_ah_offer(tmp_path, date.today() - timedelta(days=1))
    data = run({"ah": ("Albert Heijn", _blocked)}, tmp_path)
    assert data["offers"] == []
    assert "carried_over" not in data["stores"]["ah"]


def test_run_writes_next_weeks_offers_separately(tmp_path):
    next_monday = date.today() - timedelta(days=date.today().weekday()) + timedelta(weeks=1)
    upcoming = Offer(store="lidl", id="9", name="Mango", price=0.99, quantity_text="1 Stk.",
                     valid_from=next_monday.isoformat(), valid_to=(next_monday + timedelta(days=6)).isoformat())
    current = Offer(store="lidl", id="8", name="Prei", price=0.55, quantity_text="1 Stk.")
    data = run({"lidl": ("Lidl", lambda: [current, upcoming])}, tmp_path)
    next_data = json.loads((tmp_path / "offers-next.json").read_text(encoding="utf-8"))
    assert [o["key"] for o in data["offers"]] == ["lidl:8"]
    assert [o["key"] for o in next_data["offers"]] == ["lidl:9"]


# ---------- weekly refresh (scraper/publish.py) ----------
def test_refresh_replaces_lidl_and_drops_expired_ah(monkeypatch):
    this_week = prepare([Offer(store="ah", id="1", name="AH Witlof", price=1.49,
                               valid_to="2026-11-22")])[0]
    last_week = prepare([Offer(store="ah", id="2", name="AH Prei", price=1.29,
                               valid_to="2026-11-15")])[0]
    saved = {"stores": {"ah": {"name": "Albert Heijn", "ok": True}},
             "offers": [this_week.to_dict(), last_week.to_dict()]}
    fresh_lidl = [Offer(store="lidl", id="9", name="Mango", price=0.99, quantity_text="1 Stk.")]
    monkeypatch.setattr(publish, "STORES", {"lidl": ("Lidl", lambda: fresh_lidl)})
    payload, next_week = publish.refresh(saved, {}, ["lidl"], NOW)
    assert sorted(o["key"] for o in payload["offers"]) == ["ah:1", "lidl:9"]
    assert payload["stores"]["lidl"]["matched"] == 1
    assert next_week["offers"] == []


def test_publish_needs_upload_password(monkeypatch):
    monkeypatch.delenv("UPLOAD_PASSWORD", raising=False)
    assert publish.main(["--site", "https://example.invalid"]) == 2
