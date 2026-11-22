"""Entry point for the site's "upload AH bonus page" form.

Runs in the browser through Pyodide: the page extracts the cards with
``ah_cards.js`` and hands them here as JSON, together with the offers.json of
the chosen week (this week's or next week's). Strings in, string out, so the
JavaScript side stays thin.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Optional

from . import ah
from .models import Offer
from .pipeline import replace_store_offers

WEEK_NAMES = ("this week", "next week")  # index = weeks ahead


def _offers_for_week(cards_json: str, weeks_ahead: int, today: date) -> list[Offer]:
    """The page's offers, dated to the chosen bonus week."""
    cards = json.loads(cards_json)
    monday = ah.week_start(today, weeks_ahead)
    week = monday.isocalendar().week
    _check_page_week(ah.page_week(cards), week, weeks_ahead)
    # Previews of the week after would otherwise be shown a week early.
    offers = ah.offers_from_cards(ah.cards_of_week(cards, week), monday)
    if not offers:
        raise ValueError("No AH bonus offers found. Is this the saved ah.nl/bonus page?")
    return offers


def _check_page_week(found_week: Optional[int], chosen_week: int, weeks_ahead: int) -> None:
    """Catches next week's page uploaded as this week's (or the other way round)."""
    if found_week is None or found_week == chosen_week:
        return
    raise ValueError(
        f"This page has the offers of week {found_week}, but {WEEK_NAMES[weeks_ahead]} is "
        f"week {chosen_week}. Pick the other week, or save the page again.")


def _import(cards_json: str, payload_json: str, weeks_ahead: int) -> str:
    now = datetime.now(timezone.utc)
    offers = _offers_for_week(cards_json, weeks_ahead, now.date())
    payload = replace_store_offers(json.loads(payload_json), "ah", ah.LABEL, offers, now)
    return json.dumps(payload, ensure_ascii=False)


def import_ah_cards(cards_json: str, payload_json: str) -> str:
    """This week's offers.json (as JSON text) with AH replaced by the uploaded cards."""
    return _import(cards_json, payload_json, 0)


def import_next_week_ah_cards(cards_json: str, next_payload_json: str) -> str:
    """Next week's offers.json (as JSON text) with AH replaced; it moves into this week's on Monday."""
    return _import(cards_json, next_payload_json, 1)
