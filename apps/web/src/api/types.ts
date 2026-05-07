// Mirrors apps/api/rentwise/models.py — keep field names in sync.

export type PetPolicy = "required" | "ok" | "no" | "any";
export type FurnishedPolicy = "yes" | "no" | "any";
export type SortOrder = "newest" | "price_asc" | "price_desc" | "bedrooms";
export type CacheStatus = "fresh" | "stale" | "miss";

export interface NormalizedQuery {
  bedrooms_min?: number | null;
  bedrooms_max?: number | null;
  price_min?: number | null;
  price_max?: number | null;
  neighborhoods: string[];
  school_catchment?: string | null;
  pets: PetPolicy;
  furnished: FurnishedPolicy;
  available_after?: string | null; // ISO date
  transit_max_walk_minutes?: number | null;
  free_text_keywords: string[];
}

export const emptyQuery = (): NormalizedQuery => ({
  neighborhoods: [],
  pets: "any",
  furnished: "any",
  free_text_keywords: [],
});

export interface SearchRequest {
  query: NormalizedQuery;
  force_refresh?: boolean;
  limit?: number;
  offset?: number;
  sort?: SortOrder;
}

export interface SchoolCatchments {
  elementary: string | null;
  middle: string | null;
  secondary: string | null;
}

export interface TransitInfo {
  nearest_stop_name: string;
  walk_minutes: number;
  line: string | null;
}

export interface NormalizedListing {
  id: string;
  canonical_id: string;
  source: string;
  source_url: string;
  source_listing_id: string;
  title: string;
  address: string | null;
  address_normalized: string | null;
  lat: number | null;
  lon: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  price_cad: number | null;
  pets_allowed: boolean | null;
  furnished: boolean | null;
  available_date: string | null;
  posted_at: string;
  last_seen_at: string;
  photos: string[];
  description_snippet: string | null;
  school_catchments: SchoolCatchments;
  nearest_transit: TransitInfo | null;
  walkscore: number | null;
  raw_metadata: Record<string, unknown>;
}

export type AdapterHealthStatus = "ok" | "degraded" | "blocked";

export interface AdapterHealth {
  name: string;
  status: AdapterHealthStatus;
  last_successful_fetch: string | null;
  last_error: string | null;
}

export interface SearchResponse {
  listings: NormalizedListing[];
  total: number;
  cache_status: CacheStatus;
  unsupported_filters: string[];
  source_health: Record<string, AdapterHealth>;
}

export interface TranslateQueryRequest {
  text: string;
}

export interface TranslateQueryResult {
  query: NormalizedQuery;
  unsupported_filters: string[];
  lang_detected: "en" | "ko";
  model_used: string;
}

export interface LLMSettingsPublic {
  primary_model: string;
  primary_api_key_masked: string | null;
  fallback_model: string | null;
  fallback_api_key_masked: string | null;
  custom_base_url: string | null;
  timeout_seconds: number;
}

export interface LLMSettingsUpdate {
  primary_model: string;
  primary_api_key?: string | null;
  primary_api_key_clear?: boolean;
  fallback_model?: string | null;
  fallback_api_key?: string | null;
  fallback_api_key_clear?: boolean;
  custom_base_url?: string | null;
  timeout_seconds?: number;
}

export interface LLMConnectionTestRequest {
  primary_model: string;
  primary_api_key?: string | null;
  custom_base_url?: string | null;
  timeout_seconds?: number;
}

export interface LLMConnectionTestResult {
  ok: boolean;
  error: string | null;
  latency_ms: number;
  model_used: string;
}

export interface CapturePairResponse {
  token: string;
  server_url: string;
}
