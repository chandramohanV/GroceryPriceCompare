"""Download a public offers page with the scraper's own User-Agent (shared by the store scrapers)."""
from __future__ import annotations

USER_AGENT = (
    "Mozilla/5.0 (compatible; GroceryPriceCompare/1.0; "
    "+https://github.com/chandramohanV/GroceryPriceCompare)"
)
TIMEOUT_SECONDS = 30


def fetch_page(url: str) -> str:
    import httpx  # imported lazily so parsing/tests don't need it

    resp = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "nl-NL,nl;q=0.9"},
        timeout=TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text
