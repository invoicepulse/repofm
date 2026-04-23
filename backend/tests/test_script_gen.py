"""
Tests for backend/script_gen.py — pure function unit tests and integration
tests with mocked Cloudflare API.
"""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from script_gen import (
    MAX_WORDS,
    VALID_ARTIFACTS,
    VALID_CHARACTERS,
    VIBE_PROMPTS,
    _build_system_prompt,
    _is_valid_segment,
    count_words,
    generate_answer,
    generate_script,
    validate_script,
)


# ── count_words ──────────────────────────────────────────────────────────


class TestCountWords:
    def test_empty_script(self):
        assert count_words([]) == 0

    def test_single_segment(self):
        script = [{"text": "hello world foo"}]
        assert count_words(script) == 3

    def test_multiple_segments(self):
        script = [
            {"text": "one two"},
            {"text": "three four five"},
        ]
        assert count_words(script) == 5

    def test_whitespace_only_text(self):
        script = [{"text": "   "}]
        assert count_words(script) == 0


# ── _is_valid_segment ────────────────────────────────────────────────────


class TestIsValidSegment:
    def test_valid_segment_all_fields(self):
        seg = {
            "character": "narrator",
            "text": "Hello",
            "artifact": "language_chart",
        }
        assert _is_valid_segment(seg) is True

    def test_valid_segment_null_optional_fields(self):
        seg = {
            "character": "skeptic",
            "text": "Hello",
            "artifact": None,
        }
        assert _is_valid_segment(seg) is True

    def test_invalid_character(self):
        seg = {
            "character": "villain",
            "text": "Hello",
            "artifact": None,
        }
        assert _is_valid_segment(seg) is False

    def test_invalid_artifact(self):
        seg = {
            "character": "intern",
            "text": "Hello",
            "artifact": "pie_chart",
        }
        assert _is_valid_segment(seg) is False

    def test_missing_character_key(self):
        seg = {"text": "Hello", "artifact": None}
        assert _is_valid_segment(seg) is False


# ── validate_script ──────────────────────────────────────────────────────


class TestValidateScript:
    def _make_seg(self, text="word", character="narrator", artifact=None):
        return {
            "character": character,
            "text": text,
            "artifact": artifact,
        }

    def test_empty_script(self):
        assert validate_script([]) == []

    def test_filters_invalid_segments(self):
        valid = self._make_seg(text="good")
        invalid = self._make_seg(text="bad", character="villain")
        result = validate_script([valid, invalid])
        assert len(result) == 1
        assert result[0]["text"] == "good"

    def test_truncates_to_380_words(self):
        # Each segment has 100 words → 5 segments = 500 words → should truncate
        segs = [self._make_seg(text=" ".join(["word"] * 100)) for _ in range(5)]
        result = validate_script(segs)
        assert count_words(result) <= MAX_WORDS

    def test_keeps_all_when_under_limit(self):
        segs = [self._make_seg(text="one two three") for _ in range(3)]
        result = validate_script(segs)
        assert len(result) == 3

    def test_truncation_removes_from_end(self):
        # 3 segments: 200 + 200 + 200 = 600 words → should keep first 1 (200 ≤ 380)
        segs = [
            self._make_seg(text=" ".join(["w"] * 200), character="narrator"),
            self._make_seg(text=" ".join(["w"] * 200), character="skeptic"),
            self._make_seg(text=" ".join(["w"] * 200), character="fan"),
        ]
        result = validate_script(segs)
        # After removing last → 400 > 380, remove another → 200 ≤ 380
        assert len(result) == 1
        assert result[0]["character"] == "narrator"

    def test_all_valid_artifacts_accepted(self):
        for artifact in VALID_ARTIFACTS:
            seg = self._make_seg(artifact=artifact)
            result = validate_script([seg])
            assert len(result) == 1

    def test_all_valid_characters_accepted(self):
        for char in VALID_CHARACTERS:
            seg = self._make_seg(character=char)
            result = validate_script([seg])
            assert len(result) == 1


# ── _build_system_prompt ─────────────────────────────────────────────────


class TestBuildSystemPrompt:
    def test_contains_vibe_instruction(self):
        prompt = _build_system_prompt("roast", {})
        assert "Skeptic delivers 60%+" in prompt

    def test_contains_word_limit(self):
        prompt = _build_system_prompt("deep_dive", {})
        assert "380" in prompt

    def test_contains_json_instruction(self):
        prompt = _build_system_prompt("beginner_friendly", {})
        assert "raw JSON array" in prompt

    def test_unknown_vibe_falls_back_to_deep_dive(self):
        prompt = _build_system_prompt("unknown_vibe", {})
        assert "Narrator leads" in prompt

    def test_lists_available_artifacts(self):
        data = {"language_chart": {"Python": 100}, "file_size_graph": []}
        prompt = _build_system_prompt("roast", data)
        assert "language_chart" in prompt


# ── generate_script (mocked LLM) ────────────────────────────────────────


class TestGenerateScript:
    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-account")
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-token")

    def _mock_response(self, script_data):
        """Create a mock httpx.Response returning the given script data."""
        resp = httpx.Response(
            200,
            json={"result": {"response": json.dumps(script_data)}},
            request=httpx.Request("POST", "https://example.com"),
        )
        return resp

    @pytest.mark.asyncio
    async def test_valid_response(self):
        script_data = [
            {
                "character": "narrator",
                "text": "Welcome to the show",
                "artifact": None,
            }
        ]
        mock_resp = self._mock_response(script_data)

        with patch("script_gen.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = mock_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await generate_script("code here", "roast", {})

        assert len(result) == 1
        assert result[0]["character"] == "narrator"

    @pytest.mark.asyncio
    async def test_invalid_json_raises_500(self):
        resp = httpx.Response(
            200,
            json={"result": {"response": "not valid json {{{"}},
            request=httpx.Request("POST", "https://example.com"),
        )

        with patch("script_gen.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            with pytest.raises(Exception) as exc_info:
                await generate_script("code", "roast", {})
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_non_list_json_raises_500(self):
        resp = httpx.Response(
            200,
            json={"result": {"response": '{"not": "a list"}'}},
            request=httpx.Request("POST", "https://example.com"),
        )

        with patch("script_gen.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            with pytest.raises(Exception) as exc_info:
                await generate_script("code", "deep_dive", {})
            assert exc_info.value.status_code == 500


# ── generate_answer (mocked LLM) ────────────────────────────────────────


class TestGenerateAnswer:
    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-account")
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-token")

    @pytest.mark.asyncio
    async def test_returns_answer_string(self):
        resp = httpx.Response(
            200,
            json={"result": {"response": "The repo uses Python and FastAPI."}},
            request=httpx.Request("POST", "https://example.com"),
        )

        with patch("script_gen.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            answer = await generate_answer("What language is this?", "codebase text")

        assert answer == "The repo uses Python and FastAPI."

    @pytest.mark.asyncio
    async def test_sends_both_transcript_and_codebase(self):
        resp = httpx.Response(
            200,
            json={"result": {"response": "answer"}},
            request=httpx.Request("POST", "https://example.com"),
        )

        with patch("script_gen.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            await generate_answer("my question", "my codebase")

            # Verify the POST body includes both transcript and codebase
            call_args = instance.post.call_args
            body = call_args.kwargs.get("json") or call_args[1].get("json")
            user_msg = body["messages"][1]["content"]
            assert "my question" in user_msg
            assert "my codebase" in user_msg
