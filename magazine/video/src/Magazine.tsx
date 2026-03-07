import { AbsoluteFill, Audio, Sequence, useVideoConfig, interpolate, useCurrentFrame, staticFile } from "remotion";
import { Opening } from "./scenes/Opening";
import { SinglePhoto } from "./scenes/SinglePhoto";
import { VideoClip } from "./scenes/VideoClip";
import { MultiPhoto } from "./scenes/MultiPhoto";
import { Closing } from "./scenes/Closing";
import { ProgressBar } from "./components/ProgressBar";
import { getPalette } from "./lib/palette";
import type { MagazineData, PaletteKey } from "./lib/types";
import { selectTrack } from "./lib/music";

import magazineData from "../public/data.json";

const data = magazineData as MagazineData;

export const Magazine: React.FC = () => {
  const { fps, durationInFrames } = useVideoConfig();
  const frame = useCurrentFrame();
  const openingDuration = 3 * fps;
  const closingDuration = 4 * fps;
  const defaultPalette = getPalette("warm_gold");

  const scenes = data.scenes ?? [];

  // Select music track based on scene palettes (fallback to default if no scenes)
  const scenePalettes = scenes.map((s) => s.palette as PaletteKey);
  const track = selectTrack(scenePalettes.length > 0 ? scenePalettes : ["warm_gold"]);
  const musicSrc = staticFile(`music/tracks/${track.file}`);

  // Music volume: fade in during opening, fade out during closing
  const fadeIn = Math.min(fps, Math.floor(durationInFrames / 4));
  const fadeOut = Math.min(2 * fps, Math.floor(durationInFrames / 4));
  const musicVolume = durationInFrames > fadeIn + fadeOut
    ? interpolate(
        frame,
        [0, fadeIn, durationInFrames - fadeOut, durationInFrames],
        [0, 0.6, 0.6, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
      )
    : 0.6;

  let currentFrame = 0;

  return (
    <AbsoluteFill style={{ backgroundColor: defaultPalette.bg }}>
      {/* Background music */}
      <Audio src={musicSrc} volume={musicVolume} />

      {/* Opening */}
      <Sequence from={currentFrame} durationInFrames={openingDuration}>
        <Opening
          title={data.title}
          subtitle={data.subtitle}
          palette={defaultPalette}
        />
      </Sequence>

      {/* Photo/Video scenes */}
      {(() => {
        currentFrame = openingDuration;
        return scenes.map((scene, i) => {
          const from = currentFrame;
          currentFrame += scene.durationFrames;

          if (scene.photos.length === 1) {
            if (scene.photos[0].mediaType === "video" && scene.photos[0].videoSrc) {
              return (
                <Sequence key={i} from={from} durationInFrames={scene.durationFrames}>
                  <VideoClip scene={scene} />
                </Sequence>
              );
            }
            return (
              <Sequence key={i} from={from} durationInFrames={scene.durationFrames}>
                <SinglePhoto scene={scene} sceneIndex={i} />
              </Sequence>
            );
          }

          return (
            <Sequence key={i} from={from} durationInFrames={scene.durationFrames}>
              <MultiPhoto scene={scene} />
            </Sequence>
          );
        });
      })()}

      {/* Closing */}
      <Sequence
        from={currentFrame}
        durationInFrames={closingDuration}
      >
        <Closing title={data.title} palette={defaultPalette} />
      </Sequence>

      {/* Progress bar */}
      <ProgressBar accentColor={defaultPalette.accent} />
    </AbsoluteFill>
  );
};
