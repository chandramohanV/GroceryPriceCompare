"""Refresh the live site: scrape stores and merge them into this week's and next week's offers.

Usage:  python -m scraper.publish --site https://grocerypricecompare.pages.dev [--stores lidl,aldi,dirk,jumbo]
Needs the UPLOAD_PASSWORD environment variable. Run by the daily GitHub Actions
job (every morning at 06:00), which the site's Run button can also start.

Both weeks' offers are kept in Cloudflare KV (see functions/api/offers.js), next
to the AH offers uploaded from the site, so only the scraped stores change.
Offers in next week's set whose week has started (AH uploaded ahead) move into
this week's set first.
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Optional

from .pipeline import offers_from_dicts, replace_store_offers
from .run import STORES
from .weeks import replace_store_weeks, roll_over

API_PATH = "/api/offers"
NEXT_WEEK_QUERY = "?week=next"
# Before next week's set existed, next week's AH upload was held here (Nov 2026). Its document is
# moved into next week's set once; drop this and functions/api/next-week.js when it answers 404.
LEGACY_HELD_PATH = "/api/next-week"
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


def delete_legacy_held(held_url: str, password: str) -> None:
    import httpx

    resp = httpx.delete(held_url, timeout=TIMEOUT_SECONDS, headers=_auth(password))
    resp.raise_for_status()


def adopt_legacy_held(upcoming: dict, held: dict, now: datetime) -> dict:
    """Next week's set with the offers of an old held document (see LEGACY_HELD_PATH).

    An upload made since then into next week's set is newer, so it wins.
    """
    if any(o["store"] == held["store"] for o in upcoming.get("offers", [])):
        return upcoming
    return replace_store_offers(upcoming, held["store"], held["label"], offers_from_dicts(held["offers"]), now)


def mark_failed(payload: dict, store: str, label: str, error: Exception) -> dict:
    """The payload with the store marked as failed this run; its earlier offers stay (until they end)."""
    if "offers" not in payload:  # nothing saved yet, so nothing to mark
        return payload
    status = {**payload["stores"].get(store, {}), "name": label, "ok": False,
              "error": f"{type(error).__name__}: {error}"[:300]}
    return {**payload, "stores": {**payload["stores"], store: status}}


def refresh(current: dict, upcoming: dict, stores: list[str], now: datetime) -> tuple[dict, dict, list[str]]:
    """(this week's payload, next week's, the stores that failed) after rolling over and scraping.

    A failing store doesn't stop the others or the roll-over (AH's new week): it keeps its offers.
    """
    current, upcoming = roll_over(current, upcoming, now)
    failed = []
    for key in stores:
        label, scrape = STORES[key]
        try:
            scraped = scrape()
        except Exception as e:  # any scraper bug or site change; reported, and the run goes on
            print(f"[{key}] FAILED: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            failed.append(key)
            current = mark_failed(current, key, label, e)
            continue
        current, upcoming = replace_store_weeks(current, upcoming, key, label, scraped, now)
        print(f"[{key}] {current['stores'][key]['matched']} offers this week, "
              f"{upcoming['stores'][key]['matched']} next week", file=sys.stderr)
    return current, upcoming, failed


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
    api_url, next_url, held_url = site + API_PATH, site + API_PATH + NEXT_WEEK_QUERY, site + LEGACY_HELD_PATH
    stores = [s.strip() for s in args.stores.split(",") if s.strip()]
    now = datetime.now(timezone.utc)

    current, upcoming = fetch_json(api_url) or {}, fetch_json(next_url) or {}
    held = fetch_json(held_url)
    if held:
        upcoming = adopt_legacy_held(upcoming, held, now)
    current, upcoming, failed = refresh(current, upcoming, stores, now)
    # This week first: if saving next week then fails, its started offers are still there to roll
    # over again on the next run.
    post_payload(api_url, current, password)
    post_payload(next_url, upcoming, password)
    if held:
        delete_legacy_held(held_url, password)
    if failed:
        # Everything else is saved; failing the job makes the broken store visible on GitHub.
        print(f"Saved, but these stores failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
