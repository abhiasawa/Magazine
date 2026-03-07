import type { PaletteKey } from "./types";

export interface TrackMeta {
  file: string; // filename in music/tracks/
  name: string;
  mood: MoodCategory;
  bpm?: number;
}

export type MoodCategory =
  | "warm_romantic"
  | "gentle_acoustic"
  | "ambient_cinematic"
  | "upbeat_joyful"
  | "emotional_cinematic";

// Track registry — each entry maps to a file in music/tracks/
export const TRACKS: TrackMeta[] = [
  // Warm / romantic piano
  { file: "warm-piano-01.mp3", name: "Tender Light", mood: "warm_romantic" },
  { file: "warm-piano-02.mp3", name: "Soft Reflections", mood: "warm_romantic" },
  { file: "warm-piano-03.mp3", name: "Quiet Devotion", mood: "warm_romantic" },
  { file: "warm-piano-04.mp3", name: "Ember Glow", mood: "warm_romantic" },
  // Gentle acoustic / strings
  { file: "gentle-acoustic-01.mp3", name: "Morning Walk", mood: "gentle_acoustic" },
  { file: "gentle-acoustic-02.mp3", name: "Still Waters", mood: "gentle_acoustic" },
  { file: "gentle-acoustic-03.mp3", name: "Autumn Breeze", mood: "gentle_acoustic" },
  { file: "gentle-acoustic-04.mp3", name: "Meadow Path", mood: "gentle_acoustic" },
  // Ambient / cinematic
  { file: "ambient-cinematic-01.mp3", name: "Horizons", mood: "ambient_cinematic" },
  { file: "ambient-cinematic-02.mp3", name: "Vast Skies", mood: "ambient_cinematic" },
  { file: "ambient-cinematic-03.mp3", name: "Deep Current", mood: "ambient_cinematic" },
  { file: "ambient-cinematic-04.mp3", name: "Nightfall", mood: "ambient_cinematic" },
  // Upbeat / joyful
  { file: "upbeat-joyful-01.mp3", name: "Golden Days", mood: "upbeat_joyful" },
  { file: "upbeat-joyful-02.mp3", name: "Sunlit Rhythm", mood: "upbeat_joyful" },
  { file: "upbeat-joyful-03.mp3", name: "Happy Trail", mood: "upbeat_joyful" },
  { file: "upbeat-joyful-04.mp3", name: "Celebration", mood: "upbeat_joyful" },
  // Emotional / cinematic (versatile)
  { file: "emotional-cinematic-01.mp3", name: "Journey Home", mood: "emotional_cinematic" },
  { file: "emotional-cinematic-02.mp3", name: "Unspoken", mood: "emotional_cinematic" },
  { file: "emotional-cinematic-03.mp3", name: "First Light", mood: "emotional_cinematic" },
  { file: "emotional-cinematic-04.mp3", name: "The Long Road", mood: "emotional_cinematic" },
];

// Map palette hints to preferred music moods
const PALETTE_TO_MOOD: Record<PaletteKey, MoodCategory[]> = {
  warm_gold: ["warm_romantic", "emotional_cinematic"],
  cool_stone: ["gentle_acoustic", "ambient_cinematic"],
  deep_shadow: ["ambient_cinematic", "emotional_cinematic"],
  soft_light: ["upbeat_joyful", "gentle_acoustic"],
};

/**
 * Select the best track based on the dominant mood across all scenes.
 * Counts palette occurrences, maps to preferred music moods, picks the
 * first available track in that mood category.
 */
export function selectTrack(palettes: PaletteKey[]): TrackMeta {
  // Count mood votes from scene palettes
  const votes: Record<MoodCategory, number> = {
    warm_romantic: 0,
    gentle_acoustic: 0,
    ambient_cinematic: 0,
    upbeat_joyful: 0,
    emotional_cinematic: 0,
  };

  for (const palette of palettes) {
    const prefs = PALETTE_TO_MOOD[palette] ?? PALETTE_TO_MOOD.warm_gold;
    for (const mood of prefs) {
      votes[mood] += 1;
    }
  }

  // Find the mood with the most votes
  let bestMood: MoodCategory = "emotional_cinematic";
  let bestCount = 0;
  for (const [mood, count] of Object.entries(votes) as [MoodCategory, number][]) {
    if (count > bestCount) {
      bestCount = count;
      bestMood = mood;
    }
  }

  // Pick a random track from the winning mood
  const candidates = TRACKS.filter((t) => t.mood === bestMood);
  if (candidates.length === 0) return TRACKS[0];
  const idx = Math.floor(Math.random() * candidates.length);
  return candidates[idx];
}
