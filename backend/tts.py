"""
RepoFM — TTS integration module.

Calls the ElevenLabs Text-to-Speech API to synthesize audio for each
segment in a podcast script. Uses parallel requests for speed.
"""

import asyncio
import base64
import logging
import os

import httpx
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Voice ID mapping — one unique ElevenLabs voice per character.
# ---------------------------------------------------------------------------
VOICE_IDS: dict[str, str] = {
    "narrator": os.environ.get("VOICE_ID_NARRATOR", "placeholder_narrator_voice_id"),
    "skeptic": os.environ.get("VOICE_ID_SKEPTIC", "placeholder_skeptic_voice_id"),
    "fan": os.environ.get("VOICE_ID_FAN", "placeholder_fan_voice_id"),
    "intern": os.environ.get("VOICE_ID_INTERN", "placeholder_intern_voice_id"),
}

# ---------------------------------------------------------------------------
# ElevenLabs TTS configuration
# ---------------------------------------------------------------------------
ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
TTS_MODEL_ID = "eleven_flash_v2_5"  # fastest model for low latency

# Max parallel TTS requests (avoid hammering the API)
MAX_CONCURRENT = 5


async def synthesize_segment(text: str, character: str) -> str:
    """Call the ElevenLabs TTS API for a single segment.

    Returns base64-encoded audio (mp3) data.
    Raises HTTPException(502) on failure.
    """
    voice_id = VOICE_IDS.get(character)
    if not voice_id:
        raise HTTPException(
            status_code=502,
            detail=f"TTS synthesis failed: unknown character '{character}'.",
        )

    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    url = ELEVENLABS_TTS_URL.format(voice_id=voice_id)

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }

    body = {
        "text": text,
        "model_id": TTS_MODEL_ID,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            audio_bytes = resp.content
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=f"TTS synthesis failed for character '{character}'.",
        )

    return base64.b64encode(audio_bytes).decode("utf-8")


async def _synthesize_one(
    idx: int, segment: dict, semaphore: asyncio.Semaphore
) -> tuple[int, str]:
    """Synthesize a single segment with concurrency control."""
    async with semaphore:
        character = segment.get("character", "narrator")
        text = segment.get("text", "")
        try:
            audio_b64 = await synthesize_segment(text, character)
            return (idx, audio_b64)
        except HTTPException:
            logging.error(f"TTS failed for segment {idx} (character: {character})")
            raise HTTPException(
                status_code=502,
                detail=f"TTS synthesis failed for segment {idx} (character: {character}).",
            )


async def synthesize_all(script: list[dict]) -> list[dict]:
    """Synthesize TTS audio for all segments IN PARALLEL.

    Uses a semaphore to limit concurrent requests to MAX_CONCURRENT
    to avoid overwhelming the ElevenLabs API.
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    tasks = [
        _synthesize_one(idx, segment, semaphore)
        for idx, segment in enumerate(script)
    ]

    results = await asyncio.gather(*tasks)

    # Assign audio back to segments in order
    for idx, audio_b64 in results:
        script[idx]["audio_b64"] = audio_b64

    return script
