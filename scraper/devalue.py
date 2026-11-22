"""Decode the ``__NUXT_DATA__`` payload that Nuxt sites (such as dirk.nl) embed in their pages.

Nuxt serialises its state with the "devalue" format: one flat JSON array in
which objects and arrays hold *indexes* of other entries instead of values, so
shared values are stored once. Index 0 is the root. Special values are
negative indexes, and typed values are arrays that start with a type name,
e.g. ``["Date", "2026-11-18T00:00:00Z"]`` or ``["Reactive", 12]`` (Vue state).
"""
from __future__ import annotations

import json
import re
from typing import Any

_PAYLOAD_RE = re.compile(r'<script[^>]*\bid="__NUXT_DATA__"[^>]*>(.*?)</script>', re.S)

# Negative indexes stand for values JSON can't hold; we only need them as Python values.
_SPECIAL_VALUES = {-1: None, -2: None, -3: float("nan"), -4: float("inf"), -5: float("-inf"), -6: -0.0}
# Vue/Nuxt wrappers around a single value: unwrap to that value.
_WRAPPERS = {"Reactive", "ShallowReactive", "Ref", "ShallowRef", "NuxtError", "Island"}
_EMPTY_WRAPPERS = {"EmptyRef", "EmptyShallowRef"}


class PayloadMissing(ValueError):
    """The page has no ``__NUXT_DATA__`` script."""


def payload_from_html(page: str) -> Any:
    """The decoded Nuxt state embedded in a page."""
    match = _PAYLOAD_RE.search(page)
    if not match:
        raise PayloadMissing("no __NUXT_DATA__ script in the page")
    return decode(json.loads(match.group(1)))


def decode(entries: list) -> Any:
    """Rebuild the original value from a devalue array (shared values stay shared)."""
    decoded: dict[int, Any] = {}

    def value_at(index: int) -> Any:
        if index < 0:
            return _SPECIAL_VALUES.get(index)
        if index in decoded:
            return decoded[index]
        entry = entries[index]
        if isinstance(entry, dict):
            obj: dict = {}
            decoded[index] = obj  # registered first so cycles resolve to the same object
            obj.update((key, value_at(i)) for key, i in entry.items())
            return obj
        if isinstance(entry, list):
            if entry and isinstance(entry[0], str):  # plain arrays only hold indexes
                decoded[index] = typed_value(entry)
                return decoded[index]
            items: list = []
            decoded[index] = items
            items.extend(value_at(i) for i in entry)
            return items
        return entry

    def typed_value(entry: list) -> Any:
        kind, args = entry[0], entry[1:]
        if kind in _WRAPPERS:
            return value_at(args[0])
        if kind in _EMPTY_WRAPPERS:
            return None
        if kind == "Date":
            return args[0]
        if kind == "Set":
            return [value_at(i) for i in args]
        if kind == "Map":  # key and value indexes, alternating
            return {value_at(args[i]): value_at(args[i + 1]) for i in range(0, len(args), 2)}
        if kind == "null":  # an object without prototype: literal keys, value indexes
            return {args[i]: value_at(args[i + 1]) for i in range(0, len(args), 2)}
        raise ValueError(f"unknown devalue type {kind!r}")

    return value_at(0)
