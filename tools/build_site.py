"""Assemble the deployable static site in one folder (default: _site/).

    python tools/build_site.py [out_dir]

Copies site/, the latest data/offers.json (and offers-next.json), and the scraper sources that the
upload form runs in the browser (into py/scraper/). Used by the GitHub Pages
workflow and before `wrangler pages deploy`.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BROWSER_SOURCES = ("*.py", "*.js")  # site/upload.js picks the modules it needs
DATA_FILES = ("offers.json", "offers-next.json")


def build(out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(ROOT / "site", out_dir)
    (out_dir / "data").mkdir()
    for name in DATA_FILES:
        if (ROOT / "data" / name).exists():  # offers-next.json only after a local run that found next week
            shutil.copy2(ROOT / "data" / name, out_dir / "data" / name)
    scraper_out = out_dir / "py" / "scraper"
    scraper_out.mkdir(parents=True)
    for pattern in BROWSER_SOURCES:
        for source in (ROOT / "scraper").glob(pattern):
            shutil.copy2(source, scraper_out / source.name)


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "_site")
