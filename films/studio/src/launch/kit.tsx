import React from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { PARLU } from "../brand";

/**
 * Shared pieces for the launch film. One visual language throughout:
 * white ground, ink type in one face, blur-in words, soft 3D product shots,
 * and every scene entering and leaving the same way (a short blur dip).
 */

export const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
export const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
export const easeInOut = Easing.bezier(0.65, 0, 0.35, 1);

/** Scene wrapper: soft ground, plus the shared blur dip in and out. */
export function Scene({ children, dur, inF = 10, outF = 10, bg = PARLU.bg }: {
  children: React.ReactNode;
  dur: number;
  inF?: number;
  outF?: number;
  bg?: string;
}) {
  const f = useCurrentFrame();
  const a = interpolate(f, [0, inF], [0, 1], { ...clamp, easing: easeOut });
  const b = interpolate(f, [dur - outF, dur], [1, 0], { ...clamp, easing: Easing.in(Easing.quad) });
  const v = Math.min(a, b);
  return (
    <AbsoluteFill style={{ background: bg, fontFamily: PARLU.font, color: PARLU.ink }}>
      <Ground />
      <AbsoluteFill style={{ opacity: v, filter: v < 1 ? `blur(${(1 - v) * 18}px)` : undefined, transform: `scale(${1.04 - 0.04 * v})` }}>
        {children}
      </AbsoluteFill>
    </AbsoluteFill>
  );
}

/** A barely-there warm glow so white never looks flat on video. */
export function Ground() {
  return (
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(1200px 700px at 50% 38%, rgba(20,137,122,.045), transparent 70%), radial-gradient(900px 600px at 80% 90%, rgba(238,123,91,.05), transparent 70%)",
      }}
    />
  );
}

type Word = { t: string; c?: string; w?: number };

/** Words that arrive one by one out of a blur. The trend type treatment. */
export function BlurLine({ words, start = 0, stagger = 4, size = 96, weight = 700, align = "center", leave, style }: {
  words: (string | Word)[];
  start?: number;
  stagger?: number;
  size?: number;
  weight?: number;
  align?: "center" | "left";
  /** Frame (scene time) when the line blurs away. */
  leave?: number;
  style?: React.CSSProperties;
}) {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const out = leave === undefined ? 1 : interpolate(f, [leave, leave + 10], [1, 0], clamp);
  return (
    <div
      style={{
        fontSize: size,
        fontWeight: weight,
        letterSpacing: "-0.045em",
        lineHeight: 1.04,
        textAlign: align,
        display: "flex",
        flexWrap: "wrap",
        justifyContent: align === "center" ? "center" : "flex-start",
        columnGap: size * 0.26,
        opacity: out,
        filter: out < 1 ? `blur(${(1 - out) * 14}px)` : undefined,
        ...style,
      }}
    >
      {words.map((w, i) => {
        const word: Word = typeof w === "string" ? { t: w } : w;
        if (word.t === "\n") return <div key={i} style={{ flexBasis: "100%", height: 0 }} />;
        const s = spring({ frame: f - start - i * stagger, fps, config: { damping: 200, stiffness: 120, mass: 0.7 } });
        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              color: word.c ?? PARLU.ink,
              fontWeight: word.w ?? weight,
              opacity: s,
              filter: `blur(${(1 - s) * 16}px)`,
              transform: `translateY(${(1 - s) * 0.32 * size}px)`,
            }}
          >
            {word.t}
          </span>
        );
      })}
    </div>
  );
}

/** Split a sentence into words, colouring any listed ones. */
export const words = (s: string, colours: Record<string, string> = {}): Word[] =>
  s.split(" ").map((t) => ({ t, c: colours[t.replace(/[.,?!]/g, "")] }));

/** Small grey label above a heading, like the site's eyebrow. */
export function Eyebrow({ children, at = 0 }: { children: React.ReactNode; at?: number }) {
  const f = useCurrentFrame();
  const o = interpolate(f, [at, at + 10], [0, 1], clamp);
  return (
    <div style={{ fontSize: 26, fontWeight: 600, letterSpacing: "0.14em", textTransform: "uppercase", color: PARLU.faint, opacity: o }}>
      {children}
    </div>
  );
}

/** A macOS-style pointer. Scales down a touch while pressed. */
export function Cursor({ x, y, down = 0 }: { x: number; y: number; down?: number }) {
  return (
    <svg
      viewBox="0 0 28 28"
      width={44}
      height={44}
      style={{ position: "absolute", left: x, top: y, transform: `scale(${1 - down * 0.14})`, transformOrigin: "4px 4px", filter: "drop-shadow(0 6px 10px rgba(0,0,0,.25))", zIndex: 50 }}
    >
      <path d="M5 3l16 11.2-7 .9 4 8.1-3 1.4-4-8.2-6 4.6z" fill="#1b1a17" stroke="#fff" strokeWidth={1.6} strokeLinejoin="round" />
    </svg>
  );
}

/** Interpolate a value along keyframes with the film's easing. */
export const key = (f: number, at: number[], vals: number[], ease = easeInOut) =>
  interpolate(f, at, vals, { ...clamp, easing: ease });
