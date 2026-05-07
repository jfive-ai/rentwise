import { z } from "zod";

export const SOURCE_IDS = [
  "rentals_ca",
  "padmapper",
  "zumper",
  "rew_ca",
  "liv_rent",
  "facebook_marketplace",
] as const;
export type SourceId = (typeof SOURCE_IDS)[number];

export const PAGE_TYPES = ["search_results", "listing_detail"] as const;
export type PageType = (typeof PAGE_TYPES)[number];

const httpUrl = z.string().url().refine((u) => /^https?:\/\//.test(u), {
  message: "must be http(s) url",
});

export const CaptureListingSchema = z.object({
  source_listing_id: z.string().min(1).max(200),
  url: httpUrl,
  title: z.string().max(500).nullish(),
  price: z.number().int().min(0).max(1_000_000).nullish(),
  bedrooms: z.number().min(0).max(20).nullish(),
  bathrooms: z.number().min(0).max(20).nullish(),
  sqft: z.number().int().min(0).max(100_000).nullish(),
  neighborhood: z.string().max(200).nullish(),
  posted_at: z.string().datetime().nullish(),
  thumbnail_url: httpUrl.nullish(),
  photo_urls: z.array(httpUrl).default([]),
  description_snippet: z.string().max(200).nullish(),
  capture_method: z.literal("extension").default("extension"),
  page_type: z.enum(PAGE_TYPES),
});
export type CaptureListing = z.infer<typeof CaptureListingSchema>;

export const CapturePayloadSchema = z.object({
  source: z.enum(SOURCE_IDS),
  captured_at: z.string().datetime(),
  page_type: z.enum(PAGE_TYPES),
  page_url: httpUrl,
  schema_version: z.string().min(1).max(64),
  listings: z.array(CaptureListingSchema).max(500),
});
export type CapturePayload = z.infer<typeof CapturePayloadSchema>;

export const CaptureHealthPayloadSchema = z.object({
  source: z.enum(SOURCE_IDS),
  schema_version: z.string().min(1).max(64),
  status: z.literal("degraded"),
  reason: z.string().min(1).max(500),
});
export type CaptureHealthPayload = z.infer<typeof CaptureHealthPayloadSchema>;

export const CaptureItemErrorSchema = z.object({
  index: z.number().int(),
  message: z.string(),
});

export const CaptureResponseSchema = z.object({
  accepted: z.number().int(),
  skipped_duplicates: z.number().int(),
  errors: z.array(CaptureItemErrorSchema).default([]),
});
export type CaptureResponse = z.infer<typeof CaptureResponseSchema>;
