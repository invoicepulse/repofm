# RepoFM

Turn any public GitHub repository into a 3-minute AI podcast episode. Four characters — Narrator, Skeptic, Fan, and Intern — debate, roast, and analyze the codebase. Built for the ElevenLabs x Kiro Hackathon.

## Features

- **Multi-character podcast**: Four distinct AI voices discuss your codebase
- **Vibe Modes**: Choose Roast, Deep Dive, or Beginner Friendly
- **Live artifacts**: Charts and reports appear on screen as the episode plays
- **Voice interrupt**: Ask questions mid-episode using your microphone

## Architecture

| Layer | Tech | Deploy |
|-------|------|--------|
| Frontend | Next.js 14 (App Router, TypeScript, Tailwind) | Vercel |
| Backend | Python FastAPI | Azure VM |
| LLM | Cloudflare Workers AI (kimi-k2.5) | Cloudflare |
| TTS / STT | ElevenLabs API | ElevenLabs |
| Artifacts | Thesys C1 API | Thesys |
| Ingestion | Self-hosted GitIngest | Azure VM |

## Setup

### Prerequisites

- Node.js 18+
- Python 3.11+
- An ElevenLabs API key
- A Cloudflare account with Workers AI access
- A Thesys C1 API key

### 1. Clone and configure environment

```bash
git clone https://github.com/your-username/repofm.git
cd repofm
cp .env.example .env
# Edit .env with your real API keys
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ELEVENLABS_API_KEY` | ElevenLabs API key for TTS and STT |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID for Workers AI |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token for Workers AI |
| `THESYS_API_KEY` | Thesys C1 API key for live artifacts |
| `GITINGEST_URL` | GitIngest service URL (default: `http://20.118.230.124:8000`) |
| `VOICE_ID_NARRATOR` | ElevenLabs voice ID for the Narrator character |
| `VOICE_ID_SKEPTIC` | ElevenLabs voice ID for the Skeptic character |
| `VOICE_ID_FAN` | ElevenLabs voice ID for the Fan character |
| `VOICE_ID_INTERN` | ElevenLabs voice ID for the Intern character |

See `.env.example` for a template with placeholder values.

## Project Structure

```
repofm/
├── frontend/       Next.js 14 App Router — UI, playback, artifacts
├── backend/        Python FastAPI — ingestion, LLM, TTS, STT
├── .kiro/          Kiro specs, steering, and hooks (committed)
├── .env.example    Placeholder environment variables
├── .gitignore      Ignores .env — never ignores .kiro/
└── LICENSE         MIT
```

## License

MIT — see [LICENSE](LICENSE) for details.
