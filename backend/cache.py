"""
In-memory codebase cache.

Stores ingested codebase text keyed by repository URL so that
subsequent interrupt requests reuse the already-fetched content
without a second GitIngest call. Not persisted — resets on process restart.
"""

_cache: dict[str, str] = {}


def set(url: str, codebase: str) -> None:
    """Cache codebase text for a repository URL (normalized to lowercase)."""
    _cache[url.lower()] = codebase


def get(url: str) -> str | None:
    """Retrieve cached codebase text by URL (normalized to lowercase). Returns None on miss."""
    return _cache.get(url.lower())
