/**
 * Thin wrapper around chrome.storage.local. Centralized so the same
 * shape is used by background, popup, options, and content scripts.
 *
 * Per-source toggles default to `true` — installation enables capture on
 * any host the manifest already grants. The user can opt out per source
 * from the popup.
 */

import type { SourceId } from "@/schemas/capture";

export type Pairing = {
  token: string;
  serverUrl: string; // e.g. "http://127.0.0.1:8000"
};

export type SiteHealth = {
  status: "ok" | "degraded";
  schemaVersion: string;
  reason?: string;
  at: number; // epoch ms
};

export type CapturedToday = {
  date: string; // YYYY-MM-DD
  bySite: Partial<Record<SourceId, number>>;
};

export type StorageShape = {
  pairing?: Pairing;
  enabledSites: Partial<Record<SourceId, boolean>>;
  health: Partial<Record<SourceId, SiteHealth>>;
  capturedToday: CapturedToday;
};

const DEFAULTS: StorageShape = {
  enabledSites: {},
  health: {},
  capturedToday: { date: "", bySite: {} },
};

export async function getAll(): Promise<StorageShape> {
  const out = await chrome.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...out } as StorageShape;
}

export async function getPairing(): Promise<Pairing | undefined> {
  const { pairing } = await chrome.storage.local.get({ pairing: undefined });
  return pairing;
}

export async function setPairing(p: Pairing): Promise<void> {
  await chrome.storage.local.set({ pairing: p });
}

export async function clearPairing(): Promise<void> {
  await chrome.storage.local.remove("pairing");
}

export async function isSiteEnabled(source: SourceId): Promise<boolean> {
  const { enabledSites } = await chrome.storage.local.get({ enabledSites: {} });
  // default-on if the user has not explicitly toggled
  return enabledSites[source] !== false;
}

export async function setSiteEnabled(source: SourceId, enabled: boolean): Promise<void> {
  const { enabledSites } = await chrome.storage.local.get({ enabledSites: {} });
  enabledSites[source] = enabled;
  await chrome.storage.local.set({ enabledSites });
}

export async function setSiteHealth(source: SourceId, health: SiteHealth): Promise<void> {
  const { health: cur } = await chrome.storage.local.get({ health: {} });
  cur[source] = health;
  await chrome.storage.local.set({ health: cur });
}

function todayKey(): string {
  const d = new Date();
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(
    d.getUTCDate(),
  ).padStart(2, "0")}`;
}

export async function bumpCapturedToday(source: SourceId, n: number): Promise<void> {
  const { capturedToday } = await chrome.storage.local.get({
    capturedToday: { date: "", bySite: {} } as CapturedToday,
  });
  const key = todayKey();
  const next: CapturedToday =
    capturedToday.date === key
      ? capturedToday
      : { date: key, bySite: {} };
  next.bySite[source] = (next.bySite[source] ?? 0) + n;
  await chrome.storage.local.set({ capturedToday: next });
}
