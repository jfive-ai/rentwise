"""Typed exceptions for the LLM layer.

Callers (FastAPI handlers) map these to HTTP responses. Keeping them as a
shallow hierarchy makes `except LLMError` a one-liner at the boundary.
"""

from __future__ import annotations


class LLMError(Exception):
    """Base for any LLM-layer failure that should surface to the API caller."""


class LLMTransportError(LLMError):
    """Network / provider error from LiteLLM (after fallback exhausted)."""


class LLMMalformedResponse(LLMError):  # noqa: N818
    """Provider returned no tool call or arguments that can't be parsed."""
