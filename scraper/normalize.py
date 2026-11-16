"""Turn store-specific price/quantity/deal text into comparable numbers.

* ``parse_quantity("2 x 150 g")``  -> (0.3, "kg")
* ``deal_factor("1+1 gratis")``    -> 0.5   (you pay half per item)
* ``enrich(offer)`` fills qty_amount / qty_unit / effective_price / unit_price
"""
from __future__ import annotations

import re
from typing import Optional

from .models import Offer

_NUM = r"(\d+(?:[.,]\d+)?)"


def _num(s: str) -> float:
    return float(s.replace(",", "."))


_WEIGHT_UNITS = {
    "kg": 1.0, "kilo": 1.0, "kilogram": 1.0,
    "g": 0.001, "gr": 0.001, "gram": 0.001,
    "l": 1.0, "liter": 1.0, "ltr": 1.0,
    "ml": 0.001, "cl": 0.01,
}
_PIECE_WORDS = (
    "stuk", "stuks", "stk", "st", "bos", "bosje", "krop", "kropje", "struik",
    "net", "zak", "bak", "bakje", "doos", "pak", "trosje", "tros",
)


def parse_quantity(text: Optional[str]) -> tuple[Optional[float], Optional[str]]:
    """Return (amount, unit) where unit is "kg", "l" or "stuk"."""
    if not text:
        return None, None
    t = text.lower().replace("ca.", "").replace("ongeveer", "").strip()

    # "2 x 150 g" / "4x125g"
    m = re.search(_NUM + r"\s*[x×]\s*" + _NUM + r"\s*(kg|kilo|gram|gr|g|ml|cl|liter|ltr|l)\b", t)
    if m:
        unit = m.group(3)
        amount = _num(m.group(1)) * _num(m.group(2)) * _WEIGHT_UNITS[unit]
        return round(amount, 4), ("l" if unit in ("l", "liter", "ltr", "ml", "cl") else "kg")

    units = r"(kilogram|kilo|kg|gram|gr|g|ml|cl|liter|ltr|l)\b"
    # "1500 g", "per 500 g", "1,5 kg"
    m = re.search(r"\b" + _NUM + r"\s*" + units, t)
    if m:
        unit = m.group(2)
        amount = _num(m.group(1)) * _WEIGHT_UNITS[unit]
        return round(amount, 4), ("l" if unit in ("l", "liter", "ltr", "ml", "cl") else "kg")
    # "per kilo", "per kg"
    m = re.search(r"\bper\s+" + units, t)
    if m:
        unit = m.group(1)
        return _WEIGHT_UNITS[unit], ("l" if unit in ("l", "liter", "ltr", "ml", "cl") else "kg")

    # "6 stuks", "1 Stk.", "per stuk", "per bos"
    m = re.search(r"(?:\b" + _NUM + r"\s*)?\b(" + "|".join(_PIECE_WORDS) + r")\b\.?", t)
    if m and (m.group(1) or re.search(r"\b(per|1)\s+" + m.group(2), t) or m.group(2) in ("stuk", "stuks", "stk")):
        return (_num(m.group(1)) if m.group(1) else 1.0), "stuk"

    return None, None


def deal_factor(deal: Optional[str]) -> float:
    """Multiplier applied to the pack price for multi-buy deals.

    Percent discounts are *not* applied here when the store already shows the
    discounted price (Lidl does). Use ``apply_percent=True`` callers for AH.
    """
    if not deal:
        return 1.0
    t = deal.lower()
    m = re.search(r"(\d+)\s*\+\s*(\d+)\s*gratis", t)
    if m:  # 1+1 gratis -> pay 1 of 2; 2+1 gratis -> pay 2 of 3
        pay, free = int(m.group(1)), int(m.group(2))
        return pay / (pay + free)
    if re.search(r"2e\s*halve\s*prijs|tweede\s*halve\s*prijs", t):
        return 0.75
    if re.search(r"2e\s*gratis", t):
        return 0.5
    return 1.0


def percent_off(deal: Optional[str]) -> Optional[float]:
    if not deal:
        return None
    m = re.search(r"(\d+)\s*%", deal)
    return int(m.group(1)) / 100 if m else None


def multi_price(deal: Optional[str]) -> Optional[tuple[int, float]]:
    """'2 voor 5,00' / '3 voor €4' -> (2, 5.0)."""
    if not deal:
        return None
    m = re.search(r"(\d+)\s*(?:stuks\s*)?voor\s*€?\s*" + _NUM, deal.lower())
    if m:
        return int(m.group(1)), _num(m.group(2))
    return None


def enrich(offer: Offer, price_already_discounted: bool = True) -> Offer:
    amount, unit = parse_quantity(offer.quantity_text)
    if amount is None:
        amount, unit = parse_quantity(offer.name)
    offer.qty_amount, offer.qty_unit = amount, unit

    candidates = [p for p in (offer.price, offer.member_price) if p is not None]
    if not candidates:
        return offer
    base = min(candidates)

    mp = multi_price(offer.deal_text)
    if mp:
        base = min(base, mp[1] / mp[0])
    else:
        base *= deal_factor(offer.deal_text)
        pct = percent_off(offer.deal_text)
        if pct and not price_already_discounted:
            base *= 1 - pct

    offer.effective_price = round(base, 2)
    if amount:
        offer.unit_price = round(base / amount, 2)
    return offer
