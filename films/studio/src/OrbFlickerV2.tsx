import { AbsoluteFill, Series, staticFile } from "remotion";
import { PARLU, BOT_PEBBLE, MARK_SVG } from "./brand";
import { HelloZoom } from "./components/snap-cn/hello-zoom";
import { DropLine } from "./components/snap-cn/drop-line";
import { TextRewrite } from "./components/snap-cn/text-rewrite";
import { OrbSwarm } from "./components/snap-cn/orb-swarm";
import { TextReveal } from "./components/snap-cn/text-reveal";
import { LogoFlicker } from "./components/snap-cn/logo-flicker";
import { ChatPile } from "./scenes/ChatPile";
import { PeopleIntro } from "./scenes/PeopleIntro";
import { Pair } from "./scenes/Pair";

const FONT = "Plus Jakarta Sans";

// Darker to brighter, in the order LogoFlicker visits them ((step * 7) % 17).
const FACES = [
  "px_31649111", "px_13120070", "px_35659764", "px_10493844", "px_40663010",
  "px_40704337", "px_8868795", "px_38602608", "px_40899157", "px_11215202",
  "px_4931333", "px_33323689", "px_14484468", "px_7348675", "px_34301627",
  "px_18039499", "tm_3182812",
].map((f) => staticFile(`photos/${f}.jpg`));

/** Version 2 (28 Nov): slower, with real people and their assistants woven through. */
export const SCENES_V2 = {
  hello: 94,
  people: 160,
  drop: 92,
  chat: 100,
  rewrite: 136,
  talk: 160,
  orbs: 188,
  yes: 110,
  reveal: 110,
  logo: 150,
} as const;
export const V2_FRAMES = Object.values(SCENES_V2).reduce((a, b) => a + b, 0);

export function OrbFlickerV2() {
  return (
    <AbsoluteFill style={{ background: PARLU.bg }}>
      <Series>
        <Series.Sequence durationInFrames={SCENES_V2.hello}>
          <HelloZoom
            words={["Birthdays", "Dinners", "Weekends away", "School runs", "Side projects"]}
            lead="Plans"
            rest="should be easy."
            nextWord="Everyone"
            fontFamily={FONT}
            inkColor={PARLU.ink}
            paperColor={PARLU.bg}
            speed={0.8}
          />
        </Series.Sequence>
        <Series.Sequence durationInFrames={SCENES_V2.people}>
          <PeopleIntro />
        </Series.Sequence>
        <Series.Sequence durationInFrames={SCENES_V2.drop}>
          <DropLine words={["So", "you're", "stuck", "in", "the", "middle."]} fontFamily={FONT} mode="dark" ink={PARLU.ink} paper={PARLU.bg} speed={0.6} />
        </Series.Sequence>
        <Series.Sequence durationInFrames={SCENES_V2.chat}>
          <ChatPile pace={0.65} />
        </Series.Sequence>
        <Series.Sequence durationInFrames={SCENES_V2.rewrite}>
          <TextRewrite
            headline="With Parlu, just ask your assistant"
            keep={2}
            append="talks to theirs."
            wordStagger={0.13}
            speed={0.75}
            fontFamily={FONT}
            fontWeight={600}
            accentColor={PARLU.accent}
            markPath={BOT_PEBBLE}
            markColor={PARLU.sun}
            theme={{ background: PARLU.bg, foreground: PARLU.ink }}
            mode="light"
          />
        </Series.Sequence>
        <Series.Sequence durationInFrames={SCENES_V2.talk}>
          <Pair phase="talk" />
        </Series.Sequence>
        <Series.Sequence durationInFrames={SCENES_V2.orbs}>
          <OrbSwarm
            script="Sunday at 1? | The Orangery? | who books? | who pays? | sorted between them | then they ask you once"
            background={PARLU.bg}
            ink={PARLU.ink}
            orbColor={PARLU.sun}
            fontFamily={FONT}
            softness={0}
            speed={0.85}
          />
        </Series.Sequence>
        <Series.Sequence durationInFrames={SCENES_V2.yes}>
          <Pair phase="yes" />
        </Series.Sequence>
        <Series.Sequence durationInFrames={SCENES_V2.reveal}>
          <AbsoluteFill style={{ background: PARLU.bg }}>
            <TextReveal
              text="They do the back and forth. You say yes."
              fontSize={84}
              fontWeight={700}
              fontFamily={FONT}
              color={PARLU.ink}
              wordColors={[PARLU.faint, PARLU.faint, PARLU.faint, PARLU.faint, PARLU.faint, PARLU.faint, PARLU.ink, PARLU.ink, PARLU.accent]}
              letterSpacing="-0.04em"
              speed={0.8}
            />
          </AbsoluteFill>
        </Series.Sequence>
        <Series.Sequence durationInFrames={SCENES_V2.logo}>
          <LogoFlicker
            images={FACES}
            flipInterval={8}
            speed={0.8}
            logoSrc={MARK_SVG}
            brandName="Parlu"
            mode="light"
            background={PARLU.bg}
            theme={{ background: PARLU.bg, foreground: PARLU.ink }}
            fontFamily={FONT}
          />
        </Series.Sequence>
      </Series>
    </AbsoluteFill>
  );
}
