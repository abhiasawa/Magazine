import { useCurrentFrame, useVideoConfig } from "remotion";

interface ProgressBarProps {
  accentColor: string;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({ accentColor }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const progress = frame / durationInFrames;

  return (
    <div
      style={{
        position: "absolute",
        bottom: 0,
        left: 0,
        right: 0,
        height: 3,
        backgroundColor: "rgba(255,255,255,0.1)",
      }}
    >
      <div
        style={{
          height: "100%",
          width: `${progress * 100}%`,
          backgroundColor: accentColor,
          transition: "width 0.1s linear",
        }}
      />
    </div>
  );
};
