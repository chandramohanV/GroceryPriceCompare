---
name: clean-code
description: Clean code principles for every change in GroceryPriceCompare. Use whenever writing, editing, refactoring, or reviewing any code in this repo — Python in scraper/ and tests/, JavaScript/HTML/CSS in site/, and the GitHub Actions workflow — including small fixes, new stores, parser tweaks, and UI changes.
---

# Clean Code for GroceryPriceCompare

Apply these principles to **every** change. Code should read like the README does: plain, small and
obvious. When a rule conflicts with consistency with the surrounding code, keep it consistent and
mention the trade-off.

## 1. Names reveal intent

- Name things by what they mean, not how they are stored: `unit_price`, `member_price`,
  `is_processed_product`. Avoid `data`, `tmp`, `x`, `res`, `obj`, `info`.
- Functions are verbs (`parse_quantity`, `renderStatus`, `loadData`); booleans read as questions
  (`is_fruit_or_veg`, `has_member_price`, `s.ok`).
- One word per concept across the codebase: if it is `offer` in Python, it is `offer` in JS and
  JSON. Keep the existing domain words (`store`, `deal_text`, `effective_price`, `unit_price`).
- Short names are fine only in tiny scopes (`for o in offers`, lambda args).
- Dutch product/deal vocabulary stays Dutch in data and regexes ("1+1 gratis", "per stuk"); code
  identifiers and comments are English.

## 2. Small functions that do one thing

- A function does one thing at one level of abstraction. If you need "and" to describe it, split
  it (e.g. *fetch* the page, *extract* tiles, *map* a tile to an `Offer` — three functions).
- Aim for functions that fit on a screen (~20–30 lines). Extract helpers with good names instead
  of adding comments that explain a block.
- At most ~3 parameters; beyond that, pass a dataclass or dict with a clear shape.
- No flag arguments that switch between two different behaviours (`render(x, compact=True)`
  producing two different layouts) — write two functions. A defaulted option that narrows or
  tunes one behaviour is fine (`parse_html(page, only_produce=True)`).
- Return early with guard clauses instead of nesting `if` deeper than two levels.

## 3. Separation of responsibilities (this repo's architecture)

Keep each module to its job; don't leak concerns across the boundary:

| Module | Owns | Must not |
|---|---|---|
| `scraper/<store>.py` | Fetching and parsing one store into `list[Offer]` | Classify produce, compute unit prices, write files |
| `scraper/match.py` | Recognising fruit/veg from names | Do I/O or know about stores |
| `scraper/normalize.py` | Quantities, deals, effective/unit price | Do I/O or know about stores |
| `scraper/models.py` | The `Offer` data shape | Contain scraping logic |
| `scraper/run.py` | Orchestration, comparison, writing JSON | Contain store-specific parsing |
| `site/app.js` | Loading `offers.json` and rendering | Re-implement price normalisation |

- Pure functions (parsing, matching, normalising, comparing) stay free of network, filesystem,
  clock and randomness, so they are trivially testable.
- I/O lives at the edges (`scrape()`, `run.py` main, `loadData()`).
- New store = new `scraper/<store>.py` with `scrape() -> list[Offer]` registered in `STORES`.
  Don't add `if store == "..."` branches elsewhere.

## 4. DRY, but not prematurely

- Remove real duplication of *knowledge* (the same rule or constant in two places). Example:
  unit labels, store names, regexes for "per kg" belong in one place.
- Don't abstract on the first repetition; wait for the third, or until the two copies must change
  together.
- Python and JS may each need a small mapping (e.g. store display names); if it grows, move it
  into `offers.json` instead of duplicating it.

## 5. No magic values

- Name constants at module top in `UPPER_SNAKE_CASE` (Python) / `UPPER_SNAKE_CASE` `const` (JS):
  URLs, CSS selectors, category names, timeouts, scroll counts, thresholds.
- Use the existing vocabulary sets (`"kg" | "l" | "stuk"`, `"fruit" | "groente"`) rather than
  re-typing string literals in new places.

## 6. Comments explain *why*, code explains *what*

- Prefer a better name or an extracted function over a comment.
- Good comments: why a workaround exists ("AH returns Access Denied to cloud IPs, so …"), units
  and examples (`# e.g. "2 x 150 g"`), links to the source format.
- Delete commented-out code and stale comments; git has history.
- Every module keeps a one-line docstring saying what it is for. Public functions get a short
  docstring when the name + type hints aren't enough.

## 7. Errors are explicit

- Never use bare `except:` or `except Exception: pass`. Catch the narrowest exception, and either
  handle it meaningfully or let it propagate.
- Store isolation is intentional: one failing store must not stop the others (`run.py`). Record
  the error message so the site can show "not available" — don't swallow it silently.
- Parsers return `None` for "couldn't parse" (as `parse_quantity` does) rather than raising for
  expected messy input; raise for programmer errors.
- In JS, `catch` blocks either recover with a comment saying why (`/* try next URL */`) or surface
  the error to the user.

## 8. Python style

- Python 3.10+ with `from __future__ import annotations`; type hints on all function signatures.
- Use `@dataclass` for structured data (see `Offer`); no ad-hoc dicts passed through many layers.
- Follow PEP 8; imports grouped stdlib / third-party / local; no wildcard imports.
- Prefer comprehensions and small helpers over long loops with mutable accumulators, when it
  stays readable.
- Use `pathlib.Path` for file paths, f-strings for formatting.
- Keep dependencies minimal (`httpx`, `playwright`, `pytest`). Ask before adding a new one.

## 9. JavaScript / HTML / CSS style

- Plain ES2020+, no build step, no frameworks — keep it that way.
- `"use strict"`, `const` by default, `let` only when reassigned, never `var`.
- Build DOM with `textContent` / the `el()` helper, never `innerHTML` with data from
  `offers.json` (scraped text is untrusted).
- Rendering functions take data and return or fill elements; keep state changes in one place
  (`state`).
- CSS: reuse existing classes and custom properties; no inline styles from JS unless dynamic.

## 10. Tests

- Every behaviour change in `scraper/` comes with a test in `tests/`; every bug fix gets a test
  that would have caught it.
- Prefer `pytest.mark.parametrize` tables for parsers (follow `test_parse_quantity`).
- Tests use fixtures in `tests/fixtures/`, never the live network.
- Test names describe behaviour: `test_two_for_price_deal_halves_unit_price`.
- Run `python -m pytest -q` before declaring a change done and report the result.

## 11. Keep changes focused

- Leave code cleaner than you found it (Boy Scout rule), but only in the area you're touching —
  don't mix large unrelated refactors into a feature or fix.
- Delete dead code, unused imports and unused variables you come across in touched files.
- Update `README.md` when behaviour, setup, or the file table changes.

## Checklist before finishing a change

1. Names say what things mean; no vague or abbreviated names.
2. Each new/changed function does one thing, is short, and has ≤ 3 parameters.
3. Logic sits in the right module (table in §3); pure logic has no I/O.
4. No magic numbers/strings; no duplicated knowledge.
5. No swallowed errors; no commented-out code.
6. Type hints (Python) / `const` + no `innerHTML` with data (JS).
7. Tests added or updated, and `python -m pytest -q` passes.
8. README updated if user-visible behaviour changed.
