"use client";

import { useState, useRef, FormEvent, useCallback, useEffect } from "react";
import Image from "next/image";
import { isValidGitHubUrl } from "@/lib/validation";
import VibeSelector from "@/components/VibeSelector";
import Player from "@/components/Player";
import ArtifactPanel from "@/components/ArtifactPanel";
import type { VibeMode, Segment, EpisodeMetadata, PlaybackState, ArtifactData } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "/_/backend";
const PLAY_AFTER = 3; // Start playback after this many segments

function base64ToAudioUrl(b64: string): string {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return URL.createObjectURL(new Blob([bytes], { type: "audio/mpeg" }));
}

export default function Home() {
  // --- Form state ---
  const [url, setUrl] = useState("");
  const [vibe, setVibe] = useState<VibeMode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStep, setProgressStep] = useState("");

  // --- Episode state ---
  const [mode, setMode] = useState<"form" | "player">("form");
  const [segments, setSegments] = useState<Segment[]>([]);
  const [metadata, setMetadata] = useState<EpisodeMetadata | null>(null);
  const [streamDone, setStreamDone] = useState(false);
  const [playbackState, setPlaybackState] = useState<PlaybackState>("idle");
  const [segmentIndex, setSegmentIndex] = useState(0);

  // --- Refs ---
  const segmentsRef = useRef<Segment[]>([]);
  const streamDoneRef = useRef(false);
  const speechAudioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlsRef = useRef<string[]>([]);
  const waitingForRef = useRef<number | null>(null);
  const startedPlaybackRef = useRef(false);

  const isFormValid = url.trim() !== "" && vibe !== null;

  // Cleanup object URLs
  useEffect(() => {
    const urls = objectUrlsRef.current;
    return () => { urls.forEach((u) => URL.revokeObjectURL(u)); };
  }, []);

  // Play segment by index — uses refs, no stale closures
  const playSegment = useCallback((index: number) => {
    const segs = segmentsRef.current;

    if (index >= segs.length && streamDoneRef.current) {
      setPlaybackState("complete");
      waitingForRef.current = null;
      return;
    }

    if (index >= segs.length) {
      waitingForRef.current = index;
      return; // Will be triggered when segment arrives
    }

    waitingForRef.current = null;
    const seg = segs[index];
    setSegmentIndex(index);

    const audioUrl = base64ToAudioUrl(seg.audio_b64);
    objectUrlsRef.current.push(audioUrl);
    const audio = new Audio(audioUrl);
    speechAudioRef.current = audio;
    setPlaybackState("playing_speech");

    audio.onended = () => { speechAudioRef.current = null; playSegment(index + 1); };
    audio.onerror = () => { speechAudioRef.current = null; playSegment(index + 1); };
    audio.play().catch(() => playSegment(index + 1));
  }, []);

  // Handle new segment arriving
  const onSegmentArrived = useCallback((seg: Segment) => {
    segmentsRef.current = [...segmentsRef.current, seg];
    setSegments(prev => [...prev, seg]);

    // Switch to player mode after enough segments
    if (segmentsRef.current.length >= PLAY_AFTER && !startedPlaybackRef.current) {
      startedPlaybackRef.current = true;
      setMode("player");
      setLoading(false);
      playSegment(0);
    }

    // If playback was waiting for this segment, play it
    if (waitingForRef.current !== null && waitingForRef.current < segmentsRef.current.length) {
      const idx = waitingForRef.current;
      waitingForRef.current = null;
      playSegment(idx);
    }
  }, [playSegment]);

  // Handle stream finished
  const onStreamDone = useCallback(() => {
    streamDoneRef.current = true;
    setStreamDone(true);

    // If we never got enough segments to start, start now
    if (!startedPlaybackRef.current && segmentsRef.current.length > 0) {
      startedPlaybackRef.current = true;
      setMode("player");
      setLoading(false);
      playSegment(0);
    }

    // If waiting past end, mark complete
    if (waitingForRef.current !== null && waitingForRef.current >= segmentsRef.current.length) {
      setPlaybackState("complete");
      waitingForRef.current = null;
    }
  }, [playSegment]);

  // Submit form — start SSE
  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (!isValidGitHubUrl(url.trim())) {
      setError("Invalid GitHub URL. Expected format: https://github.com/{owner}/{repo}");
      return;
    }
    if (!vibe) return;

    // Reset episode state
    segmentsRef.current = [];
    streamDoneRef.current = false;
    startedPlaybackRef.current = false;
    waitingForRef.current = null;
    setSegments([]);
    setMetadata(null);
    setStreamDone(false);
    setSegmentIndex(0);
        setPlaybackState("idle");

    setLoading(true);
    setProgress(0);
    setProgressStep("Connecting...");

    try {
      const res = await fetch(`${API_URL}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ github_url: url.trim(), vibe }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        setError(body?.detail || `Request failed (${res.status})`);
        setLoading(false);
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const dataStr = line.slice(6).trim();
          if (!dataStr) continue;

          try {
            const data = JSON.parse(dataStr);
            if (data.step !== undefined && data.percent !== undefined) {
              setProgress(data.percent);
              setProgressStep(data.step);
            } else if (data.repo_name !== undefined) {
              setMetadata(data as EpisodeMetadata);
            } else if (data.character !== undefined && data.audio_b64 !== undefined) {
              onSegmentArrived(data as Segment);
            } else if (data.detail !== undefined) {
              throw new Error(data.detail);
            }
          } catch (parseErr) {
            if (parseErr instanceof Error && parseErr.message !== "Unexpected end of JSON input") {
              throw parseErr;
            }
          }
        }
      }

      onStreamDone();
    } catch (err) {
      if (!startedPlaybackRef.current) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
        setLoading(false);
      }
    }
  }

  // Pause/Resume
  const handleToggle = useCallback(() => {
    if (playbackState === "playing_speech") {
      speechAudioRef.current?.pause();
      setPlaybackState("paused");
    } else if (playbackState === "paused") {
      speechAudioRef.current?.play().catch(() => {});
      setPlaybackState("playing_speech");
    } else if (playbackState === "complete") {
      setSegmentIndex(0);
            playSegment(0);
    }
  }, [playbackState, playSegment]);

  // New episode
  const handleNewEpisode = useCallback(() => {
    speechAudioRef.current?.pause();
    speechAudioRef.current = null;
    setMode("form");
    setSegments([]);
    setMetadata(null);
    setStreamDone(false);
    setPlaybackState("idle");
    setSegmentIndex(0);
        setLoading(false);
    setProgress(0);
    segmentsRef.current = [];
    streamDoneRef.current = false;
    startedPlaybackRef.current = false;
    waitingForRef.current = null;
  }, []);

  const currentSegment = segments[segmentIndex] ?? null;
  const isPlaying = playbackState === "playing_speech";
  const totalSegments = streamDone ? segments.length : Math.max(segments.length, segmentIndex + 1);
  const artifactData: ArtifactData = metadata?.artifact_data ?? {
    language_chart: {}, file_size_graph: [], security_report: [], project_structure: { total_files: 0, file_types: {} },
  };

  // ===================== FORM VIEW =====================
  if (mode === "form") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-between px-4 py-12 bg-[#09090f]">
        <div className="flex-1 flex flex-col items-center justify-center w-full">
          {/* HERO SECTION */}
          <div className="flex flex-col items-center gap-6 text-center max-w-2xl mb-10">
            <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-emerald-500/10 text-emerald-400 text-sm font-medium">
              🎧 AI-Powered Podcast Generator
            </span>
            <h1 className="text-5xl md:text-6xl font-bold tracking-tight text-white">
              Turn any GitHub repo into a{" "}
              <span className="text-emerald-400">podcast episode</span>
            </h1>
            <p className="text-lg text-gray-400 max-w-lg">
              4 AI characters debate, roast, and analyze your codebase in minutes.
            </p>
          </div>

          {/* CHARACTER PREVIEW */}
          <div className="flex items-center justify-center gap-6 mb-10">
            {[
              { src: "/avatars/narrator.jpeg", name: "Narrator" },
              { src: "/avatars/skeptic.jpeg", name: "Skeptic" },
              { src: "/avatars/fan.jpeg", name: "Fan" },
              { src: "/avatars/intern.jpeg", name: "Intern" },
            ].map((char, i) => (
              <div key={char.name} className="flex flex-col items-center gap-1.5" style={{ marginLeft: i > 0 ? "-8px" : "0" }}>
                <div className="w-10 h-10 rounded-full overflow-hidden border-2 border-[#13131f]">
                  <Image src={char.src} alt={char.name} width={40} height={40} className="object-cover w-full h-full" />
                </div>
                <span className="text-[11px] text-gray-500 font-medium">{char.name}</span>
              </div>
            ))}
          </div>

          {/* FORM CARD */}
          <div className="w-full max-w-xl bg-[#13131f] rounded-2xl p-8 border border-[#1e1e3a]">
            <form onSubmit={handleSubmit} className="w-full flex flex-col gap-6" noValidate>
              <div className="flex flex-col gap-2">
                <label htmlFor="repo-url" className="text-sm font-medium text-zinc-300">GitHub Repository URL</label>
                <input id="repo-url" type="url" placeholder="Paste a GitHub URL..." value={url}
                  onChange={(e) => { setUrl(e.target.value); if (error) setError(null); }} disabled={loading}
                  className="w-full px-4 py-3 rounded-xl bg-[#0f0f1a] border border-[#1e1e3a] text-white placeholder-zinc-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-colors disabled:opacity-50" />
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium text-zinc-300">Choose your vibe</label>
                <VibeSelector selected={vibe} onSelect={(v) => { setVibe(v); if (error) setError(null); }} />
              </div>

              {error && (
                <p className="text-red-400 text-sm bg-red-950/30 border border-red-800/40 rounded-lg px-4 py-2" role="alert">{error}</p>
              )}

              <button type="submit" disabled={!isFormValid || loading}
                className="w-full py-3.5 rounded-xl font-semibold text-black bg-emerald-500 hover:bg-emerald-400 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
                {loading ? "Generating..." : "Generate Episode"}
              </button>

              {loading && (
                <div className="w-full flex flex-col gap-3">
                  <div className="w-full h-3 bg-[#0f0f1a] rounded-full overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 rounded-full transition-all duration-500 ease-out"
                      style={{ width: `${Math.max(progress, 2)}%` }} />
                  </div>
                  <div className="flex justify-between items-center">
                    <p className="text-gray-400 text-sm">{progressStep}</p>
                    <p className="text-emerald-400 text-sm font-medium">{progress}%</p>
                  </div>
                </div>
              )}
            </form>
          </div>
        </div>

        {/* FOOTER */}
        <div className="flex flex-col items-center gap-1 mt-12">
          <p className="text-xs text-gray-600">Built for ElevenLabs × Kiro Hackathon</p>
          <p className="text-xs text-gray-700">Powered by Groq, ElevenLabs, GitIngest</p>
        </div>
      </div>
    );
  }

  // ===================== PLAYER VIEW =====================

  const vibeColor: Record<string, string> = {
    roast: "bg-red-500",
    deep_dive: "bg-emerald-500",
    beginner_friendly: "bg-green-500",
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#09090f]">
      {/* Top bar */}
      <header className="h-16 bg-[#0f0f1a] border-b border-[#1e1e3a] flex items-center px-6 flex-shrink-0">
        {/* Left: Logo */}
        <h1 className="text-xl font-bold tracking-tight text-white">
          Repo<span className="text-emerald-400">FM</span>
        </h1>

        {/* Center: Repo name + vibe pill */}
        <div className="flex-1 flex items-center justify-center gap-3">
          {metadata && (
            <>
              <span className="text-[#f8fafc] text-sm font-medium">{metadata.repo_name}</span>
              <span
                className={`px-2.5 py-0.5 rounded-full text-xs font-semibold text-white ${
                  vibeColor[metadata.vibe] ?? "bg-emerald-500"
                }`}
              >
                {metadata.vibe.replace(/_/g, " ")}
              </span>
            </>
          )}
        </div>

        {/* Right: Segment counter */}
        <span className="text-[#64748b] text-sm">
          {totalSegments > 0
            ? playbackState === "complete"
              ? `${segments.length} of ${segments.length} segments`
              : `Segment ${segmentIndex + 1} of ${totalSegments}`
            : ""}
        </span>
      </header>

      {/* Main content */}
      <div className="flex-1 flex flex-col lg:flex-row gap-6 p-6 max-w-[1400px] mx-auto w-full">
        {/* Left column: Player + progress */}
        <div className="w-full lg:w-[55%] flex flex-col gap-4">
          <Player
            character={currentSegment?.character ?? null}
            isPlaying={isPlaying}
            onToggle={handleToggle}
            text={currentSegment?.text}
          />

          {/* Still loading indicator */}
          {!streamDone && (
            <div className="flex items-center gap-2 px-3 py-2 bg-emerald-950/30 border border-emerald-800/30 rounded-lg">
              <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-emerald-300 text-xs">
                Generating remaining segments... {segments.length} ready
              </span>
            </div>
          )}

          {/* Episode progress bar */}
          {totalSegments > 0 && (
            <div className="flex flex-col gap-2">
              <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full transition-all duration-300"
                  style={{
                    width: `${
                      playbackState === "complete"
                        ? 100
                        : (segmentIndex / totalSegments) * 100
                    }%`,
                  }}
                />
              </div>
              <span className="text-[#64748b] text-xs">
                {playbackState === "complete"
                  ? `Segment ${segments.length} of ${segments.length}`
                  : `Segment ${segmentIndex + 1} of ${totalSegments}`}
              </span>
            </div>
          )}

          {/* Episode complete */}
          {playbackState === "complete" && (
            <div className="flex flex-col items-center gap-4 py-8 bg-[#13131f] rounded-2xl">
              <span className="text-4xl">🎧</span>
              <h2 className="text-xl font-semibold text-white">Episode Complete</h2>
              <p className="text-[#64748b] text-sm text-center max-w-sm">
                That&apos;s a wrap{metadata ? ` on ${metadata.repo_name}` : ""}!
              </p>
              <div className="flex gap-3 mt-2">
                <button
                  onClick={handleToggle}
                  className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium transition-colors"
                >
                  Replay
                </button>
                <button
                  onClick={handleNewEpisode}
                  className="px-5 py-2 rounded-lg bg-[#13131f] hover:bg-[#1e1e3a] text-[#f8fafc] text-sm font-medium transition-colors border border-[#1e1e3a]"
                >
                  New Episode
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Right column: Artifact panel */}
        <div className="w-full lg:w-[45%] lg:sticky lg:top-6 lg:self-start">
          <ArtifactPanel artifactData={artifactData} />
        </div>
      </div>
    </div>
  );
}
