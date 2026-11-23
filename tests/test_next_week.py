"""Tests for next week's offers: AH bonus weeks, the week split (weeks.py), the upload and the daily refresh."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from scraper import ah, publish, upload, weeks
from scraper.models import Offer
from scraper.pipeline import build_payload, prepare

MONDAY = date(2026, 11, 23)  # ISO week 48
SUNDAY_BEFORE = MONDAY - timedelta(days=1)
WITLOF_CARD = {"href": "/producten/product/wi1/ah-witlof", "title": "AH Witlof",
               "text": "voor 1.49 AH Witlof 1.49 2.29 4 stuks"}
TOY_CARD = {"href": "/producten/product/t1/speelgoed", "title": "Speelgoedauto", "text": "Speelgoedauto 9.99"}
SITE = "https://example.invalid"


def _card_for_week(week: int) -> dict:
    return {**WITLOF_CARD, "href": f"/bonus/groep/1?week={week}"}


def _offer(store: str, oid: str, valid_from: str, valid_to: str, name: str = "Prei") -> Offer:
    return Offer(store=store, id=oid, name=name, price=1.29, quantity_text="1 stuk",
                 valid_from=valid_from, valid_to=valid_to)


def _payload(*offers: Offer, now: datetime = None) -> dict:
    prepared = prepare(list(offers))
    status = {o.store: {"name": o.store.title(), "ok": True} for o in prepared}
    return build_payload(prepared, status, now or _at(SUNDAY_BEFORE))


def _keys(payload: dict) -> list[str]:
    return sorted(o["key"] for o in payload["offers"])


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


def test_ah_page_week_is_the_week_most_links_name():
    # A real next-week page linked 4 previews of the week after before its 229 offers.
    cards = [_card_for_week(49)] * 2 + [_card_for_week(48)] * 5
    assert ah.page_week(cards) == 48


def test_ah_cards_of_week_drops_other_weeks_and_keeps_unknown():
    cards = [_card_for_week(48), _card_for_week(49), WITLOF_CARD]
    assert ah.cards_of_week(cards, 48) == [_card_for_week(48), WITLOF_CARD]


def test_ah_page_week_unknown_without_week_links():
    assert ah.page_week([WITLOF_CARD, {"title": "no link"}]) is None


def test_ah_card_dated_to_given_week():
    offer = ah.card_to_offer(WITLOF_CARD, MONDAY)
    assert (offer.valid_from, offer.valid_to) == ("2026-11-23", "2026-11-29")


# ---------- which week an offer belongs to (scraper/weeks.py) ----------
@pytest.mark.parametrize("store,day,start", [
    ("lidl", date(2026, 11, 22), date(2026, 11, 16)),   # Sunday ends a Monday week
    ("lidl", date(2026, 11, 23), date(2026, 11, 23)),
    ("jumbo", date(2026, 11, 24), date(2026, 11, 18)),  # Tuesday ends a Wednesday week
    ("jumbo", date(2026, 11, 25), date(2026, 11, 25)),
    ("dirk", date(2026, 11, 22), date(2026, 11, 18)),
])
def test_week_start_follows_the_store(store, day, start):
    assert weeks.week_start(store, day) == start


@pytest.mark.parametrize("offer,expected", [
    (_offer("lidl", "1", "2026-11-23", "2026-11-29"), 0),
    (_offer("lidl", "2", "2026-11-26", "2026-11-29"), 0),  # Lidl's Thursday deal stays in this week
    (_offer("lidl", "3", "2026-11-30", "2026-12-06"), 1),
    (_offer("jumbo", "4", "2026-11-25", "2026-12-01"), 1),  # Jumbo's next week starts on Wednesday
    (_offer("aldi", "5", "2026-12-07", "2026-12-13"), 2),
    (_offer("dirk", "6", "2026-11-01", "2026-12-31"), 0),   # started weeks ago and still running
    (_offer("ah", "7", None, None), 0),
])
def test_weeks_ahead(offer, expected):
    assert weeks.weeks_ahead(offer, MONDAY) == expected


def test_split_by_week_leaves_out_ended_and_later_offers():
    ended = _offer("jumbo", "1", "2026-11-11", "2026-11-17")
    now = _offer("jumbo", "2", "2026-11-18", "2026-11-24")
    upcoming = _offer("jumbo", "3", "2026-11-25", "2026-12-01")
    later = _offer("jumbo", "4", "2026-12-02", "2026-12-08")
    assert weeks.split_by_week([ended, now, upcoming, later], MONDAY) == ([now], [upcoming])


def test_replace_store_weeks_splits_a_scrape_into_both_payloads():
    scraped = [_offer("jumbo", "now", "2026-11-18", "2026-11-24", "Rode uien"),
               _offer("jumbo", "next", "2026-11-25", "2026-12-01", "Prei")]
    current, upcoming = weeks.replace_store_weeks({}, {}, "jumbo", "Jumbo", scraped, _at(MONDAY))
    assert (_keys(current), _keys(upcoming)) == (["jumbo:now"], ["jumbo:next"])


def test_replace_store_weeks_keeps_this_weeks_offers_when_the_page_moved_on():
    # On Sunday Lidl's page already shows next week; this week's offers still run today.
    running = _offer("lidl", "old", "2026-11-16", "2026-11-22")
    scraped = [_offer("lidl", "new", "2026-11-23", "2026-11-29")]
    current, upcoming = weeks.replace_store_weeks(_payload(running), {}, "lidl", "Lidl", scraped,
                                                  _at(SUNDAY_BEFORE))
    assert (_keys(current), _keys(upcoming)) == (["lidl:old"], ["lidl:new"])


def test_roll_over_moves_started_offers_into_this_week():
    this_weeks_ah = _offer("ah", "old", "2026-11-16", "2026-11-22")
    lidl_now = _offer("lidl", "1", "2026-11-23", "2026-11-29")
    next_weeks_ah = _offer("ah", "new", "2026-11-23", "2026-11-29")
    current, upcoming = weeks.roll_over(_payload(this_weeks_ah, lidl_now), _payload(next_weeks_ah), _at(MONDAY))
    assert _keys(current) == ["ah:new", "lidl:1"]
    assert _keys(upcoming) == []


def test_roll_over_waits_until_the_week_starts():
    current, upcoming = _payload(_offer("ah", "old", "2026-11-16", "2026-11-22")), \
        _payload(_offer("ah", "new", "2026-11-23", "2026-11-29"))
    assert weeks.roll_over(current, upcoming, _at(SUNDAY_BEFORE)) == (current, upcoming)


def test_roll_over_drops_a_next_week_that_already_ended():
    current = _payload(_offer("ah", "old", "2026-11-30", "2026-12-06"))
    upcoming = _payload(_offer("ah", "stale", "2026-11-23", "2026-11-29"))
    after, rest = weeks.roll_over(current, upcoming, _at(date(2026, 11, 30)))
    assert (_keys(after), _keys(rest)) == (["ah:old"], [])


# ---------- upload form (scraper/upload.py) ----------
def test_upload_next_week_goes_into_next_weeks_payload():
    next_monday = ah.week_start(date.today(), 1)
    lidl = _offer("lidl", "9", next_monday.isoformat(), ah.week_end(next_monday).isoformat())
    payload = json.loads(upload.import_next_week_ah_cards(
        json.dumps([WITLOF_CARD, TOY_CARD]), json.dumps(_payload(lidl))))
    ah_offers = [o for o in payload["offers"] if o["store"] == "ah"]
    assert [o["name"] for o in ah_offers] == ["AH Witlof"]
    assert ah_offers[0]["valid_from"] == next_monday.isoformat()
    assert "lidl:9" in _keys(payload)
    assert (payload["stores"]["ah"]["scraped"], payload["stores"]["ah"]["matched"]) == (2, 1)


def test_upload_leaves_out_previews_of_the_week_after():
    next_week = ah.week_start(date.today(), 1).isocalendar().week
    preview = {**TOY_CARD, "title": "AH Prei", "text": "AH Prei 1.29",
               "href": f"/bonus/groep/2?week={next_week + 1}"}
    cards = [preview, _card_for_week(next_week), _card_for_week(next_week)]
    payload = json.loads(upload.import_next_week_ah_cards(json.dumps(cards), "{}"))
    assert [o["name"] for o in payload["offers"]] == ["AH Witlof"]


def test_upload_rejects_next_weeks_page_as_this_week():
    next_week = ah.week_start(date.today(), 1).isocalendar().week
    with pytest.raises(ValueError, match=f"offers of week {next_week}, but this week is"):
        upload.import_ah_cards(json.dumps([_card_for_week(next_week)]), "{}")


def test_upload_rejects_this_weeks_page_as_next_week():
    this_week = ah.week_start(date.today()).isocalendar().week
    with pytest.raises(ValueError, match="but next week is"):
        upload.import_next_week_ah_cards(json.dumps([_card_for_week(this_week)]), "{}")


def test_upload_next_week_rejects_page_without_offers():
    with pytest.raises(ValueError, match="No AH bonus offers"):
        upload.import_next_week_ah_cards("[]", "{}")


# ---------- daily refresh (scraper/publish.py) ----------
class _FixedClock:
    def __init__(self, now: datetime):
        self._now = now

    def now(self, tz=None):
        return self._now


class FakeSite:
    """Stands in for the site's /api/offers (both weeks) and the legacy /api/next-week."""

    def __init__(self, current=None, upcoming=None, legacy_held=None):
        self.docs = {publish.API_PATH: current, publish.API_PATH + publish.NEXT_WEEK_QUERY: upcoming,
                     publish.LEGACY_HELD_PATH: legacy_held}
        self.posted, self.deleted = {}, []

    def install(self, monkeypatch, now: datetime, lidl_scrape=()) -> None:
        monkeypatch.setenv("UPLOAD_PASSWORD", "secret")
        monkeypatch.setattr(publish, "STORES", {"lidl": ("Lidl", lambda: list(lidl_scrape)),
                                                "aldi": ("Aldi", _broken_scrape)})
        monkeypatch.setattr(publish, "fetch_json", lambda url: self.docs[url.removeprefix(SITE)])
        monkeypatch.setattr(publish, "post_payload",
                            lambda url, payload, pw: self.posted.__setitem__(url.removeprefix(SITE), payload))
        monkeypatch.setattr(publish, "delete_legacy_held", lambda url, pw: self.deleted.append(url))
        monkeypatch.setattr(publish, "datetime", _FixedClock(now))

    def keys(self, week_path: str) -> list[str]:
        return _keys(self.posted[week_path])


def _broken_scrape():
    raise RuntimeError("Aldi offers data has an unexpected shape")


NEXT_PATH = publish.API_PATH + publish.NEXT_WEEK_QUERY


def _run(monkeypatch, site: FakeSite, now: datetime, lidl_scrape=(), stores: str = "lidl") -> int:
    site.install(monkeypatch, now, lidl_scrape)
    return publish.main(["--site", SITE, "--stores", stores])


def test_publish_saves_both_weeks_from_one_scrape(monkeypatch):
    site = FakeSite()
    scrape = [_offer("lidl", "now", "2026-11-16", "2026-11-22", "Rode uien"),
              _offer("lidl", "next", "2026-11-23", "2026-11-29")]
    assert _run(monkeypatch, site, _at(date(2026, 11, 20)), scrape) == 0
    assert site.keys(publish.API_PATH) == ["lidl:now"]
    assert site.keys(NEXT_PATH) == ["lidl:next"]


def test_publish_rolls_next_weeks_ah_into_this_week_on_monday(monkeypatch):
    site = FakeSite(current=_payload(_offer("ah", "old", "2026-11-16", "2026-11-22")),
                    upcoming=_payload(_offer("ah", "new", "2026-11-23", "2026-11-29")))
    assert _run(monkeypatch, site, _at(MONDAY)) == 0
    assert site.keys(publish.API_PATH) == ["ah:new"]
    assert site.keys(NEXT_PATH) == []


def test_publish_moves_a_legacy_held_upload_into_next_week_once(monkeypatch):
    held_offer = _offer("ah", "wi1", "2026-11-23", "2026-11-29", "AH Witlof")
    held = {"store": "ah", "label": "Albert Heijn", "valid_from": "2026-11-23", "valid_to": "2026-11-29",
            "offers": [held_offer.to_dict()]}
    site = FakeSite(legacy_held=held)
    assert _run(monkeypatch, site, _at(SUNDAY_BEFORE)) == 0
    assert site.keys(NEXT_PATH) == ["ah:wi1"]
    assert site.deleted == [SITE + publish.LEGACY_HELD_PATH]


def test_publish_prefers_a_newer_next_week_upload_over_the_legacy_held_one(monkeypatch):
    old = _offer("ah", "old", "2026-11-23", "2026-11-29", "AH Witlof")
    held = {"store": "ah", "label": "Albert Heijn", "offers": [old.to_dict()]}
    site = FakeSite(upcoming=_payload(_offer("ah", "newer", "2026-11-23", "2026-11-29")), legacy_held=held)
    assert _run(monkeypatch, site, _at(SUNDAY_BEFORE)) == 0
    assert site.keys(NEXT_PATH) == ["ah:newer"]
    assert site.deleted == [SITE + publish.LEGACY_HELD_PATH]


def test_publish_without_legacy_held_upload_deletes_nothing(monkeypatch):
    site = FakeSite()
    assert _run(monkeypatch, site, _at(MONDAY)) == 0
    assert site.deleted == []


def test_publish_still_rolls_ah_over_and_saves_when_a_store_fails(monkeypatch):
    # Monday 23 Nov 2026: Aldi broke every run, so AH's new week was never saved.
    aldi_now = _offer("aldi", "a1", "2026-11-23", "2026-11-29", "Spruiten")
    site = FakeSite(current=_payload(_offer("ah", "old", "2026-11-16", "2026-11-22"), aldi_now),
                    upcoming=_payload(_offer("ah", "new", "2026-11-23", "2026-11-29")))
    scrape = [_offer("lidl", "1", "2026-11-23", "2026-11-29", "Rode uien")]
    assert _run(monkeypatch, site, _at(MONDAY), scrape, stores="lidl,aldi") == 1
    assert site.keys(publish.API_PATH) == ["ah:new", "aldi:a1", "lidl:1"]
    assert site.keys(NEXT_PATH) == []
    aldi_status = site.posted[publish.API_PATH]["stores"]["aldi"]
    assert aldi_status["ok"] is False and "unexpected shape" in aldi_status["error"]
