import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { PARLU } from "../brand";
import { clamp, easeOut } from "./kit";

/**
 * The Parlu ident. A person (teal) and their assistant (coral, with eyes)
 * come in from either side and meet. Where they overlap, the ink lens forms
 * and a single yes ring ripples out. Then the name rises letter by letter.
 */
export function Ident({ meet = 24, size = 1, tagline }: { meet?: number; size?: number; tagline?: string }) {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const travel = Math.min(meet, 22);
  const t = interpolate(f, [meet - travel, meet], [0, 1], { ...clamp, easing: (x) => 1 - Math.pow(1 - x, 3) });
  const settle = spring({ frame: f - meet, fps, config: { damping: 9, stiffness: 180, mass: 0.6 } });
  // Circles: final centres at 18 and 30 in a 48 box. Approach from far apart, overshoot a touch, settle.
  const gap = (1 - t) * 26 - (f >= meet ? Math.sin(settle * Math.PI) * 1.2 : 0);
  const tx = 18 - gap;
  const cx = 30 + gap;
  const arc = (1 - t) * (1 - t) * 8;
  const squash = f < meet ? 1 + (t > 0.85 ? (t - 0.85) * 0.3 : 0) : 1 + (1 - settle) * 0.04;
  const lens = interpolate(f, [meet - 1, meet + 4], [0, 1], clamp);
  const ring = interpolate(f, [meet, meet + 26], [0, 1], { ...clamp, easing: easeOut });
  const eyes = interpolate(f, [meet - 4, meet + 2], [1, 0], clamp);
  // Lockup: the mark slides left as the name arrives.
  const slide = interpolate(f, [meet + 10, meet + 34], [0, 1], { ...clamp, easing: easeOut });
  const mark = 190 * size;
  const word = 210 * size;
  const nameW = 560 * size;
  const tag = interpolate(f, [meet + 44, meet + 60], [0, 1], clamp);
  // Start big and close, then pull back into the lockup.
  const zoom = interpolate(f, [meet + 4, meet + 30], [1.9, 1], { ...clamp, easing: easeOut });
  const glow = interpolate(f, [meet - 2, meet + 6, meet + 40], [0, 0.55, 0], clamp);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 46 * size }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: mark * 1.3 }}>
        <div style={{ position: "relative", width: mark, height: mark, transform: `scale(${zoom})`, transformOrigin: `${50 + slide * 0}% 50%` }}>
          <div style={{ position: "absolute", inset: -mark * 0.6, borderRadius: "50%", background: `radial-gradient(circle, rgba(20,137,122,${glow * 0.5}), transparent 65%)` }} />
          <svg viewBox="0 0 48 48" width={mark} height={mark} style={{ overflow: "visible", position: "absolute", inset: 0 }}>
            <defs>
              <clipPath id="identPerson">
                <circle cx={tx} cy={24 - arc} r={12} />
              </clipPath>
            </defs>
            <circle cx={24} cy={24} r={14 + ring * 18} fill="none" stroke={PARLU.accent} strokeWidth={1.2 * (1 - ring)} opacity={f >= meet ? 1 - ring : 0} />
            <ellipse cx={tx} cy={24 - arc} rx={12 * squash} ry={12 / squash} fill={PARLU.accent} />
            <ellipse cx={cx} cy={24 - arc} rx={12 * squash} ry={12 / squash} fill={PARLU.sun} />
            <g opacity={eyes}>
              <rect x={cx - 3.6} y={20 - arc} width={2.4} height={4.4} rx={1.2} fill="#fff" />
              <rect x={cx + 1.4} y={20 - arc} width={2.4} height={4.4} rx={1.2} fill="#fff" />
            </g>
            <circle cx={cx} cy={24 - arc} r={12} fill={PARLU.ink} clipPath="url(#identPerson)" opacity={lens} />
          </svg>
        </div>
        <div style={{ width: slide * (nameW + 30 * size), overflow: "hidden", display: "flex", justifyContent: "flex-end" }}>
          <div style={{ display: "flex", fontSize: word, fontWeight: 700, letterSpacing: "-0.055em", lineHeight: 1, paddingBottom: 0.14 * word, paddingLeft: 30 * size, flex: "none" }}>
            {"Parlu".split("").map((ch, i) => {
              const s = spring({ frame: f - meet - 16 - i * 3, fps, config: { damping: 200, stiffness: 140 } });
              return (
                <span key={i} style={{ display: "inline-block", opacity: s, filter: `blur(${(1 - s) * 10}px)`, transform: `translateY(${(1 - s) * 0.35 * word}px)` }}>
                  {ch}
                </span>
              );
            })}
          </div>
        </div>
      </div>
      {tagline ? (
        <div style={{ fontSize: 44 * size, fontWeight: 600, color: PARLU.faint, letterSpacing: "-0.02em", opacity: tag, filter: `blur(${(1 - tag) * 8}px)`, transform: `translateY(${(1 - tag) * 16}px)` }}>
          {tagline}
        </div>
      ) : null}
    </div>
  );
}
