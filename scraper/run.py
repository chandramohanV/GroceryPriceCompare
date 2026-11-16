"""Scrape all stores, keep fruit & veg, normalise and compare.

Usage:  python -m scraper.run [--out data] [--stores lidl,ah]
Writes data/offers.json (latest) and data/history/YYYY-MM-DD.json.
A store that fails is reported in the output but doesn't stop the others.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import ah, lidl
from .match import classify, variety
from .models import Offer
from .normalize import enrich

STORES: dict[str, tuple[str, Callable[[], list[Offer]]]] = {
    "lidl": ("Lidl", lidl.scrape),
    "ah": ("Albert Heijn", ah.scrape),
}


def prepare(offers: list[Offer]) -> list[Offer]:
    kept = []
    for o in offers:
        hit = classify(o.name)
        if not hit:
            continue
        o.product, o.category = hit
        v = variety(o.name, o.product)
        if v:
            o.extras["variety"] = v
        enrich(o, price_already_discounted=(o.store == "lidl" or o.old_price is not None))
        kept.append(o)
    return kept


def compare(offers: list[Offer]) -> list[dict]:
    """Group offers per canonical product and pick the cheapest per unit."""
    groups: dict[str, list[Offer]] = {}
    for o in offers:
        groups.setdefault(o.product, []).append(o)

    result = []
    for product, items in groups.items():
        # compare on the most common unit within the group (kg beats stuk on ties)
        units = [o.qty_unit for o in items if o.unit_price is not None]
        unit = max(set(units), key=lambda u: (units.count(u), u == "kg")) if units else None
        comparable = [o for o in items if o.qty_unit == unit and o.unit_price is not None]
        comparable.sort(key=lambda o: o.unit_price)
        best = comparable[0] if comparable else None
        stores = sorted({o.store for o in items})
        entry = {
            "product": product,
            "category": items[0].category,
            "unit": unit,
            "stores": stores,
            "offer_ids": [f"{o.store}:{o.id}" for o in sorted(
                items, key=lambda o: (o.unit_price is None, o.unit_price or 0))],
            "best": None,
            "saving_pct": None,
        }
        if best:
            entry["best"] = {"store": best.store, "id": best.id, "unit_price": best.unit_price}
            others = [o for o in comparable if o.store != best.store]
            if others:
                nxt = others[0].unit_price
                entry["saving_pct"] = round((nxt - best.unit_price) / nxt * 100) if nxt else None
        result.append(entry)

    # products sold by several stores first, then alphabetical
    result.sort(key=lambda e: (-len(e["stores"]), e["category"], e["product"]))
    return result


def run(stores: list[str], out_dir: Path) -> dict:
    all_offers: list[Offer] = []
    status = {}
    for key in stores:
        label, fn = STORES[key]
        try:
            raw = fn()
            kept = prepare(raw)
            all_offers.extend(kept)
            status[key] = {"name": label, "ok": True, "scraped": len(raw), "produce": len(kept)}
            print(f"[{key}] {len(raw)} offers scraped, {len(kept)} fruit & veg", file=sys.stderr)
        except Exception as e:  # keep going with other stores
            status[key] = {"name": label, "ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
            print(f"[{key}] FAILED: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    now = datetime.now(timezone.utc)
    data = {
        "generated_at": now.isoformat(timespec="seconds"),
        "stores": status,
        "offers": [{"key": f"{o.store}:{o.id}", **o.to_dict()} for o in all_offers],
        "comparisons": compare(all_offers),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "history").mkdir(exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=1)
    (out_dir / "offers.json").write_text(payload, encoding="utf-8")
    (out_dir / "history" / f"{now.date().isoformat()}.json").write_text(payload, encoding="utf-8")
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data", type=Path)
    ap.add_argument("--stores", default=",".join(STORES))
    args = ap.parse_args(argv)
    stores = [s.strip() for s in args.stores.split(",") if s.strip()]
    data = run(stores, args.out)
    # Fail the job only when every store failed (so a dead site is noticed
    # but one blocked store doesn't stop the daily update).
    return 0 if any(s["ok"] for s in data["stores"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
