import { Composition } from "remotion";
import { OrbFlicker, ORB_FLICKER_FRAMES } from "./OrbFlicker";
import { OrbFlickerV2, V2_FRAMES } from "./OrbFlickerV2";
import { Launch, LAUNCH_FRAMES } from "./Launch";

export function Root() {
  return (
    <>
      <Composition id="OrbFlicker" component={OrbFlicker} durationInFrames={ORB_FLICKER_FRAMES} fps={30} width={1920} height={1080} />
      <Composition id="OrbFlickerV2" component={OrbFlickerV2} durationInFrames={V2_FRAMES} fps={30} width={1920} height={1080} />
      <Composition id="Launch" component={Launch} durationInFrames={LAUNCH_FRAMES} fps={30} width={1920} height={1080} />
    </>
  );
}
