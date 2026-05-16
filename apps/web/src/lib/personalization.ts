// Issue #125 — bias the Match Score by what the user has saved or hidden.
//
// Personal-use tool: the profile lives entirely client-side (localStorage)
// via ListingFeatures snapshots. No server-side learning, no third-party
// recommender — completely transparent to the user, who can clear it by
// clearing the browser.
//
// Profile shape: per-feature counter of liked - disliked occurrences.
// Apply: a listing whose features overlap with the profile gets a small
// (±5) bonus on its match_score. Capped so personalization never trumps
// constraint-fit (a $9k 5BR will never be promoted past a $2k 2BR for a
// user who searched "2BR under $3000").

import type { NormalizedListing } from "@/src/api/types";
import type { ListingActions } from "@/src/storage/listingActions";
import type { ListingFeatures, SnapshotMap } from "@/src/storage/listingSnapshots";
import { listingToFeatures } from "@/src/storage/listingSnapshots";

export const MAX_BIAS = 5;

export interface Profile {
  /** weight per source name (positive = liked, negative = hidden) */
  source: Record<string, number>;
  /** weight per bedrooms-rounded-to-0.5 bucket */
  bedrooms: Record<string, number>;
  /** weight per $250 price bucket */
  price_bucket: Record<string, number>;
  /** weight per neighborhood */
  neighborhood: Record<string, number>;
  /** True when the profile has at least one signal — UI uses this to hide labels otherwise. */
  hasSignal: boolean;
}

function emptyProfile(): Profile {
  return {
    source: {},
    bedrooms: {},
    price_bucket: {},
    neighborhood: {},
    hasSignal: false,
  };
}

function bump(map: Record<string, number>, key: string | null, delta: number): void {
  if (key == null) return;
  map[key] = (map[key] ?? 0) + delta;
}

export function buildProfile(
  actions: Record<string, ListingActions>,
  snapshots: SnapshotMap,
): Profile {
  const p = emptyProfile();
  for (const [id, acts] of Object.entries(actions)) {
    const snap = snapshots[id];
    if (!snap) continue;
    const weight = acts.saved ? 1 : acts.hidden ? -1 : 0;
    if (weight === 0) continue;
    bump(p.source, snap.source, weight);
    bump(
      p.bedrooms,
      snap.bedrooms != null ? String(snap.bedrooms) : null,
      weight,
    );
    bump(
      p.price_bucket,
      snap.price_bucket != null ? String(snap.price_bucket) : null,
      weight,
    );
    bump(p.neighborhood, snap.neighborhood, weight);
    p.hasSignal = true;
  }
  return p;
}

/**
 * Compute a bias score for `listing` against `profile`. Range is roughly
 * -MAX_BIAS to +MAX_BIAS — clipped so it can never dominate the underlying
 * match score.
 */
export function bias(
  listing: NormalizedListing,
  profile: Profile,
): { delta: number; reason: "positive" | "negative" | "neutral" } {
  if (!profile.hasSignal) {
    return { delta: 0, reason: "neutral" };
  }
  const features = listingToFeatures(listing);
  let raw = 0;
  raw += profile.source[features.source] ?? 0;
  if (features.bedrooms != null) raw += profile.bedrooms[String(features.bedrooms)] ?? 0;
  if (features.price_bucket != null)
    raw += profile.price_bucket[String(features.price_bucket)] ?? 0;
  if (features.neighborhood != null)
    raw += profile.neighborhood[features.neighborhood] ?? 0;
  // Squash to [-MAX_BIAS, MAX_BIAS]. tanh-ish via clipping: 4 matched
  // feature occurrences = 1 bias point.
  const delta = Math.max(-MAX_BIAS, Math.min(MAX_BIAS, Math.round(raw / 4)));
  return {
    delta,
    reason: delta > 0 ? "positive" : delta < 0 ? "negative" : "neutral",
  };
}

/**
 * Return a copy of `listing` with its match_score nudged by the
 * personalization bias (clipped to 0-100). Also tacks a tiny extra hint
 * onto match_explanation so the user sees why a listing's score moved.
 */
export function applyBias(
  listing: NormalizedListing,
  profile: Profile,
): NormalizedListing {
  const { delta, reason } = bias(listing, profile);
  if (delta === 0) return listing;
  const base = listing.match_score ?? 0;
  const newScore = Math.max(0, Math.min(100, base + delta));
  const hint =
    reason === "positive"
      ? "like ones you've saved"
      : "like ones you've hidden";
  return {
    ...listing,
    match_score: newScore,
    match_explanation: listing.match_explanation
      ? `${listing.match_explanation} · ${hint}`
      : hint,
  };
}

/** Helper used by SearchScreen — runs `applyBias` over the whole pool. */
export function applyBiasAll(
  listings: NormalizedListing[],
  profile: Profile,
): NormalizedListing[] {
  if (!profile.hasSignal) return listings;
  return listings.map((l) => applyBias(l, profile));
}

export type { ListingFeatures };
