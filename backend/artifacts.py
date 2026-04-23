"""
RepoFM — Artifact data extraction module.

Parses the ingested codebase text (GitIngest format) to produce data
payloads for the five artifact types rendered by the frontend via
Thesys C1.  All extraction is purely text-based — no external API
calls are made.
"""

import json
import os
import re

# ---------------------------------------------------------------------------
# GitIngest file-section header (same pattern used in ingest.py)
# ---------------------------------------------------------------------------
_FILE_HEADER_RE = re.compile(
    r"^={4,}\s*\n(?:File|FILE):\s*(?P<path>.+)\s*\n={4,}",
    re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Extension → language mapping
# ---------------------------------------------------------------------------
_EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".java": "Java",
    ".rb": "Ruby",
    ".go": "Go",
    ".rs": "Rust",
    ".c": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".h": "C",
    ".hpp": "C++",
    ".cs": "C#",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".php": "PHP",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".less": "Less",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".xml": "XML",
    ".md": "Markdown",
    ".sh": "Shell",
    ".bash": "Shell",
    ".sql": "SQL",
    ".r": "R",
    ".lua": "Lua",
    ".dart": "Dart",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".toml": "TOML",
    ".ini": "INI",
    ".cfg": "INI",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hs": "Haskell",
    ".scala": "Scala",
    ".pl": "Perl",
    ".pm": "Perl",
}

# ---------------------------------------------------------------------------
# Security scan patterns
# ---------------------------------------------------------------------------
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"password\s*=\s*[\"']?.+", re.IGNORECASE),
    re.compile(r"api_key\s*=\s*[\"']?.+", re.IGNORECASE),
    re.compile(r"secret\s*=\s*[\"']?.+", re.IGNORECASE),
    re.compile(r"token\s*=\s*[\"']?.+", re.IGNORECASE),
]

# File paths that are expected to contain placeholder secrets and should
# be excluded from the security report.
_EXAMPLE_FILE_PATTERNS = (".example", ".sample", ".template", "example.")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_file_blocks(codebase: str) -> list[tuple[str, str]]:
    """Split *codebase* into ``(file_path, content)`` tuples.

    Uses the GitIngest ``====`` / ``File: <path>`` / ``====`` markers.
    """
    blocks: list[tuple[str, str]] = []

    matches = list(_FILE_HEADER_RE.finditer(codebase))
    for idx, match in enumerate(matches):
        file_path = match.group("path").strip()
        content_start = match.end()
        content_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(codebase)
        content = codebase[content_start:content_end]
        blocks.append((file_path, content))

    return blocks


def _get_extension(path: str) -> str:
    """Return the lowercase file extension including the dot, e.g. ``.py``."""
    _, ext = os.path.splitext(path)
    return ext.lower()


def _is_example_file(path: str) -> bool:
    """Return True if *path* looks like an example/template file."""
    lower = path.lower()
    return any(pat in lower for pat in _EXAMPLE_FILE_PATTERNS)


def _extract_language_chart(blocks: list[tuple[str, str]]) -> dict[str, int]:
    """Build ``{language: line_count}`` by scanning file extensions."""
    chart: dict[str, int] = {}
    for path, content in blocks:
        ext = _get_extension(path)
        language = _EXT_TO_LANGUAGE.get(ext)
        if language is None:
            continue
        line_count = content.count("\n")
        chart[language] = chart.get(language, 0) + line_count
    return chart


def _extract_file_size_graph(blocks: list[tuple[str, str]]) -> list[dict[str, object]]:
    """Return the top 20 largest files by character count."""
    sized = [{"file": path, "size": len(content)} for path, content in blocks]
    sized.sort(key=lambda d: d["size"], reverse=True)
    return sized[:20]


def _extract_security_report(blocks: list[tuple[str, str]]) -> list[str]:
    """Scan for suspicious patterns in non-example files."""
    findings: list[str] = []
    for path, content in blocks:
        if _is_example_file(path):
            continue
        for line_num, line in enumerate(content.splitlines(), start=1):
            for pattern in _SECRET_PATTERNS:
                if pattern.search(line):
                    snippet = line.strip()[:120]
                    findings.append(f"{path}:{line_num} — {snippet}")
                    break  # one finding per line is enough
    return findings


def _extract_dependency_map(blocks: list[tuple[str, str]]) -> dict[str, str]:
    """Parse ``package.json`` or ``requirements.txt`` for dependencies."""
    deps: dict[str, str] = {}

    for path, content in blocks:
        basename = path.rsplit("/", 1)[-1] if "/" in path else path

        if basename == "package.json":
            deps.update(_parse_package_json(content))

        if basename == "requirements.txt":
            deps.update(_parse_requirements_txt(content))

    return deps


def _parse_package_json(content: str) -> dict[str, str]:
    """Extract dependencies from a ``package.json`` file body."""
    deps: dict[str, str] = {}
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return deps

    for key in ("dependencies", "devDependencies"):
        section = data.get(key)
        if isinstance(section, dict):
            for name, version in section.items():
                if isinstance(name, str) and isinstance(version, str):
                    deps[name] = version
    return deps


def _parse_requirements_txt(content: str) -> dict[str, str]:
    """Extract packages from a ``requirements.txt`` file body."""
    deps: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Handle ==, >=, ~=, <=, != version specifiers
        for sep in ("==", ">=", "~=", "<=", "!="):
            if sep in line:
                name, version = line.split(sep, 1)
                deps[name.strip()] = f"{sep}{version.strip()}"
                break
        else:
            # No version specifier — record with empty version
            deps[line] = ""
    return deps


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_artifact_data(codebase: str) -> dict:
    """Parse the codebase text to extract data payloads for all artifact types."""
    blocks = _parse_file_blocks(codebase)

    # Project structure: count files by type
    structure: dict[str, int] = {}
    for path, _ in blocks:
        ext = _get_extension(path)
        if ext:
            structure[ext] = structure.get(ext, 0) + 1
        else:
            structure["(no ext)"] = structure.get("(no ext)", 0) + 1

    return {
        "language_chart": _extract_language_chart(blocks),
        "file_size_graph": _extract_file_size_graph(blocks),
        "security_report": _extract_security_report(blocks),
        "project_structure": {
            "total_files": len(blocks),
            "file_types": dict(sorted(structure.items(), key=lambda x: x[1], reverse=True)[:10]),
        },
    }
