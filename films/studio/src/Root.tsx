import { Composition } from "remotion";
import { OrbFlicker, ORB_FLICKER_FRAMES } from "./OrbFlicker";

export function Root() {
  return (
    <Composition
      id="OrbFlicker"
      component={OrbFlicker}
      durationInFrames={ORB_FLICKER_FRAMES}
      fps={30}
      width={1920}
      height={1080}
    />
  );
}
