"""Best-effort regex parser for Craigslist apartment-listing titles.

Pattern (informal):
  $<price> / <beds>br - <sqft>ft² - <free text> (<area code>)

Failures (any of price/beds/sqft/hint) leave the corresponding field None.
This parser MUST never raise on adversarial input — see property tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rentwise.adapters.craigslist.neighborhoods import (
    _ALIASES,
    NEIGHBORHOOD_POSTAL_SEEDS,
)

_PRICE_RE = re.compile(r"\$\s*(\d{3,5})\b")
_BEDS_RE = re.compile(r"\b(\d)\s*(?:br|bd|bed)\b", re.IGNORECASE)
_STUDIO_RE = re.compile(r"\bstudio\b", re.IGNORECASE)
_SQFT_RE = re.compile(r"\b(\d{2,5})\s*(?:ft²|ft2|sqft|sf)\b", re.IGNORECASE)
_AREA_RE = re.compile(r"\(([^)]+)\)\s*$")

# All known names (aliases + canonical), sorted longest-first so multi-word matches win
_ALL_KNOWN: list[str] = sorted(
    list(_ALIASES.keys()) + list(NEIGHBORHOOD_POSTAL_SEEDS.keys()),
    key=len,
    reverse=True,
)


@dataclass(frozen=True)
class TitleParseResult:
    price_cad: int | None = None
    bedrooms: float | None = None
    sqft: int | None = None
    neighborhood_hint: str | None = None


def parse_title(title: str) -> TitleParseResult:
    if not title:
        return TitleParseResult()
    try:
        return _parse(title)
    except Exception:  # absolute belt-and-suspenders
        return TitleParseResult()


def _parse(title: str) -> TitleParseResult:
    price = None
    if (m := _PRICE_RE.search(title)) is not None:
        try:
            price = int(m.group(1))
        except ValueError:
            price = None

    beds: float | None = None
    if _STUDIO_RE.search(title):
        beds = 0.5
    elif (m := _BEDS_RE.search(title)) is not None:
        try:
            beds = float(int(m.group(1)))
        except ValueError:
            beds = None

    sqft: int | None = None
    if (m := _SQFT_RE.search(title)) is not None:
        try:
            sqft = int(m.group(1))
        except ValueError:
            sqft = None

    hint = None

    # Primary: explicit parenthesised area code at end of title
    if (m := _AREA_RE.search(title)) is not None:
        raw = m.group(1).split("/")[0].strip().lower()
        # only set hint if the value looks neighborhood-shaped (letters + spaces + hyphens)
        if re.fullmatch(r"[a-z\s\-]+", raw):
            hint = raw

    # Fallback: scan the lowercased tail for a known alias or neighborhood name
    if hint is None:
        tail = title.lower()
        for name in _ALL_KNOWN:
            if tail.endswith(name):
                hint = name
                break

    return TitleParseResult(price_cad=price, bedrooms=beds, sqft=sqft, neighborhood_hint=hint)
