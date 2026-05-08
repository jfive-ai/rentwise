"""Phase 4 enrichment: address normalization, geocoding, and (in PR-B) school/transit lookups.

Modules:
- address: pyap-based address normalizer with a Vancouver-flavored
  preprocessor + canonical-key generator (used by dedup in PR-C).
- geocode: async Nominatim client + DB-cached lookups.
- service: orchestrates the pipeline for one NormalizedListing.
"""
