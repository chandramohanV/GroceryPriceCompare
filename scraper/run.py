"""Scrape all stores, keep the products we compare, normalise and compare.

Usage:  python -m scraper.run [--out data] [--stores lidl,aldi,dirk,jumbo,ah] [--ah-page bonus.html]
Writes data/offers.json (latest) and data/history/YYYY-MM-DD.json.
A store that fails is reported in the output but doesn't stop the others; its
earlier offers are kept until their offer week ends.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Callable, Optional

from . import ah, aldi, dirk, jumbo, lidl
from .models import Offer
from .pipeline import build_payload, offers_from_payload, prepare, still_valid

Scraper = Callable[[], list[Offer]]

STORES: dict[str, tuple[str, Scraper]] = {
    "lidl": (lidl.LABEL, lidl.scrape),
    "aldi": (aldi.LABEL, aldi.scrape),
    "dirk": (dirk.LABEL, dirk.scrape),
    "jumbo": (jumbo.LABEL, jumbo.scrape),
    "ah": (ah.LABEL, ah.scrape),
}


def scrape_store(key: str, label: str, scrape: Scraper) -> tuple[list[Offer], dict]:
    """Scrape one store; a failure is recorded in its status instead of raised."""
    try:
        raw = scrape()
    except Exception as e:  # keep going with other stores
        print(f"[{key}] FAILED: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return [], {"name": label, "ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
    kept = prepare(raw)
    print(f"[{key}] {len(raw)} offers scraped, {len(kept)} matched", file=sys.stderr)
    return kept, {"name": label, "ok": True, "scraped": len(raw), "matched": len(kept)}


def load_offers(path: Path) -> list[Offer]:
    """Offers from an earlier offers.json, or [] when there is none yet."""
    if not path.exists():
        return []
    return offers_from_payload(json.loads(path.read_text(encoding="utf-8")))


def run(scrapers: dict[str, tuple[str, Scraper]], out_dir: Path) -> dict:
    now = datetime.now(timezone.utc)
    previous = load_offers(out_dir / "offers.json")
    all_offers: list[Offer] = []
    status = {}
    for key, (label, scrape) in scrapers.items():
        offers, status[key] = scrape_store(key, label, scrape)
        if not status[key]["ok"]:
            # e.g. AH blocks the daily job: keep this week's imported AH offers
            offers = still_valid(previous, key, now.date())
            if offers:
                status[key]["carried_over"] = len(offers)
        all_offers.extend(offers)

    data = build_payload(all_offers, status, now)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "history").mkdir(exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=1)
    (out_dir / "offers.json").write_text(payload, encoding="utf-8")
    (out_dir / "history" / f"{now.date().isoformat()}.json").write_text(payload, encoding="utf-8")
    return data


def build_scrapers(stores: list[str], ah_page: Optional[Path]) -> dict[str, tuple[str, Scraper]]:
    """Scrapers for the chosen stores; a saved AH page replaces the live AH scraper."""
    scrapers = {key: STORES[key] for key in stores}
    if ah_page:
        scrapers["ah"] = (STORES["ah"][0], partial(ah.scrape_saved_page, ah_page))
    return scrapers


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data", type=Path)
    ap.add_argument("--stores", default=",".join(STORES))
    ap.add_argument("--ah-page", type=Path,
                    help="ah.nl/bonus saved from your browser (Ctrl+S), used instead of live AH")
    args = ap.parse_args(argv)
    stores = [s.strip() for s in args.stores.split(",") if s.strip()]
    data = run(build_scrapers(stores, args.ah_page), args.out)
    # Fail the job only when every store failed (so a dead site is noticed
    # but one blocked store doesn't stop the daily update).
    return 0 if any(s["ok"] for s in data["stores"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
