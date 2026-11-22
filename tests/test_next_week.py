"""Tests for uploading AH's next bonus week ahead and switching it in (ah, upload, held, publish)."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from scraper import ah, held, publish, upload
from scraper.models import Offer
from scraper.pipeline import prepare

MONDAY = date(2026, 11, 23)  # ISO week 48
WITLOF_CARD = {"href": "/producten/product/wi1/ah-witlof", "title": "AH Witlof",
               "text": "voor 1.49 AH Witlof 1.49 2.29 4 stuks"}
TOY_CARD = {"href": "/producten/product/t1/speelgoed", "title": "Speelgoedauto", "text": "Speelgoedauto 9.99"}


def _card_for_week(week: int) -> dict:
    return {**WITLOF_CARD, "href": f"/bonus/groep/1?week={week}"}


def _held_witlof(valid_from: date) -> dict:
    offers = [Offer(store="ah", id="wi1", name="AH Witlof", price=1.49, quantity_text="4 stuks")]
    return held.hold("ah", "Albert Heijn", offers, valid_from, ah.week_end(valid_from),
                     datetime(2026, 11, 20, tzinfo=timezone.utc))


def _payload_with_this_weeks_ah() -> dict:
    offer = prepare([Offer(store="ah", id="old", name="AH Prei", price=1.29,
                           valid_from="2026-11-16", valid_to="2026-11-22")])[0]
    return {"stores": {"ah": {"name": "Albert Heijn", "ok": True}}, "offers": [offer.to_dict()]}


def _at(day: date, hour: int = 5) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc)


# ---------- AH bonus weeks ----------
@pytest.mark.parametrize("today,weeks_ahead,monday", [
    (date(2026, 11, 23), 0, date(2026, 11, 23)),  # Monday
    (date(2026, 11, 29), 0, date(2026, 11, 23)),  # Sunday still belongs to that week
    (date(2026, 11, 26), 1, date(2026, 11, 30)),
    (date(2026, 12, 31), 1, date(2027, 1, 4)),    # across the year end
])
def test_ah_week_start(today, weeks_ahead, monday):
    assert ah.week_start(today, weeks_ahead) == monday


def test_ah_week_end_is_sunday():
    assert ah.week_end(MONDAY) == date(2026, 11, 29)


def test_ah_page_week_reads_card_links():
    cards = [{"href": "/bonus/banner"}, {"href": "/bonus/groep/832162?week=48&x=1"}]
    assert ah.page_week(cards) == 48


def test_ah_page_week_unknown_without_week_links():
    assert ah.page_week([WITLOF_CARD, {"title": "no link"}]) is None


def test_ah_card_dated_to_given_week():
    offer = ah.card_to_offer(WITLOF_CARD, MONDAY)
    assert (offer.valid_from, offer.valid_to) == ("2026-11-23", "2026-11-29")


# ---------- upload form (scraper/upload.py) ----------
def test_upload_holds_next_week_with_next_weeks_dates():
    next_monday = ah.week_start(date.today(), 1)
    doc = json.loads(upload.hold_next_week_ah_cards(json.dumps([WITLOF_CARD, TOY_CARD])))
    assert doc["store"] == "ah" and doc["label"] == "Albert Heijn"
    assert doc["valid_from"] == next_monday.isoformat()
    assert doc["valid_to"] == ah.week_end(next_monday).isoformat()
    assert (doc["scraped"], doc["matched"]) == (2, 1)
    assert [o["valid_from"] for o in doc["offers"]] == [next_monday.isoformat()] * 2


def test_upload_held_offers_are_kept_raw_for_switching():
    doc = json.loads(upload.hold_next_week_ah_cards(json.dumps([WITLOF_CARD])))
    assert doc["offers"][0]["product"] is None  # prepared when switched in, with the code of that day


def test_upload_rejects_next_weeks_page_as_this_week():
    next_week = ah.week_start(date.today(), 1).isocalendar().week
    with pytest.raises(ValueError, match=f"offers of week {next_week}, but this week is"):
        upload.import_ah_cards(json.dumps([_card_for_week(next_week)]), "{}")


def test_upload_rejects_this_weeks_page_as_next_week():
    this_week = ah.week_start(date.today()).isocalendar().week
    with pytest.raises(ValueError, match="but next week is"):
        upload.hold_next_week_ah_cards(json.dumps([_card_for_week(this_week)]))


def test_upload_accepts_matching_week():
    next_week = ah.week_start(date.today(), 1).isocalendar().week
    doc = json.loads(upload.hold_next_week_ah_cards(json.dumps([_card_for_week(next_week)])))
    assert doc["matched"] == 1


def test_upload_next_week_rejects_page_without_offers():
    with pytest.raises(ValueError, match="No AH bonus offers"):
        upload.hold_next_week_ah_cards("[]")


# ---------- switching held offers in (scraper/held.py) ----------
def test_switch_in_without_held_offers_changes_nothing():
    payload = _payload_with_this_weeks_ah()
    assert held.switch_in(payload, None, _at(MONDAY)) == (payload, False)


def test_switch_in_waits_for_the_week_to_start():
    payload = _payload_with_this_weeks_ah()
    assert held.switch_in(payload, _held_witlof(MONDAY), _at(MONDAY - timedelta(days=1))) == (payload, False)


@pytest.mark.parametrize("day", [MONDAY, MONDAY + timedelta(days=6)])
def test_switch_in_replaces_ah_during_its_week(day):
    payload, is_used = held.switch_in(_payload_with_this_weeks_ah(), _held_witlof(MONDAY), _at(day))
    assert is_used is True
    assert [o["key"] for o in payload["offers"]] == ["ah:wi1"]
    assert payload["stores"]["ah"]["matched"] == 1


def test_switch_in_drops_a_week_that_already_ended():
    payload = _payload_with_this_weeks_ah()
    after = MONDAY + timedelta(days=7)
    assert held.switch_in(payload, _held_witlof(MONDAY), _at(after)) == (payload, True)


# ---------- daily refresh (scraper/publish.py) ----------
class FakeSite:
    """Stands in for the site's /api/offers and /api/next-week."""

    def __init__(self, saved: dict, held_doc):
        self.docs = {publish.API_PATH: saved, publish.HELD_PATH: held_doc}
        self.posted, self.deleted = None, []

    def install(self, monkeypatch, now: datetime) -> None:
        monkeypatch.setenv("UPLOAD_PASSWORD", "secret")
        monkeypatch.setattr(publish, "STORES", {"lidl": ("Lidl", lambda: [])})
        monkeypatch.setattr(publish, "fetch_json", lambda url: self.docs[url.removeprefix(SITE)])
        monkeypatch.setattr(publish, "post_payload", lambda url, payload, pw: setattr(self, "posted", payload))
        monkeypatch.setattr(publish, "delete_held", lambda url, pw: self.deleted.append(url))
        monkeypatch.setattr(publish, "datetime", _FixedClock(now))


class _FixedClock:
    def __init__(self, now: datetime):
        self._now = now

    def now(self, tz=None):
        return self._now


SITE = "https://example.invalid"


def test_publish_switches_in_held_offers_and_clears_them(monkeypatch):
    site = FakeSite(_payload_with_this_weeks_ah(), _held_witlof(MONDAY))
    site.install(monkeypatch, _at(MONDAY))
    assert publish.main(["--site", SITE, "--stores", "lidl"]) == 0
    assert [o["key"] for o in site.posted["offers"]] == ["ah:wi1"]
    assert site.deleted == [SITE + publish.HELD_PATH]


def test_publish_keeps_held_offers_before_their_week(monkeypatch):
    site = FakeSite(_payload_with_this_weeks_ah(), _held_witlof(MONDAY))
    site.install(monkeypatch, _at(MONDAY - timedelta(days=2)))
    assert publish.main(["--site", SITE, "--stores", "lidl"]) == 0
    assert [o["key"] for o in site.posted["offers"]] == ["ah:old"]
    assert site.deleted == []


def test_publish_works_with_nothing_saved_yet(monkeypatch):
    site = FakeSite(None, None)
    site.install(monkeypatch, _at(MONDAY))
    assert publish.main(["--site", SITE, "--stores", "lidl"]) == 0
    assert site.posted["offers"] == [] and site.deleted == []
