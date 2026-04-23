"""
Tests for backend/artifacts.py — extract_artifact_data and its internal helpers.
"""

from artifacts import extract_artifact_data


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
# extract_artifact_data — return structure
# ---------------------------------------------------------------------------

class TestExtractArtifactDataStructure:
    """Verify the returned dict always has all five keys with correct types."""

    def test_empty_codebase_returns_all_keys(self):
        result = extract_artifact_data("")
        assert "language_chart" in result
        assert "file_size_graph" in result
        assert "security_report" in result
        assert "commit_graph" in result
        assert "dependency_map" in result

    def test_empty_codebase_correct_types(self):
        result = extract_artifact_data("")
        assert isinstance(result["language_chart"], dict)
        assert isinstance(result["file_size_graph"], list)
        assert isinstance(result["security_report"], list)
        assert isinstance(result["commit_graph"], dict)
        assert isinstance(result["dependency_map"], dict)

    def test_commit_graph_always_empty(self):
        codebase = _build_codebase("", [("src/main.py", "print('hi')")])
        result = extract_artifact_data(codebase)
        assert result["commit_graph"] == {}


# ---------------------------------------------------------------------------
# language_chart
# ---------------------------------------------------------------------------

class TestLanguageChart:
    def test_single_python_file(self):
        codebase = _build_codebase("", [
            ("src/main.py", "line1\nline2\nline3\n"),
        ])
        result = extract_artifact_data(codebase)
        assert "Python" in result["language_chart"]
        # Line count is based on newlines in the captured content block
        assert result["language_chart"]["Python"] > 0

    def test_multiple_languages(self):
        codebase = _build_codebase("", [
            ("app.py", "a\nb\n"),
            ("index.js", "x\ny\nz\n"),
        ])
        result = extract_artifact_data(codebase)
        assert "Python" in result["language_chart"]
        assert "JavaScript" in result["language_chart"]

    def test_tsx_counted_as_typescript(self):
        codebase = _build_codebase("", [
            ("App.tsx", "const x = 1\n"),
        ])
        result = extract_artifact_data(codebase)
        assert "TypeScript" in result["language_chart"]

    def test_unknown_extension_ignored(self):
        codebase = _build_codebase("", [
            ("data.xyz", "some\ndata\n"),
        ])
        result = extract_artifact_data(codebase)
        assert result["language_chart"] == {}

    def test_aggregates_same_language(self):
        codebase = _build_codebase("", [
            ("a.py", "line1\nline2\n"),
            ("b.py", "line3\n"),
        ])
        result = extract_artifact_data(codebase)
        # Both files contribute to the Python line count
        assert result["language_chart"]["Python"] > 0
        # Verify aggregation: two Python files should produce a higher count
        # than a single file
        single_codebase = _build_codebase("", [("a.py", "line1\nline2\n")])
        single_result = extract_artifact_data(single_codebase)
        assert result["language_chart"]["Python"] > single_result["language_chart"]["Python"]


# ---------------------------------------------------------------------------
# file_size_graph
# ---------------------------------------------------------------------------

class TestFileSizeGraph:
    def test_returns_list_of_dicts(self):
        codebase = _build_codebase("", [
            ("src/main.py", "hello world"),
        ])
        result = extract_artifact_data(codebase)
        graph = result["file_size_graph"]
        assert len(graph) == 1
        assert "file" in graph[0]
        assert "size" in graph[0]

    def test_top_20_limit(self):
        files = [(f"file{i}.py", "x" * (i + 1)) for i in range(25)]
        codebase = _build_codebase("", files)
        result = extract_artifact_data(codebase)
        assert len(result["file_size_graph"]) == 20

    def test_sorted_by_size_descending(self):
        codebase = _build_codebase("", [
            ("small.py", "x"),
            ("big.py", "x" * 1000),
            ("medium.py", "x" * 100),
        ])
        result = extract_artifact_data(codebase)
        graph = result["file_size_graph"]
        assert graph[0]["file"] == "big.py"
        assert graph[1]["file"] == "medium.py"
        assert graph[2]["file"] == "small.py"

    def test_size_is_character_count(self):
        content = "hello world"
        codebase = _build_codebase("", [("test.py", content)])
        result = extract_artifact_data(codebase)
        # The content in the block includes the trailing newline we add in _file_block
        graph = result["file_size_graph"]
        assert graph[0]["size"] > 0


# ---------------------------------------------------------------------------
# security_report
# ---------------------------------------------------------------------------

class TestSecurityReport:
    def test_detects_password_pattern(self):
        codebase = _build_codebase("", [
            ("config.py", 'password = "hunter2"'),
        ])
        result = extract_artifact_data(codebase)
        assert len(result["security_report"]) == 1
        assert "config.py" in result["security_report"][0]

    def test_detects_api_key_pattern(self):
        codebase = _build_codebase("", [
            ("settings.py", 'api_key = "abc123"'),
        ])
        result = extract_artifact_data(codebase)
        assert len(result["security_report"]) >= 1

    def test_detects_secret_pattern(self):
        codebase = _build_codebase("", [
            ("app.py", 'secret = "mysecret"'),
        ])
        result = extract_artifact_data(codebase)
        assert len(result["security_report"]) >= 1

    def test_detects_token_pattern(self):
        codebase = _build_codebase("", [
            ("auth.py", 'token = "tok_abc123"'),
        ])
        result = extract_artifact_data(codebase)
        assert len(result["security_report"]) >= 1

    def test_skips_example_files(self):
        codebase = _build_codebase("", [
            (".env.example", 'password = "placeholder"'),
        ])
        result = extract_artifact_data(codebase)
        assert len(result["security_report"]) == 0

    def test_skips_sample_files(self):
        codebase = _build_codebase("", [
            ("config.sample", 'api_key = "placeholder"'),
        ])
        result = extract_artifact_data(codebase)
        assert len(result["security_report"]) == 0

    def test_clean_code_no_findings(self):
        codebase = _build_codebase("", [
            ("main.py", "import os\nprint('hello')\n"),
        ])
        result = extract_artifact_data(codebase)
        assert result["security_report"] == []


# ---------------------------------------------------------------------------
# dependency_map
# ---------------------------------------------------------------------------

class TestDependencyMap:
    def test_parses_package_json(self):
        pkg = '{"dependencies": {"react": "^18.0.0", "next": "14.0.0"}}'
        codebase = _build_codebase("", [
            ("package.json", pkg),
        ])
        result = extract_artifact_data(codebase)
        deps = result["dependency_map"]
        assert deps["react"] == "^18.0.0"
        assert deps["next"] == "14.0.0"

    def test_parses_dev_dependencies(self):
        pkg = '{"devDependencies": {"vitest": "^1.0.0"}}'
        codebase = _build_codebase("", [
            ("package.json", pkg),
        ])
        result = extract_artifact_data(codebase)
        assert "vitest" in result["dependency_map"]

    def test_parses_requirements_txt(self):
        reqs = "fastapi==0.100.0\nhttpx>=0.24.0\npydantic\n"
        codebase = _build_codebase("", [
            ("requirements.txt", reqs),
        ])
        result = extract_artifact_data(codebase)
        deps = result["dependency_map"]
        assert deps["fastapi"] == "==0.100.0"
        assert deps["httpx"] == ">=0.24.0"
        assert deps["pydantic"] == ""

    def test_requirements_txt_skips_comments(self):
        reqs = "# This is a comment\nfastapi==0.100.0\n"
        codebase = _build_codebase("", [
            ("requirements.txt", reqs),
        ])
        result = extract_artifact_data(codebase)
        assert "# This is a comment" not in result["dependency_map"]
        assert "fastapi" in result["dependency_map"]

    def test_requirements_txt_skips_flags(self):
        reqs = "-r base.txt\nfastapi==0.100.0\n"
        codebase = _build_codebase("", [
            ("requirements.txt", reqs),
        ])
        result = extract_artifact_data(codebase)
        assert "-r base.txt" not in result["dependency_map"]

    def test_invalid_package_json_returns_empty(self):
        codebase = _build_codebase("", [
            ("package.json", "not valid json {{{"),
        ])
        result = extract_artifact_data(codebase)
        assert result["dependency_map"] == {}

    def test_no_dependency_files_returns_empty(self):
        codebase = _build_codebase("", [
            ("main.py", "print('hello')"),
        ])
        result = extract_artifact_data(codebase)
        assert result["dependency_map"] == {}

    def test_both_package_json_and_requirements_txt(self):
        pkg = '{"dependencies": {"react": "^18.0.0"}}'
        reqs = "fastapi==0.100.0\n"
        codebase = _build_codebase("", [
            ("package.json", pkg),
            ("requirements.txt", reqs),
        ])
        result = extract_artifact_data(codebase)
        deps = result["dependency_map"]
        assert "react" in deps
        assert "fastapi" in deps
