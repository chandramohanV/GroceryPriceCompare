"""Refresh the live site: scrape stores and merge them into the saved offers.

Usage:  python -m scraper.publish --site https://grocerypricecompare.pages.dev [--stores lidl,aldi,dirk,jumbo]
Needs the UPLOAD_PASSWORD environment variable. Run by the weekly GitHub
Actions job (every morning at 06:00), which the site's Run button can also start.

The live offers are kept in Cloudflare KV (see functions/api/offers.js), next
to the AH offers uploaded from the site, so only the scraped stores change.
Next week's AH offers, uploaded ahead (functions/api/next-week.js), are swapped
in on the first run of their week.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Optional

from .held import switch_in
from .pipeline import replace_store_offers
from .run import STORES

API_PATH = "/api/offers"
HELD_PATH = "/api/next-week"
TIMEOUT_SECONDS = 30
# AH blocks automated requests; its offers come from the site's upload form.
DEFAULT_STORES = "lidl,aldi,dirk,jumbo"


def fetch_json(url: str) -> Optional[dict]:
    """The JSON document saved at ``url``, or None when nothing is saved there yet."""
    import httpx  # imported lazily so the pipeline and tests don't need it

    resp = httpx.get(url, timeout=TIMEOUT_SECONDS)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def _auth(password: str) -> dict:
    return {"Authorization": f"Bearer {password}"}


def post_payload(api_url: str, payload: dict, password: str) -> None:
    import httpx

    resp = httpx.post(api_url, json=payload, timeout=TIMEOUT_SECONDS, headers=_auth(password))
    resp.raise_for_status()


def delete_held(held_url: str, password: str) -> None:
    import httpx

    resp = httpx.delete(held_url, timeout=TIMEOUT_SECONDS, headers=_auth(password))
    resp.raise_for_status()


def refresh(payload: dict, stores: list[str], now: datetime) -> dict:
    """Scrape each store and swap its offers into the payload."""
    for key in stores:
        label, scrape = STORES[key]
        payload = replace_store_offers(payload, key, label, scrape(), now)
        print(f"[{key}] {payload['stores'][key]['matched']} offers matched", file=sys.stderr)
    return payload


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", required=True, help="the deployed site, e.g. https://x.pages.dev")
    ap.add_argument("--stores", default=DEFAULT_STORES)
    args = ap.parse_args(argv)
    password = os.environ.get("UPLOAD_PASSWORD")
    if not password:
        print("UPLOAD_PASSWORD is not set", file=sys.stderr)
        return 2
    site = args.site.rstrip("/")
    api_url, held_url = site + API_PATH, site + HELD_PATH
    stores = [s.strip() for s in args.stores.split(",") if s.strip()]
    now = datetime.now(timezone.utc)
    payload, is_held_used = switch_in(fetch_json(api_url) or {}, fetch_json(held_url), now)
    payload = refresh(payload, stores, now)
    post_payload(api_url, payload, password)
    # Only after the live offers are saved: if this run fails, the next one switches again.
    if is_held_used:
        delete_held(held_url, password)
        print("held next-week offers switched in (or dropped, if their week had ended)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
