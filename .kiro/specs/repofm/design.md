# Design Document — RepoFM

## Overview

RepoFM is a full-stack web application that converts any public GitHub repository into a 3-minute AI-generated podcast episode. The system ingests a codebase, generates a multi-character script via an LLM, synthesizes per-character audio via TTS, and streams the result to a browser-based player that also renders live visual artifacts.

The architecture is a clean two-tier split:

- **Frontend** — Next.js 14 App Router (TypeScript) deployed on Vercel. Handles all UI, audio playback sequencing, sound effects, artifact rendering, and the voice interrupt flow.
- **Backend** — Python FastAPI deployed on an Azure VM. Orchestrates GitIngest, Cloudflare LLM, ElevenLabs TTS/STT, Thesys C1, rate limiting, and caching.

The two tiers communicate over HTTP. The frontend calls two backend endpoints (`POST /analyze`, `POST /interrupt`) and one health endpoint (`GET /health`). There is no WebSocket or streaming protocol — the full script and all audio are returned in a single `POST /analyze` response, and the frontend sequences playback locally.

### Key Design Decisions

1. **Batch response, not streaming** — The entire script + all TTS audio is returned in one JSON response. This simplifies the frontend state machine considerably and avoids partial-render edge cases. The tradeoff is a longer initial load time, mitigated by a clear loading state.
2. **Static sound effects** — Sound effect `.mp3` files are pre-generated once via `sounds_gen/generate_sounds.py` and served as static assets from `frontend/public/sounds/`. They are never regenerated at runtime, keeping the hot path free of extra API calls.
3. **In-memory rate limiting** — No database or Redis. The rate limiter resets on process restart, which is acceptable for a hackathon-scale deployment.
4. **In-memory codebase cache** — The ingested codebase text is cached in a Python dict keyed by repo URL. This allows the interrupt flow to reuse the already-fetched codebase without a second GitIngest call.
5. **Word-count enforcement at the backend** — The 380-word cap is enforced both in the LLM prompt and as a post-processing truncation step in the backend, so the frontend never needs to handle oversized scripts.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (Vercel)                         │
│                                                                 │
│  app/page.tsx          app/episode/page.tsx                     │
│  ┌──────────────┐      ┌──────────────────────────────────────┐ │
│  │ URL Input    │      │ Player.tsx  ArtifactPanel.tsx        │ │
│  │ VibeSelector │─────▶│ InterruptBtn.tsx                     │ │
│  └──────────────┘      └──────────────────────────────────────┘ │
│         │                          │                            │
│         │ POST /analyze            │ POST /interrupt            │
└─────────┼──────────────────────────┼────────────────────────────┘
          │                          │
          ▼                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (Azure VM)                    │
│                                                                 │
│  main.py ──▶ rate_limit.py                                      │
│           ──▶ ingest.py ──────────▶ GitIngest :8000             │
│           ──▶ cache.py                                          │
│           ──▶ script_gen.py ──────▶ Cloudflare kimi-k2.5        │
│           ──▶ tts.py ─────────────▶ ElevenLabs TTS              │
│           ──▶ artifacts.py ───────▶ (data extraction only)      │
│                                                                 │
│  /interrupt ──▶ stt.py ───────────▶ ElevenLabs STT              │
│             ──▶ cache.py (read)                                 │
│             ──▶ script_gen.py ────▶ Cloudflare kimi-k2.5        │
│             ──▶ tts.py ───────────▶ ElevenLabs TTS              │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (runtime) calls Thesys C1 directly for artifact       │
│  rendering — backend only extracts the data payload             │
└─────────────────────────────────────────────────────────────────┘
```

### Request Lifecycle — `POST /analyze`

```
1. Frontend validates URL format (client-side)
2. Frontend POST /analyze { github_url, vibe }
3. Backend: rate_limit.check(ip) → 429 if exceeded
4. Backend: ingest.fetch(github_url) → raw codebase text
5. Backend: ingest.filter(text) → skip node_modules, dist, etc.
6. Backend: ingest.truncate_if_needed(text) → ≤256K tokens
7. Backend: cache.set(github_url, text)
8. Backend: artifacts.extract(text) → artifact data payloads
9. Backend: script_gen.generate(text, vibe, artifact_data) → script[]
10. Backend: script_gen.validate_and_truncate(script) → ≤380 words
11. Backend: tts.synthesize_all(script) → base64 audio per segment
12. Backend: return { script[], metadata }
13. Frontend: navigate to /episode, begin sequential playback
```

### Request Lifecycle — `POST /interrupt`

```
1. Frontend pauses current segment audio
2. Frontend records mic audio blob
3. Frontend POST /interrupt { audio_blob, github_url }
4. Backend: stt.transcribe(audio_blob) → transcript
5. Backend: cache.get(github_url) → codebase text
6. Backend: script_gen.answer(transcript, codebase_text) → answer_text
7. Backend: tts.synthesize(answer_text, narrator_voice) → base64 audio
8. Backend: return { answer_text, audio }
9. Frontend: plays answer audio, then resumes episode
```

---

## Components and Interfaces

### Frontend Components

#### `app/page.tsx` — Landing Page
- Renders a URL text input and the `VibeSelector` component.
- Validates the URL against the pattern `^https://github\.com/[^/]+/[^/]+$` before submission.
- Shows an inline error message on invalid URL.
- Disables the submit button until both a valid URL and a vibe are selected.
- Shows a loading spinner/skeleton while awaiting the `/analyze` response.
- On success, stores the script + metadata in `sessionStorage` and navigates to `/episode`.

#### `app/episode/page.tsx` — Episode Player Page
- Reads script + metadata from `sessionStorage` on mount.
- Manages the playback state machine (idle → playing → paused → interrupted → complete).
- Sequences segments: play sound effect (if any) → play TTS audio → advance to next segment.
- Triggers artifact rendering when a segment with a non-null `artifact` begins.
- Renders `Player`, `ArtifactPanel`, and `InterruptBtn`.

#### `components/VibeSelector.tsx`
- Renders three radio-style buttons: Roast, Deep Dive, Beginner Friendly.
- Emits `onSelect(vibe: VibeMode)` to parent.
- Visually highlights the selected option.

#### `components/Player.tsx`
- Displays the current character name.
- Renders a waveform or animated audio indicator while audio is playing.
- Exposes play/pause controls (primarily driven by the episode page state machine).

#### `components/ArtifactPanel.tsx`
- Receives an artifact type and its data payload as props.
- Calls the Thesys C1 API client-side to render the generative UI component.
- On Thesys error: logs to console, renders nothing (episode continues unaffected).
- Retains the last successfully rendered artifact when the current segment has `artifact: null`.

#### `components/InterruptBtn.tsx`
- Renders a pulsing microphone button.
- On `mousedown`/`touchstart`: begins `MediaRecorder` capture.
- On `mouseup`/`touchend`: stops recording, emits the audio blob to the episode page.
- Visually indicates recording state (pulsing animation).

### Backend Modules

#### `main.py`
- FastAPI app instantiation and CORS configuration.
- Route definitions: `POST /analyze`, `POST /interrupt`, `GET /health`.
- Startup validation: checks all required env vars are present; raises `RuntimeError` with a descriptive message if any are missing.
- Extracts client IP from `request.client.host` (or `X-Forwarded-For` header if behind a proxy).

#### `ingest.py`
```python
async def fetch_codebase(github_url: str) -> str:
    """POST to GitIngest, return raw codebase text. Raises HTTPException(502) on failure."""

def filter_codebase(raw: str) -> str:
    """Remove lines/files matching: node_modules/, dist/, vendor/, *.lock, *.min.js, *.map"""

def truncate_if_needed(text: str, max_tokens: int = 256_000) -> str:
    """If text exceeds max_tokens, retain file tree + README + top 20 largest files."""

def estimate_tokens(text: str) -> int:
    """Rough token estimate: len(text) // 4"""
```

#### `script_gen.py`
```python
async def generate_script(codebase: str, vibe: str, artifact_data: dict) -> list[dict]:
    """Call Cloudflare kimi-k2.5. Returns validated script list. Raises HTTPException(500) on bad JSON."""

def validate_script(script: list[dict]) -> list[dict]:
    """Validate character, sound_before, artifact fields. Truncate to ≤380 words."""

def count_words(script: list[dict]) -> int:
    """Sum word counts across all segment text fields."""

async def generate_answer(transcript: str, codebase: str) -> str:
    """Generate a concise answer to a user question given the codebase context."""
```

#### `tts.py`
```python
VOICE_IDS: dict[str, str] = {
    "narrator": "<elevenlabs_voice_id>",
    "skeptic":  "<elevenlabs_voice_id>",
    "fan":      "<elevenlabs_voice_id>",
    "intern":   "<elevenlabs_voice_id>",
}

async def synthesize_segment(text: str, character: str) -> str:
    """Call ElevenLabs TTS. Returns base64-encoded audio. Raises HTTPException(502) on failure."""

async def synthesize_all(script: list[dict]) -> list[dict]:
    """Sequentially synthesize TTS for each segment. Adds 'audio_b64' field to each segment."""
```

#### `stt.py`
```python
async def transcribe(audio_bytes: bytes) -> str:
    """Call ElevenLabs STT. Returns transcript string. Raises HTTPException(502) on failure."""
```

#### `artifacts.py`
```python
def extract_artifact_data(codebase: str) -> dict:
    """
    Parse codebase text to extract:
    - language_chart: {language: line_count} dict
    - file_size_graph: [{file: str, size: int}] top 20
    - security_report: list of suspicious patterns (hardcoded secrets, exposed configs)
    - commit_graph: not extractable from static text — returns empty placeholder
    - dependency_map: parsed from package.json / requirements.txt content
    """
```

#### `rate_limit.py`
```python
class RateLimiter:
    def __init__(self, max_requests: int = 3, window_seconds: int = 3600): ...
    def check(self, ip: str) -> None:
        """Raises HTTPException(429) with reset time if limit exceeded."""
    def record(self, ip: str) -> None:
        """Records a request for the given IP."""
```

#### `cache.py`
```python
_cache: dict[str, str] = {}

def set(url: str, codebase: str) -> None: ...
def get(url: str) -> str | None: ...
```

### API Contracts

#### `POST /analyze`
```
Request:
  Content-Type: application/json
  Body: { "github_url": string, "vibe": "roast" | "deep_dive" | "beginner_friendly" }

Response 200:
  {
    "script": [
      {
        "character": "narrator" | "skeptic" | "fan" | "intern",
        "text": string,
        "sound_before": string | null,
        "artifact": string | null,
        "audio_b64": string   // base64-encoded mp3
      }
    ],
    "metadata": {
      "repo_name": string,
      "vibe": string,
      "artifact_data": {
        "language_chart": { [language: string]: number },
        "file_size_graph": [{ "file": string, "size": number }],
        "security_report": string[],
        "dependency_map": { [name: string]: string }
      }
    }
  }

Response 422: { "detail": string }   // invalid URL or private/missing repo
Response 429: { "detail": string, "reset_at": string }
Response 500: { "detail": string }   // LLM returned invalid JSON
Response 502: { "detail": string }   // GitIngest or TTS unreachable
```

#### `POST /interrupt`
```
Request:
  Content-Type: multipart/form-data
  Fields:
    audio: binary (audio blob, e.g. webm/ogg)
    github_url: string

Response 200:
  {
    "answer_text": string,
    "audio": string   // base64-encoded mp3
  }

Response 502: { "detail": string }   // STT or LLM failure
```

#### `GET /health`
```
Response 200: { "status": "ok" }
```

---

## Data Models

### TypeScript (Frontend)

```typescript
type VibeMode = "roast" | "deep_dive" | "beginner_friendly";

type Character = "narrator" | "skeptic" | "fan" | "intern";

type SoundEffect =
  | "crowd_gasp"
  | "keyboard_typing"
  | "paper_flip"
  | "record_scratch"
  | "applause"
  | "thinking_hmm"
  | "transition_jingle"
  | "mic_beep"
  | null;

type ArtifactType =
  | "language_chart"
  | "file_size_graph"
  | "security_report"
  | "commit_graph"
  | "dependency_map"
  | null;

interface Segment {
  character: Character;
  text: string;
  sound_before: SoundEffect;
  artifact: ArtifactType;
  audio_b64: string; // base64 mp3
}

interface ArtifactData {
  language_chart: Record<string, number>;
  file_size_graph: Array<{ file: string; size: number }>;
  security_report: string[];
  dependency_map: Record<string, string>;
}

interface EpisodeMetadata {
  repo_name: string;
  vibe: VibeMode;
  artifact_data: ArtifactData;
}

interface AnalyzeResponse {
  script: Segment[];
  metadata: EpisodeMetadata;
}

interface InterruptResponse {
  answer_text: string;
  audio: string; // base64 mp3
}

// Episode playback state machine
type PlaybackState =
  | "idle"
  | "loading"
  | "playing_sound"
  | "playing_speech"
  | "paused"
  | "interrupted"
  | "complete";
```

### Python (Backend)

```python
from pydantic import BaseModel
from typing import Literal

VibeMode = Literal["roast", "deep_dive", "beginner_friendly"]
Character = Literal["narrator", "skeptic", "fan", "intern"]
SoundEffect = Literal[
    "crowd_gasp", "keyboard_typing", "paper_flip", "record_scratch",
    "applause", "thinking_hmm", "transition_jingle", "mic_beep"
] | None
ArtifactType = Literal[
    "language_chart", "file_size_graph", "security_report",
    "commit_graph", "dependency_map"
] | None

class AnalyzeRequest(BaseModel):
    github_url: str
    vibe: VibeMode

class Segment(BaseModel):
    character: Character
    text: str
    sound_before: SoundEffect
    artifact: ArtifactType
    audio_b64: str = ""  # populated after TTS

class ArtifactData(BaseModel):
    language_chart: dict[str, int] = {}
    file_size_graph: list[dict] = []
    security_report: list[str] = []
    dependency_map: dict[str, str] = {}

class EpisodeMetadata(BaseModel):
    repo_name: str
    vibe: VibeMode
    artifact_data: ArtifactData

class AnalyzeResponse(BaseModel):
    script: list[Segment]
    metadata: EpisodeMetadata

class InterruptResponse(BaseModel):
    answer_text: str
    audio: str  # base64 mp3
```

### LLM Prompt Schema

The system prompt instructs the LLM to return a raw JSON array (no markdown fences) matching:

```json
[
  {
    "character": "narrator|skeptic|fan|intern",
    "text": "...",
    "sound_before": "crowd_gasp|keyboard_typing|...|null",
    "artifact": "language_chart|file_size_graph|...|null"
  }
]
```

The prompt enforces:
- Total word count across all `text` fields ≤ 380 words
- Character distribution based on selected vibe mode
- No markdown, no code fences — raw JSON only

### Vibe Mode → LLM Prompt Mapping

| Vibe Mode | Prompt Instruction |
|---|---|
| `roast` | "Skeptic delivers 60%+ of segments. Tone is merciless critique and dark humor. Narrator introduces and closes." |
| `deep_dive` | "Narrator leads with 50%+ of segments. Balanced technical analysis. All four characters contribute." |
| `beginner_friendly` | "Intern asks questions in 40%+ of segments. Fan explains without jargon. Skeptic and Narrator play supporting roles." |

### Rate Limiter Internal State

```python
# In-memory dict — not persisted
_requests: dict[str, list[float]] = {}
# key: IP address string
# value: list of Unix timestamps of requests within the current window
```

### Codebase Cache Internal State

```python
# In-memory dict — not persisted
_cache: dict[str, str] = {}
# key: github_url (normalized, lowercase)
# value: filtered + truncated codebase text
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*


### Property 1: URL Validation Rejects All Invalid Inputs

*For any* string that does not match the pattern `https://github.com/{owner}/{repo}` (where owner and repo are non-empty path segments with no additional slashes), the URL validation function SHALL return false (invalid).

**Validates: Requirements 1.2, 1.5**

---

### Property 2: Codebase Filter Removes Exactly the Excluded Patterns

*For any* codebase text containing a mix of file paths, the filter function SHALL remove all lines/files matching `node_modules/`, `dist/`, `vendor/`, `*.lock`, `*.min.js`, `*.map` and SHALL retain all lines/files that do not match any of those patterns.

**Validates: Requirements 3.2**

---

### Property 3: Truncation Correctness

*For any* codebase text: if the text is within the 256,000-token limit, `truncate_if_needed` SHALL return it unchanged; if the text exceeds the limit, the returned text SHALL contain the file tree section, the README content, and the top 20 largest files by character count.

**Validates: Requirements 3.3, 3.4**

---

### Property 4: Cache Round-Trip

*For any* repository URL and codebase text, calling `cache.set(url, text)` followed by `cache.get(url)` SHALL return the exact same text.

**Validates: Requirements 3.6**

---

### Property 5: Script Word Count Enforcement

*For any* script (list of segments), after calling `validate_and_truncate`, the total word count across all `text` fields SHALL be less than or equal to 380.

**Validates: Requirements 4.4, 4.5**

---

### Property 6: Script Field Validation

*For any* segment, the validation function SHALL accept the segment if and only if: `character` is one of `{narrator, skeptic, fan, intern}`, `sound_before` is one of the 8 named sound values or `null`, and `artifact` is one of the 5 named artifact values or `null`. Any segment with a value outside these sets SHALL be rejected.

**Validates: Requirements 4.6, 4.7, 4.8**

---

### Property 7: Response Metadata Always Present

*For any* valid `POST /analyze` request, the response SHALL contain a `metadata` object with non-empty `repo_name` and `vibe` fields.

**Validates: Requirements 4.10**

---

### Property 8: Rate Limiter Threshold

*For any* client IP address, the first 3 `POST /analyze` requests within a 60-minute window SHALL be allowed (rate limiter does not raise), and the 4th request within the same window SHALL be rejected with HTTP 429 including a `reset_at` timestamp.

**Validates: Requirements 5.2, 5.3**

---

### Property 9: Correct Voice ID Routing

*For any* script containing any mix of the four characters, each TTS call SHALL use the voice ID assigned to that segment's character — no segment SHALL be synthesized with a voice ID belonging to a different character.

**Validates: Requirements 6.2**

---

### Property 10: All Segments Have Audio in Response

*For any* validated script, every segment in the `POST /analyze` response SHALL have a non-empty `audio_b64` field containing valid base64-encoded data.

**Validates: Requirements 6.3**

---

### Property 11: TTS Calls Are Made in Script Order

*For any* script, the sequence of TTS API calls SHALL match the order of segments in the script array — segment at index `i` SHALL be synthesized before segment at index `i+1`.

**Validates: Requirements 6.5**

---

### Property 12: Sound Effect Sequencing

*For any* segment: if `sound_before` is not `null`, the sound effect audio SHALL be triggered before the TTS audio for that segment; if `sound_before` is `null`, the TTS audio SHALL begin immediately with no preceding sound effect.

**Validates: Requirements 7.2, 7.3**

---

### Property 13: Character Name Display During Playback

*For any* segment being played, the episode player SHALL display the name of that segment's character while the segment's audio is active.

**Validates: Requirements 8.2**

---

### Property 14: Sequential Segment Playback

*For any* script, the episode player SHALL play segments in the order they appear in the script array — segment at index `i` SHALL complete before segment at index `i+1` begins.

**Validates: Requirements 8.3**

---

### Property 15: Artifact Triggered for Non-Null Artifact Segments

*For any* segment whose `artifact` field is not `null`, when the frontend begins playing that segment, the Thesys C1 API SHALL be called with the correct artifact type and the corresponding data from `metadata.artifact_data`.

**Validates: Requirements 9.1**

---

### Property 16: ArtifactPanel Retains Last Artifact on Null Segments

*For any* sequence of segments where a segment with `artifact: null` follows one or more segments with non-null artifacts, the ArtifactPanel SHALL continue displaying the most recently rendered artifact rather than clearing.

**Validates: Requirements 9.3**

---

### Property 17: Artifact Data Extraction Completeness

*For any* codebase text, `extract_artifact_data` SHALL return a dict containing all five artifact type keys (`language_chart`, `file_size_graph`, `security_report`, `commit_graph`, `dependency_map`), each with a value of the correct type (even if empty).

**Validates: Requirements 9.4**

---

### Property 18: Interrupt LLM Context Includes Transcript and Codebase

*For any* interrupt request with a transcript and a cached codebase, the LLM prompt constructed by `generate_answer` SHALL include both the transcript text and the codebase text.

**Validates: Requirements 10.5**

---

### Property 19: Interrupt Response Structure

*For any* valid `POST /interrupt` request, the response SHALL contain a non-empty `answer_text` string and a non-empty `audio` string containing valid base64-encoded data.

**Validates: Requirements 10.6**

---

## Error Handling

### Backend Error Taxonomy

| Scenario | HTTP Status | Response Body |
|---|---|---|
| Invalid GitHub URL format | 422 | `{ "detail": "Invalid GitHub URL. Expected format: https://github.com/{owner}/{repo}" }` |
| Private or non-existent repo | 422 | `{ "detail": "Repository not found or is private." }` |
| Rate limit exceeded | 429 | `{ "detail": "Rate limit exceeded. Resets at {ISO timestamp}.", "reset_at": "..." }` |
| GitIngest unreachable | 502 | `{ "detail": "Failed to fetch repository from GitIngest: {error}" }` |
| LLM returns invalid JSON | 500 | `{ "detail": "LLM returned invalid JSON. Please try again." }` |
| TTS failure on segment N | 502 | `{ "detail": "TTS synthesis failed for segment {N} (character: {character})." }` |
| STT failure during interrupt | 502 | `{ "detail": "Speech-to-text transcription failed." }` |
| LLM failure during interrupt | 502 | `{ "detail": "Failed to generate answer from LLM." }` |
| Missing env var at startup | RuntimeError (crash) | Logged to stderr: `"Missing required environment variable: {VAR_NAME}"` |

### Frontend Error Handling

- **`/analyze` non-200 response**: Display the `detail` message inline on the landing page. Clear the loading state. Allow the user to retry.
- **`/interrupt` non-200 response**: Display a brief error toast. Resume episode playback from the paused position. Do not block the episode.
- **Thesys C1 error**: Log to console. Leave ArtifactPanel in its previous state. Episode continues unaffected.
- **Missing `sessionStorage` data on `/episode`**: Redirect back to the landing page.

### Retry Policy

- No automatic retries on the frontend — user-initiated retries only.
- No automatic retries on the backend for external service calls — fail fast and return a descriptive error.

---

## Testing Strategy

### Overview

The testing strategy uses a dual approach: **unit/property-based tests** for pure logic and **integration tests** for external service wiring. The property-based testing library for Python is [Hypothesis](https://hypothesis.readthedocs.io/). For the TypeScript frontend, [fast-check](https://fast-check.dev/) is used.

### Backend Testing (Python / Pytest + Hypothesis)

**Unit and Property Tests** (pure functions, no external calls):

- `ingest.py` — `filter_codebase`, `truncate_if_needed`, `estimate_tokens`
- `script_gen.py` — `validate_script`, `count_words`, prompt construction
- `rate_limit.py` — `RateLimiter.check`, `RateLimiter.record`
- `cache.py` — `set`, `get`
- `artifacts.py` — `extract_artifact_data`

Each property-based test runs a minimum of 100 iterations via Hypothesis `@given` decorator.

Tag format for property tests:
```python
# Feature: repofm, Property {N}: {property_text}
@given(...)
def test_property_N_name(...):
    ...
```

**Integration Tests** (mocked external services):

- `ingest.py` — `fetch_codebase` with mocked `httpx` calls to GitIngest
- `script_gen.py` — `generate_script`, `generate_answer` with mocked Cloudflare API
- `tts.py` — `synthesize_segment`, `synthesize_all` with mocked ElevenLabs TTS
- `stt.py` — `transcribe` with mocked ElevenLabs STT
- `main.py` — full route tests via FastAPI `TestClient` with all external services mocked

**Smoke Tests**:

- Verify `VOICE_IDS` has 4 distinct entries
- Verify startup fails with descriptive error when env vars are missing
- Verify `.env.example` contains all required variable names
- Verify `.gitignore` contains `.env` and does not contain `.kiro`

### Frontend Testing (TypeScript / Vitest + fast-check)

**Unit and Property Tests**:

- URL validation function (`isValidGitHubUrl`) — property tests with fast-check
- Playback state machine transitions — property tests verifying valid state sequences
- Sound effect sequencing logic — property tests
- Character name display logic — property tests

**Component Tests** (Vitest + React Testing Library):

- `VibeSelector` — renders 3 options, emits correct value on selection
- `Player` — displays character name, shows waveform during playback
- `ArtifactPanel` — retains last artifact on null-artifact segments
- `InterruptBtn` — triggers recording on press, stops on release
- Landing page — loading state, inline validation errors, submit disabled without vibe
- Episode page — navigation after successful response, end-of-episode state

**Integration Tests** (mocked API):

- Full `/analyze` flow: submit form → mock response → navigate to episode → play segments
- Full interrupt flow: press button → mock `/interrupt` response → play answer → resume

### Property Test Configuration

```python
# Hypothesis settings for all property tests
from hypothesis import settings, HealthCheck

settings.register_profile("repofm", max_examples=100, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("repofm")
```

```typescript
// fast-check configuration
import fc from "fast-check";
fc.configureGlobal({ numRuns: 100 });
```

### Test File Layout

```
backend/
└── tests/
    ├── test_ingest.py          # filter, truncate, token estimate properties
    ├── test_script_gen.py      # word count, validation, prompt construction
    ├── test_rate_limit.py      # rate limiter threshold property
    ├── test_cache.py           # cache round-trip property
    ├── test_artifacts.py       # extraction completeness property
    ├── test_tts.py             # voice routing, sequential calls, audio_b64 presence
    ├── test_routes.py          # full route integration tests
    └── test_smoke.py           # env vars, voice IDs, .gitignore checks

frontend/
└── __tests__/
    ├── validation.test.ts      # URL validation property tests
    ├── Player.test.tsx         # character display, waveform
    ├── ArtifactPanel.test.tsx  # artifact retention property
    ├── InterruptBtn.test.tsx   # recording state
    ├── VibeSelector.test.tsx   # 3 options, selection
    ├── episode.test.tsx        # playback sequencing, state machine
    └── page.test.tsx           # landing page form behavior
```
