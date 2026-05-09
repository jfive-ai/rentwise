# Sources audit

> Per-adapter status as of 2026-05-09. Update whenever an adapter ships
> a calibrated extractor, gets disabled by upstream changes, or has its
> TOS posture reassessed.

This doc captures the *honest* state of each rental source so anyone
deciding which adapter to enable can read the trade-off in one place.

The hard rules from `docs/operational-rules.md` apply to every source —
robots.txt is the gate, 1 req/sec ceiling (0.5 for the Playwright-based
scaffolds), identifying User-Agent, snippets ≤ 200 chars, no proxy /
CAPTCHA / login-wall games. This doc only adds per-source colour.

## Status legend

- **shipped** — calibrated against live (or recorded) markup, returns
  listings under normal conditions, default-on or opt-in via env flag.
- **scaffold** — selectors not yet calibrated against live rendered
  HTML. Adapter is registered when its env flag is enabled and reports
  `source_health = degraded` with `last_error = "scaffold: ..."` so the
  user sees why no listings appear.
- **blocked** — robots.txt or anti-bot defenses (e.g. Cloudflare
  challenge) reject our identifying User-Agent. Out of scope per the
  operational rules; we don't bypass.
- **deferred** — TOS or partnership reality argues for not building an
  adversarial adapter. Tracked here as a "no" rather than a silent gap.

| Source        | Status   | robots.txt | TOS posture | Default | Blocker / next step |
|---------------|----------|------------|-------------|---------|--------------------|
| Craigslist    | shipped  | permissive on `/jsonsearch/apa` | TOS § 5 prohibits scraping; we use the public JSON endpoint with identifying UA. | on  | — |
| PadMapper     | scaffold | permissive on listing pages; `/api`, `?box=`, `cost-calculator` Disallow'd | § 8.4 prohibits scraping. Personal-use opt-in. | off (`RENTWISE_PADMAPPER_ENABLED=true`) | Calibrate `_extract` against rendered HTML. Live probe with our UA returns 200. |
| Rentals.ca    | scaffold | empty robots.txt | § 3.16 prohibits scraping. | off (`RENTWISE_RENTALSCA_ENABLED=true`) | Cloudflare challenge returns 403 to our UA without browser-fingerprint chrome. Even with Playwright the challenge persists. **Effectively blocked** for our UA posture; treat as `deferred` until the position changes. |
| Zumper        | scaffold | search-relevant paths (`?bedrooms=`, `?box=`) Disallow'd | § 11 prohibits scraping (same template as PadMapper). | off (`RENTWISE_ZUMPER_ENABLED=true`) | robots.txt blocks the search-page query strings we'd need. Without those, only city-index pages remain — limited useful coverage. **deferred**. |
| REW.ca        | scaffold | `/rentals/search` Disallow'd | "robot, spider, or other automatic device" prohibited explicitly. | off (`RENTWISE_REW_ENABLED=true`) | Search paths are off-limits and TOS language is the strictest of any source we've considered. **deferred**. |
| liv.rent      | scaffold | unknown (root returns 301 only) | § 7.1(v)/(w) prohibits scraping. Vancouver-based startup; partnership likely the better long-term path. | off (`RENTWISE_LIVRENT_ENABLED=true`) | **deferred** — see operational-rules.md note. |
| Kijiji        | not built | `Disallow: /rss-*` (RSS explicitly blocked) | Verified live: RSS blocked. | n/a | Out of scope; no permitted path to listings. |
| Reddit r/vancouverrentals | not built | OK with our UA (200 on JSON; 99/100 rate-limit budget) | OK for personal use under their public-content policy. | n/a | Listings are unstructured prose, not addressable. Would require LLM-based extraction per post. Low ROI vs. Craigslist/PadMapper. |

## What "scaffold" means in code

`apps/api/rentwise/adapters/scaffold_base.py` is the shared base for
the Playwright-backed scaffolds (zumper, rew, livrent). Its
`_extract(html, query)` returns `[]` + a `structlog.warning` until a
subclass overrides it. Subclasses that haven't overridden it are
flagged at the aggregator layer (`_is_uncalibrated_scaffold`) so a
successful HTTP fetch + zero results reports as
`source_health = degraded` instead of silently looking like "no
matches" to the user (#94).

PadMapper and Rentals.ca have their own non-base extractors that
parse a synthetic test fixture; they're scaffolds in the sense that
the live-site selectors haven't been confirmed against rendered HTML
yet, but a calibration pass is the only blocker for PadMapper.

## Path to "shipped" for PadMapper

The next maintainer task — gated on user opt-in to live calibration:

1. Set `RENTWISE_PADMAPPER_ENABLED=true` and run a single Playwright
   render of `https://www.padmapper.com/apartments/vancouver-bc`.
2. Save the rendered HTML as
   `apps/api/tests/adapters/padmapper/fixtures/live_search.html` (use
   a 1-second-old snapshot, never auto-refresh).
3. Inspect the listing-card structure in DevTools. Update
   `padmapper/adapter.py::_extract` selectors to match the live DOM.
4. Add a regression test that loads the live fixture and asserts
   non-empty parsed listings.
5. Once tests pass, lift the scaffold note in `health_check`.

This work is intentionally **not** done in CI or by an autonomous run —
it requires live human inspection of a rendered page.
