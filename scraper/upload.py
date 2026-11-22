"""Entry point for the site's "upload AH bonus page" form.

Runs in the browser through Pyodide: the page extracts the cards with
``ah_cards.js`` and hands them here as JSON, together with the offers.json it
is currently showing. Strings in, string out, so the JavaScript side stays thin.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Optional

from . import ah
from .held import hold
from .models import Offer
from .pipeline import replace_store_offers

WEEK_NAMES = ("this week", "next week")  # index = weeks ahead


def _offers_for_week(cards_json: str, weeks_ahead: int, today: date) -> tuple[list[Offer], date]:
    """The page's offers dated to the chosen bonus week, and that week's Monday."""
    cards = json.loads(cards_json)
    monday = ah.week_start(today, weeks_ahead)
    _check_page_week(ah.page_week(cards), monday, weeks_ahead)
    offers = ah.offers_from_cards(cards, monday)
    if not offers:
        raise ValueError("No AH bonus offers found. Is this the saved ah.nl/bonus page?")
    return offers, monday


def _check_page_week(found_week: Optional[int], monday: date, weeks_ahead: int) -> None:
    """Catches next week's page uploaded as this week's (or the other way round)."""
    chosen_week = monday.isocalendar().week
    if found_week is None or found_week == chosen_week:
        return
    raise ValueError(
        f"This page has the offers of week {found_week}, but {WEEK_NAMES[weeks_ahead]} is "
        f"week {chosen_week}. Pick the other week, or save the page again.")


def import_ah_cards(cards_json: str, payload_json: str) -> str:
    """New offers.json (as JSON text) with AH replaced by this week's uploaded cards."""
    now = datetime.now(timezone.utc)
    offers, _ = _offers_for_week(cards_json, 0, now.date())
    payload = replace_store_offers(json.loads(payload_json), "ah", ah.LABEL, offers, now)
    return json.dumps(payload, ensure_ascii=False)


def hold_next_week_ah_cards(cards_json: str) -> str:
    """Next week's uploaded cards as a held document (JSON text), shown once that week starts."""
    now = datetime.now(timezone.utc)
    offers, monday = _offers_for_week(cards_json, 1, now.date())
    held = hold("ah", ah.LABEL, offers, monday, ah.week_end(monday), now)
    return json.dumps(held, ensure_ascii=False)
