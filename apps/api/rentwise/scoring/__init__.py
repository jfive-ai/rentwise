"""Scoring package — listing-level signals layered on top of the aggregator.

Currently ships:

- :mod:`rentwise.scoring.match` — deterministic 0-100 Match Score that
  ranks a normalized listing against a NormalizedQuery, plus a short
  human-readable "why matched" explanation. No live LLM dependency.
"""
