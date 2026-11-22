# GroceryPriceCompare

Compares weekly fruit & veg offers at Albert Heijn and Lidl. Python scraper (`scraper/`) writes
`data/offers.json`; a static site (`site/`) renders it. See `README.md` for details.

## Rules for every change

- **Always follow the `clean-code` skill** (`.claude/skills/clean-code/SKILL.md`) for any code you
  write, edit, refactor or review in this repo, and go through its checklist before finishing.
- Run tests with `python -m pytest -q` and `npm test` (account logic in `lib/`), and report the results.
