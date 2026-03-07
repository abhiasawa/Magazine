export interface PhotoData {
  id: string;
  src: string; // path relative to public/
  width: number;
  height: number;
  mediaType: "photo" | "video";
  videoSrc?: string; // for video clips
}

export interface NarrativeData {
  text: string;
  type: "heading_word" | "sentence";
}

export interface SceneData {
  photos: PhotoData[];
  narrative?: NarrativeData;
  palette: PaletteKey;
  durationFrames: number;
}

export type PaletteKey = "warm_gold" | "cool_stone" | "deep_shadow" | "soft_light";

export interface Palette {
  bg: string;
  text: string;
  accent: string;
  muted: string;
}

export interface MagazineData {
  title: string;
  subtitle: string;
  scenes: SceneData[];
  totalDurationFrames: number;
  fps: number;
}
