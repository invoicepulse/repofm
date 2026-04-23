"""Unit tests for the RateLimiter class."""

import time

import pytest

from rate_limit import RateLimiter, RateLimitExceeded


class TestRateLimiterCheck:
    """Tests for RateLimiter.check — verifies 429 is raised at the threshold."""

    def test_allows_requests_under_limit(self) -> None:
        rl = RateLimiter(max_requests=3, window_seconds=3600)
        ip = "10.0.0.1"
        for _ in range(3):
            rl.check(ip)  # should not raise
            rl.record(ip)

    def test_blocks_at_limit(self) -> None:
        rl = RateLimiter(max_requests=3, window_seconds=3600)
        ip = "10.0.0.1"
        for _ in range(3):
            rl.check(ip)
            rl.record(ip)
        with pytest.raises(RateLimitExceeded) as exc_info:
            rl.check(ip)
        assert exc_info.value.status_code == 429
        assert exc_info.value.reset_at is not None
        assert "Rate limit exceeded" in exc_info.value.detail

    def test_different_ips_are_independent(self) -> None:
        rl = RateLimiter(max_requests=1, window_seconds=3600)
        rl.check("a")
        rl.record("a")
        # "a" is now at the limit
        with pytest.raises(RateLimitExceeded):
            rl.check("a")
        # "b" should still be fine
        rl.check("b")

    def test_reset_at_is_iso_format(self) -> None:
        rl = RateLimiter(max_requests=1, window_seconds=60)
        rl.check("x")
        rl.record("x")
        with pytest.raises(RateLimitExceeded) as exc_info:
            rl.check("x")
        # ISO 8601 contains a "T" separator and ends with timezone info
        assert "T" in exc_info.value.reset_at


class TestRateLimiterRecord:
    """Tests for RateLimiter.record — verifies pruning of stale entries."""

    def test_prunes_old_entries(self) -> None:
        rl = RateLimiter(max_requests=3, window_seconds=10)
        ip = "10.0.0.1"
        # Manually inject old timestamps
        old_time = time.time() - 20  # 20 seconds ago, well outside the 10s window
        rl._requests[ip] = [old_time, old_time + 1, old_time + 2]
        # record should prune the old entries and add a new one
        rl.record(ip)
        assert len(rl._requests[ip]) == 1

    def test_record_appends_timestamp(self) -> None:
        rl = RateLimiter()
        rl.record("ip1")
        assert len(rl._requests["ip1"]) == 1
        rl.record("ip1")
        assert len(rl._requests["ip1"]) == 2
