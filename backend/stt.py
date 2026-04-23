"""
RepoFM — STT integration module.

Calls the ElevenLabs Speech-to-Text API to transcribe user audio
captured during the voice interrupt flow.
"""

import os

import httpx
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# ElevenLabs STT configuration
# ---------------------------------------------------------------------------
ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
STT_MODEL_ID = "scribe_v2"


async def transcribe(audio_bytes: bytes) -> str:
    """Call the ElevenLabs STT API to transcribe audio.

    Parameters
    ----------
    audio_bytes:
        Raw audio bytes (e.g. webm/ogg blob from the browser).

    Returns
    -------
    str
        The transcript text extracted from the audio.

    Raises
    ------
    HTTPException(502)
        If the STT API call fails for any reason.
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")

    headers = {
        "xi-api-key": api_key,
    }

    files = {
        "file": ("audio.webm", audio_bytes, "audio/webm"),
    }

    data = {
        "model_id": STT_MODEL_ID,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                ELEVENLABS_STT_URL,
                headers=headers,
                files=files,
                data=data,
            )
            resp.raise_for_status()
            result = resp.json()
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Speech-to-text transcription failed.",
        )

    return result.get("text", "")
