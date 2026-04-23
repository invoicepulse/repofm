---
inclusion: always
---
inclusion: always
RepoFM — Tech Stack & Build
Frontend

Framework: Next.js 14 with App Router (TypeScript)
Styling: Tailwind CSS
Package manager: npm
Deploy: Vercel (free tier)

Backend

Framework: Python FastAPI
Package manager: pip
Deploy: Azure VM — same instance where GitIngest is already running
NO Railway. NO Docker. Azure only.

External Services
ServiceProviderUsageRepo ingestionSelf-hosted GitIngestPOST http://20.118.230.124:8000/ with { url }LLMCloudflare Workers AI@cf/moonshotai/kimi-k2.5 — 256K context windowTTSElevenLabs TTS API4 different voices, one per character, called per segmentSTTElevenLabs STT APITranscribes user voice during interruptSound EffectsElevenLabs Sound Effects APIPre-generated ONCE into static .mp3 — NOT called at runtimeLive ArtifactsThesys C1 APIGenerative UI charts/reports, free tier (5K calls/month)
Environment Variables
ELEVENLABS_API_KEY=
CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_API_TOKEN=
THESYS_API_KEY=
GITINGEST_URL=http://20.118.230.124:8000

.env is gitignored — never commit real keys
.env.example with placeholders is committed

Backend Endpoints

POST /analyze — input: { github_url, vibe } — output: { script[], metadata }
POST /interrupt — input: audio blob — output: { answer_text, audio base64 }
GET /health — returns { status: ok }

Common Commands
Frontend
bashnpm install
npm run dev
npm run build
Backend
bashpip install -r requirements.txt
uvicorn main:app --reload
Hard Rules

NEVER hardcode API keys — always use environment variables
.kiro/ must NEVER be in .gitignore
NO Railway, NO Docker
Sound effects are static files — ElevenLabs Sound Effects API is only used in sounds_gen/generate_sounds.py (run once during setup)
MIT license required