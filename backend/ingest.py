"""
RepoFM — Codebase ingestion module.

Fetches a GitHub repository via the self-hosted GitIngest service,
filters out noise (node_modules, dist, vendor, lock files, etc.),
estimates token count, and truncates to fit the 256K context window.
"""

import os
import re

import httpx
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Excluded path / filename patterns
# ---------------------------------------------------------------------------
_EXCLUDED_DIR_PATTERNS = ("node_modules/", "dist/", "vendor/")
_EXCLUDED_EXT_PATTERNS = (".lock", ".min.js", ".map")

# Regex that matches a GitIngest file-section header line, e.g.:
#   ================================================
#   File: path/to/file.txt
#   ================================================
_FILE_HEADER_RE = re.compile(
    r"^={4,}\s*\n(?:File|FILE):\s*(?P<path>.+)\s*\n={4,}",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_codebase(github_url: str) -> str:
    """POST the repo URL to GitIngest and return the raw codebase text.

    GitIngest exposes a ``POST /api/ingest`` JSON endpoint that accepts
    ``input_text`` (the repo URL) and ``max_file_size`` (in KB).

    Raises ``HTTPException(502)`` on any network or service error.
    """
    gitingest_url = os.environ.get("GITINGEST_URL", "")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{gitingest_url.rstrip('/')}/api/ingest",
                json={"input_text": github_url, "max_file_size": 5120},
            )
            resp.raise_for_status()
            data = resp.json()
            # Combine tree and content for a full codebase representation
            tree = data.get("tree", "")
            content = data.get("content", "")
            return f"{tree}\n\n{content}" if tree else content
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch repository from GitIngest: {exc}",
        )


def _is_excluded_path(path: str) -> bool:
    """Return True if *path* matches any excluded directory or extension pattern."""
    for dir_pat in _EXCLUDED_DIR_PATTERNS:
        if dir_pat in path:
            return True
    for ext_pat in _EXCLUDED_EXT_PATTERNS:
        if path.endswith(ext_pat):
            return True
    return False


def filter_codebase(raw: str) -> str:
    """Remove file blocks and individual lines matching excluded patterns.

    GitIngest output uses ``====…`` / ``File: <path>`` / ``====…`` markers to
    delimit individual files.  Entire file blocks whose path matches an
    excluded pattern are dropped.  For lines outside of any file block (e.g.
    the directory tree section), individual lines containing an excluded
    pattern are removed.
    """
    # Split the raw text into sections: alternating between "outside file
    # blocks" and "file blocks".  We walk through the text and reconstruct
    # only the parts we want to keep.
    parts: list[str] = []
    last_end = 0

    for match in _FILE_HEADER_RE.finditer(raw):
        file_path = match.group("path").strip()
        header_start = match.start()

        # --- text BEFORE this file header (directory tree, preamble, etc.) ---
        between_text = raw[last_end:header_start]
        parts.append(_filter_lines(between_text))

        # --- find the end of this file block ---
        # The file content runs from the end of the header until the next
        # file header (or end-of-string).
        content_start = match.end()
        next_match = _FILE_HEADER_RE.search(raw, content_start)
        content_end = next_match.start() if next_match else len(raw)

        if not _is_excluded_path(file_path):
            # Keep the full block (header + content)
            parts.append(raw[header_start:content_end])

        last_end = content_end

    # --- any trailing text after the last file block ---
    if last_end < len(raw):
        parts.append(_filter_lines(raw[last_end:]))

    return "".join(parts)


def _filter_lines(text: str) -> str:
    """Remove individual lines that reference excluded patterns."""
    kept: list[str] = []
    for line in text.splitlines(keepends=True):
        if not _is_excluded_path(line):
            kept.append(line)
    return "".join(kept)


def estimate_tokens(text: str) -> int:
    """Rough token estimate — 1 token ≈ 4 characters."""
    return len(text) // 4


def truncate_if_needed(text: str, max_tokens: int = 256_000) -> str:
    """Return *text* unchanged if within the token budget.

    When the text exceeds *max_tokens*, retain:
    1. The file-tree / directory-listing section (everything before the first
       file block).
    2. The README file block (if present).
    3. The top 20 largest file blocks by character count.
    """
    if estimate_tokens(text) <= max_tokens:
        return text

    # --- parse into preamble + file blocks ---
    preamble, file_blocks = _parse_sections(text)

    # --- always keep README ---
    readme_blocks: list[tuple[str, str]] = []
    other_blocks: list[tuple[str, str]] = []

    for path, content in file_blocks:
        if _is_readme(path):
            readme_blocks.append((path, content))
        else:
            other_blocks.append((path, content))

    # --- top 20 largest (by character count) among the non-README blocks ---
    other_blocks.sort(key=lambda b: len(b[1]), reverse=True)
    top_blocks = other_blocks[:20]

    # --- reassemble in original order ---
    # We need to preserve the original ordering of the kept blocks.
    kept_paths = {p for p, _ in readme_blocks} | {p for p, _ in top_blocks}
    ordered_blocks = [
        (p, c) for p, c in file_blocks if p in kept_paths
    ]

    result_parts = [preamble]
    for _path, block_text in ordered_blocks:
        result_parts.append(block_text)

    return "".join(result_parts)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Split *text* into a preamble and a list of ``(path, full_block_text)`` tuples."""
    file_blocks: list[tuple[str, str]] = []
    first_match = _FILE_HEADER_RE.search(text)

    if first_match is None:
        # No file blocks at all — everything is preamble.
        return text, []

    preamble = text[: first_match.start()]
    last_end = first_match.start()

    for match in _FILE_HEADER_RE.finditer(text):
        file_path = match.group("path").strip()
        header_start = match.start()
        content_start = match.end()
        next_match = _FILE_HEADER_RE.search(text, content_start)
        content_end = next_match.start() if next_match else len(text)

        block_text = text[header_start:content_end]
        file_blocks.append((file_path, block_text))
        last_end = content_end

    # Capture any trailing text after the last block as part of the last block
    if last_end < len(text) and file_blocks:
        path, existing = file_blocks[-1]
        file_blocks[-1] = (path, existing + text[last_end:])

    return preamble, file_blocks


def _is_readme(path: str) -> bool:
    """Return True if *path* looks like a README file."""
    basename = path.rsplit("/", 1)[-1] if "/" in path else path
    return basename.upper().startswith("README")
