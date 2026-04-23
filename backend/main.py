"""
RepoFM Backend — FastAPI application entry point.

Startup validation, CORS configuration, health endpoint,
and the POST /analyze orchestration route with SSE streaming.
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# ---------------------------------------------------------------------------
# Load .env from the repo root (one level up from backend/)
# ---------------------------------------------------------------------------
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------
REQUIRED_ENV_VARS = [
    "ELEVENLABS_API_KEY",
    "GROQ_API_KEY",
    "GITINGEST_URL",
]


def _validate_env() -> None:
    missing = [var for var in REQUIRED_ENV_VARS if not os.environ.get(var)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Please set them in your .env file or environment."
        )


_validate_env()

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="RepoFM", version="0.1.0")

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
from rate_limit import RateLimiter, RateLimitExceeded  # noqa: E402

rate_limiter = RateLimiter()


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": exc.detail, "reset_at": exc.reset_at},
    )


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Backend module imports
# ---------------------------------------------------------------------------
import ingest  # noqa: E402
import cache  # noqa: E402
import artifacts  # noqa: E402
import script_gen  # noqa: E402
import tts  # noqa: E402

# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------
_GITHUB_URL_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+$")

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
VibeMode = Literal["roast", "deep_dive", "beginner_friendly"]


class AnalyzeRequest(BaseModel):
    github_url: str
    vibe: VibeMode


# ---------------------------------------------------------------------------
# POST /analyze — streaming SSE endpoint
# ---------------------------------------------------------------------------


@app.post("/analyze")
async def analyze(body: AnalyzeRequest, request: Request):
    """Orchestrate episode generation with SSE progress streaming.

    Sends events:
      - {"event": "progress", "data": {"step": "...", "percent": N}}
      - {"event": "segment", "data": {segment with audio_b64}}
      - {"event": "metadata", "data": {metadata object}}
      - {"event": "done"}
      - {"event": "error", "data": {"detail": "..."}}
    """
    # --- Rate limiting ---
    ip = request.headers.get("X-Forwarded-For")
    if ip:
        ip = ip.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"

    rate_limiter.check(ip)
    rate_limiter.record(ip)

    # --- Validate URL ---
    if not _GITHUB_URL_RE.match(body.github_url):
        raise HTTPException(
            status_code=422,
            detail="Invalid GitHub URL. Expected format: https://github.com/{owner}/{repo}",
        )

    async def event_generator():
        try:
            # Step 1: Ingest (0-20%)
            yield {"event": "progress", "data": json.dumps({"step": "Fetching repository...", "percent": 5})}

            raw_text = await ingest.fetch_codebase(body.github_url)
            filtered_text = ingest.filter_codebase(raw_text)
            filtered_text = ingest.truncate_if_needed(filtered_text)
            cache.set(body.github_url, filtered_text)

            yield {"event": "progress", "data": json.dumps({"step": "Repository fetched", "percent": 20})}

            # Step 2: Extract artifacts + generate script (20-40%)
            artifact_data = artifacts.extract_artifact_data(filtered_text)

            yield {"event": "progress", "data": json.dumps({"step": "Generating script...", "percent": 25})}

            script = await script_gen.generate_script(filtered_text, body.vibe, artifact_data)

            yield {"event": "progress", "data": json.dumps({"step": "Script ready, synthesizing segments...", "percent": 40})}

            # Step 3: Send metadata
            repo_name = body.github_url.rstrip("/").split("/")[-1]
            metadata = {
                "repo_name": repo_name,
                "vibe": body.vibe,
                "artifact_data": artifact_data,
            }
            yield {"event": "metadata", "data": json.dumps(metadata)}

            # Step 4: TTS in parallel, stream segments as they complete (40-95%)
            total_segments = len(script)
            semaphore = asyncio.Semaphore(5)
            completed = {"count": 0}

            async def synth_one(idx: int, seg: dict):
                async with semaphore:
                    character = seg.get("character", "narrator")
                    text = seg.get("text", "")
                    audio_b64 = await tts.synthesize_segment(text, character)
                    seg["audio_b64"] = audio_b64
                    completed["count"] += 1
                    return idx

            # Launch all TTS tasks
            tasks = [synth_one(i, seg) for i, seg in enumerate(script)]

            # Stream segments in order as they complete
            # We need to yield them in order, so collect results
            results = [None] * total_segments
            next_to_send = 0

            for coro in asyncio.as_completed(tasks):
                idx = await coro
                results[idx] = True
                pct = 40 + int((completed["count"] / total_segments) * 55)
                yield {
                    "event": "progress",
                    "data": json.dumps({
                        "step": f"Segment {completed['count']}/{total_segments}",
                        "percent": min(pct, 95),
                    }),
                }

                # Send any segments that are now ready in order
                while next_to_send < total_segments and results[next_to_send]:
                    yield {
                        "event": "segment",
                        "data": json.dumps(script[next_to_send]),
                    }
                    next_to_send += 1

            yield {"event": "progress", "data": json.dumps({"step": "Episode ready!", "percent": 100})}
            yield {"event": "done", "data": ""}

        except HTTPException as exc:
            yield {"event": "error", "data": json.dumps({"detail": exc.detail})}
        except Exception as exc:
            yield {"event": "error", "data": json.dumps({"detail": str(exc)})}

    return EventSourceResponse(event_generator())
