/**
 * Shared content-script utilities. Pure functions where possible so the
 * per-site scripts are testable in jsdom without the chrome.runtime stub.
 *
 * Per `docs/legal.md`: snippets are capped at 200 chars, photo URLs are
 * stored but bytes are not, no contact info. The cap is enforced at the
 * schema layer too — this keeps the over-the-wire payload small.
 */

const SNIPPET_MAX = 200;

export function text(node: Element | null | undefined): string | null {
  if (!node) return null;
  const t = (node.textContent ?? "").trim();
  return t.length === 0 ? null : t;
}

export function attr(node: Element | null | undefined, name: string): string | null {
  if (!node) return null;
  const v = node.getAttribute(name);
  if (v === null) return null;
  const t = v.trim();
  return t.length === 0 ? null : t;
}

export function snippet(s: string | null | undefined): string | null {
  if (!s) return null;
  const trimmed = s.trim();
  if (trimmed.length === 0) return null;
  return trimmed.length > SNIPPET_MAX ? trimmed.slice(0, SNIPPET_MAX) : trimmed;
}

export function parsePrice(raw: string | null | undefined): number | null {
  if (!raw) return null;
  // Strip currency, commas, spaces, "/mo" suffix.
  const m = raw.replace(/,/g, "").match(/(\d+(?:\.\d+)?)/);
  if (!m) return null;
  const n = Number(m[1]);
  if (!Number.isFinite(n) || n < 0) return null;
  return Math.round(n);
}

export function parseBedrooms(raw: string | null | undefined): number | null {
  if (!raw) return null;
  const lower = raw.toLowerCase();
  if (lower.includes("studio") || lower.includes("bachelor")) return 0;
  const m = lower.match(/(\d+(?:\.\d+)?)\s*(?:bed|br|bd)/);
  if (m) {
    const n = Number(m[1]);
    return Number.isFinite(n) ? n : null;
  }
  // "2 + 1 den" style — fall back to first integer.
  const num = lower.match(/(\d+(?:\.\d+)?)/);
  if (num) {
    const n = Number(num[1]);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

export function parseBathrooms(raw: string | null | undefined): number | null {
  if (!raw) return null;
  const m = raw.toLowerCase().match(/(\d+(?:\.\d+)?)\s*(?:bath|ba)/);
  if (!m) return null;
  const n = Number(m[1]);
  return Number.isFinite(n) ? n : null;
}

export function parseSqft(raw: string | null | undefined): number | null {
  if (!raw) return null;
  const m = raw.replace(/,/g, "").match(/(\d+)\s*(?:sq\s*ft|sqft|sf)/i);
  if (!m) return null;
  const n = Number(m[1]);
  return Number.isFinite(n) ? n : null;
}

export function absoluteUrl(href: string | null | undefined, base: string): string | null {
  if (!href) return null;
  try {
    return new URL(href, base).toString();
  } catch {
    return null;
  }
}

/**
 * In-tab idempotency cache. The same SPA can re-render the same listing
 * cards multiple times as the user filters or paginates. We dedupe by
 * source_listing_id so we don't spam /capture.
 *
 * Server-side upsert is the source of truth — this just keeps traffic clean.
 */
export class SeenCache {
  private readonly seen = new Set<string>();

  has(id: string): boolean {
    return this.seen.has(id);
  }

  /** Add the id; return true if it was new. */
  add(id: string): boolean {
    if (this.seen.has(id)) return false;
    this.seen.add(id);
    return true;
  }

  /** Filter a list of ids to only the previously-unseen ones, marking them seen. */
  filterNew<T extends { source_listing_id: string }>(items: T[]): T[] {
    const out: T[] = [];
    for (const item of items) {
      if (this.add(item.source_listing_id)) out.push(item);
    }
    return out;
  }
}

/**
 * A small in-page banner shown after a successful capture. Auto-hides.
 * Caller is responsible for not double-mounting; we no-op if an existing
 * banner is already on the page.
 */
export function showBanner(message: string, ttlMs = 3000): void {
  const id = "rentwise-banner";
  if (document.getElementById(id)) return;
  const el = document.createElement("div");
  el.id = id;
  el.textContent = message;
  el.style.cssText = [
    "position:fixed",
    "bottom:16px",
    "right:16px",
    "z-index:2147483647",
    "background:rgba(20,20,20,0.92)",
    "color:#fff",
    "font:13px/1.4 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
    "padding:8px 12px",
    "border-radius:6px",
    "box-shadow:0 2px 8px rgba(0,0,0,0.3)",
    "pointer-events:none",
  ].join(";");
  document.body.appendChild(el);
  setTimeout(() => el.remove(), ttlMs);
}
