"""
Tests for backend/ingest.py — filter_codebase, estimate_tokens, truncate_if_needed,
and fetch_codebase (with mocked httpx).
"""

import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio

from ingest import (
    estimate_tokens,
    fetch_codebase,
    filter_codebase,
    truncate_if_needed,
)
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers — build GitIngest-style text
# ---------------------------------------------------------------------------

def _file_block(path: str, content: str) -> str:
    """Return a single GitIngest file block."""
    return (
        f"================================================\n"
        f"File: {path}\n"
        f"================================================\n"
        f"{content}\n"
    )


def _build_codebase(preamble: str, files: list[tuple[str, str]]) -> str:
    """Build a full GitIngest-style codebase string."""
    parts = [preamble]
    for path, content in files:
        parts.append(_file_block(path, content))
    return "".join(parts)


# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------

class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_short_string(self):
        assert estimate_tokens("abcd") == 1

    def test_known_length(self):
        text = "a" * 100
        assert estimate_tokens(text) == 25

    def test_integer_division(self):
        # 7 chars → 7 // 4 = 1
        assert estimate_tokens("abcdefg") == 1


# ---------------------------------------------------------------------------
# filter_codebase
# ---------------------------------------------------------------------------

class TestFilterCodebase:
    def test_removes_node_modules_block(self):
        raw = _build_codebase("", [
            ("src/index.js", "console.log('hi')"),
            ("node_modules/lodash/index.js", "module.exports = {}"),
        ])
        result = filter_codebase(raw)
        assert "node_modules/" not in result
        assert "src/index.js" in result

    def test_removes_dist_block(self):
        raw = _build_codebase("", [
            ("src/app.py", "print('hello')"),
            ("dist/bundle.js", "minified code"),
        ])
        result = filter_codebase(raw)
        assert "dist/bundle.js" not in result
        assert "src/app.py" in result

    def test_removes_vendor_block(self):
        raw = _build_codebase("", [
            ("main.go", "package main"),
            ("vendor/lib/foo.go", "package foo"),
        ])
        result = filter_codebase(raw)
        assert "vendor/" not in result
        assert "main.go" in result

    def test_removes_lock_files(self):
        raw = _build_codebase("", [
            ("package.json", '{"name": "test"}'),
            ("package-lock.json.lock", "lock content"),
            ("yarn.lock", "yarn lock content"),
        ])
        result = filter_codebase(raw)
        assert "yarn.lock" not in result
        assert "package.json" in result

    def test_removes_min_js_files(self):
        raw = _build_codebase("", [
            ("src/app.js", "code"),
            ("lib/jquery.min.js", "minified"),
        ])
        result = filter_codebase(raw)
        assert "jquery.min.js" not in result
        assert "src/app.js" in result

    def test_removes_map_files(self):
        raw = _build_codebase("", [
            ("src/app.ts", "code"),
            ("src/app.js.map", "source map"),
        ])
        result = filter_codebase(raw)
        assert "app.js.map" not in result
        assert "src/app.ts" in result

    def test_filters_lines_in_preamble(self):
        preamble = "Directory tree:\nsrc/\nnode_modules/\nREADME.md\n"
        raw = _build_codebase(preamble, [
            ("src/main.py", "code"),
        ])
        result = filter_codebase(raw)
        assert "node_modules/" not in result
        assert "src/" in result
        assert "README.md" in result

    def test_keeps_all_clean_files(self):
        raw = _build_codebase("", [
            ("src/main.py", "print('hello')"),
            ("src/utils.py", "def helper(): pass"),
            ("README.md", "# Project"),
        ])
        result = filter_codebase(raw)
        assert "src/main.py" in result
        assert "src/utils.py" in result
        assert "README.md" in result

    def test_empty_input(self):
        assert filter_codebase("") == ""


# ---------------------------------------------------------------------------
# truncate_if_needed
# ---------------------------------------------------------------------------

class TestTruncateIfNeeded:
    def test_within_limit_returns_unchanged(self):
        text = "a" * 100
        assert truncate_if_needed(text, max_tokens=100) == text

    def test_exactly_at_limit_returns_unchanged(self):
        # 400 chars → 100 tokens, limit = 100
        text = "a" * 400
        assert truncate_if_needed(text, max_tokens=100) == text

    def test_over_limit_retains_preamble(self):
        preamble = "Directory tree:\nsrc/\nREADME.md\n"
        files = [(f"src/file{i}.py", "x" * 100) for i in range(50)]
        files.append(("README.md", "# My Project\nSome readme content"))
        raw = _build_codebase(preamble, files)

        # Use a small token limit to force truncation
        result = truncate_if_needed(raw, max_tokens=50)
        assert "Directory tree:" in result

    def test_over_limit_retains_readme(self):
        preamble = "tree:\n"
        files = [("README.md", "# Important readme content")]
        files += [(f"src/file{i}.py", "x" * 200) for i in range(50)]
        raw = _build_codebase(preamble, files)

        result = truncate_if_needed(raw, max_tokens=50)
        assert "README.md" in result
        assert "Important readme content" in result

    def test_over_limit_keeps_top_20_largest(self):
        preamble = "tree:\n"
        # Create 30 files with varying sizes
        files = []
        for i in range(30):
            size = (i + 1) * 100  # file29 is largest
            files.append((f"src/file{i:02d}.py", "x" * size))
        raw = _build_codebase(preamble, files)

        result = truncate_if_needed(raw, max_tokens=50)

        # The top 20 largest files are file10..file29
        for i in range(10, 30):
            assert f"src/file{i:02d}.py" in result

        # The 10 smallest should be dropped
        for i in range(10):
            assert f"src/file{i:02d}.py" not in result

    def test_no_file_blocks_returns_preamble(self):
        text = "Just a preamble with no file blocks\n" * 1000
        # Even if over limit, with no file blocks the whole text is preamble
        result = truncate_if_needed(text, max_tokens=1)
        assert "Just a preamble" in result


# ---------------------------------------------------------------------------
# fetch_codebase (async, mocked httpx)
# ---------------------------------------------------------------------------

class TestFetchCodebase:
    @pytest.mark.asyncio
    async def test_success(self):
        mock_response = AsyncMock()
        mock_response.text = "codebase content"
        mock_response.raise_for_status = lambda: None

        with patch.dict(os.environ, {"GITINGEST_URL": "http://fake:8000"}):
            with patch("ingest.httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.post.return_value = mock_response
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = instance

                result = await fetch_codebase("https://github.com/owner/repo")
                assert result == "codebase content"
                instance.post.assert_called_once_with(
                    "http://fake:8000",
                    json={"url": "https://github.com/owner/repo"},
                )

    @pytest.mark.asyncio
    async def test_failure_raises_502(self):
        with patch.dict(os.environ, {"GITINGEST_URL": "http://fake:8000"}):
            with patch("ingest.httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.post.side_effect = httpx.ConnectError("connection refused")
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = instance

                with pytest.raises(HTTPException) as exc_info:
                    await fetch_codebase("https://github.com/owner/repo")
                assert exc_info.value.status_code == 502
                assert "Failed to fetch repository from GitIngest" in exc_info.value.detail
