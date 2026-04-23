"use client";

import { useRef, useState, useCallback } from "react";

interface InterruptBtnProps {
  onAudioReady: (blob: Blob) => void;
  disabled: boolean;
}

export default function InterruptBtn({ onAudioReady, disabled }: InterruptBtnProps) {
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const startRecording = useCallback(async () => {
    if (disabled) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mediaRecorder.mimeType || "audio/webm" });
        chunksRef.current = [];
        // Stop all tracks to release the microphone
        stream.getTracks().forEach((track) => track.stop());
        onAudioReady(blob);
      };

      mediaRecorder.start();
      setRecording(true);
    } catch {
      // Microphone permission denied or unavailable — silently ignore
    }
  }, [disabled, onAudioReady]);

  const stopRecording = useCallback(() => {
    const mediaRecorder = mediaRecorderRef.current;
    if (mediaRecorder && mediaRecorder.state === "recording") {
      mediaRecorder.stop();
      mediaRecorderRef.current = null;
      setRecording(false);
    }
  }, []);

  return (
    <div className="flex flex-col items-center gap-3">
      {/* Pulsing ring container */}
      <div className="relative flex items-center justify-center">
        {/* Pulsing ring — visible only while recording */}
        {recording && (
          <span
            className="absolute inset-0 rounded-full bg-emerald-500/30 animate-interrupt-pulse"
            aria-hidden="true"
          />
        )}

        {/* Mic button */}
        <button
          type="button"
          disabled={disabled}
          onMouseDown={startRecording}
          onMouseUp={stopRecording}
          onTouchStart={startRecording}
          onTouchEnd={stopRecording}
          aria-label={recording ? "Release to send question" : "Hold to ask a question"}
          className={`
            relative z-10 w-16 h-16 rounded-full flex items-center justify-center
            transition-all duration-200 select-none touch-none
            ${
              recording
                ? "bg-emerald-600 border-2 border-emerald-400 shadow-lg shadow-emerald-500/40 scale-110"
                : disabled
                ? "bg-zinc-800 border-2 border-zinc-700 opacity-40 cursor-not-allowed"
                : "bg-zinc-800 border-2 border-zinc-600 hover:border-emerald-500 hover:bg-zinc-700 cursor-pointer"
            }
          `}
        >
          {/* Microphone SVG icon */}
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className={`w-7 h-7 ${recording ? "text-white" : "text-zinc-400"}`}
            aria-hidden="true"
          >
            <path d="M8.25 4.5a3.75 3.75 0 1 1 7.5 0v8.25a3.75 3.75 0 1 1-7.5 0V4.5Z" />
            <path d="M6 10.5a.75.75 0 0 1 .75.75v1.5a5.25 5.25 0 1 0 10.5 0v-1.5a.75.75 0 0 1 1.5 0v1.5a6.751 6.751 0 0 1-6 6.709v2.291h3a.75.75 0 0 1 0 1.5h-7.5a.75.75 0 0 1 0-1.5h3v-2.291a6.751 6.751 0 0 1-6-6.709v-1.5A.75.75 0 0 1 6 10.5Z" />
          </svg>
        </button>
      </div>

      {/* Status text */}
      <span className={`text-sm font-medium ${recording ? "text-emerald-400" : "text-zinc-500"}`}>
        {recording ? "Listening…" : "Hold to ask"}
      </span>
    </div>
  );
}
