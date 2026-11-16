# GroceryPriceCompare 🥕

Compares this week's **fruit & vegetable offers** at **Albert Heijn** (ah.nl/bonus) and
**Lidl** (lidl.nl/aanbiedingen): picture, price, discount and the effective price
**per kg / per piece**, with the cheapest offer marked **Best deal**.

Runs completely **free**: a daily GitHub Actions job scrapes the offers, saves them as JSON in
this repo, and publishes a static website on GitHub Pages.

```
GitHub Actions (daily) ──> scraper (Python) ──> data/offers.json ──> GitHub Pages site
                           Lidl: HTTP + embedded JSON              cards, filters, best-deal badge
                           AH:   headless Chromium (experimental)
```

## Setup (one time)

1. Push this repo to GitHub (it must be **public** for unlimited free Actions minutes).
2. **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. **Actions** tab → *Update offers & deploy site* → **Run workflow**.
4. Your site appears at `https://<your-username>.github.io/GroceryPriceCompare/`.

After that it updates itself every morning.

## How it works

| File | What it does |
|---|---|
| `scraper/lidl.py` | Downloads the Lidl offers page; every product tile has its data as JSON in the HTML. Keeps the "Groenten & fruit" category. Reads regular and Lidl Plus prices. |
| `scraper/ah.py` | **Experimental.** Opens ah.nl/bonus in headless Chromium, scrolls, and reads the promotion cards. |
| `scraper/match.py` | Recognises fruit/veg in Dutch product names ("Jonagold appels" → *Appels*) using whole-word matching, and skips processed products (appelsap, appeltaart, vlaai…). |
| `scraper/normalize.py` | Parses quantities ("2 x 150 g", "Per 500 g", "1 Stk.") and deals ("1+1 gratis", "2e halve prijs", "2 voor 5,00") into an effective price per kg / per piece. |
| `scraper/run.py` | Runs all stores (one failing store doesn't stop the others), compares, and writes `data/offers.json` plus `data/history/YYYY-MM-DD.json`. |
| `site/` | Static website (plain HTML/CSS/JS, no build step). |

**Comparison rule:** for each product, offers are compared on the effective price per kg (or per
piece when sold per piece), using the lowest price you can get, including free loyalty programmes
(Lidl Plus, AH Bonuskaart).

## ⚠️ About Albert Heijn

ah.nl is protected against automated traffic and may answer **Access Denied** to cloud servers
such as GitHub Actions. The scraper does not try to get around that; it records the store as
"not available" and the site shows Lidl offers only. If that happens, run the scraper from your
own computer (below) and push the result, or schedule it there with Task Scheduler / cron.

The AH card parser is generic because AH's HTML could not be tested while this was built. If it
finds no products, adjust `_EXTRACT_JS` in `scraper/ah.py`.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
python -m scraper.run            # or: python -m scraper.run --stores lidl
python -m pytest -q
python -m http.server 8000       # then open http://localhost:8000/site/
```

## Adding a store

Write `scraper/<store>.py` with a `scrape() -> list[Offer]` function and register it in
`STORES` in `scraper/run.py`.

## Fair use

One request per store per day, public offer pages only, respecting each site's `robots.txt`.
Not affiliated with Albert Heijn or Lidl. Prices can differ in store; always check before you go.
