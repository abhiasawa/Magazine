import { AbsoluteFill, Img, interpolate, useCurrentFrame } from "remotion";

interface KenBurnsProps {
  src: string;
  durationFrames: number;
  direction?: "zoom-in" | "zoom-out" | "pan-left" | "pan-right";
}

export const KenBurns: React.FC<KenBurnsProps> = ({
  src,
  durationFrames,
  direction = "zoom-in",
}) => {
  const frame = useCurrentFrame();
  const progress = frame / durationFrames;

  let scale: number;
  let translateX: number;
  let translateY: number;

  switch (direction) {
    case "zoom-in":
      scale = interpolate(progress, [0, 1], [1.0, 1.12]);
      translateX = interpolate(progress, [0, 1], [0, -1.5]);
      translateY = interpolate(progress, [0, 1], [0, -1]);
      break;
    case "zoom-out":
      scale = interpolate(progress, [0, 1], [1.12, 1.0]);
      translateX = interpolate(progress, [0, 1], [-1.5, 0]);
      translateY = interpolate(progress, [0, 1], [-1, 0]);
      break;
    case "pan-left":
      scale = 1.08;
      translateX = interpolate(progress, [0, 1], [2, -2]);
      translateY = 0;
      break;
    case "pan-right":
      scale = 1.08;
      translateX = interpolate(progress, [0, 1], [-2, 2]);
      translateY = 0;
      break;
  }

  return (
    <AbsoluteFill>
      <Img
        src={src}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${scale}) translate(${translateX}%, ${translateY}%)`,
        }}
      />
    </AbsoluteFill>
  );
};
