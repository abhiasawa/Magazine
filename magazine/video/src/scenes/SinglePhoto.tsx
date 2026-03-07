import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { KenBurns } from "../components/KenBurns";
import { NarrativeText } from "../components/NarrativeText";
import type { SceneData } from "../lib/types";
import { getPalette } from "../lib/palette";

const KB_DIRECTIONS = ["zoom-in", "zoom-out", "pan-left", "pan-right"] as const;

interface SinglePhotoProps {
  scene: SceneData;
  sceneIndex: number;
}

export const SinglePhoto: React.FC<SinglePhotoProps> = ({ scene, sceneIndex }) => {
  const frame = useCurrentFrame();
  const palette = getPalette(scene.palette);
  const photo = scene.photos[0];
  const direction = KB_DIRECTIONS[sceneIndex % KB_DIRECTIONS.length];

  // Scene fade in
  const fadeIn = interpolate(frame, [0, 10], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: palette.bg, opacity: fadeIn }}>
      <KenBurns
        src={photo.src}
        durationFrames={scene.durationFrames}
        direction={direction}
      />

      {/* Vignette overlay */}
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.4) 100%)",
        }}
      />

      {scene.narrative && (
        <NarrativeText
          narrative={scene.narrative}
          palette={palette}
          durationFrames={scene.durationFrames}
        />
      )}
    </AbsoluteFill>
  );
};
