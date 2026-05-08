# Operational rules

> **Personal-use tool.** RentWise is a single-user, locally-installed app that helps me search rentals across multiple sources. It is not a hosted service and is not distributed to other users. These rules exist so I don't accidentally hammer a site, get my IP banned, or generate enough noise to draw a complaint — *regardless* of personal-use intent.

## Hard rules every adapter follows

1. **Honor `robots.txt`.** Check at adapter init. If our path is `Disallow`'d for the wildcard or `RentWise` user-agent, the adapter aborts and reports `source_health="blocked"`.
2. **Throttle aggressively.**
   - ≤ 1 request per second per source, with 500–1500 ms random jitter.
   - ≤ 60 requests per hour per source for any background polling.
   - Exponential backoff on errors.
   - Never run parallel requests against the same source — `asyncio.Semaphore(1)` per adapter.
3. **Identify honestly.** Send a real User-Agent that names the project so a sysadmin can grep their logs and email me:
   ```
   RentWise/0.1 (+https://github.com/<user>/rentwise; contact@example.com)
   ```
4. **Store metadata, not content.**
   - ✅ Source URL, address, price, bedrooms, photo URLs (not bytes), lat/lon, posted timestamp, ≤200-char description snippet.
   - ❌ Full verbatim descriptions, downloaded photo bytes, landlord contact details, anything behind a login wall.
5. **Always link back to the source.** Every result in the UI must show the platform name and a working link to the original listing. RentWise is a *finder*, not a republisher.

## What I will never do

- Bypass paywalls or login walls.
- Solve CAPTCHAs programmatically.
- Route requests through proxies / VPNs to evade IP rate limiting.
- Submit applications, contact landlords, or take any action on the user's behalf without explicit per-action confirmation.

## If a site asks me to stop

Disable the adapter within 7 days; purge that source's cached rows within 14 days. Contact info lives in the User-Agent.

## Source notes

### Craigslist
RSS feed only — `https://vancouver.craigslist.org/search/apa?format=rss`. Never the HTML pages. Live runs require a residential connection (CL returns HTTP 403 to most datacenter ranges regardless of User-Agent); CI runs against a recorded fixture.

### Zumper (Phase 8 PR-E — scaffold, disabled by default)
TOS § 11 mirrors PadMapper § 8.4 (same parent — Zumper Inc.) and prohibits scraping. The adapter is a scaffold gated behind `RENTWISE_ZUMPER_ENABLED=true`; default is `false` and must stay `false` in shipped configs. Re-check robots.txt at adapter init (the `PlaywrightFetcher` does this automatically) before flipping the flag on for personal use. Rate ceiling 0.5 req/sec, identifying User-Agent. The current `_extract` is a stub returning `[]`; do not claim coverage of this source until real selectors land in a follow-up PR.

### REW.ca (Phase 8 PR-E — scaffold, disabled by default)
REW.ca's TOS forbids "robot, spider, or other automatic device, process, or means" *and* names "screen scraping" / "database scraping" by name — the most explicit anti-scraping language of any source we've considered. The adapter is a scaffold gated behind `RENTWISE_REW_ENABLED=true`; default is `false`. Even for personal-use, opting in here is a deliberate choice. Re-check robots.txt at adapter init. Rate ceiling 0.5 req/sec, identifying User-Agent. The current `_extract` is a stub returning `[]`. If REW.ca asks us to stop, we disable within 7 days and purge cached rows within 14 days — see "If a site asks me to stop" above.

### liv.rent (Phase 8 PR-E — scaffold, disabled by default)
liv.rent § 7.1(v)/(w) prohibits scraping/indexing/data-mining and bot use. The adapter is a scaffold gated behind `RENTWISE_LIVRENT_ENABLED=true`; default is `false`. liv.rent is a Vancouver-based startup; an explicit partnership is likely a more durable long-term path than an adversarial adapter, but that work is non-engineering and tracked separately. Re-check robots.txt at adapter init. Rate ceiling 0.5 req/sec, identifying User-Agent. The current `_extract` is a stub returning `[]`.

### Vancouver School Board / Open Data / Google Maps
- VSB catchment GeoJSON — public, attribute properly.
- Vancouver Open Data — CC-BY, attribute.
- Google Maps Distance Matrix — bring your own API key, respect Google's quotas.

### Rentals.ca
- **robots.txt:** Permissive. `User-agent: *` with `Allow: /` and a small set of `Disallow` rules: `*-feed.json`, `*-feed.xml`, and any URL with a `bbox=`, `amenities=`, or `types=` query parameter. **No `Crawl-delay`.** The adapter both consults `robots.txt` and enforces an explicit allow-list of query parameters in its URL builder so we never accidentally include a disallowed param.
- **TOS § 3.16** explicitly prohibits "computer bots, scripts, or automated tools to extract data ... unless explicitly authorized by us in writing." TOS § 3.17 prohibits using site content to train AI algorithms. The robots.txt position is more permissive than the TOS; using this adapter is a deliberate personal-use choice and the operational rules above (rate, identity, snippets-only) still apply.
- **Rate ceiling:** 0.5 req/sec with 500–1500 ms jitter, single-flight per source.
- **Opt-in env var:** `RENTWISE_RENTALSCA_ENABLED=true`. Disabled by default; the adapter is not registered in `_build_adapters` unless the flag is set. Tests use synthetic HTML fixtures only — no live rentals.ca fetches in CI.
- **Selectors:** scaffold as of 2026-05-08, calibrated against the synthetic test fixture only. The site is client-side rendered and our exploratory fetch returned HTTP 403 to the project User-Agent, so the production selectors have not yet been validated against live markup. `_extract` logs `rentalsca.selectors_not_yet_calibrated` and returns `[]` when no cards match. Do not enable in production until selectors are re-calibrated by manually inspecting a rendered page.
- **Anti-bot evasion:** none. If the site blocks the User-Agent (consecutive 403/429), `health_check` reports `blocked` and the aggregator skips the adapter. We do not rotate IPs, solve CAPTCHAs, or impersonate Chrome/Safari.

### PadMapper
- **robots.txt:** Disallows `/api`, `/backlinks`, `/external`, `/static`, `/buildings/*/cost-calculator`, `/rentals/*/cost-calculator`, and any URL with a `box=` query parameter (the map-viewport bounds). The wildcard agent IS permitted on `/rentals/...` and `/buildings/...` listing pages and on the city-scoped search index (`/apartments/vancouver-bc`). A handful of named crawlers (`ccbot`, `Yandex`, `MJ12bot`, etc.) are blocked by name; our `User-Agent` is `RentWise/...` so that block doesn't apply, but the path Disallows do.
- **TOS § 8.4** explicitly prohibits scraping. Owned by Zumper Inc. — same TOS template as Zumper. The robots.txt position is more permissive than the TOS; using this adapter is a personal-use choice and the operational rules above (rate, identity, snippets-only) still apply.
- **Rate ceiling:** 0.5 req/sec with 500–1500 ms jitter, single-flight per source.
- **Opt-in env var:** `RENTWISE_PADMAPPER_ENABLED=true`. Disabled by default; the adapter is not registered in `_build_adapters` unless the flag is set. Tests use synthetic HTML fixtures only — no live padmapper.com fetches in CI.
- The adapter both consults `robots.txt` and enforces an explicit in-process guard against the documented Disallow paths and the `box=` query parameter, because Python's `urllib.robotparser` does not parse `Disallow: /*box=*` wildcards reliably.

### Other platforms
Sources that explicitly prohibit automated access in their TOS or have anti-bot defenses I'd need to bypass to use are out of scope. If I want one of those sources, the right move is to look for an official API or partnership rather than build an adapter that fights the site.
