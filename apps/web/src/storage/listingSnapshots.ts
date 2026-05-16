// Issue #125 — listing-feature snapshots so personalization can read
// "what kind of listing did the user save/hide?" later, without re-
// hydrating the listings themselves from the API.
//
// Only stores the features the bias function uses: source, bedrooms,
// price_cad rounded into a bucket, and neighborhood. Capped at 200 rows
// so localStorage stays small.

import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import type { NormalizedListing } from "@/src/api/types";

const KEY = "rentwise.listingSnapshots.v1";
const MAX_ROWS = 200;

export interface ListingFeatures {
  source: string;
  bedrooms: number | null;
  /** Price rounded to nearest $250 bucket; null if no price. */
  price_bucket: number | null;
  neighborhood: string | null;
}

export type SnapshotMap = Record<string, ListingFeatures>;

interface StorageBackend {
  getItem(k: string): Promise<string | null>;
  setItem(k: string, v: string): Promise<void>;
}

function backend(): StorageBackend {
  if (Platform.OS === "web") {
    return {
      async getItem(k) {
        return window.localStorage.getItem(k);
      },
      async setItem(k, v) {
        window.localStorage.setItem(k, v);
      },
    };
  }
  return {
    async getItem(k) {
      return AsyncStorage.getItem(k);
    },
    async setItem(k, v) {
      await AsyncStorage.setItem(k, v);
    },
  };
}

export function listingToFeatures(l: NormalizedListing): ListingFeatures {
  return {
    source: l.source,
    bedrooms: l.bedrooms,
    price_bucket: l.price_cad == null ? null : Math.round(l.price_cad / 250) * 250,
    neighborhood: l.neighborhood ?? null,
  };
}

export async function loadSnapshots(): Promise<SnapshotMap> {
  const raw = await backend().getItem(KEY);
  if (!raw) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as SnapshotMap;
    }
    return {};
  } catch {
    return {};
  }
}

export async function rememberSnapshot(
  listingId: string,
  listing: NormalizedListing,
): Promise<void> {
  const all = await loadSnapshots();
  all[listingId] = listingToFeatures(listing);
  // Cap by dropping oldest keys when over the limit. We don't carry
  // timestamps yet; for v1 the dictionary insertion order is stable
  // enough since browsers preserve it.
  const keys = Object.keys(all);
  if (keys.length > MAX_ROWS) {
    const drop = keys.slice(0, keys.length - MAX_ROWS);
    for (const k of drop) delete all[k];
  }
  await backend().setItem(KEY, JSON.stringify(all));
}
