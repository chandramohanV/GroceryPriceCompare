# GroceryPriceCompare 🛒

Compares this week's offers at **Albert Heijn** (ah.nl/bonus), **Lidl**
(lidl.nl/aanbiedingen), **Aldi** (aldi.nl/aanbiedingen) and **Dirk** (dirk.nl/aanbiedingen) on
**fruit, vegetables, meat, fish, dairy & eggs, cereals and coffee**: picture, price, discount and
the effective price **per kg / litre / piece**, with the cheapest offer marked **Best deal**.

Pick which stores to compare (Best deal is then worked out among those only), switch between
light and dark mode, and keep a **grocery list**: in your browser, or saved to your account so
it follows you to every device.

Runs **free** on Cloudflare Pages (site + Functions + KV) and GitHub Actions.

```
Every Monday / "Run now" button ──> GitHub Actions: scrape Lidl + Aldi + Dirk ──┐
                                                                                ├─> /api/offers (Cloudflare KV) ──> site
"Upload AH bonus page" form ──> parsed in your browser (Pyodide) ───────────────┘
```

## Weekly use

On the site, open **Update prices** (top right) and enter the update password.

- **Lidl, Aldi and Dirk:** run by themselves every Monday. Press **Run now** for an extra run; new
  prices appear after about three minutes.
- **Albert Heijn:** ah.nl blocks scripts, so upload the page from your own browser:
  1. Open <https://www.ah.nl/bonus> and scroll to the bottom so every offer loads.
  2. Press **Ctrl+S** and save it as **Webpage, Complete**.
  3. Choose the saved `.html` file and press **Upload**.

The AH page is read in your browser with the same Python code the scraper uses (via Pyodide,
~10 MB on the first upload); only the resulting offers are sent to the site.

## Accounts and grocery lists

Anyone can use the grocery list without an account; it is then kept in that browser only.
With an account, the list and preferences (chosen stores, theme, language) are saved on the
site and appear on every device where you sign in.

**Creating users.** Sign-up is invite-only:

1. Choose an invite code once and save it on Cloudflare (redeploy afterwards so it takes effect):
   `npx wrangler pages secret put INVITE_CODE`
2. Give the code to each person who should get an account.
3. They open the site, press **Sign in** → **Create an account**, and pick their own username
   and password (at least 8 characters) and enter the invite code.

To stop new sign-ups, change the invite code; existing accounts keep working. Passwords are
stored as salted PBKDF2 hashes; after 10 wrong passwords an account is locked for 15 minutes.
To remove an account, delete its `user:<name>` and `data:<name>` keys from the `USERS` KV
namespace in the Cloudflare dashboard (Workers & Pages → KV).

## Deploy (Cloudflare Pages)

```bash
python tools/build_site.py                      # assembles _site/
npx wrangler pages deploy                       # uses wrangler.toml
```

One-time setup, already done for `grocerypricecompare.pages.dev`:

| What | Where | Command / setting |
|---|---|---|
| KV namespace `OFFERS` | Cloudflare | `npx wrangler kv namespace create OFFERS` (id in `wrangler.toml`) |
| KV namespace `USERS` (accounts) | Cloudflare | `npx wrangler kv namespace create USERS` (id in `wrangler.toml`) |
| `INVITE_CODE` secret (sign-up) | Cloudflare | `npx wrangler pages secret put INVITE_CODE` |
| `UPLOAD_PASSWORD` secret | Cloudflare | `npx wrangler pages secret put UPLOAD_PASSWORD` |
| `GITHUB_TOKEN` secret (Run button) | Cloudflare | fine-grained token for this repo with **Actions: read and write**, then `npx wrangler pages secret put GITHUB_TOKEN` |
| `UPLOAD_PASSWORD` secret | GitHub repo | `gh secret set UPLOAD_PASSWORD` (same value) |
| `SITE_URL` variable | GitHub repo | `gh variable set SITE_URL --body https://grocerypricecompare.pages.dev` |

## How it works

| File | What it does |
|---|---|
| `scraper/lidl.py` | Downloads the Lidl offers page; every product tile has its data as JSON in the HTML. Keeps the food aisles (skips pet food, bakery, frozen pizza, sweets). Reads regular and Lidl Plus prices. |
| `scraper/aldi.py` | Downloads Aldi's this-week and next-week offer pages; the products are JSON in the page's `__NEXT_DATA__` script. Keeps the offers running in the compared week (the week containing tomorrow, so on Sunday that is next week). |
| `scraper/dirk.py` + `devalue.py` | Downloads Dirk's offers page; the offers are in Nuxt's `__NUXT_DATA__` payload, which `devalue.py` decodes. Pack sizes and pictures come from each offer's products. Dirk's week runs Wednesday–Tuesday. |
| `scraper/web.py` | Shared page download (User-Agent, timeout) for the Lidl, Aldi and Dirk scrapers. |
| `scraper/ah.py` + `ah_cards.js` | Reads AH promotion cards from a saved bonus page (or live, usually blocked). `ah_cards.js` finds the cards and is shared by Playwright and the site's upload form. |
| `scraper/match.py` | Recognises products in Dutch names ("Jonagold appels" → *Appels*, "Half-om-half gehakt" → *Gehakt*) with whole-word matching, and skips things that only look like them (appeltaart, koffiebroodjes, vegetarisch gehakt…). |
| `scraper/normalize.py` | Parses quantities ("2 x 150 g", "Per 500 g", "1 Stk.") and deals ("1+1 gratis", "2e halve prijs", "2 voor 5,00") into an effective price per kg / litre / piece. |
| `scraper/translate.py` | Translates Dutch names, quantities and deals to English with a built-in glossary. The site shows English by default with a Nederlands toggle. |
| `scraper/pipeline.py` | Pure logic: classify, normalise, compare and build the `offers.json` payload. Runs in Python and in the browser. |
| `scraper/upload.py` | Entry point for the upload form (runs in Pyodide). |
| `scraper/publish.py` | Weekly refresh: scrapes Lidl, Aldi and Dirk, merges it into the saved offers and saves them back. |
| `scraper/run.py` | Local run: scrapes all stores and writes `data/offers.json` plus `data/history/`. |
| `functions/api/` | Cloudflare Pages Functions: `offers.js` (read/save offers in KV), `run.js` (Run button) and `account/` (sign-up, login, logout, saved list). |
| `lib/` | Code shared by the Functions: `password.js` (update password), `accounts.js` (accounts, sessions, saved data; storage passed in so it is testable), `session.js` (cookies, JSON bodies). |
| `site/` | Static website (plain HTML/CSS/JS, Material Design 3 styling, no build step). `state.js` keeps each person's preferences and list (browser or account), `list.js` the list panel, `account.js` the sign-in dialog, `theme.js` the light/dark button. |

**Comparison rule:** for each product, offers are compared on the effective price per kg (or per
piece when sold per piece), using the lowest price you can get, including free loyalty programmes.
When one store's offer has no price (e.g. "25% korting" without a shelf price), the card says
"Can't compare: price missing". `offers.json` also holds the verdict for every combination of
stores (`verdicts_by_store_set`), so the site never re-implements this rule in JavaScript.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
python -m scraper.run                            # or: --stores lidl,aldi,dirk
python -m scraper.run --ah-page ah-bonus.html    # with AH from a saved page
python -m pytest -q
npm test                                         # account logic (Node's built-in test runner)
python -m http.server 8000                       # then open http://localhost:8000/site/
```

The plain local server has no `/api`, so saving uploads, Run now and accounts only work on
Cloudflare. To test those locally: `python tools/build_site.py`, put `UPLOAD_PASSWORD=...` and
`INVITE_CODE=...` in `.dev.vars`, then `npx wrangler pages dev` (it serves `_site/`, so rebuild
after changing `site/`).

## Adding a store

Write `scraper/<store>.py` with a `LABEL` and a `scrape() -> list[Offer]` function and register it
in `STORES` in `scraper/run.py` (and `DEFAULT_STORES` in `scraper/publish.py` if the weekly job
should scrape it). Add its name to `site/stores.js` and a `--<store>` colour in `site/style.css`.

## Fair use

A few requests per store per week, public offer pages only. Not affiliated with Albert Heijn,
Lidl, Aldi or Dirk. Prices can differ in store; always check before you go.
