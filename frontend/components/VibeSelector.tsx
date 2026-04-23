"use client";

import { VibeMode } from "@/types";

interface VibeSelectorProps {
  onSelect: (vibe: VibeMode) => void;
  selected: VibeMode | null;
}

const vibeOptions: {
  value: VibeMode;
  label: string;
  emoji: string;
  description: string;
  accentColor: string;
  selectedBg: string;
  selectedBorder: string;
  selectedText: string;
}[] = [
  {
    value: "roast",
    label: "Roast",
    emoji: "🔥",
    description: "Merciless critique. Skeptic dominates.",
    accentColor: "text-red-400",
    selectedBg: "bg-red-950/40",
    selectedBorder: "border-red-500",
    selectedText: "text-red-300",
  },
  {
    value: "deep_dive",
    label: "Deep Dive",
    emoji: "🔬",
    description: "Balanced technical analysis.",
    accentColor: "text-blue-400",
    selectedBg: "bg-blue-950/40",
    selectedBorder: "border-blue-500",
    selectedText: "text-blue-300",
  },
  {
    value: "beginner_friendly",
    label: "Beginner Friendly",
    emoji: "🎓",
    description: "No jargon. Intern asks, Fan explains.",
    accentColor: "text-green-400",
    selectedBg: "bg-green-950/40",
    selectedBorder: "border-green-500",
    selectedText: "text-green-300",
  },
];

export default function VibeSelector({ onSelect, selected }: VibeSelectorProps) {
  return (
    <div className="flex flex-col gap-3 w-full" role="radiogroup" aria-label="Vibe mode selection">
      {vibeOptions.map((option) => {
        const isSelected = selected === option.value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={isSelected}
            onClick={() => onSelect(option.value)}
            className={`
              flex items-center gap-4 w-full px-5 py-4 rounded-xl border-2 transition-all duration-200
              cursor-pointer text-left
              ${
                isSelected
                  ? `${option.selectedBg} ${option.selectedBorder} ${option.selectedText} shadow-lg`
                  : "bg-zinc-900/60 border-zinc-700/50 text-zinc-400 hover:border-zinc-500 hover:bg-zinc-800/60"
              }
            `}
          >
            <span className="text-3xl flex-shrink-0" aria-hidden="true">
              {option.emoji}
            </span>
            <div className="flex flex-col gap-0.5">
              <span
                className={`font-semibold text-base ${
                  isSelected ? option.selectedText : "text-zinc-200"
                }`}
              >
                {option.label}
              </span>
              <span
                className={`text-sm ${
                  isSelected ? option.accentColor : "text-zinc-500"
                }`}
              >
                {option.description}
              </span>
            </div>
            <div className="ml-auto flex-shrink-0">
              <div
                className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors ${
                  isSelected ? option.selectedBorder : "border-zinc-600"
                }`}
              >
                {isSelected && (
                  <div
                    className={`w-2.5 h-2.5 rounded-full ${
                      option.value === "roast"
                        ? "bg-red-500"
                        : option.value === "deep_dive"
                        ? "bg-blue-500"
                        : "bg-green-500"
                    }`}
                  />
                )}
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
