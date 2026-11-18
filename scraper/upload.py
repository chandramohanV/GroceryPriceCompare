"""Entry point for the site's "upload AH bonus page" form.

Runs in the browser through Pyodide: the page extracts the cards with
``ah_cards.js`` and hands them here as JSON, together with the offers.json it
is currently showing. Strings in, string out, so the JavaScript side stays thin.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import ah
from .pipeline import replace_store_offers


def import_ah_cards(cards_json: str, payload_json: str) -> str:
    """New offers.json (as JSON text) with AH replaced by the uploaded cards."""
    offers = ah.offers_from_cards(json.loads(cards_json))
    if not offers:
        raise ValueError("No AH bonus offers found. Is this the saved ah.nl/bonus page?")
    payload = replace_store_offers(json.loads(payload_json), "ah", ah.LABEL, offers,
                                   datetime.now(timezone.utc))
    return json.dumps(payload, ensure_ascii=False)
