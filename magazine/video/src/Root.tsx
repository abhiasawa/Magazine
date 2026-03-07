import { Composition } from "remotion";
import { Magazine } from "./Magazine";

import magazineData from "../public/data.json";

const data = magazineData as { totalDurationFrames: number; fps: number };

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Magazine"
        component={Magazine}
        durationInFrames={data.totalDurationFrames}
        fps={data.fps}
        width={1080}
        height={1920}
      />
    </>
  );
};
