"""This week's and next week's offers: which week an offer belongs to, and keeping both payloads.

Each store's offer week starts on its own weekday (AH, Lidl and Aldi on Monday, Dirk and Jumbo on
Wednesday), so an offer counts as "next week" when it starts in the store's following offer week.
Lidl's mid-week deals ("vanaf donderdag") start inside the current week and stay in this week.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .models import Offer
from .pipeline import offers_from_payload, replace_store_offers, still_valid

MONDAY, WEDNESDAY = 0, 2
WEEK_STARTS_ON = {"ah": MONDAY, "lidl": MONDAY, "aldi": MONDAY, "dirk": WEDNESDAY, "jumbo": WEDNESDAY}
DAYS_PER_WEEK = 7
THIS_WEEK, NEXT_WEEK = 0, 1


def week_start(store: str, day: date) -> date:
    """The first day of the store's offer week that contains ``day``."""
    days_since_start = (day.weekday() - WEEK_STARTS_ON.get(store, MONDAY)) % DAYS_PER_WEEK
    return day - timedelta(days=days_since_start)


def weeks_ahead(offer: Offer, today: date) -> int:
    """0 for an offer running this week (or started earlier), 1 for next week, 2+ for later."""
    if not offer.valid_from:
        return THIS_WEEK
    starts = week_start(offer.store, date.fromisoformat(offer.valid_from))
    return max(THIS_WEEK, (starts - week_start(offer.store, today)).days // DAYS_PER_WEEK)


def split_by_week(offers: list[Offer], today: date) -> tuple[list[Offer], list[Offer]]:
    """(this week's offers, next week's); offers starting later than next week are left out."""
    this_week = [o for o in offers if weeks_ahead(o, today) == THIS_WEEK and not has_ended(o, today)]
    next_week = [o for o in offers if weeks_ahead(o, today) == NEXT_WEEK]
    return this_week, next_week


def has_ended(offer: Offer, today: date) -> bool:
    return bool(offer.valid_to) and offer.valid_to < today.isoformat()


def replace_store_weeks(current: dict, upcoming: dict, store: str, label: str,
                        scraped: list[Offer], now: datetime) -> tuple[dict, dict]:
    """(this week's payload, next week's) with one store's freshly scraped offers swapped in.

    When the scrape has nothing for this week (on Sunday Lidl's page already shows next week),
    the store's earlier offers that still run today stay.
    """
    today = now.date()
    this_week, next_week = split_by_week(scraped, today)
    if not this_week:
        this_week = still_valid(offers_from_payload(current), store, today)
    return (replace_store_offers(current, store, label, this_week, now),
            replace_store_offers(upcoming, store, label, next_week, now))


def roll_over(current: dict, upcoming: dict, now: datetime) -> tuple[dict, dict]:
    """Moves offers whose week has started from next week's payload into this week's.

    This is how uploaded AH offers go live; scraped stores are replaced by their fresh scrape anyway.
    """
    today = now.date()
    waiting = offers_from_payload(upcoming)
    for store in sorted({o.store for o in waiting}):
        offers = [o for o in waiting if o.store == store]
        started = [o for o in offers if weeks_ahead(o, today) == THIS_WEEK and not has_ended(o, today)]
        later = [o for o in offers if weeks_ahead(o, today) >= NEXT_WEEK]
        if len(later) == len(offers):
            continue
        label = upcoming.get("stores", {}).get(store, {}).get("name", store)
        if started:
            current = replace_store_offers(current, store, label, started, now)
        upcoming = replace_store_offers(upcoming, store, label, later, now)
    return current, upcoming
