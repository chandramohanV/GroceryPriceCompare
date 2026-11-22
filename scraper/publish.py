"""Refresh the live site: scrape stores and merge them into the saved offers.

Usage:  python -m scraper.publish --site https://grocerypricecompare.pages.dev [--stores lidl,aldi,dirk,jumbo]
Needs the UPLOAD_PASSWORD environment variable. Run by the weekly GitHub
Actions job, which the site's Run button can also start.

The live offers are kept in Cloudflare KV (see functions/api/offers.js), next
to the AH offers uploaded from the site, so only the scraped stores change.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from .pipeline import replace_store_offers
from .run import STORES

API_PATH = "/api/offers"
TIMEOUT_SECONDS = 30
# AH blocks automated requests; its offers come from the site's upload form.
DEFAULT_STORES = "lidl,aldi,dirk,jumbo"


def fetch_payload(api_url: str) -> dict:
    """The offers currently saved on the site, or {} when nothing is saved yet."""
    import httpx  # imported lazily so the pipeline and tests don't need it

    resp = httpx.get(api_url, timeout=TIMEOUT_SECONDS)
    if resp.status_code == 404:
        return {}
    resp.raise_for_status()
    return resp.json()


def post_payload(api_url: str, payload: dict, password: str) -> None:
    import httpx

    resp = httpx.post(api_url, json=payload, timeout=TIMEOUT_SECONDS,
                      headers={"Authorization": f"Bearer {password}"})
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
    api_url = args.site.rstrip("/") + API_PATH
    stores = [s.strip() for s in args.stores.split(",") if s.strip()]
    payload = refresh(fetch_payload(api_url), stores, datetime.now(timezone.utc))
    post_payload(api_url, payload, password)
    return 0


if __name__ == "__main__":
    sys.exit(main())
