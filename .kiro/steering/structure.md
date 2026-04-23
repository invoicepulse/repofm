---
inclusion: always
---
# RepoFM — Project Structure

repofm/
├── frontend/                   Next.js 14 — deployed on Vercel
│   ├── app/
│   │   ├── page.tsx            Landing page: URL input + vibe selector
│   │   └── episode/page.tsx    Episode player + artifact panel
│   ├── components/
│   │   ├── Player.tsx          Audio controls, waveform, speaker name
│   │   ├── InterruptBtn.tsx    Pulsing mic button
│   │   ├── ArtifactPanel.tsx   Thesys C1 renders here
│   │   └── VibeSelector.tsx    3-option vibe picker
│   └── public/sounds/          Pre-generated static .mp3 files — NEVER regenerated at runtime
│       ├── crowd_gasp.mp3
│       ├── keyboard_typing.mp3
│       ├── paper_flip.mp3
│       ├── record_scratch.mp3
│       ├── applause.mp3
│       ├── thinking_hmm.mp3
│       ├── transition_jingle.mp3
│       └── mic_beep.mp3
│
├── backend/                    Python FastAPI — deployed on Azure VM
│   ├── main.py                 FastAPI app + all routes
│   ├── ingest.py               Calls GitIngest at 20.118.230.124:8000
│   ├── script_gen.py           Calls Cloudflare kimi-k2.5, returns script JSON
│   ├── tts.py                  ElevenLabs TTS per segment
│   ├── stt.py                  ElevenLabs STT for interrupts
│   ├── artifacts.py            Thesys C1 artifact trigger logic
│   ├── rate_limit.py           IP-based limiter (in-memory dict)
│   └── cache.py                Caches codebase text per repo URL (for interrupt reuse)
│
├── sounds_gen/
│   └── generate_sounds.py      Run ONCE only — generates all .mp3 via ElevenLabs Sound Effects API
│
├── .kiro/                      COMMITTED — never in .gitignore
│   ├── specs/
│   ├── steering/
│   └── hooks/
│
├── .env                        Real keys — GITIGNORED
├── .env.example                Placeholder keys — COMMITTED
├── .gitignore                  Includes .env — never includes .kiro
├── LICENSE                     MIT
└── README.md

Conventions

Frontend and backend are completely separate top-level directories
App Router conventions: page.tsx, layout.tsx, loading.tsx, error.tsx
Backend organized by concern — one file per responsibility (ingest, tts, stt, etc.)
All secrets via environment variables only — never hardcoded