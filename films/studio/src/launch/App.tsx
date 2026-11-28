import React from "react";
import { PARLU, MARK_SVG } from "../brand";
import { Bot, Face } from "../scenes/Bot";

/**
 * The Parlu app, rebuilt from the live demo (parlu-app.vercel.app) as plain
 * components so the camera can move through it and stay sharp at any zoom.
 * People are face photos with their assistant beside them.
 */

export const AMA = "px_11215202";
export const JOEL = "px_40704337";

const NAV: [string, string?][] = [["Home", "3"], ["Rooms", "2"], ["Groups"], ["Recents"], ["Assistants"], ["Money"]];

export function AppWindow({ children, width = 1600, height = 980 }: { children: React.ReactNode; width?: number; height?: number }) {
  return (
    <div
      style={{
        width,
        height,
        borderRadius: 28,
        background: "#fafaf9",
        boxShadow: "0 0 0 1.5px rgba(27,26,23,.08), 0 60px 120px -40px rgba(27,26,23,.35), 0 20px 40px -20px rgba(27,26,23,.15)",
        display: "flex",
        overflow: "hidden",
        fontFamily: PARLU.font,
        color: PARLU.ink,
      }}
    >
      <Sidebar />
      <div style={{ flex: 1, margin: "16px 16px 16px 0", background: "#fff", borderRadius: 22, boxShadow: "0 0 0 1.5px #efeeec", position: "relative", overflow: "hidden" }}>
        {children}
      </div>
    </div>
  );
}

function Sidebar() {
  return (
    <div style={{ width: 300, padding: "30px 22px", display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "0 10px 26px" }}>
        <img src={MARK_SVG} style={{ width: 34, height: 34 }} />
        <span style={{ fontSize: 30, fontWeight: 700, letterSpacing: "-0.045em" }}>Parlu</span>
      </div>
      {NAV.map(([n, c], i) => (
        <div
          key={n}
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "12px 16px",
            borderRadius: 14,
            fontSize: 19,
            fontWeight: 600,
            background: i === 0 ? PARLU.ink : "transparent",
            color: i === 0 ? "#fff" : "#3a3833",
          }}
        >
          {n}
          {c ? <span style={{ background: PARLU.sun, color: "#fff", borderRadius: 999, fontSize: 14, padding: "2px 9px" }}>{c}</span> : null}
        </div>
      ))}
      <div style={{ fontSize: 15, color: PARLU.faint, fontWeight: 600, padding: "18px 16px 4px" }}>Your rooms</div>
      {["Nana's 80th", "Launch website"].map((r, i) => (
        <div key={r} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 16px", fontSize: 18, fontWeight: 500 }}>
          <span style={{ width: 22, height: 22, borderRadius: 7, background: i ? "#2f6f9f" : PARLU.accent }} />
          {r}
        </div>
      ))}
      <div style={{ flex: 1 }} />
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: 14, borderRadius: 18, background: "#fff", boxShadow: "0 0 0 1.5px #efeeec" }}>
        <Face name={AMA} size={44} />
        <div style={{ lineHeight: 1.25 }}>
          <div style={{ fontWeight: 700, fontSize: 17 }}>Ama</div>
          <div style={{ fontSize: 14, color: PARLU.faint }}>
            <span style={{ color: PARLU.accent }}>●</span> Pip is ready
          </div>
        </div>
      </div>
    </div>
  );
}

/** Face with its assistant tucked beside it, as in the app. */
export function Pairing({ face, bot = "coral", shape = "pebble", size = 40, eyes = "idle" }: {
  face: string;
  bot?: "coral" | "rose" | "amber" | "rust" | "berry" | "clay";
  shape?: "pebble" | "cloud" | "bean" | "drop" | "squircle";
  size?: number;
  eyes?: "idle" | "look" | "done" | "blink";
}) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: size * 0.12 }}>
      <Face name={face} size={size} />
      <Bot shape={shape} colour={bot} size={size * 0.92} eyes={eyes} />
    </span>
  );
}

/** The composer at the foot of Home: "Ask Pip to start something". */
export function Composer({ typed, caret, sent }: { typed: string; caret: boolean; sent: number }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 16,
        padding: "16px 16px 16px 30px",
        borderRadius: 999,
        background: "#fff",
        boxShadow: "0 0 0 1.5px #e6e5e2, 0 14px 30px -18px rgba(27,26,23,.25)",
        fontSize: 26,
        fontWeight: 500,
      }}
    >
      <span style={{ flex: 1, color: typed ? PARLU.ink : PARLU.faint, whiteSpace: "nowrap", overflow: "hidden" }}>
        {typed || "Ask Pip to start something…"}
        {caret ? <span style={{ display: "inline-block", width: 3, height: 30, background: PARLU.accent, marginLeft: 3, verticalAlign: -5 }} /> : null}
      </span>
      <span
        style={{
          width: 58,
          height: 58,
          borderRadius: 999,
          background: sent ? PARLU.accent : PARLU.ink,
          color: "#fff",
          display: "grid",
          placeItems: "center",
          fontSize: 30,
          transform: `scale(${1 - sent * 0.1})`,
        }}
      >
        ↑
      </span>
    </div>
  );
}
