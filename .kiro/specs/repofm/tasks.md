I n# Implementation Plan: RepoFM

## Overview

Full-stack implementation of RepoFM — a web app that converts any public GitHub repository into a 3-minute AI podcast episode. The backend is Python FastAPI (Azure VM) and the frontend is Next.js 14 App Router (TypeScript, Vercel). Tasks are ordered so each step builds on the previous, ending with full integration.

## Tasks

- [x] 1. Project scaffolding and repository setup
  - Create top-level directory structure: `frontend/`, `backend/`, `sounds_gen/`, `.kiro/`
  - Write `LICENSE` file with MIT license text
  - Write `README.md` with project description, setup instructions, and environment variable reference
  - Write `.env.example` with placeholder values for all required variables: `ELEVENLABS_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `THESYS_API_KEY`, `GITINGEST_URL`
  - Write `.gitignore` that includes `.env` and explicitly does NOT include `.kiro/`
  - _Requirements: 12.3, 12.4, 12.5_

- [x] 2. Backend foundation — FastAPI app, env validation, CORS, health endpoint
  - Create `backend/main.py` with FastAPI app instantiation
  - Add startup validation that reads all required env vars (`ELEVENLABS_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `THESYS_API_KEY`, `GITINGEST_URL`) and raises `RuntimeError` with a descriptive message if any are missing
  - Configure CORS to allow requests from the Vercel frontend origin
  - Implement `GET /health` route returning `{ "status": "ok" }`
  - Create `backend/requirements.txt` with pinned versions: `fastapi`, `uvicorn`, `httpx`, `python-dotenv`, `pydantic`, `python-multipart`, `hypothesis`, `pytest`, `pytest-asyncio`
  - _Requirements: 11.1, 11.2, 12.1, 12.2_

- [x] 3. Rate limiter module
  - Create `backend/rate_limit.py` with `RateLimiter` class
  - Implement `__init__(self, max_requests: int = 3, window_seconds: int = 3600)` storing an in-memory `dict[str, list[float]]`
  - Implement `check(self, ip: str) -> None` that raises `HTTPException(429)` with `reset_at` ISO timestamp when the IP has ≥3 requests in the sliding window
  - Implement `record(self, ip: str) -> None` that appends the current Unix timestamp and prunes entries older than the window
  - Wire `RateLimiter` instance into `main.py` — call `check` then `record` at the start of the `POST /analyze` handler
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 3.1 Write property test for rate limiter threshold (Property 8)
    - **Property 8: Rate Limiter Threshold**
    - Use Hypothesis `@given` to generate arbitrary IP strings and verify: first 3 calls to `check`+`record` do not raise, 4th call raises `HTTPException(429)` with a `reset_at` field
    - **Validates: Requirements 5.2, 5.3**

- [x] 4. Codebase cache module
  - Create `backend/cache.py` with module-level `_cache: dict[str, str] = {}`
  - Implement `set(url: str, codebase: str) -> None` that normalizes the URL to lowercase before storing
  - Implement `get(url: str) -> str | None` that normalizes the URL to lowercase before lookup
  - _Requirements: 3.6_

  - [ ]* 4.1 Write property test for cache round-trip (Property 4)
    - **Property 4: Cache Round-Trip**
    - Use Hypothesis `@given(url=st.text(), text=st.text())` to verify `cache.set(url, text)` followed by `cache.get(url)` returns the exact same text
    - **Validates: Requirements 3.6**

- [x] 5. Codebase ingestion module
  - Create `backend/ingest.py` with all four functions matching the design signatures
  - Implement `fetch_codebase(github_url: str) -> str` using `httpx.AsyncClient` to POST `{ "url": github_url }` to `GITINGEST_URL`; raise `HTTPException(502)` on any failure
  - Implement `filter_codebase(raw: str) -> str` that removes lines/file blocks matching `node_modules/`, `dist/`, `vendor/`, `*.lock`, `*.min.js`, `*.map`
  - Implement `estimate_tokens(text: str) -> int` as `len(text) // 4`
  - Implement `truncate_if_needed(text: str, max_tokens: int = 256_000) -> str` that returns text unchanged if within limit; otherwise retains the file tree section, README content, and the top 20 largest files by character count
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 5.1 Write property test for codebase filter (Property 2)
    - **Property 2: Codebase Filter Removes Exactly the Excluded Patterns**
    - Use Hypothesis to generate codebase text with random mixes of excluded and non-excluded file paths; verify all excluded patterns are removed and all non-excluded lines are retained
    - **Validates: Requirements 3.2**

  - [ ]* 5.2 Write property test for truncation correctness (Property 3)
    - **Property 3: Truncation Correctness**
    - Use Hypothesis to generate text below and above the 256K-token threshold; verify text within limit is returned unchanged, and text above limit contains file tree, README, and top-20 files
    - **Validates: Requirements 3.3, 3.4**

- [x] 6. Script generation module
  - Create `backend/script_gen.py` with all functions matching the design signatures
  - Implement `count_words(script: list[dict]) -> int` summing `len(seg["text"].split())` across all segments
  - Implement `validate_script(script: list[dict]) -> list[dict]` that validates `character`, `sound_before`, and `artifact` fields against their allowed value sets, then truncates segments from the end until total word count ≤ 380
  - Implement `generate_script(codebase: str, vibe: str, artifact_data: dict) -> list[dict]` that builds the system prompt with vibe-mode instructions and the 380-word cap, calls Cloudflare `@cf/moonshotai/kimi-k2.5` via the Workers AI REST API, parses the JSON response, and calls `validate_script`; raises `HTTPException(500)` if the response is not valid JSON
  - Implement `generate_answer(transcript: str, codebase: str) -> str` that sends both the transcript and codebase text to the LLM and returns a concise answer string
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 10.5_

  - [ ]* 6.1 Write property test for script word count enforcement (Property 5)
    - **Property 5: Script Word Count Enforcement**
    - Use Hypothesis to generate arbitrary lists of segment dicts with random `text` values; verify that after `validate_script`, `count_words` returns ≤ 380
    - **Validates: Requirements 4.4, 4.5**

  - [ ]* 6.2 Write property test for script field validation (Property 6)
    - **Property 6: Script Field Validation**
    - Use Hypothesis to generate segments with both valid and invalid `character`, `sound_before`, and `artifact` values; verify `validate_script` accepts only segments with all-valid fields and rejects any with out-of-set values
    - **Validates: Requirements 4.6, 4.7, 4.8**

- [x] 7. TTS integration module
  - Create `backend/tts.py` with `VOICE_IDS` dict mapping all four characters to their ElevenLabs voice IDs (read from env vars `VOICE_ID_NARRATOR`, `VOICE_ID_SKEPTIC`, `VOICE_ID_FAN`, `VOICE_ID_INTERN` or hardcoded placeholder IDs to be replaced)
  - Implement `synthesize_segment(text: str, character: str) -> str` that calls the ElevenLabs TTS API with the correct voice ID for the character and returns base64-encoded audio; raises `HTTPException(502)` on failure
  - Implement `synthesize_all(script: list[dict]) -> list[dict]` that iterates segments sequentially in order, calls `synthesize_segment` for each, and adds the `audio_b64` field to each segment dict
  - Add `VOICE_ID_NARRATOR`, `VOICE_ID_SKEPTIC`, `VOICE_ID_FAN`, `VOICE_ID_INTERN` to `.env.example`
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 7.1 Write property test for correct voice ID routing (Property 9)
    - **Property 9: Correct Voice ID Routing**
    - Use Hypothesis to generate scripts with arbitrary mixes of the four characters; mock the ElevenLabs API call and verify each call uses the voice ID matching that segment's character
    - **Validates: Requirements 6.2**

  - [ ]* 7.2 Write property test for TTS sequential ordering (Property 11)
    - **Property 11: TTS Calls Are Made in Script Order**
    - Use Hypothesis to generate scripts of varying lengths; mock the API and verify the sequence of calls matches the segment index order
    - **Validates: Requirements 6.5**

- [x] 8. STT integration module
  - Create `backend/stt.py`
  - Implement `transcribe(audio_bytes: bytes) -> str` that POSTs the audio bytes to the ElevenLabs STT API using `ELEVENLABS_API_KEY` and returns the transcript string; raises `HTTPException(502)` on failure
  - _Requirements: 10.4_

- [x] 9. Artifact data extraction module
  - Create `backend/artifacts.py`
  - Implement `extract_artifact_data(codebase: str) -> dict` that parses the codebase text to produce:
    - `language_chart`: `{language: line_count}` dict by scanning file extensions
    - `file_size_graph`: list of `{file, size}` dicts for the top 20 largest files by character count
    - `security_report`: list of suspicious pattern matches (hardcoded secrets, exposed configs — scan for patterns like `password=`, `api_key=`, `secret=`, `token=` in non-example files)
    - `commit_graph`: empty placeholder `{}`
    - `dependency_map`: parsed from `package.json` or `requirements.txt` content found in the codebase text
  - _Requirements: 9.4_

  - [ ]* 9.1 Write property test for artifact data extraction completeness (Property 17)
    - **Property 17: Artifact Data Extraction Completeness**
    - Use Hypothesis to generate arbitrary codebase text strings; verify `extract_artifact_data` always returns a dict with all five keys (`language_chart`, `file_size_graph`, `security_report`, `commit_graph`, `dependency_map`), each with the correct type
    - **Validates: Requirements 9.4**

- [x] 10. POST /analyze route — full orchestration
  - In `backend/main.py`, implement the `POST /analyze` route handler with `AnalyzeRequest` Pydantic model
  - Extract client IP from `request.client.host` (fall back to `X-Forwarded-For` header)
  - Call `rate_limiter.check(ip)` then `rate_limiter.record(ip)`
  - Validate `github_url` format against `^https://github\.com/[^/]+/[^/]+$`; return 422 on mismatch
  - Call `ingest.fetch_codebase`, `ingest.filter_codebase`, `ingest.truncate_if_needed`
  - Call `cache.set(github_url, filtered_text)`
  - Call `artifacts.extract_artifact_data(filtered_text)`
  - Call `script_gen.generate_script(text, vibe, artifact_data)`
  - Call `tts.synthesize_all(script)`
  - Return `AnalyzeResponse` with `script` and `metadata` (including `repo_name` extracted from URL and `artifact_data`)
  - _Requirements: 1.3, 1.4, 1.5, 3.1, 3.6, 4.1, 4.10, 5.1, 5.2, 5.3, 6.2, 6.3, 9.4_

  - [ ]* 10.1 Write integration tests for POST /analyze route
    - Use FastAPI `TestClient` with all external services mocked (httpx, Cloudflare, ElevenLabs)
    - Test: valid request returns 200 with correct response shape
    - Test: invalid URL returns 422
    - Test: rate limit exceeded returns 429 with `reset_at`
    - Test: GitIngest failure returns 502
    - Test: LLM invalid JSON returns 500
    - _Requirements: 1.3, 1.4, 1.5, 5.2, 5.3_

- [x] 11. POST /interrupt route — full orchestration
  - In `backend/main.py`, implement the `POST /interrupt` route handler accepting `multipart/form-data` with `audio` (binary) and `github_url` (string) fields
  - Call `stt.transcribe(audio_bytes)` → transcript
  - Call `cache.get(github_url)` → codebase text
  - Call `script_gen.generate_answer(transcript, codebase_text)` → answer text
  - Call `tts.synthesize_segment(answer_text, "narrator")` → base64 audio
  - Return `InterruptResponse` with `answer_text` and `audio`
  - Return 502 on STT or LLM failure with descriptive message
  - _Requirements: 10.4, 10.5, 10.6, 10.8_

  - [ ]* 11.1 Write integration tests for POST /interrupt route
    - Use FastAPI `TestClient` with mocked STT, LLM, and TTS
    - Test: valid audio + cached URL returns 200 with `answer_text` and `audio`
    - Test: STT failure returns 502
    - Test: LLM failure returns 502
    - _Requirements: 10.4, 10.5, 10.6, 10.8_

- [x] 12. Backend smoke tests
  - Create `backend/tests/test_smoke.py`
  - Test: `VOICE_IDS` in `tts.py` has exactly 4 distinct entries
  - Test: FastAPI app startup raises `RuntimeError` with a descriptive message when any required env var is missing
  - Test: `.env.example` file exists and contains all required variable names
  - Test: `.gitignore` contains `.env` and does NOT contain `.kiro`
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [x] 13. Backend checkpoint — all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Frontend scaffolding — Next.js 14, Tailwind, dependencies
  - Scaffold `frontend/` with `npx create-next-app@14 --typescript --tailwind --app --src-dir no --import-alias "@/*"`
  - Install additional dependencies: `fast-check`, `vitest`, `@vitejs/plugin-react`, `@testing-library/react`, `@testing-library/jest-dom`
  - Create `frontend/public/sounds/` directory with `.gitkeep` (actual `.mp3` files are generated by `sounds_gen/generate_sounds.py`)
  - Create `frontend/app/layout.tsx` with root layout, Tailwind base styles, and `<html lang="en">`
  - Create `frontend/next.config.js` with any required App Router settings
  - Add `vitest.config.ts` configured for React + jsdom
  - _Requirements: 8.1_

- [x] 15. TypeScript types and shared interfaces
  - Create `frontend/types/index.ts` defining all shared TypeScript types from the design: `VibeMode`, `Character`, `SoundEffect`, `ArtifactType`, `Segment`, `ArtifactData`, `EpisodeMetadata`, `AnalyzeResponse`, `InterruptResponse`, `PlaybackState`
  - _Requirements: 4.2, 6.3, 8.1_

- [x] 16. URL validation utility
  - Create `frontend/lib/validation.ts` exporting `isValidGitHubUrl(url: string): boolean` that tests against `^https://github\.com/[^/]+/[^/]+$`
  - _Requirements: 1.2_

  - [ ]* 16.1 Write property test I I have updated the author name in metadata dot JSON because that was needed to be updated. Because, actually, we don't have to match the GitHub username. We actually have to match the retool community username. So I have corrected it and saved it. And, also, I have added thecover.png. Now you will just need to push it to the new GitHub account. Okay? Make sure, as I told you previously, very, you know, many times that, you know, each each component is built for a separate GitHub account. So we will do a new login with a different GitHub account. I'm new I'm sharing you the details to which account we have to push it up.for URL validation (Property 1)
    - **Property 1: URL Validation Rejects All Invalid Inputs**
    - Use fast-check `fc.string()` and `fc.constantFrom(...)` to generate both valid and invalid URL strings; verify `isValidGitHubUrl` returns `true` only for strings matching the exact pattern
    - **Validates: Requirements 1.2, 1.5**

- [x] 17. VibeSelector component
  - Create `frontend/components/VibeSelector.tsx`
  - Render exactly three radio-style buttons: "Roast", "Deep Dive", "Beginner Friendly"
  - Accept `onSelect: (vibe: VibeMode) => void` and `selected: VibeMode | null` props
  - Visually highlight the selected option using Tailwind classes
  - _Requirements: 2.1, 2.5_

  - [ ]* 17.1 Write component tests for VibeSelector
    - Test: renders exactly 3 options
    - Test: clicking each option calls `onSelect` with the correct `VibeMode` value
    - Test: selected option has the highlighted visual state
    - _Requirements: 2.1, 2.5_

- [x] 18. Landing page — URL input, vibe selection, form submission, loading state
  - Create `frontend/app/page.tsx`
  - Render a URL text input and the `VibeSelector` component
  - Validate URL on submit using `isValidGitHubUrl`; display inline error message on invalid input
  - Disable the submit button until both a valid URL and a vibe are selected
  - On submit, POST `{ github_url, vibe }` to the backend `/analyze` endpoint
  - Show a loading spinner/skeleton while awaiting the response
  - On success, store `{ script, metadata }` in `sessionStorage` and navigate to `/episode`
  - On error, display the `detail` message inline and clear the loading state
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.5, 8.6_

  - [ ]* 18.1 Write component tests for landing page
    - Test: submit button is disabled without a vibe selected
    - Test: inline validation error appears for invalid URL
    - Test: loading state is shown while request is in flight
    - Test: error message is displayed on non-200 response
    - _Requirements: 1.1, 1.2, 2.5, 8.6_

- [x] 19. Player component
  - Create `frontend/components/Player.tsx`
  - Accept `character: Character | null`, `isPlaying: boolean`, and `onToggle: () => void` props
  - Display the current character's name (capitalized) while audio is playing
  - Render an animated waveform or audio indicator (CSS animation) while `isPlaying` is true
  - _Requirements: 8.2, 8.5_

  - [ ]* 19.1 Write component tests for Player
    - Test: displays the correct character name for each of the four characters
    - Test: waveform indicator is visible when `isPlaying` is true and hidden when false
    - _Requirements: 8.2, 8.5_

- [x] 20. ArtifactPanel component
  - Create `frontend/components/ArtifactPanel.tsx`
  - Accept `artifactType: ArtifactType` and `artifactData: ArtifactData` props
  - When `artifactType` is not null, call the Thesys C1 API client-side to render the generative UI component
  - When `artifactType` is null, retain the previously rendered artifact without clearing
  - On Thesys error, log to console and leave the panel in its previous state
  - _Requirements: 9.1, 9.2, 9.3, 9.5_

  - [ ]* 20.1 Write property test for ArtifactPanel artifact retention (Property 16)
    - **Property 16: ArtifactPanel Retains Last Artifact on Null Segments**
    - Use fast-check to generate sequences of `ArtifactType` values (mix of non-null and null); verify the panel always displays the most recently non-null artifact when the current segment has `artifact: null`
    - **Validates: Requirements 9.3**

- [x] 21. InterruptBtn component
  - Create `frontend/components/InterruptBtn.tsx`
  - Accept `onAudioReady: (blob: Blob) => void` and `disabled: boolean` props
  - On `mousedown`/`touchstart`: request microphone permission and begin `MediaRecorder` capture
  - On `mouseup`/`touchend`: stop recording and call `onAudioReady` with the recorded audio blob
  - Apply a pulsing CSS animation while recording is active
  - _Requirements: 10.1, 10.2, 10.3_

  - [ ]* 21.1 Write component tests for InterruptBtn
    - Test: recording begins on press and stops on release
    - Test: `onAudioReady` is called with a Blob on release
    - Test: pulsing animation class is applied during recording
    - _Requirements: 10.1, 10.2, 10.3_

- [x] 22. Episode player page — playback state machine and segment sequencing
  - Create `frontend/app/episode/page.tsx`
  - On mount, read `{ script, metadata }` from `sessionStorage`; redirect to `/` if missing
  - Implement the playback state machine with states: `idle → playing_sound → playing_speech → paused → interrupted → complete`
  - For each segment: if `sound_before` is not null, play the corresponding `frontend/public/sounds/{sound_before}.mp3` first, then play the segment's TTS audio decoded from `audio_b64`
  - If `sound_before` is null, play the TTS audio immediately
  - When a segment with a non-null `artifact` begins, pass the artifact type and data to `ArtifactPanel`
  - Advance to the next segment automatically when the current audio ends
  - Display an end-of-episode state when all segments have played
  - Render `Player`, `ArtifactPanel`, and `InterruptBtn`
  - On `InterruptBtn` audio ready: pause current audio, POST `multipart/form-data` with `audio` blob and `github_url` to `/interrupt`, play the answer audio, then resume from the paused position
  - On interrupt error: display a brief error toast and resume playback
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 9.1, 9.2, 9.3, 10.1, 10.2, 10.3, 10.7, 10.8_

  - [ ]* 22.1 Write property test for sequential segment playback (Property 14)
    - **Property 14: Sequential Segment Playback**
    - Use fast-check to generate scripts of varying lengths; mock audio playback and verify segments are played in index order with no skips
    - **Validates: Requirements 8.3**

  - [ ]* 22.2 Write property test for sound effect sequencing (Property 12)
    - **Property 12: Sound Effect Sequencing**
    - Use fast-check to generate segments with random `sound_before` values (null and non-null); verify sound effect audio is triggered before TTS audio when non-null, and TTS begins immediately when null
    - **Validates: Requirements 7.2, 7.3**

  - [ ]* 22.3 Write property test for character name display (Property 13)
    - **Property 13: Character Name Display During Playback**
    - Use fast-check to generate scripts; verify the Player component displays the correct character name for each segment while that segment's audio is active
    - **Validates: Requirements 8.2**

  - [ ]* 22.4 Write integration test for full episode flow
    - Mock the backend `/analyze` response; verify form submission → navigation → segment playback → end-of-episode state
    - Mock the backend `/interrupt` response; verify pause → answer playback → resume
    - _Requirements: 8.1, 8.3, 8.4, 10.7_

- [x] 23. Frontend checkpoint — all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 24. Sound effects generator script
  - Create `sounds_gen/generate_sounds.py`
  - Read `ELEVENLABS_API_KEY` from environment (load `.env` via `python-dotenv`)
  - Define a list of all 8 sound effect names with descriptive text prompts for the ElevenLabs Sound Effects API: `crowd_gasp`, `keyboard_typing`, `paper_flip`, `record_scratch`, `applause`, `thinking_hmm`, `transition_jingle`, `mic_beep`
  - For each sound, call the ElevenLabs Sound Effects API and write the resulting `.mp3` to `frontend/public/sounds/{name}.mp3`
  - Print progress to stdout; skip files that already exist
  - Add a `README` note in the script header: "Run once during setup — never run at runtime"
  - _Requirements: 7.1, 7.4, 7.5_

- [x] 25. Final integration checkpoint — all tests pass
  - Ensure all backend and frontend tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The design has 19 correctness properties — all are covered by property test sub-tasks above
- Property tests use Hypothesis (backend) and fast-check (frontend) with 100 iterations minimum
- Sound effect `.mp3` files must be generated by running `sounds_gen/generate_sounds.py` once before the frontend will have working sound effects
- The ElevenLabs Sound Effects API is ONLY called from `sounds_gen/generate_sounds.py` — never at runtime
- `.kiro/` must never appear in `.gitignore`
