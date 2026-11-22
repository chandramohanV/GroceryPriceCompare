"""Test helper: build a fake page that embeds Nuxt state the way Nuxt sites (Dirk, Jumbo) do."""
import json


def devalue_encode(value) -> list:
    """Encode a value the way Nuxt does: a flat array of entries that point at each other."""
    entries: list = []

    def add(v) -> int:
        index = len(entries)
        entries.append(None)
        if isinstance(v, dict):
            entries[index] = {k: add(x) for k, x in v.items()}
        elif isinstance(v, list):
            entries[index] = [add(x) for x in v]
        else:
            entries[index] = v
        return index

    add(value)
    return entries


def nuxt_page(state, before: str = "") -> str:
    """An HTML page with ``state`` in its ``__NUXT_DATA__`` script, after ``before``."""
    payload = json.dumps(devalue_encode(state))
    return f'{before}<script type="application/json" id="__NUXT_DATA__">{payload}</script>'
