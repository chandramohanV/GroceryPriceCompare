# GroceryPriceCompare 🛒

Compares this week's and next week's offers at **Albert Heijn** (ah.nl/bonus), **Lidl**
(lidl.nl/aanbiedingen), **Aldi** (aldi.nl/aanbiedingen) **Dirk** (dirk.nl/aanbiedingen) and **Jumbo** (jumbo.com/aanbiedingen/nu) on
**fruit, vegetables, meat, fish, dairy & eggs, cereals, coffee and frozen food**: picture, price, discount and
the effective price **per kg / litre / piece**, with the cheapest offer marked **Best deal**.

Switch between **This week** and **Next week** (next week shows each store's offers as soon as
it publishes them: Lidl and Aldi late in the week, Jumbo from about Sunday, AH when you upload
it; AH announces it on Friday), pick which stores to compare (Best deal is then worked out among those only), switch between
light and dark mode, and keep a **grocery list**: in your browser, or saved to your account so
it follows you to every device.

Runs **free** on Cloudflare Pages (site + Functions + KV) and GitHub Actions.

```
Daily 06:00, Friday 20:00, "Run now" ──> GitHub Actions: scrape Lidl + Aldi + Dirk + Jumbo,  ┐   /api/offers            (this week)
                                         AH (this week) from its app API,                    ├─> /api/offers?week=next (next week) ──> site
                                         split into this week / next week                    │   (Cloudflare KV)
"Upload AH bonus page" form ──> parsed in your browser (Pyodide) ────────────────────────────┘
```

## Weekly use

Open the **Update prices** page at `/update` on the site (for example
`https://grocerypricecompare.pages.dev/update`; the deals page doesn't link to it) and enter the
update password.

- **Lidl, Aldi, Dirk, Jumbo and this week's Albert Heijn:** run by themselves every morning at
  06:00, and on Friday at 20:00 to pick up next week's offers (Dutch time; GitHub may start
  scheduled runs a few minutes late). Press **Run now** for an extra run; new prices appear
  after about three minutes.
- **Albert Heijn, next week:** AH's app API only shows bonuses once their week has started, so to
  see next week's AH offers before Monday (AH announces them on Friday), upload the page from your
  own browser:
  1. Open <https://www.ah.nl/bonus> and scroll to the bottom so every offer loads. For next
     week's offers, pick next week at the top of that page first.
  2. Press **Ctrl+S** and save it as **Webpage, Complete**.
  3. Choose **This week** or **Next week**, choose the saved `.html` file and press **Upload**.

  *This week* replaces the AH offers right away. *Next week* shows under **Next week** (the update
  section says so) and moves into this week with the 06:00 run on Monday; uploading again
  replaces it. A page from the other week is refused (AH's card links name their bonus week), and
  the few previews of the week after on a bonus page are left out.

The AH page is read in your browser with the same Python code the scraper uses (via Pyodide,
~10 MB on the first upload); only the resulting offers are sent to the site.

## Accounts and grocery lists

Add offers from the cards, or type your own items and pick the shop to buy them at (or "Any
shop"); the list is grouped per shop.

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

## Ask Claude about the offers (MCP)

The site has a read-only [MCP](https://modelcontextprotocol.io) server at `/mcp`, so Claude can
search and compare this week's and next week's offers for you, also from the Claude mobile app.
Add it once on [claude.ai](https://claude.ai): **Settings → Connectors → Add custom connector**,
name it "Grocery deals" and use the URL `https://grocerypricecompare.pages.dev/mcp` (no login:
the offers are public). It then shows up in Claude on the web, desktop and mobile; ask things
like "Where is cheese cheapest this week?" or "Best deals at Lidl and Aldi?".

Tools: `get_overview` (dates, stores, categories), `list_products`, `search_offers`,
`compare_product` (all stores side by side) and `best_deals`; give `week: "next"` for next week
and `stores` to weigh only the shops you go to. It reads the same offers as the site.

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
| `scraper/lidl.py` | Downloads the Lidl offers page; every product tile has its data as JSON in the HTML. Keeps the food aisles (skips pet food, bakery, sweets). Reads regular and Lidl Plus prices. |
| `scraper/aldi.py` | Downloads Aldi's this-week and next-week offer pages; the products are JSON in the page's `__NEXT_DATA__` script. Returns both weeks' offers; `weeks.py` sorts them into this week and next week. |
| `scraper/dirk.py` + `devalue.py` | Downloads Dirk's offers page; the offers are in Nuxt's `__NUXT_DATA__` payload, which `devalue.py` decodes. Pack sizes and pictures come from each offer's products. Dirk's week runs Wednesday–Tuesday. |
| `scraper/jumbo.py` | Downloads Jumbo's "nu" offers page; every promotion of this week and, from about Sunday, next week ("Vanaf woensdag"), featured and per aisle, is in the `__NUXT_DATA__` payload. Jumbo shows promotions, not shelf prices: the price or deal comes from the tag ("voor 1,00", "2 voor 3,00", "1+1 gratis") and the pack size from the subtitle, so there is no old price. Jumbo's week runs Wednesday–Tuesday. Sends the User-Agent without the repo link, because Jumbo's bot protection stalls requests whose User-Agent contains a URL. |
| `scraper/ah_api.py` | This week's AH bonus from AH's app API (anonymous token, no account). The search's bonus filter is ignored, so it reads the search's first 3,000 products (as far as its paging goes; bonus products rank high) and keeps in-store bonus products (`NATIONAL`), skipping online-only deals and aisles we never compare. Weight deals ("100 gram voor 1.99") are priced per that weight. Unofficial: AH can change or close it; a failure keeps the AH offers saved earlier. |
| `scraper/web.py` | Shared page download (User-Agent, timeout) for the Lidl, Aldi, Dirk and Jumbo scrapers. |
| `scraper/ah.py` + `ah_cards.js` | Reads AH promotion cards from a saved bonus page (next week's upload; ah.nl refuses scripts). `ah_cards.js` finds the cards and is shared by Playwright and the site's upload form. |
| `scraper/match.py` | Recognises products in Dutch names ("Jonagold appels" → *Appels*, "Half-om-half gehakt" → *Gehakt*) with whole-word matching, and skips things that only look like them (appeltaart, koffiebroodjes, vegetarisch gehakt…). Frozen food goes by the store's own label (Lidl's and Jumbo's frozen aisle, Aldi's "Diepvries" seal, Dirk's department, AH's frozen section on the bonus page) into frozen groups (fries, snacks, ice cream, pizza, meals, frozen vegetables, fruit, fish, meat), so it is never compared with fresh. |
| `scraper/normalize.py` | Parses quantities ("2 x 150 g", "Per 500 g", "1 Stk.") and deals ("1+1 gratis", "2e halve prijs", "2 voor 5,00") into an effective price per kg / litre / piece. |
| `scraper/translate.py` | Translates Dutch names, quantities and deals to English with a built-in glossary. The site shows English by default with a Nederlands toggle. |
| `scraper/pipeline.py` | Pure logic: classify, normalise, compare and build the `offers.json` payload. Runs in Python and in the browser. |
| `scraper/weeks.py` | Which offer week an offer belongs to (each store's week starts on its own weekday: Monday for AH, Lidl and Aldi, Wednesday for Dirk and Jumbo), splitting a scrape into this week and next week, and moving next week's offers into this week once their week starts. |
| `scraper/upload.py` | Entry point for the upload form (runs in Pyodide): AH into this week's or next week's offers. |
| `scraper/publish.py` | Daily refresh: moves started offers from next week into this week, scrapes Lidl, Aldi, Dirk, Jumbo and AH, splits them into both weeks and saves both back. A store with nothing for next week keeps its earlier next-week offers (so next week's AH upload stays). |
| `scraper/run.py` | Local run: scrapes all stores and writes `data/offers.json`, `data/offers-next.json` and `data/history/`. |
| `functions/api/` | Cloudflare Pages Functions: `offers.js` (read/save this week's offers in KV, next week's with `?week=next`), `run.js` (Run button), `account/` (sign-up, login, logout, saved list) and `next-week.js` (legacy: next week's AH upload as held before Nov 2026; the daily refresh moves it into next week's offers once). `functions/mcp.js` is the MCP server at `/mcp`. |
| `lib/` | Code shared by the Functions: `password.js` (update password), `offers.js` (upload shape checks), `accounts.js` (accounts, sessions, saved data; storage passed in so it is testable), `session.js` (cookies, JSON bodies), `mcp.js` (MCP protocol and tools) and `offer-queries.js` (the MCP tools' answers). |
| `site/` | Static website (plain HTML/CSS/JS, Material Design 3 styling, no build step). `style.css` holds the layout and design tokens; `modern.css`, loaded after it, reskins the site and only overrides styles. `state.js` keeps each person's preferences and list (browser or account), `list.js` the list panel, `account.js` the sign-in dialog, `theme.js` the light/dark button. `update.html` is the owner's page with `run.js` (Run now) and `upload.js` (AH bonus upload); `offers-data.js` loads the offers for both pages. |

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
python -m scraper.run                            # or: --stores lidl,aldi,dirk,jumbo
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
in `STORES` in `scraper/run.py` (and `DEFAULT_STORES` in `scraper/publish.py` if the daily job
should scrape it). Add its name to `site/stores.js` and a `--<store>` colour in `site/style.css`.

## Fair use

A few requests per store per day: public offer pages, and for AH four requests to its
app API (an unofficial API, used without an account). Not affiliated with Albert Heijn,
Lidl, Aldi, Dirk or Jumbo. Prices can differ in store; always check before you go.
