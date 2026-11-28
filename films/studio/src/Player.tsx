import { Player } from "@remotion/player";
import { OrbFlicker, ORB_FLICKER_FRAMES } from "./OrbFlicker";

/** Drop-in player for showing the film inside a React page. */
export function OrbFlickerPlayer() {
  return (
    <Player
      component={OrbFlicker}
      durationInFrames={ORB_FLICKER_FRAMES}
      fps={30}
      compositionWidth={1920}
      compositionHeight={1080}
      style={{ width: "100%", aspectRatio: "16 / 9" }}
      controls
      loop
    />
  );
}
