"""
Backend smoke tests — quick sanity checks for configuration, env validation,
and repository hygiene.

Requirements: 12.1, 12.2, 12.3, 12.4, 12.5
"""

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Repo root is two levels up from this test file (backend/tests/ → repo root)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _import_validate_env():
    """Import _validate_env from main.py without triggering the module-level call.

    main.py calls _validate_env() at module scope, which raises RuntimeError
    when env vars are missing. To test the function in isolation we need to
    either:
      a) import from an already-loaded module (if main was previously imported
         with valid env), or
      b) temporarily set all required vars so the module-level call succeeds,
         then grab the function reference.

    We use approach (b) for reliability.
    """
    required = [
        "ELEVENLABS_API_KEY",
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
        "THESYS_API_KEY",
        "GITINGEST_URL",
    ]

    if "main" in sys.modules:
        return sys.modules["main"]._validate_env

    # Temporarily set all required vars so the module-level _validate_env() passes
    saved = {var: os.environ.get(var) for var in required}
    try:
        for var in required:
            os.environ[var] = "test_placeholder"
        import main  # noqa: F811
        return main._validate_env
    finally:
        # Restore original env state
        for var, val in saved.items():
            if val is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = val


# ---------------------------------------------------------------------------
# 12.1 — VOICE_IDS has exactly 4 distinct entries
# ---------------------------------------------------------------------------

class TestVoiceIds:
    """Validates: Requirement 12.1 — unique voice per character."""

    def test_voice_ids_has_exactly_four_entries(self):
        from tts import VOICE_IDS

        assert len(VOICE_IDS) == 4, (
            f"Expected exactly 4 VOICE_IDS entries, got {len(VOICE_IDS)}"
        )

    def test_voice_ids_keys_are_the_four_characters(self):
        from tts import VOICE_IDS

        expected_keys = {"narrator", "skeptic", "fan", "intern"}
        assert set(VOICE_IDS.keys()) == expected_keys

    def test_voice_ids_values_are_distinct(self):
        from tts import VOICE_IDS

        values = list(VOICE_IDS.values())
        assert len(values) == len(set(values)), (
            "VOICE_IDS values must be distinct — each character needs a unique voice"
        )


# ---------------------------------------------------------------------------
# 12.2 — FastAPI app startup raises RuntimeError when env vars are missing
# ---------------------------------------------------------------------------

class TestEnvValidation:
    """Validates: Requirement 12.2 — fail fast on missing env vars."""

    REQUIRED_ENV_VARS = [
        "ELEVENLABS_API_KEY",
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
        "THESYS_API_KEY",
        "GITINGEST_URL",
    ]

    @pytest.fixture(autouse=True)
    def _get_validate_env(self):
        """Grab a reference to _validate_env before each test."""
        self._validate_env = _import_validate_env()

    @pytest.mark.parametrize("missing_var", REQUIRED_ENV_VARS)
    def test_validate_env_raises_on_missing_var(self, missing_var: str):
        """Removing a single required var should trigger a RuntimeError."""
        fake_env = {var: "test_value" for var in self.REQUIRED_ENV_VARS}
        fake_env.pop(missing_var)

        with patch.dict(os.environ, fake_env, clear=True):
            with pytest.raises(RuntimeError, match=missing_var):
                self._validate_env()

    def test_validate_env_passes_when_all_vars_set(self):
        """No error when every required var is present."""
        fake_env = {var: "test_value" for var in self.REQUIRED_ENV_VARS}

        with patch.dict(os.environ, fake_env, clear=True):
            # Should not raise
            self._validate_env()

    def test_validate_env_error_message_is_descriptive(self):
        """The RuntimeError message should mention the missing variable name."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError) as exc_info:
                self._validate_env()

            error_msg = str(exc_info.value)
            # Should mention at least one of the missing vars
            assert any(var in error_msg for var in self.REQUIRED_ENV_VARS), (
                f"Error message should mention missing variable names, got: {error_msg}"
            )


# ---------------------------------------------------------------------------
# 12.3 — .env.example exists and contains all required variable names
# ---------------------------------------------------------------------------

class TestEnvExample:
    """Validates: Requirement 12.3 — .env.example has all required vars."""

    REQUIRED_VARS = [
        "ELEVENLABS_API_KEY",
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
        "THESYS_API_KEY",
        "GITINGEST_URL",
    ]

    def test_env_example_file_exists(self):
        env_example = REPO_ROOT / ".env.example"
        assert env_example.exists(), f".env.example not found at {env_example}"

    def test_env_example_contains_all_required_vars(self):
        env_example = REPO_ROOT / ".env.example"
        content = env_example.read_text()

        for var in self.REQUIRED_VARS:
            assert var in content, (
                f".env.example is missing required variable: {var}"
            )


# ---------------------------------------------------------------------------
# 12.4, 12.5 — .gitignore contains .env and does NOT contain .kiro
# ---------------------------------------------------------------------------

class TestGitignore:
    """Validates: Requirements 12.4, 12.5 — .gitignore hygiene."""

    def test_gitignore_file_exists(self):
        gitignore = REPO_ROOT / ".gitignore"
        assert gitignore.exists(), f".gitignore not found at {gitignore}"

    def test_gitignore_contains_dot_env(self):
        gitignore = REPO_ROOT / ".gitignore"
        content = gitignore.read_text()

        # Check that .env appears as a standalone entry (not just as part of
        # .env.example or similar)
        lines = [line.strip() for line in content.splitlines()]
        assert ".env" in lines, (
            ".gitignore must contain '.env' as a standalone entry"
        )

    def test_gitignore_does_not_contain_kiro(self):
        gitignore = REPO_ROOT / ".gitignore"
        content = gitignore.read_text()

        # .kiro must never appear in .gitignore — the directory must be committed
        assert ".kiro" not in content, (
            ".gitignore must NOT contain '.kiro' — the .kiro/ directory must be committed"
        )
