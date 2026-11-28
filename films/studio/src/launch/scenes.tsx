import React from "react";
import { AbsoluteFill, Img, interpolate, interpolateColors, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { MARK_SVG, PARLU } from "../brand";
import { Bot, BOT_COLOURS, Face, blinking } from "../scenes/Bot";
import { AMA, AppWindow, Composer, JOEL, Pairing } from "./App";
import { BlurLine, Cursor, Scene, clamp, easeInOut, easeOut, key, words } from "./kit";

const W = 1920;
const H = 1080;

/* ------------------------------------------------------------------ */
/* 1. Everyone has an assistant now. But they can't talk to each other. */
/* ------------------------------------------------------------------ */

const CAST: { face: string; shape: "pebble" | "cloud" | "bean" | "drop" | "squircle"; colour: keyof typeof BOT_COLOURS }[] = [
  { face: AMA, shape: "pebble", colour: "coral" },
  { face: "px_13120070", shape: "bean", colour: "amber" },
  { face: "px_18039499", shape: "drop", colour: "berry" },
  { face: "px_33323689", shape: "squircle", colour: "rust" },
  { face: JOEL, shape: "cloud", colour: "rose" },
];

export const EVERYONE = 270;
export function Everyone() {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const TRY = 168;
  return (
    <Scene dur={EVERYONE} inF={14}>
      <div style={{ position: "absolute", top: 170, width: W }}>
        <BlurLine words={words("Everyone has an assistant now.")} start={8} leave={140} size={104} />
      </div>
      <div style={{ position: "absolute", top: 170, width: W }}>
        <BlurLine words={words("But they can't talk to each other.", { "can't": PARLU.coral })} start={152} size={104} />
      </div>
      <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>
        {CAST.slice(0, -1).map((_, i) => {
          const x1 = 960 + (i - 2) * 350 + 100;
          const x2 = x1 + 350;
          const p = interpolate(f, [TRY + i * 6, TRY + 30 + i * 6], [0, 0.46], { ...clamp, easing: easeOut });
          const fade = interpolate(f, [TRY + 52 + i * 6, TRY + 72 + i * 6], [1, 0], clamp);
          return (
            <g key={i} opacity={fade}>
              <clipPath id={`c${i}`}>
                <rect x={x1} y={380} width={(x2 - x1) * p} height={300} />
              </clipPath>
              <path d={`M${x1} 580 Q${(x1 + x2) / 2} 470 ${x2} 580`} stroke={PARLU.sun} strokeWidth={5} strokeDasharray="4 14" strokeLinecap="round" fill="none" clipPath={`url(#c${i})`} />
            </g>
          );
        })}
      </svg>
      {CAST.map((c, i) => {
        const cx = 960 + (i - 2) * 350;
        const s = spring({ frame: f - 34 - i * 7, fps, config: { damping: 14, stiffness: 140 } });
        const bob = Math.sin((f + i * 20) / 22) * 6;
        const eyes = f > TRY + 40 ? "look" : blinking(f, i) ? "blink" : "idle";
        return (
          <div key={c.face} style={{ position: "absolute", left: cx - 85, top: 615 + bob, transform: `scale(${s})`, opacity: s }}>
            <Face name={c.face} size={170} />
            <div style={{ position: "absolute", left: 137, top: -73 }}>
              <Bot shape={c.shape} colour={c.colour} size={96} eyes={eyes} glance={f > TRY + 40 ? (i < 2 ? 1 : -1) : 0} />
            </div>
          </div>
        );
      })}
    </Scene>
  );
}

/* ------------------------------------------------------------------ */
/* 2. So you're stuck in the group chat.                               */
/* ------------------------------------------------------------------ */

const THREAD = [
  ["Nana's 80th!! Ideas?", 0],
  ["Lunch somewhere?", 1],
  ["Sunday works", 0],
  ["I'm away Sunday", 0],
  ["Saturday then?", 1],
  ["Can't do Sat", 0],
  ["Who's booking?", 0],
  ["Is it step-free?", 1],
  ["No idea", 0],
  ["??", 0],
] as const;

const SHOUTS = [
  { t: "Who's free Sunday?", face: "px_13120070", x: -1, y: 380, at: 28 },
  { t: "Has anyone booked?", face: "px_33323689", x: 1, y: 470, at: 50 },
  { t: "Is it step-free?", face: "px_18039499", x: -1, y: 640, at: 72 },
  { t: "Who owes who?", face: JOEL, x: 1, y: 730, at: 94 },
];

export const CHAT = 241;
export function GroupChat() {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const count = Math.floor(interpolate(f, [10, 120], [4, 140], { ...clamp, easing: (t) => t * t }));
  const shown = Math.min(THREAD.length, Math.floor(f / 9) + 3);
  const ry = key(f, [0, CHAT], [-26, -10]);
  const sc = key(f, [0, CHAT], [0.9, 1.0]);
  return (
    <Scene dur={CHAT}>
      <div style={{ position: "absolute", top: 90, width: W }}>
        <BlurLine words={words("So you're stuck in the group chat.")} start={4} leave={112} size={84} />
      </div>
      <div style={{ position: "absolute", top: 90, width: W }}>
        <BlurLine words={words("Chasing everyone. Doing it all yourself.")} start={120} size={84} />
      </div>
      <AbsoluteFill style={{ perspective: 1800, alignItems: "center", justifyContent: "center", paddingTop: 150 }}>
        <div
          style={{
            width: 380,
            height: 740,
            borderRadius: 60,
            background: PARLU.raised,
            border: `10px solid ${PARLU.ink}`,
            boxShadow: "0 60px 90px -40px rgba(27,26,23,.45)",
            transform: `rotateY(${ry}deg) rotateX(6deg) scale(${sc})`,
            overflow: "hidden",
            position: "relative",
          }}
        >
          <div style={{ padding: "40px 24px 16px", background: "#fff", borderBottom: `2px solid ${PARLU.line}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontWeight: 700, fontSize: 24 }}>Nana's 80th</span>
            <span style={{ background: PARLU.sun, color: "#fff", fontWeight: 800, fontSize: 22, borderRadius: 999, padding: "4px 14px", fontVariantNumeric: "tabular-nums" }}>
              {count >= 99 ? "99+" : count}
            </span>
          </div>
          <div style={{ position: "absolute", left: 18, right: 18, bottom: 20, display: "flex", flexDirection: "column", gap: 10 }}>
            {THREAD.slice(0, shown).slice(-8).map(([t, mine]) => (
              <div
                key={t}
                style={{
                  alignSelf: mine ? "flex-end" : "flex-start",
                  background: mine ? PARLU.accent : "#fff",
                  color: mine ? "#fff" : PARLU.ink,
                  fontSize: 20,
                  fontWeight: 500,
                  padding: "10px 16px",
                  borderRadius: 20,
                }}
              >
                {t}
              </div>
            ))}
          </div>
        </div>
      </AbsoluteFill>
      {SHOUTS.map((m) => {
        const s = spring({ frame: f - m.at, fps, config: { damping: 15, stiffness: 160 } });
        const left = m.x < 0;
        return (
          <div
            key={m.t}
            style={{
              position: "absolute",
              top: m.y,
              ...(left ? { right: W / 2 + 250 } : { left: W / 2 + 250 }),
              display: "flex",
              flexDirection: left ? "row" : "row-reverse",
              alignItems: "center",
              gap: 14,
              opacity: s,
              filter: `blur(${(1 - s) * 10}px)`,
              transform: `translateX(${(1 - s) * (left ? -40 : 40)}px)`,
            }}
          >
            <Face name={m.face} size={72} />
            <div style={{ background: "#fff", fontSize: 30, fontWeight: 600, padding: "14px 24px", borderRadius: 24, boxShadow: "0 18px 40px -20px rgba(27,26,23,.35), 0 0 0 1.5px #ebebe9", whiteSpace: "nowrap" }}>
              {m.t}
            </div>
          </div>
        );
      })}
    </Scene>
  );
}

/* ------------------------------------------------------------------ */
/* 3. Introducing Parlu.                                               */
/* ------------------------------------------------------------------ */

export function Lockup({ at = 0, size = 1 }: { at?: number; size?: number }) {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const m = spring({ frame: f - at, fps, config: { damping: 13, stiffness: 120 } });
  const reveal = interpolate(f, [at + 16, at + 40], [0, 1], { ...clamp, easing: easeOut });
  const mark = 170 * size;
  const word = 200 * size;
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 28 * size }}>
      <Img src={MARK_SVG} style={{ width: mark, height: mark, transform: `scale(${m}) rotate(${(1 - m) * -40}deg)` }} />
      <div style={{ overflow: "hidden", width: reveal * 520 * size, transition: "none" }}>
        <div
          style={{
            fontSize: word,
            fontWeight: 700,
            letterSpacing: "-0.055em",
            lineHeight: 1,
            paddingBottom: 0.12 * word,
            transform: `translateX(${(1 - reveal) * -120}px)`,
            filter: `blur(${(1 - reveal) * 12}px)`,
          }}
        >
          Parlu
        </div>
      </div>
    </div>
  );
}

export const INTRO = 120;
export function Intro() {
  return (
    <Scene dur={INTRO} inF={1}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 30 }}>
        <BlurLine words={["Introducing"]} start={-4} size={40} weight={600} style={{ color: PARLU.faint, letterSpacing: "0.02em" }} />
        <Lockup at={-3} />
      </AbsoluteFill>
    </Scene>
  );
}

/* ------------------------------------------------------------------ */
/* 4. Just ask your assistant once. (inside the real app)              */
/* ------------------------------------------------------------------ */

const ASK = "Sort Nana's 80th lunch with Joel's family. Sunday, step-free, about £60 each.";
export const ASKF = 220;
export function Ask() {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const T0 = 40;
  const T1 = 118;
  const n = Math.round(interpolate(f, [T0, T1], [0, ASK.length], clamp));
  const typed = ASK.slice(0, n);
  const SEND = 134;
  const down = interpolate(f, [SEND - 3, SEND, SEND + 5], [0, 1, 0], clamp);
  const sent = f >= SEND ? 1 : 0;
  // Camera: rise out of a tilt, then push into the composer.
  const rx = key(f, [0, 34, ASKF], [26, 10, 4]);
  const sc = key(f, [0, 34, 110, ASKF], [0.74, 0.84, 1.08, 1.14]);
  const ty = key(f, [0, 34, 110, ASKF], [260, 150, 90, 40]);
  const cx = key(f, [T1, SEND - 2], [1500, 1404]);
  const cy = key(f, [T1, SEND - 2], [880, 662]);
  const bubble = spring({ frame: f - SEND - 2, fps, config: { damping: 18, stiffness: 140 } });
  const reply = spring({ frame: f - SEND - 22, fps, config: { damping: 18, stiffness: 140 } });
  return (
    <Scene dur={ASKF}>
      <div style={{ position: "absolute", top: 70, width: W, zIndex: 5 }}>
        <BlurLine words={words("Just ask your assistant once.", { once: PARLU.accent })} start={6} leave={92} size={84} />
      </div>
      <AbsoluteFill style={{ perspective: 2200, alignItems: "center", justifyContent: "center" }}>
        <div style={{ transform: `translateY(${ty}px) rotateX(${rx}deg) scale(${sc})`, transformOrigin: "50% 60%" }}>
          <AppWindow>
            <div style={{ padding: "64px 110px" }}>
              <div style={{ fontSize: 17, letterSpacing: "0.12em", fontWeight: 700, color: "#6f6a60" }}>SATURDAY 7 NOVEMBER · 09:12</div>
              <div style={{ fontSize: 48, fontWeight: 700, letterSpacing: "-0.035em", lineHeight: 1.15, marginTop: 16, maxWidth: 1000 }}>
                <span style={{ color: PARLU.faint }}>Morning Ama.</span> Nothing needs you right now.
              </div>
              <div style={{ marginTop: 40, minHeight: 170, display: "flex", flexDirection: "column", gap: 14 }}>
                {sent ? (
                  <div style={{ alignSelf: "flex-end", maxWidth: 860, background: PARLU.accent, color: "#fff", fontSize: 24, fontWeight: 500, padding: "16px 24px", borderRadius: 24, opacity: bubble, transform: `translateY(${(1 - bubble) * 30}px)` }}>
                    {ASK}
                  </div>
                ) : null}
                {f > SEND + 20 ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 14, opacity: reply, transform: `translateY(${(1 - reply) * 24}px)` }}>
                    <Bot shape="pebble" colour="coral" size={52} eyes={blinking(f, 2) ? "blink" : "idle"} />
                    <div style={{ background: PARLU.raised, fontSize: 24, fontWeight: 500, padding: "16px 24px", borderRadius: 24 }}>
                      On it. I'll sort it out with Wren, Joel's assistant.
                    </div>
                  </div>
                ) : null}
              </div>
              <div style={{ marginTop: 26 }}>
                <Composer typed={sent ? "" : typed} caret={!sent && f > T0 - 10 && Math.floor(f / 8) % 2 === 0} sent={down} />
              </div>
            </div>
          </AppWindow>
          {f > T1 - 4 && f < SEND + 16 ? <Cursor x={cx - 160} y={cy - 40} down={down} /> : null}
        </div>
      </AbsoluteFill>
    </Scene>
  );
}

/* ------------------------------------------------------------------ */
/* 5. It sorts it out with theirs.                                     */
/* ------------------------------------------------------------------ */

const TALK: [string, 0 | 1][] = [
  ["Is Sunday 14th good for Joel?", 0],
  ["Yes, he's free from 12.", 1],
  ["Nana needs step-free.", 0],
  ["The Orangery has a ramp.", 1],
  ["1pm, about £60 each?", 0],
  ["Joel's happy with that.", 1],
  ["I'll hold a table for 8.", 0],
  ["Great. Checking with Joel.", 1],
];

export const TALKF = 267;
export function Talk() {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const START = 30;
  const GAP = 22;
  const arrived = Math.max(0, Math.min(TALK.length, Math.floor((f - START) / GAP) + 1));
  const speaking = arrived > 0 ? TALK[arrived - 1][1] : -1;
  const sinceLast = f - START - (arrived - 1) * GAP;
  const hop = (side: number) => (speaking === side ? Math.max(0, Math.sin(Math.min(1, sinceLast / 10) * Math.PI)) * -14 : 0);
  const msgs = Math.round(interpolate(f, [START, START + GAP * TALK.length], [0, 23], clamp));
  const ROW = 78;
  const pairIn = (d: number) => spring({ frame: f - d, fps, config: { damping: 16, stiffness: 130 } });
  return (
    <Scene dur={TALKF}>
      <div style={{ position: "absolute", top: 80, width: W }}>
        <BlurLine words={words("Pip sorts it out with Joel's assistant.", { Pip: PARLU.sun })} start={4} size={76} />
      </div>
      {/* Ama and Pip */}
      <div style={{ position: "absolute", left: 150, top: 420, display: "flex", alignItems: "center", gap: 22, opacity: pairIn(6), transform: `translateX(${(1 - pairIn(6)) * -60}px)` }}>
        <div style={{ textAlign: "center" }}>
          <Face name={AMA} size={220} />
          <div style={{ fontSize: 28, fontWeight: 700, marginTop: 14 }}>Ama</div>
        </div>
        <div style={{ transform: `translateY(${hop(0) - 30}px)` }}>
          <Bot shape="pebble" colour="coral" size={140} eyes={blinking(f, 1) ? "blink" : "idle"} glance={1} />
          <div style={{ fontSize: 24, fontWeight: 600, textAlign: "center", color: PARLU.faint }}>Pip</div>
        </div>
      </div>
      {/* Joel and Wren */}
      <div style={{ position: "absolute", right: 150, top: 420, display: "flex", alignItems: "center", gap: 22, opacity: pairIn(12), transform: `translateX(${(1 - pairIn(12)) * 60}px)` }}>
        <div style={{ transform: `translateY(${hop(1) - 30}px)` }}>
          <Bot shape="cloud" colour="rose" size={140} eyes={blinking(f, 4) ? "blink" : "idle"} glance={-1} />
          <div style={{ fontSize: 24, fontWeight: 600, textAlign: "center", color: PARLU.faint }}>Wren</div>
        </div>
        <div style={{ textAlign: "center" }}>
          <Face name={JOEL} size={220} />
          <div style={{ fontSize: 28, fontWeight: 700, marginTop: 14 }}>Joel</div>
        </div>
      </div>
      {/* The conversation between the two assistants */}
      <div style={{ position: "absolute", left: 640, width: 640, top: 250, height: 560, overflow: "hidden", maskImage: "linear-gradient(transparent, #000 30%)", WebkitMaskImage: "linear-gradient(transparent, #000 30%)" }}>
        {TALK.slice(0, arrived).map(([t, side], i) => {
          const age = arrived - 1 - i;
          const s = spring({ frame: f - START - i * GAP, fps, config: { damping: 18, stiffness: 170 } });
          const y = 560 - ROW - (age + (1 - s) * -1) * ROW - 10;
          return (
            <div
              key={t}
              style={{
                position: "absolute",
                top: y,
                ...(side ? { right: 0 } : { left: 0 }),
                display: "flex",
                alignItems: "center",
                gap: 10,
                flexDirection: side ? "row-reverse" : "row",
                opacity: s,
                transform: `scale(${0.9 + 0.1 * s})`,
                transformOrigin: side ? "right center" : "left center",
              }}
            >
              <span style={{ width: 14, height: 14, borderRadius: 99, background: side ? BOT_COLOURS.rose : BOT_COLOURS.coral }} />
              <span style={{ background: "#fff", fontSize: 27, fontWeight: 600, padding: "14px 22px", borderRadius: 22, boxShadow: "0 14px 30px -18px rgba(27,26,23,.35), 0 0 0 1.5px #ebebe9", whiteSpace: "nowrap" }}>{t}</span>
            </div>
          );
        })}
      </div>
      <div style={{ position: "absolute", top: 880, width: W, textAlign: "center", fontSize: 34, fontWeight: 600, color: PARLU.faint, opacity: interpolate(f, [START + 10, START + 24], [0, 1], clamp) }}>
        <span style={{ color: PARLU.ink, fontVariantNumeric: "tabular-nums" }}>{msgs} messages</span> between Pip and Wren.{" "}
        <span style={{ color: PARLU.accent }}>None from Ama or Joel.</span>
      </div>
    </Scene>
  );
}

/* ------------------------------------------------------------------ */
/* 6. You just say yes.                                                */
/* ------------------------------------------------------------------ */

export const YESF = 190;
export function Yes() {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const HOLD0 = 70;
  const HOLD1 = HOLD0 + 45; // the one motion: a 1.5s fill
  const fill = interpolate(f, [HOLD0, HOLD1], [0, 1], clamp);
  const done = spring({ frame: f - HOLD1, fps, config: { damping: 16, stiffness: 120 } });
  const pressed = f >= HOLD0 && f < HOLD1 ? 1 : 0;
  const rx = key(f, [0, 40], [16, 0]);
  const sc = key(f, [0, 40, YESF], [0.9, 1, 1.04]);
  const cx = key(f, [24, HOLD0 - 4], [1700, 1265]);
  const cy = key(f, [24, HOLD0 - 4], [1000, 742]);
  return (
    <Scene dur={YESF}>
      <div style={{ position: "absolute", top: 110, width: W }}>
        <BlurLine words={words("You just say yes.", { yes: PARLU.accent })} start={4} size={96} />
      </div>
      <AbsoluteFill style={{ perspective: 2000, alignItems: "center", justifyContent: "center", paddingTop: 140 }}>
        <div
          style={{
            width: 1180,
            borderRadius: 40,
            padding: "44px 52px",
            background: interpolateColors(Math.min(1, done), [0, 1], [PARLU.ink, PARLU.accent]),
            color: "#fff",
            transform: `rotateX(${rx}deg) scale(${sc})`,
            boxShadow: "0 60px 100px -40px rgba(27,26,23,.55)",
            position: "relative",
            minHeight: 360,
          }}
        >
          <div style={{ opacity: 1 - done, position: done > 0.99 ? "absolute" : "relative" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <Bot shape="pebble" colour="coral" size={58} eyes={blinking(f, 3) ? "blink" : "idle"} />
              <div>
                <div style={{ fontSize: 26, fontWeight: 700 }}>Pip, your assistant</div>
                <div style={{ fontSize: 20, color: "#b9b4aa" }}>Nana's 80th · agreed with Wren</div>
              </div>
            </div>
            <div style={{ fontSize: 46, fontWeight: 700, letterSpacing: "-0.03em", lineHeight: 1.2, marginTop: 30, maxWidth: 1000 }}>
              Lunch at The Orangery, Sunday 14th, 1pm. Step-free, £60 each. Book it?
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 16, marginTop: 36 }}>
              <span style={{ fontSize: 24, fontWeight: 600, padding: "16px 30px", borderRadius: 999, boxShadow: "inset 0 0 0 2px #55524b" }}>Not now</span>
              <span
                style={{
                  fontSize: 24,
                  fontWeight: 700,
                  padding: "16px 34px",
                  borderRadius: 999,
                  color: PARLU.ink,
                  background: `linear-gradient(90deg, #c9efe9 ${fill * 100}%, #fff ${fill * 100}%)`,
                  boxShadow: `0 0 0 ${4 + pressed * 2}px ${fill > 0 ? PARLU.accent : "transparent"}`,
                  transform: `scale(${1 - pressed * 0.04})`,
                }}
              >
                Hold to say yes
              </span>
            </div>
          </div>
          {done > 0.01 ? (
            <div style={{ opacity: done, transform: `translateY(${(1 - done) * 20}px)`, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 272, gap: 26 }}>
              <div style={{ display: "flex", gap: 46 }}>
                <Pairing face={AMA} size={84} eyes="done" />
                <Pairing face={JOEL} bot="rose" shape="cloud" size={84} eyes="done" />
              </div>
              <div style={{ fontSize: 56, fontWeight: 700, letterSpacing: "-0.035em" }}>✓ Booked. Joel said yes too.</div>
            </div>
          ) : null}
        </div>
        {f > 20 && f < HOLD1 + 18 ? <Cursor x={cx} y={cy} down={pressed} /> : null}
      </AbsoluteFill>
    </Scene>
  );
}

/* ------------------------------------------------------------------ */
/* 7. Everyday life and work: a rolling list plus photo cards.         */
/* ------------------------------------------------------------------ */

const USES: { label: string; img: string; title: string; note: string; faces: string[]; len: number; team?: boolean }[] = [
  { label: "Birthdays and visits", img: "family", title: "Visit to Nana's, Saturday 2pm", note: "Both said yes", faces: [AMA, JOEL], len: 48 },
  { label: "Trips with friends", img: "friends", title: "Cornwall cottage, £160 each", note: "4 of 4 said yes", faces: ["px_13120070", "px_18039499", "px_33323689", AMA], len: 48 },
  { label: "Swimming and clubs", img: "school", title: "Swim club lifts, every Thursday", note: "Shared with 3 parents", faces: [JOEL, "px_40663010"], len: 48 },
  { label: "Days out", img: "days", title: "Zoo tickets for 6, Sunday", note: "Paid and split 3 ways", faces: [AMA, "px_18039499"], len: 48 },
  { label: "Work with a team", img: "team", title: "Launch website", note: "3 people, 3 assistants, one plan", faces: [AMA, JOEL, "px_13120070"], len: 88, team: true },
];
export const USESF = USES.reduce((a, u) => a + u.len, 0);

const TEAM: { who: string; shape: "pebble" | "cloud" | "bean"; colour: keyof typeof BOT_COLOURS; part: string; state: string; at: number }[] = [
  { who: "Pip", shape: "pebble", colour: "coral", part: "Writes the copy", state: "Done", at: 14 },
  { who: "Wren", shape: "cloud", colour: "rose", part: "Builds the page", state: "Done", at: 30 },
  { who: "Bo", shape: "bean", colour: "amber", part: "Books the domain", state: "Needs a yes", at: 46 },
];

export function Uses() {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  let acc = 0;
  const starts = USES.map((u) => {
    const s = acc;
    acc += u.len;
    return s;
  });
  const idx = Math.max(0, starts.findIndex((s, i) => f >= s && f < s + USES[i].len));
  // Smooth list position: ease between items over 12 frames.
  const pos = USES.reduce((p, _u, i) => p + key(f, [starts[i] - 6, starts[i] + 6], [0, 1]) * (i ? 1 : 0), 0);
  const ITEM = 104;
  return (
    <Scene dur={USESF}>
      <div style={{ position: "absolute", left: 170, top: 0, height: H, width: 820, overflow: "hidden", maskImage: "linear-gradient(transparent, #000 30%, #000 70%, transparent)", WebkitMaskImage: "linear-gradient(transparent, #000 30%, #000 70%, transparent)" }}>
        {USES.map((u, i) => {
          const d = Math.abs(i - pos);
          return (
            <div
              key={u.label}
              style={{
                position: "absolute",
                top: H / 2 - ITEM / 2 + (i - pos) * ITEM,
                fontSize: 80,
                fontWeight: 700,
                letterSpacing: "-0.045em",
                whiteSpace: "nowrap",
                color: d < 0.5 ? PARLU.ink : "#cfcbc4",
                filter: d > 0.5 ? `blur(${Math.min(3, d * 1.5)}px)` : undefined,
              }}
            >
              {u.label}
            </div>
          );
        })}
      </div>
      {USES.map((u, i) => {
        const local = f - starts[i];
        if (local < -14 || local > u.len + 14) return null;
        const inS = spring({ frame: local + 3, fps, config: { damping: 18, stiffness: 120 } });
        const out = i === USES.length - 1 ? 0 : interpolate(local, [u.len - 6, u.len + 12], [0, 1], clamp);
        const gone = i === USES.length - 1 ? 1 : interpolate(local, [u.len + 8, u.len + 13], [1, 0], clamp);
        const card = spring({ frame: local - 8, fps, config: { damping: 18, stiffness: 150 } });
        return (
          <div
            key={u.img}
            style={{
              position: "absolute",
              left: 1080,
              top: 150,
              width: 624,
              height: 780,
              borderRadius: 36,
              overflow: "hidden",
              boxShadow: "0 50px 90px -40px rgba(27,26,23,.5)",
              opacity: Math.min(1, inS * 3) * gone,
              transform: `translateX(${(1 - inS) * 160 - out * 120}px) rotate(${(1 - inS) * 4 - out * 3}deg) scale(${1 - out * 0.06})`,
              zIndex: i,
            }}
          >
            <Img src={staticFile(`cards/${u.img}.jpg`)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            <div
              style={{
                position: "absolute",
                left: 28,
                right: 28,
                bottom: 28,
                background: "rgba(255,255,255,.96)",
                borderRadius: 26,
                padding: "22px 26px",
                opacity: card,
                transform: `translateY(${(1 - card) * 30}px)`,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{ display: "flex" }}>
                  {u.faces.map((fc, k) => (
                    <div key={fc + k} style={{ marginLeft: k ? -14 : 0, borderRadius: 99, boxShadow: "0 0 0 3px #fff" }}>
                      <Face name={fc} size={44} />
                    </div>
                  ))}
                </div>
                <div style={{ fontSize: 25, fontWeight: 700, letterSpacing: "-0.02em" }}>{u.title}</div>
              </div>
              {u.team ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 16 }}>
                  {TEAM.map((t) => {
                    const r = spring({ frame: local - t.at, fps, config: { damping: 18, stiffness: 150 } });
                    return (
                      <div key={t.who} style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 21, fontWeight: 600, opacity: r, transform: `translateX(${(1 - r) * 20}px)` }}>
                        <Bot shape={t.shape} colour={t.colour} size={34} eyes={t.state === "Done" ? "done" : "idle"} />
                        <span style={{ width: 70 }}>{t.who}</span>
                        <span style={{ flex: 1, color: "#4a4740", fontWeight: 500 }}>{t.part}</span>
                        <span style={{ fontSize: 17, fontWeight: 700, padding: "5px 12px", borderRadius: 99, background: t.state === "Done" ? "#e2f3f0" : "#fdebe4", color: t.state === "Done" ? PARLU.accent : PARLU.coral }}>{t.state}</span>
                      </div>
                    );
                  })}
                </div>
              ) : null}
              <div style={{ marginTop: 12, fontSize: 20, fontWeight: 600, color: PARLU.accent }}>✓ {u.note}</div>
            </div>
          </div>
        );
      })}
      <div style={{ display: "none" }}>{idx}</div>
    </Scene>
  );
}

/* ------------------------------------------------------------------ */
/* 8. They do the back and forth. You say yes.                         */
/* ------------------------------------------------------------------ */

export const LINEF = 110;
export function Line() {
  return (
    <Scene dur={LINEF}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <BlurLine
          words={[
            ...words("They do the back and forth.").map((w) => ({ ...w, c: PARLU.faint })),
            { t: "\n" },
            ...words("You say yes.", { yes: PARLU.accent }),
          ]}
          start={4}
          stagger={5}
          size={124}
          style={{ maxWidth: 1600, rowGap: 6 }}
        />
      </AbsoluteFill>
    </Scene>
  );
}

/* ------------------------------------------------------------------ */
/* 9. End card.                                                        */
/* ------------------------------------------------------------------ */

export const END_F = 180;
export function End() {
  const f = useCurrentFrame();
  const sub = interpolate(f, [44, 60], [0, 1], clamp);
  return (
    <Scene dur={END_F} outF={24}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 40 }}>
        <Lockup at={4} />
        <div style={{ fontSize: 44, fontWeight: 600, color: PARLU.faint, letterSpacing: "-0.02em", opacity: sub, filter: `blur(${(1 - sub) * 8}px)` }}>
          Let your assistant sort it out with theirs.
        </div>
      </AbsoluteFill>
    </Scene>
  );
}

export { easeInOut };
