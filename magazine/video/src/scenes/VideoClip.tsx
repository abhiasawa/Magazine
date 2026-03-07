import { AbsoluteFill, Video, interpolate, useCurrentFrame } from "remotion";
import { NarrativeText } from "../components/NarrativeText";
import type { SceneData } from "../lib/types";
import { getPalette } from "../lib/palette";

interface VideoClipProps {
  scene: SceneData;
}

export const VideoClip: React.FC<VideoClipProps> = ({ scene }) => {
  const frame = useCurrentFrame();
  const palette = getPalette(scene.palette);
  const photo = scene.photos[0];

  const fadeIn = interpolate(frame, [0, 10], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: palette.bg, opacity: fadeIn }}>
      {photo.videoSrc ? (
        <Video
          src={photo.videoSrc}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
          volume={0}
          startFrom={60} // start 2 seconds in at 30fps
        />
      ) : (
        // Fallback to still frame if no video available
        <img
          src={photo.src}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
        />
      )}

      {/* Vignette */}
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.3) 100%)",
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
