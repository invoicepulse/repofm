export type VibeMode = "roast" | "deep_dive" | "beginner_friendly";

export type Character = "narrator" | "skeptic" | "fan" | "intern";

export type ArtifactType =
  | "language_chart"
  | "file_size_graph"
  | "security_report"
  | "project_structure"
  | null;

export interface Segment {
  character: Character;
  text: string;
  artifact: ArtifactType;
  audio_b64: string;
}

export interface ProjectStructure {
  total_files: number;
  file_types: Record<string, number>;
}

export interface ArtifactData {
  language_chart: Record<string, number>;
  file_size_graph: Array<{ file: string; size: number }>;
  security_report: string[];
  project_structure: ProjectStructure;
}

export interface EpisodeMetadata {
  repo_name: string;
  vibe: VibeMode;
  artifact_data: ArtifactData;
}

export interface AnalyzeResponse {
  script: Segment[];
  metadata: EpisodeMetadata;
}

export type PlaybackState =
  | "idle"
  | "loading"
  | "playing_speech"
  | "paused"
  | "interrupted"
  | "complete";
