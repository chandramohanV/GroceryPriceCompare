# GroceryPriceCompare 🛒

Compares this week's offers at **Albert Heijn** (ah.nl/bonus) and **Lidl**
(lidl.nl/aanbiedingen) on **fruit, vegetables, meat, fish, dairy & eggs, cereals and coffee**:
picture, price, discount and the effective price **per kg / litre / piece**, with the cheapest
offer marked **Best deal**.

Runs **free** on Cloudflare Pages (site + Functions + KV) and GitHub Actions.

```
Every Monday / "Run now" button ──> GitHub Actions: scrape Lidl ──┐
                                                                  ├─> /api/offers (Cloudflare KV) ──> site
"Upload AH bonus page" form ──> parsed in your browser (Pyodide) ─┘
```

## Weekly use

On the site, open **Update prices** (top right) and enter the update password.

- **Lidl:** runs by itself every Monday. Press **Run now** for an extra run; new prices appear
  after about three minutes.
- **Albert Heijn:** ah.nl blocks scripts, so upload the page from your own browser:
  1. Open <https://www.ah.nl/bonus> and scroll to the bottom so every offer loads.
  2. Press **Ctrl+S** and save it as **Webpage, Complete**.
  3. Choose the saved `.html` file and press **Upload**.

The AH page is read in your browser with the same Python code the scraper uses (via Pyodide,
~10 MB on the first upload); only the resulting offers are sent to the site.

## Deploy (Cloudflare Pages)

```bash
python tools/build_site.py                      # assembles _site/
npx wrangler pages deploy                       # uses wrangler.toml
```

One-time setup, already done for `grocerypricecompare.pages.dev`:

| What | Where | Command / setting |
|---|---|---|
| KV namespace `OFFERS` | Cloudflare | `npx wrangler kv namespace create OFFERS` (id in `wrangler.toml`) |
| `UPLOAD_PASSWORD` secret | Cloudflare | `npx wrangler pages secret put UPLOAD_PASSWORD` |
| `GITHUB_TOKEN` secret (Run button) | Cloudflare | fine-grained token for this repo with **Actions: read and write**, then `npx wrangler pages secret put GITHUB_TOKEN` |
| `UPLOAD_PASSWORD` secret | GitHub repo | `gh secret set UPLOAD_PASSWORD` (same value) |
| `SITE_URL` variable | GitHub repo | `gh variable set SITE_URL --body https://grocerypricecompare.pages.dev` |

## How it works

| File | What it does |
|---|---|
| `scraper/lidl.py` | Downloads the Lidl offers page; every product tile has its data as JSON in the HTML. Keeps the food aisles (skips pet food, bakery, frozen pizza, sweets). Reads regular and Lidl Plus prices. |
| `scraper/ah.py` + `ah_cards.js` | Reads AH promotion cards from a saved bonus page (or live, usually blocked). `ah_cards.js` finds the cards and is shared by Playwright and the site's upload form. |
| `scraper/match.py` | Recognises products in Dutch names ("Jonagold appels" → *Appels*, "Half-om-half gehakt" → *Gehakt*) with whole-word matching, and skips things that only look like them (appeltaart, koffiebroodjes, vegetarisch gehakt…). |
| `scraper/normalize.py` | Parses quantities ("2 x 150 g", "Per 500 g", "1 Stk.") and deals ("1+1 gratis", "2e halve prijs", "2 voor 5,00") into an effective price per kg / litre / piece. |
| `scraper/translate.py` | Translates Dutch names, quantities and deals to English with a built-in glossary. The site shows English by default with a Nederlands toggle. |
| `scraper/pipeline.py` | Pure logic: classify, normalise, compare and build the `offers.json` payload. Runs in Python and in the browser. |
| `scraper/upload.py` | Entry point for the upload form (runs in Pyodide). |
| `scraper/publish.py` | Weekly refresh: scrapes Lidl, merges it into the saved offers and saves them back. |
| `scraper/run.py` | Local run: scrapes all stores and writes `data/offers.json` plus `data/history/`. |
| `functions/api/` | Cloudflare Pages Functions: `offers.js` (read/save offers in KV) and `run.js` (Run button). |
| `site/` | Static website (plain HTML/CSS/JS, Material Design 3 styling, no build step). |

**Comparison rule:** for each product, offers are compared on the effective price per kg (or per
piece when sold per piece), using the lowest price you can get, including free loyalty programmes.
When one store's offer has no price (e.g. "25% korting" without a shelf price), the card says
"Can't compare: price missing".

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
python -m scraper.run                            # or: --stores lidl
python -m scraper.run --ah-page ah-bonus.html    # with AH from a saved page
python -m pytest -q
python -m http.server 8000                       # then open http://localhost:8000/site/
```

The plain local server has no `/api`, so saving uploads and Run now only work on Cloudflare. To
test those locally: `python tools/build_site.py`, put `UPLOAD_PASSWORD=...` in `.dev.vars`, then
`npx wrangler pages dev`.

## Adding a store

Write `scraper/<store>.py` with a `LABEL` and a `scrape() -> list[Offer]` function and register it
in `STORES` in `scraper/run.py`.

## Fair use

A few requests per store per week, public offer pages only. Not affiliated with Albert Heijn or
Lidl. Prices can differ in store; always check before you go.
