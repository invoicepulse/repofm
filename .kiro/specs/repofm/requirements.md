# Requirements Document

## Introduction

RepoFM is a web application that transforms any public GitHub repository into a 3-minute AI-generated podcast episode. Four distinct characters — Narrator, Skeptic, Fan, and Intern — debate, roast, and analyze the codebase. Users select a Vibe Mode before generation, can watch live UI artifacts appear as the episode plays, and can interrupt mid-episode with a voice question. Built for the ElevenLabs x Kiro Hackathon.

## Glossary

- **System**: The RepoFM web application (frontend + backend combined)
- **Frontend**: The Next.js 14 App Router application deployed on Vercel
- **Backend**: The Python FastAPI application deployed on the Azure VM
- **GitIngest**: The self-hosted codebase ingestion service at `http://20.118.230.124:8000`
- **LLM**: Cloudflare Workers AI model `@cf/moonshotai/kimi-k2.5` with 256K context window
- **TTS_Service**: ElevenLabs Text-to-Speech API
- **STT_Service**: ElevenLabs Speech-to-Text API
- **Artifact_Service**: Thesys C1 API for generative UI artifacts
- **Script**: A JSON array of segments produced by the LLM, each containing character, text, sound cue, and artifact type
- **Segment**: A single element of the Script — one character's spoken line with optional sound and artifact metadata
- **Vibe_Mode**: One of three episode tones selected by the user: Roast, Deep Dive, or Beginner Friendly
- **Narrator**: The professional, calm character who introduces topics and summarizes
- **Skeptic**: The cynical senior dev character who critiques and roasts
- **Fan**: The enthusiastic junior dev character who finds genius in everything
- **Intern**: The confused beginner character who asks basic questions
- **Rate_Limiter**: The in-memory IP-based request throttle in the Backend
- **Sound_Effect**: A pre-generated static `.mp3` file stored in `frontend/public/sounds/`
- **Artifact**: A generative UI component (chart, graph, or report) rendered by the Thesys C1 API
- **Interrupt**: A user-initiated voice question submitted mid-episode via microphone

---

## Requirements

### Requirement 1: Repository URL Input and Validation

**User Story:** As a user, I want to paste a GitHub repository URL and have it validated before processing, so that I receive clear feedback if the URL is invalid before wasting time on generation.

#### Acceptance Criteria

1. THE Frontend SHALL render a text input field on the landing page that accepts a GitHub repository URL.
2. WHEN a user submits a URL that does not match the pattern `https://github.com/{owner}/{repo}`, THE Frontend SHALL display an inline validation error message before sending any request to the Backend.
3. WHEN a user submits a valid GitHub repository URL, THE Frontend SHALL send the URL and selected Vibe_Mode to the Backend `POST /analyze` endpoint.
4. IF the Backend receives a `github_url` value that references a private repository or a non-existent repository, THEN THE Backend SHALL return an HTTP 422 response with a descriptive error message.
5. IF the Backend receives a `github_url` value that is not a valid GitHub URL, THEN THE Backend SHALL return an HTTP 422 response with a descriptive error message.

---

### Requirement 2: Vibe Mode Selection

**User Story:** As a user, I want to choose a Vibe Mode before generating an episode, so that the tone and character balance of the podcast matches what I want to hear.

#### Acceptance Criteria

1. THE Frontend SHALL render exactly three selectable Vibe_Mode options: Roast, Deep Dive, and Beginner Friendly.
2. WHEN a user selects the Roast Vibe_Mode, THE Backend SHALL instruct the LLM to produce a Script where the Skeptic character delivers the majority of segments with a merciless critique tone.
3. WHEN a user selects the Deep Dive Vibe_Mode, THE Backend SHALL instruct the LLM to produce a Script where the Narrator character leads with balanced technical analysis.
4. WHEN a user selects the Beginner Friendly Vibe_Mode, THE Backend SHALL instruct the LLM to produce a Script where the Intern asks questions and the Fan explains concepts without technical jargon.
5. THE Frontend SHALL require a Vibe_Mode to be selected before the episode generation form can be submitted.

---

### Requirement 3: Codebase Ingestion

**User Story:** As a user, I want the system to automatically fetch and process the repository contents, so that the podcast is based on the actual code rather than generic commentary.

#### Acceptance Criteria

1. WHEN the Backend receives a valid `POST /analyze` request, THE Backend SHALL send a POST request to GitIngest at `http://20.118.230.124:8000` with the body `{ "url": "<github_url>" }`.
2. WHEN GitIngest returns the codebase text, THE Backend SHALL skip all files matching the patterns: `node_modules/`, `dist/`, `vendor/`, `*.lock`, `*.min.js`, `*.map`.
3. WHEN the ingested codebase text exceeds 256,000 tokens, THE Backend SHALL truncate the content by retaining the full file tree, the README, and the top 20 largest files by character count.
4. WHEN the ingested codebase text is within the 256,000 token limit, THE Backend SHALL pass the full content to the LLM without truncation.
5. IF GitIngest returns an error or is unreachable, THEN THE Backend SHALL return an HTTP 502 response with a descriptive error message to the Frontend.
6. THE Backend SHALL cache the ingested codebase text keyed by repository URL so that subsequent Interrupt requests for the same repository do not re-fetch from GitIngest.

---

### Requirement 4: Script Generation

**User Story:** As a user, I want the AI to generate a multi-character podcast script from the codebase, so that I get an entertaining and informative episode about the repository.

#### Acceptance Criteria

1. WHEN the Backend has ingested codebase text, THE Backend SHALL send the codebase text and Vibe_Mode to the LLM using the `@cf/moonshotai/kimi-k2.5` model via the Cloudflare Workers AI API.
2. THE Backend SHALL instruct the LLM via system prompt to return a valid JSON array where each element contains exactly the fields: `character`, `text`, `sound_before`, and `artifact`.
3. THE Backend SHALL enforce a maximum of 380 words total across all Segment `text` fields in the LLM prompt instruction.
4. WHEN the LLM returns a Script, THE Backend SHALL validate that the total word count across all `text` fields does not exceed 380 words.
5. IF the LLM returns a Script exceeding 380 words, THEN THE Backend SHALL truncate Segments from the end of the Script until the total word count is at or below 380 words.
6. THE Backend SHALL validate that each Segment `character` field contains one of: `narrator`, `skeptic`, `fan`, `intern`.
7. THE Backend SHALL validate that each Segment `sound_before` field contains one of: `crowd_gasp`, `keyboard_typing`, `paper_flip`, `record_scratch`, `applause`, `thinking_hmm`, `transition_jingle`, `mic_beep`, or `null`.
8. THE Backend SHALL validate that each Segment `artifact` field contains one of: `language_chart`, `file_size_graph`, `security_report`, `commit_graph`, `dependency_map`, or `null`.
9. IF the LLM returns a response that is not valid JSON, THEN THE Backend SHALL return an HTTP 500 response with a descriptive error message.
10. WHEN the Backend returns the Script to the Frontend, THE Backend SHALL include a `metadata` object containing at minimum the repository name and the selected Vibe_Mode.

---

### Requirement 5: Rate Limiting

**User Story:** As a system operator, I want to limit episode generation per IP address, so that the service is not abused and API costs remain controlled.

#### Acceptance Criteria

1. THE Rate_Limiter SHALL track the number of `POST /analyze` requests per client IP address using an in-memory dictionary.
2. WHEN a client IP address has made 3 or more `POST /analyze` requests within a 60-minute sliding window, THE Backend SHALL return an HTTP 429 response with a message indicating when the limit resets.
3. WHEN a client IP address has made fewer than 3 `POST /analyze` requests within the current 60-minute window, THE Backend SHALL process the request normally.
4. THE Rate_Limiter SHALL NOT persist state to disk or any external store — the limit resets when the Backend process restarts.

---

### Requirement 6: Text-to-Speech Audio Generation

**User Story:** As a user, I want each character's lines to be spoken in a distinct voice, so that the podcast feels like a real multi-person conversation.

#### Acceptance Criteria

1. THE Backend SHALL assign a unique ElevenLabs voice ID to each of the four characters: Narrator, Skeptic, Fan, and Intern.
2. WHEN the Backend has a validated Script, THE Backend SHALL call the TTS_Service for each Segment using the voice ID assigned to that Segment's `character`.
3. THE Backend SHALL return the generated audio for each Segment as base64-encoded audio data within the Script response to the Frontend.
4. IF the TTS_Service returns an error for any Segment, THEN THE Backend SHALL return an HTTP 502 response with a message identifying which Segment failed.
5. THE Backend SHALL call the TTS_Service for each Segment sequentially in Script order to preserve episode continuity.

---

### Requirement 7: Sound Effects Playback

**User Story:** As a user, I want to hear sound effects before each character's line, so that the episode feels dynamic and radio-like.

#### Acceptance Criteria

1. THE Frontend SHALL store all Sound_Effect files as static `.mp3` files in `frontend/public/sounds/` — the files are: `crowd_gasp.mp3`, `keyboard_typing.mp3`, `paper_flip.mp3`, `record_scratch.mp3`, `applause.mp3`, `thinking_hmm.mp3`, `transition_jingle.mp3`, `mic_beep.mp3`.
2. WHEN the Frontend is about to play a Segment whose `sound_before` field is not `null`, THE Frontend SHALL play the corresponding Sound_Effect `.mp3` file before playing the Segment's TTS audio.
3. WHEN the Frontend is about to play a Segment whose `sound_before` field is `null`, THE Frontend SHALL play the Segment's TTS audio immediately without a preceding Sound_Effect.
4. THE Frontend SHALL NOT call the ElevenLabs Sound Effects API at runtime — Sound_Effect files are pre-generated and static.
5. THE `sounds_gen/generate_sounds.py` script SHALL call the ElevenLabs Sound Effects API once during setup to generate all Sound_Effect `.mp3` files and write them to `frontend/public/sounds/`.

---

### Requirement 8: Episode Playback and Player UI

**User Story:** As a user, I want a clear player interface that shows me which character is speaking and lets me control playback, so that I can follow the episode easily.

#### Acceptance Criteria

1. THE Frontend SHALL navigate to the episode player page after receiving a successful Script response from the Backend.
2. WHEN the episode is playing, THE Frontend SHALL display the name of the character whose Segment is currently being spoken.
3. THE Frontend SHALL play Segments sequentially in the order returned by the Backend.
4. WHEN all Segments have been played, THE Frontend SHALL display an end-of-episode state indicating the episode is complete.
5. THE Frontend SHALL render a waveform or visual audio indicator while a Segment is playing.
6. THE Frontend SHALL display a loading state on the landing page while the Backend is processing the `POST /analyze` request.

---

### Requirement 9: Live Artifact Display

**User Story:** As a user, I want to see visual charts and reports appear on screen as the episode progresses, so that I can follow along with the analysis visually.

#### Acceptance Criteria

1. WHEN the Frontend begins playing a Segment whose `artifact` field is not `null`, THE Frontend SHALL send a request to the Artifact_Service (Thesys C1 API) to render the corresponding Artifact type.
2. THE Frontend SHALL render the Artifact returned by the Artifact_Service in the ArtifactPanel component alongside the audio player.
3. WHEN the Frontend begins playing a Segment whose `artifact` field is `null`, THE Frontend SHALL leave the ArtifactPanel in its previous state without clearing it.
4. THE Backend SHALL extract the data required for each Artifact type from the ingested codebase and include it in the Script metadata returned to the Frontend.
5. IF the Artifact_Service returns an error, THEN THE Frontend SHALL log the error and continue episode playback without displaying an Artifact for that Segment.

---

### Requirement 10: Voice Interrupt

**User Story:** As a user, I want to ask a question mid-episode using my microphone, so that I can get an immediate AI-generated answer about the codebase without stopping the episode permanently.

#### Acceptance Criteria

1. THE Frontend SHALL render a microphone button (InterruptBtn) on the episode player page that is accessible during episode playback.
2. WHEN a user presses the InterruptBtn, THE Frontend SHALL pause the current Segment's audio playback and begin recording audio from the user's microphone.
3. WHEN a user releases the InterruptBtn, THE Frontend SHALL stop recording and send the recorded audio blob to the Backend `POST /interrupt` endpoint.
4. WHEN the Backend receives a `POST /interrupt` request, THE Backend SHALL transcribe the audio using the STT_Service.
5. WHEN the STT_Service returns a transcript, THE Backend SHALL send the transcript and the cached codebase text for the current repository to the LLM to generate a concise answer.
6. THE Backend SHALL return the answer text and a base64-encoded TTS audio of the answer to the Frontend in the `POST /interrupt` response.
7. WHEN the Frontend receives the interrupt response, THE Frontend SHALL play the answer audio and then resume episode playback from the point where it was paused.
8. IF the STT_Service or LLM returns an error during interrupt processing, THEN THE Backend SHALL return an HTTP 502 response and THE Frontend SHALL display an error message and resume episode playback.

---

### Requirement 11: Health Check Endpoint

**User Story:** As a system operator, I want a health check endpoint, so that I can verify the Backend is running and reachable.

#### Acceptance Criteria

1. THE Backend SHALL expose a `GET /health` endpoint.
2. WHEN the `GET /health` endpoint is called, THE Backend SHALL return an HTTP 200 response with the body `{ "status": "ok" }`.

---

### Requirement 12: Environment Configuration and Security

**User Story:** As a developer, I want all API keys and secrets managed through environment variables, so that credentials are never committed to the repository.

#### Acceptance Criteria

1. THE System SHALL read all API keys (`ELEVENLABS_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `THESYS_API_KEY`) and service URLs (`GITINGEST_URL`) exclusively from environment variables.
2. THE Backend SHALL refuse to start and SHALL log a descriptive error if any required environment variable is missing at startup.
3. THE repository SHALL include a committed `.env.example` file containing placeholder values for all required environment variables.
4. THE `.gitignore` file SHALL include `.env` to prevent real credentials from being committed.
5. THE `.gitignore` file SHALL NOT include `.kiro/` — the `.kiro/` directory must be committed.
