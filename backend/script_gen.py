"""
RepoFM — Script generation module.

Generates multi-character podcast scripts via Groq (Llama 3.3 70B)
and validates the output. Falls back to Cloudflare Workers AI if needed.
"""

import json
import logging
import os
import re

import httpx
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Allowed field values
# ---------------------------------------------------------------------------
VALID_CHARACTERS = {"narrator", "skeptic", "fan", "intern"}

VALID_ARTIFACTS = {
    "language_chart",
    "file_size_graph",
    "security_report",
    "project_structure",
}

MAX_WORDS = 800  # ~4-5 minutes of spoken audio

# ---------------------------------------------------------------------------
# Vibe mode → LLM prompt instruction mapping
# ---------------------------------------------------------------------------
VIBE_PROMPTS: dict[str, str] = {
    "roast": (
        "Skeptic delivers 60%+ of segments. Tone is merciless critique "
        "and dark humor. Narrator introduces and closes. The Skeptic should "
        "actively challenge and mock what Fan says. Intern asks naive questions "
        "that lead to more roasting."
    ),
    "deep_dive": (
        "Narrator leads with 40%+ of segments. Balanced technical "
        "analysis. All four characters contribute. Skeptic raises concerns, "
        "Fan highlights strengths, Intern asks clarifying questions that "
        "the others answer."
    ),
    "beginner_friendly": (
        "Intern asks questions in 40%+ of segments. Fan explains "
        "without jargon. Skeptic plays devil's advocate but keeps it light. "
        "Narrator guides the conversation and summarizes key points."
    ),
}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def count_words(script: list[dict]) -> int:
    """Sum word counts across all segment ``text`` fields."""
    return sum(len(seg["text"].split()) for seg in script)


def _extract_json_array(text: str) -> list[dict] | None:
    """Try to extract a JSON array from LLM output that may contain extra text."""
    text = text.strip()

    # 1. Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. Try extracting from markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence_match:
        try:
            result = json.loads(fence_match.group(1).strip())
            if isinstance(result, list):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

    # 3. Try finding the first [ ... ] block
    bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
    if bracket_match:
        try:
            result = json.loads(bracket_match.group(0))
            if isinstance(result, list):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

    # 4. Handle truncated JSON — close at last complete object
    if "[" in text:
        arr_start = text.index("[")
        partial = text[arr_start:]
        last_brace = partial.rfind("}")
        if last_brace > 0:
            attempt = partial[: last_brace + 1] + "]"
            try:
                result = json.loads(attempt)
                if isinstance(result, list):
                    return result
            except (json.JSONDecodeError, TypeError):
                pass

    return None


def _is_valid_segment(seg: dict) -> bool:
    """Return True if all constrained fields have allowed values."""
    if seg.get("character") not in VALID_CHARACTERS:
        return False
    artifact = seg.get("artifact")
    if artifact is not None and artifact not in VALID_ARTIFACTS:
        return False
    return True


def validate_script(script: list[dict]) -> list[dict]:
    """Validate segment fields and enforce the word cap."""
    valid: list[dict] = [seg for seg in script if _is_valid_segment(seg)]
    while valid and count_words(valid) > MAX_WORDS:
        valid.pop()
    return valid


# ---------------------------------------------------------------------------
# LLM interaction — Groq API (Llama 3.3 70B)
# ---------------------------------------------------------------------------


def _build_system_prompt(vibe: str, artifact_data: dict) -> str:
    """Construct the system prompt sent to the LLM."""
    vibe_instruction = VIBE_PROMPTS.get(vibe, VIBE_PROMPTS["deep_dive"])
    available_artifacts = [k for k, v in artifact_data.items() if v]

    return (
        "You are a podcast script writer for RepoFM — a show where 4 characters "
        "have a REAL CONVERSATION about GitHub repositories. This is NOT a series "
        "of monologues. Characters must RESPOND to each other, DISAGREE, ASK "
        "FOLLOW-UP QUESTIONS, and BUILD on what others say.\n\n"

        "THE FOUR CHARACTERS:\n"
        "- narrator: Professional host. Introduces topics, asks questions to other "
        "characters, summarizes, and keeps the conversation flowing.\n"
        "- skeptic: Cynical senior dev. Challenges claims, points out flaws, roasts "
        "bad code. Often disagrees with fan.\n"
        "- fan: Enthusiastic junior dev. Defends the repo, finds clever patterns, "
        "gets excited. Often clashes with skeptic.\n"
        "- intern: Confused beginner. Asks basic questions that others answer. "
        "Sometimes says something accidentally insightful.\n\n"

        "CONVERSATION RULES:\n"
        "1. Characters MUST reference what the previous character just said\n"
        "2. Include at least 3 moments where characters directly respond to each other\n"
        "3. Include at least 1 disagreement between skeptic and fan\n"
        "4. Narrator should ask questions that prompt other characters to speak\n"
        "5. Intern should ask at least 2 questions that get answered by others\n"
        "6. Make it feel like a real podcast conversation, not scripted monologues\n"
        "7. CRITICAL RULES FOR QUESTIONS: "
        "(a) Every question asked by ANY character MUST be answered by ANOTHER character in the VERY NEXT segment. "
        "(b) The LAST TWO segments must both be STATEMENTS, not questions. The second-to-last should be a concluding thought from skeptic or fan, and the last must be a closing statement from narrator. "
        "(c) No question should ever go unanswered.\n\n"

        "OUTPUT FORMAT:\n"
        "Your response must be ONLY a valid JSON array. No markdown fences, no explanation.\n"
        "Each element: {\"character\": \"...\", \"text\": \"...\", \"artifact\": ...}\n"
        "- character: one of narrator, skeptic, fan, intern\n"
        "- text: the spoken line\n"
        "- artifact: one of language_chart, file_size_graph, security_report, "
        "project_structure, or null\n\n"

        f"Generate 18-22 segments for a 4-5 minute episode. "
        f"MINIMUM 18 segments required. "
        f"Total word count should be 500-{MAX_WORDS} words.\n\n"

        "CONTENT FOCUS: The conversation should primarily discuss the repository itself — "
        "its purpose, architecture, code quality, interesting patterns, potential issues, "
        "and what makes it unique. Only 2-3 segments should reference artifacts. "
        "The rest should be genuine discussion about the codebase.\n\n"

        f"Vibe mode: {vibe}. {vibe_instruction}\n\n"

        f"Available artifact data: {available_artifacts}. "
        "Include artifact references in only 2-3 segments total. "
        "Most segments should have artifact: null."
    )


async def _call_groq_llm(system_prompt: str, user_content: str) -> str:
    """Send a chat completion request to Groq and return the response text."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="GROQ_API_KEY not configured.",
        )

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    body = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": 4096,
        "temperature": 0.9,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        for attempt in range(3):
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code == 429:
                import asyncio
                await asyncio.sleep((attempt + 1) * 5)
                continue
            resp.raise_for_status()
            data = resp.json()
            break
        else:
            raise HTTPException(
                status_code=429,
                detail="LLM rate limit exceeded. Please wait a minute and try again.",
            )

    # Groq uses OpenAI-compatible response format
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        logging.error(f"Unexpected Groq response: {json.dumps(data)[:500]}")
        raise HTTPException(
            status_code=500,
            detail="LLM returned unexpected response format.",
        )


async def generate_script(
    codebase: str, vibe: str, artifact_data: dict
) -> list[dict]:
    """Generate a podcast script from the codebase via the LLM."""
    system_prompt = _build_system_prompt(vibe, artifact_data)

    # Send more codebase context to the 70B model (it can handle it)
    max_codebase_chars = 15000
    truncated_codebase = codebase[:max_codebase_chars]
    if len(codebase) > max_codebase_chars:
        truncated_codebase += "\n\n[... codebase truncated for brevity ...]"

    user_content = (
        "Here is the codebase to discuss in the podcast:\n\n" + truncated_codebase
    )

    raw_response = await _call_groq_llm(system_prompt, user_content)

    script = _extract_json_array(raw_response)

    if script is None:
        logging.error(
            f"Failed to parse LLM response as JSON. "
            f"Raw (first 500 chars): {raw_response[:500]}"
        )
        raise HTTPException(
            status_code=500,
            detail="LLM returned invalid JSON. Please try again.",
        )

    return validate_script(script)


async def generate_answer(transcript: str, codebase: str) -> str:
    """Generate a concise answer to a user's voice question about the codebase."""
    system_prompt = (
        "You are a helpful assistant for the RepoFM podcast. "
        "A listener has interrupted the episode with a question. "
        "Answer concisely based on the codebase provided. "
        "Keep your answer under 3 sentences."
    )

    # Truncate codebase for the answer context
    max_chars = 8000
    truncated = codebase[:max_chars]

    user_content = (
        f"Codebase:\n{truncated}\n\n"
        f"Listener question: {transcript}"
    )

    return await _call_groq_llm(system_prompt, user_content)
