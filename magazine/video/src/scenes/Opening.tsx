import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import type { Palette } from "../lib/types";

interface OpeningProps {
  title: string;
  subtitle: string;
  palette: Palette;
}

export const Opening: React.FC<OpeningProps> = ({ title, subtitle, palette }) => {
  const frame = useCurrentFrame();

  // Accent line scales in
  const lineWidth = interpolate(frame, [10, 40], [0, 120], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Title fades in
  const titleOpacity = interpolate(frame, [15, 40], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleY = interpolate(frame, [15, 40], [30, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Subtitle fades in later
  const subtitleOpacity = interpolate(frame, [40, 60], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: palette.bg,
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      {/* Accent line */}
      <div
        style={{
          width: lineWidth,
          height: 1,
          backgroundColor: palette.accent,
          marginBottom: 40,
        }}
      />

      {/* Title */}
      <div
        style={{
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
          fontFamily: "'Cormorant Garamond', Georgia, serif",
          fontSize: 64,
          fontWeight: 300,
          color: palette.text,
          letterSpacing: "0.15em",
          textTransform: "uppercase",
          textAlign: "center",
          padding: "0 60px",
        }}
      >
        {title}
      </div>

      {/* Subtitle */}
      {subtitle && (
        <div
          style={{
            opacity: subtitleOpacity,
            fontFamily: "'Cormorant Garamond', Georgia, serif",
            fontSize: 24,
            fontWeight: 300,
            fontStyle: "italic",
            color: palette.muted,
            marginTop: 20,
            letterSpacing: "0.08em",
          }}
        >
          {subtitle}
        </div>
      )}
    </AbsoluteFill>
  );
};
