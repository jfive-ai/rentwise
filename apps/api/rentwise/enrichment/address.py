"""Vancouver address normalizer.

Wraps :mod:`pyap` with a small preprocessor and post-processor so that
two listings with addresses like "1234 W 4th Ave" and "1234 West 4th
Avenue, Vancouver, BC V6H 1S6, Canada" produce the *same* canonical
key. The dedup step in PR-C will key off this string.

We do **not** rely on pyap as the source of truth for the parsed parts —
its CA grammar mishandles common Vancouver patterns like "Apt 5, ..."
and "500 - 1234 West Broadway". Instead we strip those suite/unit
prefixes ourselves before pyap sees the string, then let pyap split out
the rest, then rebuild a canonical form.
"""

from __future__ import annotations

import re
import warnings

# pyap's source modules emit a stack of SyntaxWarning on import (raw-string
# escape issues in a vendored regex). Silence them at the boundary so they
# don't pollute test output. Real call-site warnings still surface.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", SyntaxWarning)
    import pyap

__all__ = ["DIRECTIONAL", "STREET_TYPE", "normalize_address", "preprocess"]

# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

DIRECTIONAL: dict[str, str] = {
    # short → long, lowercased on input
    "n": "north",
    "s": "south",
    "e": "east",
    "w": "west",
    "ne": "northeast",
    "nw": "northwest",
    "se": "southeast",
    "sw": "southwest",
}

STREET_TYPE: dict[str, str] = {
    # Common Vancouver/BC street types. Long-form is the canonical key.
    "ave": "avenue",
    "av": "avenue",
    "blvd": "boulevard",
    "boul": "boulevard",
    "cres": "crescent",
    "ct": "court",
    "dr": "drive",
    "hwy": "highway",
    "ln": "lane",
    "pl": "place",
    "pkwy": "parkway",
    "rd": "road",
    "st": "street",
    "ter": "terrace",
    "way": "way",
}

# Suite/unit prefix patterns we strip before handing the string to pyap.
# Order matters: more specific patterns first.
# 1) "Apt 5, ", "Unit 12, ", "Suite 200, ", "Ste 200, ", "#7 - " — keyword + id + sep
# 2) "500 - " when followed by another number ("500 - 1234 W Broadway")
_SUITE_PREFIX_RE = re.compile(
    r"^\s*(?:(?:apt|apartment|unit|suite|ste|#)\s*[A-Za-z0-9-]+\s*[,-]\s*"
    r"|\d+\s*-\s*(?=\d+\s))",
    re.IGNORECASE,
)

# After preprocessing we also drop the country tail; pyap can take it but
# it adds noise to the canonical key.
_COUNTRY_TAIL_RE = re.compile(r",?\s*canada\s*$", re.IGNORECASE)

# Whitespace + punctuation collapse for the canonical key.
_WS_RE = re.compile(r"\s+")


def preprocess(raw: str) -> str:
    """Strip suite prefixes and the country tail; collapse whitespace.

    Pure / deterministic; safe to call on already-clean input.
    """
    s = raw.strip()
    s = _SUITE_PREFIX_RE.sub("", s)
    s = _COUNTRY_TAIL_RE.sub("", s)
    s = _WS_RE.sub(" ", s).strip(" ,")
    return s


def _expand_token(tok: str) -> str:
    lower = tok.lower().strip(",.")
    if lower in DIRECTIONAL:
        return DIRECTIONAL[lower]
    if lower in STREET_TYPE:
        return STREET_TYPE[lower]
    return lower


def _expand(s: str) -> str:
    return " ".join(_expand_token(t) for t in s.split())


def normalize_address(raw: str | None) -> str | None:
    """Return a canonical key for ``raw``, or ``None`` if no address parses.

    The key is intentionally simple — lowercased, abbreviation-expanded,
    whitespace-collapsed. Two addresses that refer to the same building
    should produce the same key under reasonable input variants.

    Examples
    --------
    >>> normalize_address("1234 W 4th Ave, Vancouver, BC V6H 1S6")
    '1234 west 4th avenue vancouver bc v6h 1s6'
    >>> normalize_address("1234 West 4th Avenue, Vancouver, BC V6H 1S6, Canada")
    '1234 west 4th avenue vancouver bc v6h 1s6'
    >>> normalize_address("Apt 5, 1234 W 4th Ave, Vancouver, BC") == \
    ...     normalize_address("1234 W 4th Ave, Vancouver, BC")
    True
    >>> normalize_address("studio in Kits, no address") is None
    True
    """
    if raw is None:
        return None
    cleaned = preprocess(raw)
    if not cleaned:
        return None
    parsed = pyap.parse(cleaned, country="CA")
    if not parsed:
        return None
    a = parsed[0]
    parts: list[str] = []
    for attr in ("street_number", "street_name", "street_type", "city", "region1", "postal_code"):
        v = getattr(a, attr, None)
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        parts.append(_expand(s))
    if not parts:
        return None
    canonical = " ".join(parts)
    canonical = _WS_RE.sub(" ", canonical).strip()
    return canonical
