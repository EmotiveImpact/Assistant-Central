import { AbsoluteFill, Series, staticFile } from "remotion";
import { PARLU, BOT_PEBBLE, MARK_SVG } from "./brand";
import { HelloZoom } from "./components/snap-cn/hello-zoom";
import { DropLine } from "./components/snap-cn/drop-line";
import { TextRewrite } from "./components/snap-cn/text-rewrite";
import { OrbSwarm } from "./components/snap-cn/orb-swarm";
import { TextReveal } from "./components/snap-cn/text-reveal";
import { LogoFlicker } from "./components/snap-cn/logo-flicker";
import { ChatPile } from "./scenes/ChatPile";

const FONT = "Plus Jakarta Sans";

const FACES = [
  "px_11215202", "px_4931333", "px_13120070", "px_35659764", "px_18039499",
  "px_7348675", "px_33323689", "px_10493844", "px_38602608", "tm_3182812",
  "px_40663010", "px_31649111", "px_40704337", "px_34301627", "px_40899157",
  "px_14484468", "px_8868795",
].map((f) => staticFile(`photos/${f}.jpg`));

/** Scene lengths in frames at 30fps. */
export const SCENES = {
  hello: 75,
  drop: 38,
  chat: 60,
  rewrite: 90,
  orbs: 165,
  reveal: 80,
  logo: 135,
} as const;
export const ORB_FLICKER_FRAMES = Object.values(SCENES).reduce((a, b) => a + b, 0);

export function OrbFlicker() {
  return (
    <AbsoluteFill style={{ background: PARLU.bg }}>
      <Series>
        {/* 1. Everyday plans flicker, then "Everyone has an assistant now." and a dive into "But" */}
        <Series.Sequence durationInFrames={SCENES.hello}>
          <HelloZoom
            words={["Birthdays", "Dinners", "Weekends", "School runs", "Projects", "Holidays"]}
            lead="Everyone"
            rest="has an assistant now."
            nextWord="But"
            fontFamily={FONT}
            inkColor={PARLU.ink}
            paperColor={PARLU.bg}
          />
        </Series.Sequence>

        {/* 2. The problem: the last word sinks away from its own dot */}
        <Series.Sequence durationInFrames={SCENES.drop}>
          <DropLine words={["yours", "can't", "reach", "theirs."]} fontFamily={FONT} mode="dark" ink={PARLU.ink} paper={PARLU.bg} />
        </Series.Sequence>

        {/* 3. So you're stuck in the group chat */}
        <Series.Sequence durationInFrames={SCENES.chat}>
          <ChatPile />
        </Series.Sequence>

        {/* 4. The turn: the line rewrites itself */}
        <Series.Sequence durationInFrames={SCENES.rewrite}>
          <TextRewrite
            headline="With Parlu, just ask your assistant"
            keep={2}
            append="talks to theirs."
            wordStagger={0.13}
            fontFamily={FONT}
            fontWeight={600}
            accentColor={PARLU.accent}
            markPath={BOT_PEBBLE}
            markColor={PARLU.sun}
            theme={{ background: PARLU.bg, foreground: PARLU.ink }}
            mode="light"
          />
        </Series.Sequence>

        {/* 5. The assistants get to work: orbs burst, swarm and loop round the ask */}
        <Series.Sequence durationInFrames={SCENES.orbs}>
          <OrbSwarm
            script="Sunday at 1? | The Orangery? | who books? | who pays? | sorted between them | then they ask you once"
            background={PARLU.bg}
            ink={PARLU.ink}
            orbColor={PARLU.sun}
            fontFamily={FONT}
            softness={0}
          />
        </Series.Sequence>

        {/* 6. The line */}
        <Series.Sequence durationInFrames={SCENES.reveal}>
          <AbsoluteFill style={{ background: PARLU.bg }}>
            <TextReveal
              text="They do the back and forth. You say yes."
              fontSize={84}
              fontWeight={700}
              fontFamily={FONT}
              color={PARLU.ink}
              wordColors={[PARLU.faint, PARLU.faint, PARLU.faint, PARLU.faint, PARLU.faint, PARLU.faint, PARLU.ink, PARLU.ink, PARLU.accent]}
              letterSpacing="-0.04em"
            />
          </AbsoluteFill>
        </Series.Sequence>

        {/* 7. Everyone's faces flicker past, then Parlu resolves */}
        <Series.Sequence durationInFrames={SCENES.logo}>
          <LogoFlicker
            images={FACES}
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
