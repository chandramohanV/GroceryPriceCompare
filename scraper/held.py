"""Offers uploaded before their week starts (AH's next bonus week), held until it does.

The held document lives next to the live offers (functions/api/next-week.js); the
daily refresh (publish.py) swaps it in on the first morning of its week.
"""
from __future__ import annotations

import copy
from datetime import date, datetime
from typing import Optional

from .models import Offer
from .pipeline import offers_from_dicts, prepare, replace_store_offers


def hold(store: str, label: str, offers: list[Offer], valid_from: date, valid_to: date,
         now: datetime) -> dict:
    """The document saved until ``valid_from``; offers are kept raw and prepared on switching."""
    matched = len(prepare(copy.deepcopy(offers)))  # prepare() fills in fields, so count on a copy
    return {
        "store": store,
        "label": label,
        "valid_from": valid_from.isoformat(),
        "valid_to": valid_to.isoformat(),
        "saved_at": now.isoformat(timespec="seconds"),
        "scraped": len(offers),
        "matched": matched,
        "offers": [o.to_dict() for o in offers],
    }


def is_due(held: dict, today: date) -> bool:
    return held["valid_from"] <= today.isoformat() <= held["valid_to"]


def is_expired(held: dict, today: date) -> bool:
    return held["valid_to"] < today.isoformat()


def switch_in(payload: dict, held: Optional[dict], now: datetime) -> tuple[dict, bool]:
    """(payload with the held offers swapped in once their week has started, is the held copy used up).

    A held week that already ended (the daily run failed all week) is used up without showing it.
    """
    today = now.date()
    if not held:
        return payload, False
    if is_expired(held, today):
        return payload, True
    if not is_due(held, today):
        return payload, False
    offers = offers_from_dicts(held["offers"])
    return replace_store_offers(payload, held["store"], held["label"], offers, now), True
