import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { PARLU } from "../brand";
import { Bot, BOT_COLOURS, blinking, Face, SHAPES } from "./Bot";

/**
 * Real people pop in, each with their own assistant beside them. Then the
 * assistants try to reach each other and can't: the lines stall halfway and
 * fade, and the bots look worried.
 */
const PEOPLE: { face: string; shape: keyof typeof SHAPES; colour: keyof typeof BOT_COLOURS; x: number; y: number }[] = [
  { face: "px_11215202", shape: "pebble", colour: "coral", x: -560, y: -10 },
  { face: "px_13120070", shape: "bean", colour: "amber", x: 0, y: -10 },
  { face: "px_33323689", shape: "cloud", colour: "rose", x: 560, y: -10 },
  { face: "px_18039499", shape: "drop", colour: "berry", x: -560, y: 300 },
  { face: "px_40704337", shape: "squircle", colour: "rust", x: 0, y: 300 },
  { face: "px_40663010", shape: "pebble", colour: "clay", x: 560, y: 300 },
];
const FACE = 220;
const BOT = 100;
const botAt = (p: (typeof PEOPLE)[number]) => ({ x: p.x + 60 + BOT / 2 + 12, y: p.y + 70 });
const LINKS: [number, number][] = [
  [0, 1],
  [1, 2],
  [3, 4],
  [4, 5],
  [1, 3],
];
const TRY_AT = 96;

function Caption({ text, from, to, frame }: { text: string; from: number; to: number; frame: number }) {
  const words = text.split(" ");
  const out = interpolate(frame, [to - 8, to], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div
      style={{
        position: "absolute",
        top: 150,
        width: "100%",
        textAlign: "center",
        fontSize: 72,
        fontWeight: 700,
        letterSpacing: "-0.04em",
        color: PARLU.ink,
        opacity: out,
      }}
    >
      {words.map((w, i) => {
        const t = frame - from - i * 4;
        const o = interpolate(t, [0, 8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        const y = interpolate(t, [0, 12], [24, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
        return (
          <span key={i} style={{ display: "inline-block", opacity: o, transform: `translateY(${y}px)`, marginRight: "0.25em" }}>
            {w}
          </span>
        );
      })}
    </div>
  );
}

export function PeopleIntro() {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const cx = width / 2;
  const cy = height / 2 + 40;
  const push = interpolate(frame, [0, durationInFrames], [1, 1.05]);
  const trying = frame >= TRY_AT;
  const exit = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ background: PARLU.bg, fontFamily: PARLU.font, opacity: exit }}>
      <Caption text="Everyone has an assistant now." from={4} to={TRY_AT - 4} frame={frame} />
      {frame >= TRY_AT - 2 && (
        <Caption text="But they can't talk to each other." from={TRY_AT} to={durationInFrames + 20} frame={frame} />
      )}
      <AbsoluteFill style={{ transform: `scale(${push})` }}>
        <svg width={width} height={height} style={{ position: "absolute", inset: 0 }}>
          {LINKS.map(([a, b], k) => {
            const A = botAt(PEOPLE[a]);
            const B = botAt(PEOPLE[b]);
            const start = TRY_AT + 6 + k * 5;
            const grow = interpolate(frame, [start, start + 26], [0, 0.42], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.out(Easing.cubic),
            });
            const fade = interpolate(frame, [start + 34, start + 50], [1, 0.18], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
            const ax = cx + A.x;
            const ay = cy + A.y;
            const bx = cx + B.x;
            const by = cy + B.y;
            // Both ends reach toward each other and stall short of the middle.
            return (
              <g key={k} opacity={fade} stroke={PARLU.sun} strokeWidth={5} strokeDasharray="2 14" strokeLinecap="round">
                <line x1={ax} y1={ay} x2={ax + (bx - ax) * grow} y2={ay + (by - ay) * grow} />
                <line x1={bx} y1={by} x2={bx + (ax - bx) * grow} y2={by + (ay - by) * grow} />
              </g>
            );
          })}
        </svg>
        {PEOPLE.map((p, i) => {
          const at = 6 + i * 7;
          const s = spring({ frame: frame - at, fps, config: { damping: 14, stiffness: 160 } });
          const bs = spring({ frame: frame - at - 8, fps, config: { damping: 9, stiffness: 200 } });
          const bob = Math.sin((frame + i * 11) / 9) * 5;
          const target = PEOPLE[LINKS.find(([a]) => a === i)?.[1] ?? LINKS.find(([, b]) => b === i)?.[0] ?? i];
          const glance = trying ? Math.sign(target.x - p.x) || Math.sign(target.y - p.y) * 0.3 : 0;
          const eyes = blinking(frame, i) ? "blink" : trying && frame > TRY_AT + 40 ? "look" : "idle";
          return (
            <div key={p.face}>
              <div
                style={{
                  position: "absolute",
                  left: cx + p.x - 60 - FACE / 2,
                  top: cy + p.y - FACE / 2,
                  transform: `scale(${s})`,
                }}
              >
                <Face name={p.face} size={FACE} />
              </div>
              <div
                style={{
                  position: "absolute",
                  left: cx + botAt(p).x - BOT / 2,
                  top: cy + botAt(p).y - BOT / 2 + bob,
                  transform: `scale(${bs})`,
                }}
              >
                <Bot shape={p.shape} colour={p.colour} size={BOT} eyes={eyes} glance={glance} />
              </div>
            </div>
          );
        })}
      </AbsoluteFill>
    </AbsoluteFill>
  );
}
