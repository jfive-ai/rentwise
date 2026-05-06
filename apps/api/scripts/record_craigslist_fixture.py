"""One-time live-fetch + sanitize for `tests/fixtures/craigslist/vancouver_apa.rss`.

Usage:  python -m scripts.record_craigslist_fixture > tests/fixtures/craigslist/vancouver_apa.rss

Run only when CL's RSS schema seems to have changed. Never commits live email
addresses or contact info — strips them before writing.
"""

from __future__ import annotations

import re
import sys

import httpx

URL = "https://vancouver.craigslist.org/search/apa?format=rss&hasPic=1"
USER_AGENT = "RentWise/0.1 (+https://github.com/jfive-ai/rentwise; contact@example.com)"

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")


def main() -> int:
    resp = httpx.get(URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    text = resp.text
    text = EMAIL_RE.sub("redacted@example.com", text)
    text = PHONE_RE.sub("604-555-0100", text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
