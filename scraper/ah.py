"""Albert Heijn bonus scraper (EXPERIMENTAL).

ah.nl/bonus is rendered with JavaScript, so we load the public page in a
regular headless Chromium (Playwright), scroll to load all cards, and read
each promotion card's text. No login, no private APIs, no bot-protection
workarounds: if AH refuses the request (e.g. "Access Denied" for datacenter
IPs) we stop and report the error, and the site shows Lidl data only.

If AH blocks GitHub's servers, run the scraper from your own computer instead
(see README: "Running locally").

Note: AH changes its HTML from time to time. Card detection below is
deliberately generic (it looks for links to product / bonus-group pages that
contain an image and a price), but it may need adjusting.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

from .models import Offer

BONUS_URL = "https://www.ah.nl/bonus"
BASE = "https://www.ah.nl"

DEAL_RE = re.compile(
    r"(\d+\s*\+\s*\d+\s*gratis|2e\s*halve\s*prijs|2e\s*gratis|\d+\s*%\s*korting|"
    r"\d+\s*voor\s*€?\s*\d+[.,]\d{2}|\d+\s*voor\s*€?\s*\d+|voor\s*€?\s*\d+[.,]\d{2})",
    re.I,
)
PRICE_RE = re.compile(r"(?<![\d.,])(\d{1,3})[.,](\d{2})(?![\d])")
QTY_RE = re.compile(
    r"(\d+\s*[x×]\s*\d+\s*(?:g|gram|ml)|\d+(?:[.,]\d+)?\s*(?:kg|kilo|gram|g|ml|l|liter|stuks?)\b|"
    r"per\s+(?:stuk|kilo|kg|bos|500\s*g))",
    re.I,
)

# Runs in the page: collect candidate promotion cards.
_EXTRACT_JS = r"""
() => {
  const out = [];
  const seen = new Set();
  const anchors = Array.from(document.querySelectorAll(
    'a[href*="/bonus/groep/"], a[href*="/producten/product/"], [data-testhook*="promotion-card"] a, [class*="promotion-card"] a'
  ));
  for (const a of anchors) {
    // climb to the card container that holds an image and some text
    let card = a;
    for (let i = 0; i < 4 && card.parentElement; i++) {
      if (card.querySelector('img') && card.innerText.trim().length > 5) break;
      card = card.parentElement;
    }
    const href = a.getAttribute('href');
    if (!href || seen.has(href)) continue;
    seen.add(href);
    const img = card.querySelector('img');
    const titleEl = card.querySelector('[data-testhook*="title"], [class*="title"], h3, h4, strong');
    out.push({
      href,
      title: (titleEl && titleEl.innerText) || a.getAttribute('aria-label') || a.title || '',
      text: card.innerText,
      img: img ? (img.currentSrc || img.src || img.getAttribute('data-src')) : null,
      alt: img ? img.alt : null,
    });
  }
  return out;
}
"""


def _parse_prices(text: str) -> tuple[Optional[float], Optional[float]]:
    """Return (offer_price, old_price) from card text. AH shows old price first."""
    vals = [float(f"{a}.{b}") for a, b in PRICE_RE.findall(text)]
    if not vals:
        return None, None
    if len(vals) == 1:
        return vals[0], None
    return min(vals[:2]), max(vals[:2])


def card_to_offer(card: dict) -> Optional[Offer]:
    text = " ".join((card.get("text") or "").split())
    title = " ".join((card.get("title") or card.get("alt") or "").split())
    if not title:
        title = text.split(" €")[0][:80]
    if not title:
        return None
    deal = DEAL_RE.search(text)
    qty = QTY_RE.search(text)
    price, old = _parse_prices(text)
    href = card.get("href") or ""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return Offer(
        store="ah",
        id=href.rstrip("/").split("/")[-1] or title,
        name=title,
        image=card.get("img"),
        url=BASE + href if href.startswith("/") else href,
        price=price,
        old_price=old,
        deal_text=deal.group(1) if deal else None,
        quantity_text=qty.group(1) if qty else None,
        # AH bonus weeks run Monday to Sunday
        valid_from=monday.isoformat(),
        valid_to=(monday + timedelta(days=6)).isoformat(),
    )


class AHBlocked(RuntimeError):
    pass


def scrape(timeout_ms: int = 45000) -> list[Offer]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(locale="nl-NL")
            resp = page.goto(BONUS_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            if resp is None or resp.status >= 400 or "Access Denied" in page.title():
                raise AHBlocked(f"ah.nl answered HTTP {resp.status if resp else '?'}")
            # Accept-cookies banner, if present (best effort)
            for label in ("Accepteren", "Alles accepteren", "Akkoord"):
                btn = page.get_by_role("button", name=label)
                if btn.count():
                    btn.first.click()
                    break
            # Scroll to trigger lazy loading
            last = 0
            for _ in range(30):
                page.mouse.wheel(0, 4000)
                page.wait_for_timeout(700)
                h = page.evaluate("document.body.scrollHeight")
                if h == last:
                    break
                last = h
            cards = page.evaluate(_EXTRACT_JS)
        finally:
            browser.close()

    offers, seen = [], set()
    for c in cards:
        o = card_to_offer(c)
        if o and o.id not in seen:
            seen.add(o.id)
            offers.append(o)
    return offers
