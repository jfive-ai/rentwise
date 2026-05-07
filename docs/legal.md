# Legal & Ethics Policy

> **This is the most important document in the project.** Do not skip it.

RentWise aggregates publicly visible rental listings from third-party platforms. To do this responsibly and legally, we follow strict rules.

## ⚠️ Important: This is not legal advice

I'm not a lawyer. This document reflects best-effort, good-faith principles. Before going beyond personal/MVP use (especially before hosting RentWise as a service for others), you should consult a lawyer in your jurisdiction.

## Core Principles

### 1. Respect `robots.txt`
Every adapter must check the platform's `robots.txt` before scraping. If a path is disallowed for our user agent, we don't fetch it. Period.

### 2. Throttle aggressively
- **Maximum 1 request per second per source**, with random jitter (500-1500ms).
- **Maximum 60 requests per hour per source** for background sync.
- Use exponential backoff on errors.
- Never run parallel requests against the same source.

### 3. Identify ourselves honestly
User-Agent string:
```
RentWise/0.1 (+https://github.com/<user>/rentwise; contact@example.com)
```
This lets platforms identify and contact us if there's a problem.

### 4. Store only metadata, link to source
We store:
- ✅ Address, price, bedrooms, photos URLs (not the photo bytes)
- ✅ A short title and a 200-character snippet of the description
- ✅ Listing URL on the source platform

We do **not** store:
- ❌ Full listing descriptions (verbatim copies)
- ❌ Downloaded copies of photos
- ❌ Landlord contact info beyond what's needed to link back
- ❌ Anything behind a login wall (without explicit user consent — see Facebook section)

### 5. Honor opt-out requests
If any platform contacts us asking to stop, we add them to a blocklist and remove cached data within 7 days. Contact info is in the User-Agent.

### 6. No commercial use without permission
The MVP is **single-user, self-hosted, personal use only**. If/when we host RentWise as a service for others, we must:
- Reach out to each platform for permission or use their official API if one becomes available
- Implement per-user rate limits
- Get a legal review

## Per-Platform Notes

### liv.rent, PadMapper, Zumper, REW.ca
Public listings, no login required to view. Standard rules above apply. Check each site's Terms of Service before adding the adapter — TOS may explicitly prohibit scraping. If it does, we either:
1. Skip that source, OR
2. Implement a "user-driven" mode where the user opens their browser, RentWise watches the page they're on, and extracts info only from pages the user visited (this is closer to a personal browsing assistant than scraping).

### PadMapper (verified 2026-05-07)

**Operator:** PadMapper Inc. (owned by Zumper Inc. since 2017).

**robots.txt:** Disallows `/api`, `/backlinks`, `/external`, `/padmapper-account`, `/static`, `/buildings/*/cost-calculator`, `/rentals/*/cost-calculator`, and any URL with `box=` query params. The public `/rentals/...` and `/buildings/...` listing pages are not disallowed for the wildcard user-agent. Several known crawlers are blocked by name (`ccbot`, `Yandex`, `MJ12bot`, `DataForSeoBot`, `Neevabot`, `archive.org_bot`, etc.).

**Terms of Service:** https://www.padmapper.com/tos (effective 2021-05-27)

**Decision: PROHIBITED.** Section 8.4 forbids scraping verbatim:

> **8.4** Not harvest or otherwise collect any data, information or Site Content from the Website, including by using manual or automated software, devices, or other processes to "crawl", "scrape" or "spider" any page of the Website or Services to copy, obtain, propagate, distribute or misappropriate any User Data or Site Content

Section 5 limits user license to "reasonable limited quantities for your personal, non-commercial use" and forbids redistribution. Section 8.5 prohibits any conduct that interferes with the service.

Permissive listing-page paths in `robots.txt` do **not** override the TOS prohibition. **No PadMapper adapter** is implemented. Because PadMapper is owned by Zumper, the Zumper TOS likely contains the same clause; verify before any Zumper work.

### Rentals.ca (verified 2026-05-06)

**robots.txt:** Permissive. `Allow: /` with disallows only on `*-feed.json`, `*-feed.xml`, and pages with `bbox=`, `amenities=`, `types=` query params. No `Crawl-delay`.

**Terms of Use:** https://rentals.ca/terms

**Decision: PROHIBITED.** The TOS explicitly forbids automated/AI extraction. Verbatim, from Section 3:

> **3.16 Automated Data Extraction.** Using computer bots, scripts, or automated tools to extract data or overload the computer systems, unless explicitly authorized by us in writing.
>
> **3.17 Use of Content for AI Algorithms.** Using images and other content from the Website to train artificial intelligence algorithms or to generate new images or content via such algorithms.

Section 4.1 reserves the right to suspend access without notice on detection. Section 7.8 commits to "vigorously enforce" IP rights via injunctive relief.

Permissive robots.txt does **not** override an explicit TOS prohibition. **No Rentals.ca adapter** is implemented. If a future user-driven mode (browser extension watching pages the user visits in their own browser) is built, that may sit outside the TOS prohibition because the user — not RentWise — is the one fetching the page; revisit then.

### Craigslist
- Has RSS feeds — **always prefer RSS over HTML scraping**.
- Craigslist has historically been litigious about scraping. Their TOS prohibits it.
- ✅ RSS feeds are explicitly provided for syndication and are safe.
- ❌ Do not scrape HTML pages.

**As implemented (2026-05-06):**
- We fetch only `https://vancouver.craigslist.org/search/apa?format=rss` (and the same with filter params). HTML pages are never fetched.
- Rate: 1 req/sec with 500–1500ms jitter. `asyncio.Semaphore(1)` enforces serialization.
- robots.txt is checked at adapter init and re-checked on each restart; a `Disallow` for `/search` aborts the search and surfaces `source_health="blocked"`.
- We store: source URL, title, posted timestamp, lat/lon (when present), price (parsed from title), bedrooms (parsed from title), 200-char snippet of the description.
- We do not store: full descriptions, photo bytes, contact info.
- **Note:** Craigslist returns HTTP 403 to requests from many datacenter / cloud IP ranges regardless of User-Agent. The adapter handles this gracefully (`health_check()` reports `blocked`); end-to-end correctness is verified via a recorded RSS fixture in CI. Live runs require a residential connection.

### Facebook Marketplace
**This is the riskiest source.** Facebook's TOS explicitly prohibits automated access.

Approach:
- ❌ **Do not** automate login.
- ❌ **Do not** scrape Facebook from a server.
- ✅ **Browser extension model** — the user installs a browser extension that runs *in their own browser session* while they're already logged in and browsing Marketplace. The extension extracts listings from pages they personally view.
- This is similar to how many price-tracking extensions work, and keeps the action in the user's own session.
- Even with this, document the risk clearly to users.

### Google Maps / VSB / Open Data
- Google Maps Distance Matrix API: use the official API with your own key, respect quotas.
- Vancouver School Board boundaries: public data, attribute properly.
- Vancouver Open Data: CC-BY licensed, attribute.

## Copyright & Reuse

When we display listings to the user, we:
- Show the platform's own thumbnail (hotlinked, not re-hosted)
- Show our own normalized fields (price, beds, etc.)
- Show a short snippet of the description (≤200 chars, like a search engine result)
- Always show the source platform name and a clear link to the original listing

This is similar to how Google Search displays results, and falls within fair use / fair dealing for personal-search purposes. It is **not** a substitute for the original listing — we always send the user back to the source.

## What We Will Never Do

- Bypass paywalls or login walls without explicit user consent and the user's own credentials
- Solve CAPTCHAs programmatically
- Use proxies/VPNs to evade IP rate limiting
- Re-display full listing content as if it were our own
- Sell or share scraped data with third parties
- Submit applications, send messages, or otherwise act on behalf of users without explicit per-action confirmation

## If a Platform Asks Us to Stop

Email: `contact@example.com` (set this up before launch)
Response time goal: 48 hours.
We will:
1. Acknowledge the request
2. Disable the relevant adapter within 7 days
3. Purge cached data from that source within 14 days
4. Add the platform to our public blocklist with a brief note
