"""Albert Heijn bonus scraper (EXPERIMENTAL).

ah.nl/bonus is rendered with JavaScript, so we load the public page in a
regular headless Chromium (Playwright), scroll to load all cards, and read
each promotion card's text. No login, no private APIs, no bot-protection
workarounds: if AH refuses the request (e.g. "Access Denied" for datacenter
IPs) we stop and report the error, and the site shows Lidl data only.

AH usually blocks automated browsers. The supported alternative is to save
ah.nl/bonus from your own browser (Ctrl+S) and import it with
``python -m scraper.run --ah-page <file>``; ``scrape_saved_page`` reads that
file offline, with every network request blocked.

Note: AH changes its HTML from time to time. Card detection below is
deliberately generic (it looks for links to product / bonus-group pages that
contain an image and a price), but it may need adjusting.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from .models import Offer

LABEL = "Albert Heijn"
BONUS_URL = "https://www.ah.nl/bonus"
BASE = "https://www.ah.nl"

DEAL_RE = re.compile(
    r"(\d+\s*\+\s*\d+\s*gratis|2e\s*halve\s*prijs|2e\s*gratis|\d+\s*%\s*korting|"
    r"€\s*\d+(?:[.,]\d{2})?\s*korting|"
    r"\d+\s*voor\s*€?\s*\d+[.,]\d{2}|\d+\s*voor\s*€?\s*\d+|voor\s*€?\s*\d+[.,]\d{2})",
    re.I,
)
# A card that opens with a price per weight, e.g. "100 gram 1.79" for meat
WEIGHT_PRICE_RE = re.compile(r"^((?:per\s+)?\d+\s*(?:gram|kilo)\s+€?\s*\d+[.,]\d{2})", re.I)
PRICE_RE = re.compile(r"(?<![\d.,])(\d{1,3})[.,](\d{2})(?![\d])")
QTY_RE = re.compile(
    r"(\d+\s*[x×]\s*\d+\s*(?:g|gram|ml)|\d+(?:[.,]\d+)?\s*(?:kg|kilo|gram|g|ml|l|liter|stuks?)\b|"
    r"per\s+(?:stuk|kilo|kg|bos|500\s*g))",
    re.I,
)

# Card links name their bonus week, e.g. "/bonus/groep/832162?week=47".
WEEK_QUERY_RE = re.compile(r"[?&]week=(\d{1,2})(?!\d)")
BONUS_WEEK_DAYS = 7

# Shared with the site's upload form; defines extractAhCards(document).
CARD_EXTRACTOR = Path(__file__).with_name("ah_cards.js")


def _extract_cards(page) -> list[dict]:
    """Run the shared card extractor in a Playwright page."""
    script = CARD_EXTRACTOR.read_text(encoding="utf-8")
    return page.evaluate(f"() => {{\n{script}\nreturn extractAhCards(document);\n}}")


def _parse_prices(text: str) -> tuple[Optional[float], Optional[float]]:
    """Return (offer_price, old_price) from card text without its deal text.

    The deal's own amount ("2 voor 4.00") is not a shelf price, so callers
    remove the deal first.
    """
    vals = [float(f"{a}.{b}") for a, b in PRICE_RE.findall(text)]
    if not vals:
        return None, None
    if len(vals) == 1:
        return vals[0], None
    return min(vals[:2]), max(vals[:2])


def _split_deal(text: str) -> tuple[Optional[str], str]:
    """Return (deal_text, the card text without it)."""
    deal = WEIGHT_PRICE_RE.match(text) or DEAL_RE.search(text)
    if not deal:
        return None, text
    return deal.group(1), text[:deal.start()] + " " + text[deal.end():]


def week_start(today: date, weeks_ahead: int = 0) -> date:
    """The Monday that starts an AH bonus week (they run Monday to Sunday)."""
    return today - timedelta(days=today.weekday()) + timedelta(weeks=weeks_ahead)


def week_end(monday: date) -> date:
    """The Sunday that ends the bonus week starting on ``monday``."""
    return monday + timedelta(days=BONUS_WEEK_DAYS - 1)


def page_week(cards: list[dict]) -> Optional[int]:
    """The ISO week number a saved bonus page is for: the one most of its card links name.

    A page also links a few offers of the week after (previews), so the first link can't be trusted.
    """
    weeks = Counter(w for w in map(card_week, cards) if w is not None)
    return weeks.most_common(1)[0][0] if weeks else None


def card_week(card: dict) -> Optional[int]:
    """The bonus week a card links to, if its link names one."""
    found = WEEK_QUERY_RE.search(card.get("href") or "")
    return int(found.group(1)) if found else None


def cards_of_week(cards: list[dict], week: int) -> list[dict]:
    """The cards of one bonus week; cards whose link names no week are kept."""
    return [c for c in cards if card_week(c) in (None, week)]


def card_to_offer(card: dict, week_monday: Optional[date] = None) -> Optional[Offer]:
    """One offer from a card; ``week_monday`` is its bonus week (default: this week)."""
    text = " ".join((card.get("text") or "").split())
    title = " ".join((card.get("title") or card.get("alt") or "").split())
    if not title:
        title = text.split(" €")[0][:80]
    if not title:
        return None
    deal, rest = _split_deal(text)
    price, old = _parse_prices(rest)
    if not deal and price is None:
        return None  # a banner such as "Heerlijke koffie, voordelig gezet", not an offer
    qty = QTY_RE.search(rest)
    href = (card.get("href") or "").split("?")[0]  # drop "?week=47"
    monday = week_monday or week_start(date.today())
    return Offer(
        store="ah",
        id=href.rstrip("/").split("/")[-1] or title,
        name=title,
        image=_absolute_url(card.get("img")),
        url=BASE + href if href.startswith("/") else href,
        price=price,
        old_price=old,
        deal_text=deal,
        quantity_text=qty.group(1) if qty else None,
        valid_from=monday.isoformat(),
        valid_to=week_end(monday).isoformat(),
    )


def _absolute_url(url: Optional[str]) -> Optional[str]:
    """Keep only web URLs; a saved page points images at local files instead."""
    return url if url and url.startswith("https://") else None


def offers_from_cards(cards: list[dict], week_monday: Optional[date] = None) -> list[Offer]:
    """Turn extracted cards into offers, one per AH product / bonus group."""
    offers, seen = [], set()
    for card in cards:
        offer = card_to_offer(card, week_monday)
        if offer and offer.id not in seen:
            seen.add(offer.id)
            offers.append(offer)
    return offers


def scrape_saved_page(path: Path) -> list[Offer]:
    """Read ah.nl/bonus as saved from the user's own browser (Ctrl+S)."""
    from playwright.sync_api import sync_playwright

    html = path.read_text(encoding="utf-8", errors="replace")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            # Offline on purpose: the saved page must not call ah.nl or its trackers.
            page.route("**/*", lambda route: route.abort())
            page.set_content(html, wait_until="domcontentloaded")
            cards = _extract_cards(page)
        finally:
            browser.close()
    return offers_from_cards(cards)


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
            cards = _extract_cards(page)
        finally:
            browser.close()
    return offers_from_cards(cards)
