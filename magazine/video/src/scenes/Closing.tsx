import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import type { Palette } from "../lib/types";

interface ClosingProps {
  title: string;
  palette: Palette;
}

export const Closing: React.FC<ClosingProps> = ({ title, palette }) => {
  const frame = useCurrentFrame();

  // Fade in
  const opacity = interpolate(frame, [0, 30], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Line animates
  const lineWidth = interpolate(frame, [20, 50], [0, 80], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Tagline fades in
  const tagOpacity = interpolate(frame, [50, 70], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: palette.bg,
        justifyContent: "center",
        alignItems: "center",
        opacity,
      }}
    >
      <div
        style={{
          fontFamily: "'Cormorant Garamond', Georgia, serif",
          fontSize: 48,
          fontWeight: 300,
          color: palette.text,
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          textAlign: "center",
        }}
      >
        {title}
      </div>

      <div
        style={{
          width: lineWidth,
          height: 1,
          backgroundColor: palette.accent,
          marginTop: 30,
          marginBottom: 30,
        }}
      />

      <div
        style={{
          opacity: tagOpacity,
          fontFamily: "sans-serif",
          fontSize: 14,
          fontWeight: 300,
          color: palette.muted,
          letterSpacing: "0.3em",
          textTransform: "uppercase",
        }}
      >
        Made with Maison Folio
      </div>
    </AbsoluteFill>
  );
};
