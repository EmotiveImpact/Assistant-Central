import { Series } from "remotion";
import { ASKF, Ask, CHAT, END_F, EVERYONE, Everyone, GroupChat, INTRO, Intro, LINEF, Line, TALKF, Talk, USESF, Uses, YESF, Yes, End } from "./launch/scenes";

/**
 * The Parlu launch film. One idea told in nine beats, all on white, in one
 * typeface, with the real app rebuilt so the camera can move through it.
 */
export const LAUNCH_SCENES = [
  ["everyone", EVERYONE, Everyone],
  ["chat", CHAT, GroupChat],
  ["intro", INTRO, Intro],
  ["ask", ASKF, Ask],
  ["talk", TALKF, Talk],
  ["yes", YESF, Yes],
  ["uses", USESF, Uses],
  ["line", LINEF, Line],
  ["end", END_F, End],
] as const;

export const LAUNCH_FRAMES = LAUNCH_SCENES.reduce((a, s) => a + s[1], 0);

export function Launch() {
  return (
    <Series>
      {LAUNCH_SCENES.map(([name, dur, C]) => (
        <Series.Sequence key={name} name={name} durationInFrames={dur}>
          <C />
        </Series.Sequence>
      ))}
    </Series>
  );
}
