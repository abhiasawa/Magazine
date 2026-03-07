import { AbsoluteFill, Img, interpolate, useCurrentFrame, staticFile } from "remotion";
import { NarrativeText } from "../components/NarrativeText";
import type { SceneData } from "../lib/types";
import { getPalette } from "../lib/palette";

interface MultiPhotoProps {
  scene: SceneData;
}

export const MultiPhoto: React.FC<MultiPhotoProps> = ({ scene }) => {
  const frame = useCurrentFrame();
  const palette = getPalette(scene.palette);
  const photos = scene.photos;

  // Each photo slides in with a stagger
  const stagger = 6; // frames between each photo appearing

  return (
    <AbsoluteFill style={{ backgroundColor: palette.bg }}>
      <div
        style={{
          position: "absolute",
          top: "10%",
          left: "6%",
          right: "6%",
          bottom: "25%",
          display: "grid",
          gridTemplateColumns:
            photos.length <= 2 ? "1fr 1fr" : "1fr 1fr",
          gridTemplateRows:
            photos.length <= 2 ? "1fr" : "1fr 1fr",
          gap: 12,
        }}
      >
        {photos.map((photo, i) => {
          const delay = i * stagger;
          const opacity = interpolate(frame - delay, [0, 12], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          const scale = interpolate(frame - delay, [0, 12], [0.92, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });

          return (
            <div
              key={photo.id}
              style={{
                opacity,
                transform: `scale(${scale})`,
                overflow: "hidden",
                borderRadius: 4,
              }}
            >
              <Img
                src={staticFile(photo.src)}
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                }}
              />
            </div>
          );
        })}
      </div>

      {scene.narrative && (
        <NarrativeText
          narrative={scene.narrative}
          palette={palette}
          durationFrames={scene.durationFrames}
          delayFrames={photos.length * stagger + 10}
        />
      )}
    </AbsoluteFill>
  );
};
