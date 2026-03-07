import type { Palette, PaletteKey } from "./types";

export const PALETTES: Record<PaletteKey, Palette> = {
  warm_gold: {
    bg: "#0C0A07",
    text: "#F0EBE0",
    accent: "#C7AA73",
    muted: "#8B7D6B",
  },
  cool_stone: {
    bg: "#0A0B0E",
    text: "#E8E6E1",
    accent: "#9BA8B8",
    muted: "#6B7280",
  },
  deep_shadow: {
    bg: "#050505",
    text: "#D4CFC5",
    accent: "#A89070",
    muted: "#6B6155",
  },
  soft_light: {
    bg: "#F4F1EA",
    text: "#1A1814",
    accent: "#B8956A",
    muted: "#8B7D6B",
  },
};

export function getPalette(key: PaletteKey): Palette {
  return PALETTES[key] ?? PALETTES.warm_gold;
}
