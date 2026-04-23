---
inclusion: always
---
# RepoFM — Product Summary

RepoFM is an open-source web app that turns any public GitHub repository into a
3-minute AI podcast episode where 4 characters debate, roast, and analyze the codebase.
Built for the ElevenLabs x Kiro Hackathon.

## Core Flow
1. User pastes a GitHub repo URL and picks a Vibe Mode
2. Backend calls GitIngest to ingest the codebase text
3. Cloudflare kimi-k2.5 generates a multi-character episode script (max 380 words)
4. Frontend plays audio segment by segment — ElevenLabs TTS per character
5. Sound effects play before each segment (pre-generated static .mp3 files)
6. Thesys C1 artifacts appear on screen as episode progresses
7. User can interrupt mid-episode with a voice question via mic button

## Four Characters
- Narrator — professional, calm. Introduces topics, summarizes.
- Skeptic — cynical senior dev. Questions everything. Source of roast.
- Fan — enthusiastic junior. Finds genius in everything.
- Intern — confused beginner. Asks basic questions. Audience proxy.

## Vibe Modes (user picks before episode starts)
- Roast — Skeptic dominates. Merciless critique. High entertainment.
- Deep Dive — Narrator leads. Balanced technical analysis. Serious tone.
- Beginner Friendly — Intern asks questions. Fan explains. No jargon. Educational.

## Episode Script JSON Format
The LLM must return a JSON array. Frontend reads it segment by segment.
[{
  "character": "narrator|skeptic|fan|intern",
  "text": "...",
  "sound_before": "crowd_gasp|keyboard_typing|paper_flip|record_scratch|applause|thinking_hmm|transition_jingle|mic_beep|null",
  "artifact": "language_chart|file_size_graph|security_report|commit_graph|dependency_map|null"
}]

## Artifact Types
- language_chart — pie chart of language percentages
- file_size_graph — bar chart of largest files
- security_report — hardcoded secrets, exposed configs
- commit_graph — commit frequency over time
- dependency_map — key dependencies from package.json / requirements.txt

## Key Constraints
- Max 380 words total across ALL segments — enforce strictly in LLM prompt
- 3 episodes per IP per hour (in-memory rate limit, no auth system)
- Repos >256K tokens: smart truncation — keep file tree + README + top 20 largest files
- Always skip: node_modules/, dist/, vendor/, *.lock, *.min.js, *.map
- MIT licensed, public GitHub repo, open source submission
- .kiro/ folder MUST be committed — never in .gitignore