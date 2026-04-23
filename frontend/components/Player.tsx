"use client";

import Image from "next/image";
import { Character } from "@/types";

interface PlayerProps {
  character: Character | null;
  isPlaying: boolean;
  onToggle: () => void;
  text?: string;
}

const CHARACTER_CONFIG: Record<
  Character,
  { avatar: string; name: string; role: string }
> = {
  narrator: { avatar: "/avatars/narrator.jpeg", name: "Narrator", role: "Host" },
  skeptic: { avatar: "/avatars/skeptic.jpeg", name: "Skeptic", role: "Senior Dev" },
  fan: { avatar: "/avatars/fan.jpeg", name: "Fan", role: "Junior Dev" },
  intern: { avatar: "/avatars/intern.jpeg", name: "Intern", role: "New Hire" },
};

const ALL_CHARACTERS: Character[] = ["narrator", "skeptic", "fan", "intern"];

function EqualizerBars() {
  return (
    <div className="flex items-end gap-[2px] h-4">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="w-[3px] rounded-full bg-emerald-500"
          style={{
            animation: "equalizer 0.6s ease-in-out infinite",
            animationDelay: `${i * 150}ms`,
            height: "4px",
          }}
        />
      ))}
      <style jsx>{`
        @keyframes equalizer {
          0%, 100% { height: 4px; }
          50% { height: 16px; }
        }
      `}</style>
    </div>
  );
}

export default function Player({ character, isPlaying, onToggle, text }: PlayerProps) {
  const isSpeaking = isPlaying && character !== null;
  const activeConfig = character ? CHARACTER_CONFIG[character] : null;

  return (
    <div className="flex flex-col gap-4 w-full">
      {/* CURRENT SPEAKER CARD */}
      <div className="bg-[#13131f] rounded-2xl p-6">
        <div className="flex items-center gap-4">
          {/* Active speaker avatar */}
          <div
            className="relative flex-shrink-0 w-20 h-20 rounded-full overflow-hidden"
            style={
              isSpeaking && activeConfig
                ? {
                    boxShadow:
                      "0 0 0 3px #10b981, 0 0 20px rgba(16,185,129,0.5)",
                  }
                : { boxShadow: "0 0 0 3px #1e1e3a" }
            }
          >
            {activeConfig ? (
              <Image
                src={activeConfig.avatar}
                alt={activeConfig.name}
                width={80}
                height={80}
                className="object-cover w-full h-full"
              />
            ) : (
              <div className="w-full h-full bg-[#1e1e3a] flex items-center justify-center">
                <span className="text-2xl text-[#64748b]">🎙️</span>
              </div>
            )}
          </div>

          {/* Name + role + equalizer */}
          <div className="flex flex-col gap-0.5">
            <div className="flex items-center gap-3">
              <span className="text-white text-lg font-semibold">
                {activeConfig?.name ?? "Waiting..."}
              </span>
              {isSpeaking && <EqualizerBars />}
            </div>
            <span className="text-emerald-400 text-sm">
              {activeConfig?.role ?? ""}
            </span>
          </div>
        </div>
      </div>

      {/* SUBTITLE BOX */}
      <div className="bg-[#13131f] rounded-2xl p-6 min-h-[80px]">
        <p
          className="text-white text-lg leading-relaxed transition-opacity duration-300"
          style={{ opacity: text ? 1 : 0.3 }}
        >
          {text || "..."}
        </p>
      </div>

      {/* CHARACTER STRIP */}
      <div className="flex items-center gap-3">
        <div className="flex-1 grid grid-cols-4 gap-2">
          {ALL_CHARACTERS.map((char) => {
            const config = CHARACTER_CONFIG[char];
            const isActive = isSpeaking && character === char;
            const isDimmed = isSpeaking && character !== char;

            return (
              <div
                key={char}
                className={`
                  flex flex-col items-center gap-2 px-2 py-3 rounded-xl transition-all duration-300
                  ${isActive ? "bg-emerald-950/30 scale-105" : "bg-transparent"}
                  ${isDimmed ? "opacity-40" : "opacity-100"}
                `}
              >
                {/* Equalizer above avatar when active */}
                <div className="h-4 flex items-end">
                  {isActive && <EqualizerBars />}
                </div>

                {/* Avatar */}
                <div
                  className={`relative w-16 h-16 rounded-full overflow-hidden flex-shrink-0 transition-all duration-300 ${
                    isDimmed ? "grayscale" : ""
                  }`}
                  style={
                    isActive
                      ? {
                          boxShadow:
                            "0 0 0 3px #10b981, 0 0 20px rgba(16,185,129,0.5)",
                        }
                      : undefined
                  }
                >
                  <Image
                    src={config.avatar}
                    alt={config.name}
                    width={64}
                    height={64}
                    className="object-cover w-full h-full"
                  />
                </div>

                {/* Name + role */}
                <span
                  className={`text-xs font-semibold ${
                    isActive ? "text-white" : "text-gray-500"
                  }`}
                >
                  {config.name}
                </span>
                <span className="text-[10px] text-[#64748b]">
                  {config.role}
                </span>
              </div>
            );
          })}
        </div>

        {/* Play/Pause button */}
        <button
          type="button"
          onClick={onToggle}
          aria-label={isPlaying ? "Pause" : "Play"}
          className="flex-shrink-0 w-14 h-14 rounded-full flex items-center justify-center bg-emerald-600 hover:bg-emerald-500 transition-colors duration-200 cursor-pointer"
          style={{
            boxShadow: "0 0 20px rgba(16,185,129,0.4)",
          }}
        >
          {isPlaying ? (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="currentColor"
              className="w-6 h-6 text-white"
            >
              <path
                fillRule="evenodd"
                d="M6.75 5.25a.75.75 0 0 1 .75.75v12a.75.75 0 0 1-1.5 0V6a.75.75 0 0 1 .75-.75Zm10.5 0a.75.75 0 0 1 .75.75v12a.75.75 0 0 1-1.5 0V6a.75.75 0 0 1 .75-.75Z"
                clipRule="evenodd"
              />
            </svg>
          ) : (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="currentColor"
              className="w-6 h-6 text-white"
            >
              <path
                fillRule="evenodd"
                d="M4.5 5.653c0-1.427 1.529-2.33 2.779-1.643l11.54 6.347c1.295.712 1.295 2.573 0 3.286L7.28 19.99c-1.25.687-2.779-.217-2.779-1.643V5.653Z"
                clipRule="evenodd"
              />
            </svg>
          )}
        </button>
      </div>
    </div>
  );
}
