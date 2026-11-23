"""Shared data model for a single supermarket offer."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Offer:
    store: str                      # "lidl" | "aldi" | "dirk" | "jumbo" | "ah"
    id: str                         # store-specific id, unique within store
    name: str                       # product title as shown by the store
    image: Optional[str] = None
    url: Optional[str] = None
    price: Optional[float] = None         # offer price everyone pays (per pack)
    old_price: Optional[float] = None     # price before discount
    member_price: Optional[float] = None  # loyalty price (Lidl Plus / AH bonuskaart)
    member_label: Optional[str] = None    # e.g. "met Lidl Plus"
    deal_text: Optional[str] = None       # e.g. "1+1 gratis", "-45%"
    quantity_text: Optional[str] = None   # e.g. "1500 g", "Per stuk"
    valid_from: Optional[str] = None      # ISO date
    valid_to: Optional[str] = None        # ISO date
    is_frozen: bool = False               # the store files it as frozen food (aisle, seal, section)
    category: Optional[str] = None        # one of match.CATEGORIES (filled by matcher)
    product: Optional[str] = None         # canonical product, e.g. "Appels"
    # Filled in by normalize.enrich()
    qty_amount: Optional[float] = None
    qty_unit: Optional[str] = None        # "kg" | "l" | "stuk"
    effective_price: Optional[float] = None  # best price per pack after deal
    unit_price: Optional[float] = None       # effective price per kg / l / stuk
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        if not d["extras"]:
            d.pop("extras")
        return d
