# RentWise Capture Extension

Browser extension that reads listing data from rental sites the user
already visits in their own browser session, and sends it to the user's
local RentWise API. **No background fetch, no automated navigation, no
login automation** — it is a passive reader of pages the user causes
the browser to load.

See `docs/superpowers/specs/2026-05-07-phase-3-launcher-extension-design.md`
for the full design and `docs/operational-rules.md` for the rate-limit / scraping rules every capture path follows.

## Sites covered

- Rentals.ca
- PadMapper
- Zumper
- REW.ca
- liv.rent
- Facebook Marketplace

The "Search across sources" launcher button lives in the RentWise web
app's filter panel — it opens one tab per enabled source and the
content scripts capture as the user lets each tab finish loading.

## Build

```bash
cd apps/extension
npm install
npm run build      # produces dist/
npm test           # vitest + jsdom
npm run typecheck
```

## Sideload (Chrome / Brave / Edge)

1. Build with `npm run build`.
2. Open `chrome://extensions` and enable **Developer mode** (top right).
3. Click **Load unpacked** → choose `apps/extension/dist`.
4. Click the puzzle icon → pin **RentWise Capture**.
5. Open the extension's **Settings** (right-click the icon → Options).
6. Open RentWise → **Settings → Extension**, copy the token + server URL
   into the extension's options page, click **Save & validate**.

## How it works

1. The extension's content script for a site runs at `document_idle`
   only on URLs that match the site's listing-related path patterns.
2. It reads the rendered DOM into a `CapturePayload` and hands it to
   the background service worker.
3. The background worker `POST`s to `http://127.0.0.1:8000/capture`
   (or whatever `serverUrl` you paired) with the shared-secret header.
4. The local FastAPI upserts the listings into your local SQLite.

The content script never originates network requests to source domains
and never reads cookies, tokens, or login state. Content scripts also
maintain an in-tab idempotency cache so SPA re-renders don't spam the
local API.

## Selector schema versioning

Each site has a `SCHEMA_VERSION` constant alongside its `SELECTORS`
table (`src/content/sites/<site>.ts`). When a required selector returns
no nodes on a page that should have it, the script:

1. Logs to the extension console with the schema version.
2. Sends a `degraded` ping to `/capture/health`.
3. The popup shows "⚠️ Selectors broken" for that site.

When you update selectors, bump the version and update the saved
fixture under `tests/fixtures/<site>/`. Tests should still pass.

## Fixture refresh

The fixtures under `tests/fixtures/` are **synthetic** — hand-authored
HTML matching the documented selector shape. They are **not** verbatim
captures of live pages.

To refresh against production:

1. In your normal browser, navigate to the relevant page on the live
   site (the same way a user would).
2. Use **View Source** (or DevTools → Elements → Copy outerHTML on
   `<html>`) to save a snapshot to `tests/fixtures/<site>/<page>.html`.
3. Trim secrets, ad payloads, and inline scripts — the tests only need
   the listing markup. Keep the file under a few hundred KB.
4. Run `npm test` and update `SELECTORS` until tests pass.

This is a manual maintainer task, not an automated job — RentWise does
not auto-fetch source pages.

## What is **never** captured

Per `docs/operational-rules.md`:

- Photo bytes (URLs only)
- Verbatim listing descriptions in full (≤200 char snippet only)
- Landlord contact details beyond the source URL
- Any data behind a login wall
- Any per-user PII

## Distribution

Sideload-only for the MVP. Chrome Web Store distribution is on the
roadmap once the launcher and remaining sites land in PR-C.
