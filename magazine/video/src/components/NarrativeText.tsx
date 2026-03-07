import { interpolate, useCurrentFrame } from "remotion";
import type { Palette, NarrativeData } from "../lib/types";

interface NarrativeTextProps {
  narrative: NarrativeData;
  palette: Palette;
  durationFrames: number;
  delayFrames?: number;
}

export const NarrativeText: React.FC<NarrativeTextProps> = ({
  narrative,
  palette,
  durationFrames,
  delayFrames = 15,
}) => {
  const frame = useCurrentFrame();
  const adjustedFrame = frame - delayFrames;

  if (adjustedFrame < 0) return null;

  const isHeading = narrative.type === "heading_word";

  // Fade in + slide up
  const opacity = interpolate(adjustedFrame, [0, 20], [0, 1], {
    extrapolateRight: "clamp",
  });
  const translateY = interpolate(adjustedFrame, [0, 20], [20, 0], {
    extrapolateRight: "clamp",
  });

  // Fade out near end
  const fadeOutStart = durationFrames - delayFrames - 15;
  const fadeOut = interpolate(
    adjustedFrame,
    [fadeOutStart, fadeOutStart + 12],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const finalOpacity = Math.min(opacity, fadeOut);

  if (isHeading) {
    return (
      <div
        style={{
          position: "absolute",
          bottom: "15%",
          left: 0,
          right: 0,
          textAlign: "center",
          opacity: finalOpacity,
          transform: `translateY(${translateY}px)`,
        }}
      >
        <div
          style={{
            fontFamily: "'Cormorant Garamond', Georgia, serif",
            fontSize: 72,
            fontWeight: 300,
            color: palette.accent,
            letterSpacing: "0.2em",
            textTransform: "uppercase",
            textShadow: "0 2px 20px rgba(0,0,0,0.6)",
          }}
        >
          {narrative.text}
        </div>
      </div>
    );
  }

  // Sentence style
  return (
    <div
      style={{
        position: "absolute",
        bottom: "8%",
        left: "8%",
        right: "8%",
        opacity: finalOpacity,
        transform: `translateY(${translateY}px)`,
      }}
    >
      {/* Gradient scrim behind text */}
      <div
        style={{
          position: "absolute",
          bottom: -40,
          left: -40,
          right: -40,
          height: 200,
          background:
            "linear-gradient(transparent, rgba(0,0,0,0.7))",
          borderRadius: 8,
          zIndex: -1,
        }}
      />
      <div
        style={{
          fontFamily: "'Cormorant Garamond', Georgia, serif",
          fontSize: 36,
          fontStyle: "italic",
          fontWeight: 400,
          color: palette.text,
          lineHeight: 1.5,
          textShadow: "0 1px 10px rgba(0,0,0,0.5)",
        }}
      >
        {narrative.text}
      </div>
    </div>
  );
};
