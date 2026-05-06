# RentWise — Specifications

## 1. Vision

A self-hosted, privacy-respecting rental aggregator that lets users search across all major Vancouver rental platforms using natural language. Built for personal use first, with a clean architecture that can scale to a hosted service.

## 2. User Stories

### MVP (v0.1)

- **As a renter**, I can type "2 bedroom in Kitsilano under $3500 pet-friendly" and see results from every supported platform.
- **As a renter**, I can use traditional filter controls (bedrooms, price, neighborhood, etc.) instead of natural language if I prefer.
- **As a renter**, I can switch between NL and filter modes without losing my current search.
- **As a renter**, I can review and correct what the AI understood before running a search.
- **As a renter**, I can switch between card grid, list/table, map, and split views to find listings the way that works best for me.
- **As a renter**, I can sort results by newest, price (asc/desc), or bedrooms.
- **As a renter**, I can save, hide, or mark listings as "contacted" so I don't see the same ones over and over.
- **As a renter**, I can save searches and get notified (email/push) when new matching listings appear.
- **As a renter**, I can see a listing only once even if it's cross-posted on 3 platforms.
- **As a renter**, I can click through to the original platform to contact the landlord.

### v0.2

- **As a renter**, I can search by school catchment (e.g. "Lord Byng catchment").
- **As a renter**, I can search by transit (e.g. "10 min walk to SkyTrain").
- **As a renter**, I can mark listings as favorites / hidden / contacted.
- **As a renter**, I can see price-history and time-on-market for each listing.

### v1.0

- **As a renter**, I can use a macOS or iOS app with the same features.
- **As a renter**, I get smart alerts (e.g. "this listing is priced 15% below similar units").

## 3. Core Features

### 3.1 Search — Hybrid UX (NL + Structured Filters)

RentWise supports **two complementary search modes** that share the same underlying query model. Users can switch between them at any time, and switching never loses their filters.

#### Mode A: Natural-language search (default)
Input: free text, in English **or Korean** (both supported from day 1).

Examples:
- `"2 bedroom in Kitsilano under $3000 pet-friendly available June"`
- `"키츠에 2베드 3000불 이하 반려동물 가능 6월 입주"`

The LLM translates this into the same structured query the filter UI produces:

```json
{
  "bedrooms_min": 2,
  "price_max": 3000,
  "neighborhoods": ["Kitsilano"],
  "school_catchment": "Lord Byng",
  "pets": "any",
  "available_after": "2026-06-01"
}
```

**Implementation:** [LiteLLM](https://docs.litellm.ai/) as the abstraction layer, allowing users to pick any LLM provider. See [llm-providers.md](llm-providers.md).

#### Mode B: Conventional filter search
A traditional faceted search UI with form controls:
- Bedrooms (min/max sliders or chips: studio, 1, 2, 3, 4+)
- Price range (min/max numeric inputs + slider)
- Neighborhoods (multi-select with map picker)
- School catchment (dropdown of Vancouver schools)
- Pets (radio: required / ok / no / any)
- Furnished (yes / no / any)
- Available after (date picker)
- Walk to transit (max minutes input)
- Keywords (free-text chip list — applied as full-text search across listings)

Both modes write to and read from the **same `NormalizedQuery` object** in app state. This means:
- User types NL → sees filter chips populate → can tweak any individual filter
- User builds query with filters → can later refine with NL ("...but only newer buildings")
- Saved searches store the structured query, regardless of how it was created

#### The "Parsed Query Preview" — transparency before search
After NL input, before running the search, RentWise shows the parsed query as **editable filter chips**:

```
You said: "2 bedroom in Kits under 3000 pet ok"
                                                     [ Edit text ]
We understood:
  ┌─────────────────────────────────────────────────┐
  │ 🛏 2+ bedrooms        ❌                        │
  │ 📍 Kitsilano          ❌                        │
  │ 💰 Up to $3,000       ❌                        │
  │ 🐾 Pets OK            ❌                        │
  │ + Add filter                                     │
  └─────────────────────────────────────────────────┘

  [ Search 6 sites → ]   [ Switch to filter view ]
```

User can:
- Remove any chip with the ❌
- Add filters the LLM missed via "+ Add filter"
- Click "Switch to filter view" to see the full filter UI pre-populated
- Click "Edit text" to refine the original NL input
- Hit Search to run with whatever's currently shown

This gives users **full control** without making them learn the system, and surfaces LLM parsing errors before they hit the network.

#### Mode switching rules
| Action | What happens |
|---|---|
| Type in NL box → click parse | Filter chips update; NL text remains visible |
| Edit a chip in filter view | NL text is cleared (filters are now the source of truth) |
| Switch from filter view back to NL | NL box is empty (don't fake a sentence; they have filters now) |
| Save a search | The structured query is saved; both views can replay it |

### 3.2 Results display — multiple view modes

Results can be displayed in several views, switchable from a single toolbar. All views share the same filtered/sorted result set; switching views never re-runs the query.

#### View modes

| View | Best for | Key elements |
|---|---|---|
| **Card grid** (default) | Browsing visually | Photo, price, beds/baths, address, source badge, save/hide buttons. Responsive: 3-col desktop, 2-col tablet, 1-col mobile. |
| **List table** | Comparing many listings fast | Sortable columns: price, beds, sqft, neighborhood, posted date, source. Compact rows, photo thumbnail. Spreadsheet-like. |
| **Map** | Location-driven search | Pins clustered at low zoom, individual at high zoom. Hover/tap pin → mini card. Sidebar list synced with map viewport. |
| **Split view** | Power users | Map on left, list on right. Hovering a list row highlights its pin (and vice versa). Default on wide desktop screens. |

#### Toolbar (always visible above results)

```
┌─────────────────────────────────────────────────────────────────────┐
│ 142 listings  │ Sort: Newest ▾ │ [⊞ Cards] [☰ List] [🗺 Map] [⊟ Split] │
└─────────────────────────────────────────────────────────────────────┘
```

#### Sort options
- Newest first (default)
- Price: low → high
- Price: high → low
- Bedrooms
- Closest to a saved location (e.g., "work address" if user has set one)
- Best match (a future ranking score combining price-vs-similar, freshness, photo quality)

#### View persistence
- The chosen view is remembered per-user (in settings).
- Default view depends on screen width: split on ≥1280px desktop, card grid on tablet, list on mobile.

#### Per-card / per-row controls
Every listing, regardless of view, shows quick-action buttons:
- ❤️ Save (favorites)
- 🚫 Hide (won't appear again — useful for filtering out same-bad-listing reposts)
- 📞 Contacted (mark that you reached out — visual indicator, doesn't notify the landlord)
- 🔗 Open original (new tab to source platform)

#### Map view technical details
- Map library: **MapLibre GL JS** (open-source, no API key needed) with OpenStreetMap tiles for MVP. Mapbox optional upgrade.
- Clustering: client-side, using `supercluster`.
- Boundary overlays: school catchment polygons, SkyTrain station radii — toggleable.
- Drag-to-search: when user pans/zooms, a "Search this area" button appears (doesn't auto-search to avoid wasted calls).

#### List/table view technical details
- Virtualized rows (react-window or TanStack Virtual) so 1000+ listings stay snappy.
- Resizable columns; user's column widths and sort persist per-session.
- Column visibility toggle (e.g., hide "sqft" if it's mostly empty for the user's queries).
- Optional CSV export of current filtered view (personal use only).

### 3.3 Multi-source ingestion

Each source is implemented as an "adapter" with a uniform interface:

```python
class SourceAdapter(Protocol):
    name: str
    base_url: str
    method: Literal["api", "rss", "browser"]

    async def search(self, query: NormalizedQuery) -> list[RawListing]: ...
    async def fetch_listing(self, listing_id: str) -> RawListing: ...
```

| Source | Method | Notes |
|---|---|---|
| liv.rent | Browser (no public API) | Respects robots.txt, throttled |
| PadMapper | Browser | Respects robots.txt, throttled |
| Zumper | Browser | Respects robots.txt, throttled |
| Rentals.ca | Browser | Respects robots.txt, throttled |
| REW.ca | Browser | Respects robots.txt, throttled |
| Craigslist Vancouver | RSS | Has RSS feeds — preferred |
| Facebook Marketplace | Browser, opt-in only | See legal.md — user must auth their own session |

### 3.4 Deduplication

Listings are matched across sources by:
1. Address normalization (street + unit number)
2. Photo hashing (perceptual hash on first image)
3. Price + bedroom count + posting date proximity

A confidence score determines whether two listings are merged into one canonical record.

### 3.5 Enrichment

Once ingested, listings are enriched with:
- **School catchment** — using Vancouver School Board boundary data (public)
- **Transit** — Google Maps / Mapbox Distance Matrix to nearest SkyTrain/bus
- **Walkscore** — if free tier API available
- **Crime stats** — Vancouver Open Data (public)
- **Estimated commute** — to user's saved work address

### 3.6 Saved searches & alerts

- User can save a search query.
- Background job re-runs saved searches on a schedule (default: every 30 min).
- New matches trigger email/push notification.

## 4. Non-Functional Requirements

### 4.1 Legal & Ethical
- **Respect robots.txt** for every source.
- **Throttle requests** — never more than 1 req/sec per source, with jitter.
- **No login bypass** — for sites requiring login (e.g. Facebook Marketplace), the user must provide their own auth session via browser cookie.
- **No re-display of full listing content** — store metadata + thumbnail only; full description/photos are linked back to source.
- **User-agent honesty** — identify as RentWise/version with contact email.
- **Honor opt-out requests** — if a platform asks us to stop, we stop.
- **Personal use scope** — MVP is single-user self-hosted; commercial/hosted usage will require platform-specific permissions.

See [legal.md](legal.md) for the full policy.

### 4.2 Privacy
- All data stays on user's machine in self-hosted mode.
- No telemetry without explicit opt-in.
- LLM API calls only send the user's natural-language query, never their browsing history or saved data.
- Users who require maximum privacy can use **Ollama (local LLM)** — no data ever leaves their machine.

### 4.3 Performance
- Initial search results within 5s (cached) or 30s (live fetch from all sources).
- Background sync runs in parallel across sources.
- Local SQLite handles up to ~50k listings comfortably.

## 5. Architecture (high level)

```
┌──────────────────────────────────────────────────┐
│  Frontend (React + Expo for web/iOS/macOS)       │
└────────────────┬─────────────────────────────────┘
                 │ REST + Server-Sent Events
┌────────────────▼─────────────────────────────────┐
│  FastAPI Backend                                  │
│  ┌────────────┐  ┌─────────────┐  ┌──────────┐  │
│  │ Query      │  │ Aggregator  │  │ Notif    │  │
│  │ Translator │  │ + Dedup     │  │ Service  │  │
│  │ (Claude)   │  │             │  │          │  │
│  └────────────┘  └─────┬───────┘  └──────────┘  │
└────────────────────────┼─────────────────────────┘
                         │
       ┌─────────────────┼──────────────────┐
       │                 │                  │
┌──────▼──────┐  ┌──────▼──────┐  ┌───────▼──────┐
│ API/RSS     │  │ Playwright  │  │ Enrichment   │
│ Adapters    │  │ Browser     │  │ Adapters     │
│ (Craigslist)│  │ Adapters    │  │ (VSB, GMaps) │
└─────────────┘  └─────────────┘  └──────────────┘
                         │
                  ┌──────▼──────┐
                  │ SQLite +    │
                  │ FTS5        │
                  └─────────────┘
```

## 6. Data Model (initial draft)

```python
class Listing:
    id: UUID
    canonical_id: UUID  # for dedup grouping
    source: str  # "livrent", "padmapper", etc.
    source_url: str
    source_listing_id: str
    title: str
    address: str
    address_normalized: str
    lat: float | None
    lon: float | None
    bedrooms: float  # 0.5 = studio, 1, 1.5, etc.
    bathrooms: float
    price_cad: int
    pets_allowed: bool | None
    furnished: bool | None
    available_date: date | None
    posted_at: datetime
    last_seen_at: datetime
    photos: list[str]  # URLs to source-hosted images
    raw_metadata: dict  # source-specific extras
    # enrichment
    school_catchments: list[str]
    nearest_transit: TransitInfo | None
    walkscore: int | None
```

## 7. Out of Scope (for MVP)

- Tenant screening / application submission
- Lease signing / payment
- Landlord-side features
- Mobile app (post-v0.2)
- Multi-region (post-v1.0)
