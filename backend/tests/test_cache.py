"""Unit tests for the codebase cache module."""

import cache


class TestCacheSetAndGet:
    """Tests for cache.set and cache.get."""

    def setup_method(self):
        """Clear the cache before each test."""
        cache._cache.clear()

    def test_set_then_get_returns_exact_text(self):
        cache.set("https://github.com/owner/repo", "some codebase text")
        assert cache.get("https://github.com/owner/repo") == "some codebase text"

    def test_get_missing_url_returns_none(self):
        assert cache.get("https://github.com/owner/nonexistent") is None

    def test_url_normalized_to_lowercase(self):
        cache.set("https://GitHub.com/Owner/Repo", "text")
        assert cache.get("https://github.com/owner/repo") == "text"

    def test_mixed_case_get_finds_lowercase_entry(self):
        cache.set("https://github.com/owner/repo", "text")
        assert cache.get("https://GitHub.com/Owner/Repo") == "text"

    def test_overwrite_existing_entry(self):
        cache.set("https://github.com/owner/repo", "old")
        cache.set("https://github.com/owner/repo", "new")
        assert cache.get("https://github.com/owner/repo") == "new"

    def test_different_urls_stored_independently(self):
        cache.set("https://github.com/a/b", "text_a")
        cache.set("https://github.com/c/d", "text_c")
        assert cache.get("https://github.com/a/b") == "text_a"
        assert cache.get("https://github.com/c/d") == "text_c"
