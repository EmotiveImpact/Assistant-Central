import React from "react";
import { Img, staticFile } from "remotion";
import { PARLU } from "../brand";
import { Bot, BOT_COLOURS, SHAPES, type Eyes } from "../scenes/Bot";

/**
 * The cast: studio portraits (Pexels, free licence) cut out and set on soft
 * tints so everyone shares one light and one look. Each person keeps their
 * own assistant, which sits at the card's shoulder and never covers them.
 */
export const PEOPLE = {
  ama: { name: "Ama", tint: "#f6e7de", shape: "pebble", colour: "coral", bot: "Pip" },
  joel: { name: "Joel", tint: "#deeeea", shape: "cloud", colour: "rose", bot: "Wren" },
  kemi: { name: "Kemi", tint: "#f7ecd6", shape: "bean", colour: "amber", bot: "Bo" },
  ken: { name: "Ken", tint: "#e6ecf4", shape: "drop", colour: "berry", bot: "Moss" },
  nana: { name: "Nana", tint: "#f3e5e8", shape: "squircle", colour: "rust", bot: "Dot" },
  frank: { name: "Frank", tint: "#ece9e2", shape: "pebble", colour: "clay", bot: "Rio" },
} as const satisfies Record<string, { name: string; tint: string; shape: keyof typeof SHAPES; colour: keyof typeof BOT_COLOURS; bot: string }>;

export type Who = keyof typeof PEOPLE;

/** A tall portrait card with its assistant at the shoulder. */
export function Portrait({ who, width, eyes = "idle", glance = 0, drift = 0, botScale = 1, label, botLift = 0, botSide = "right", style }: {
  who: Who;
  width: number;
  eyes?: Eyes;
  glance?: number;
  /** Small inner parallax, -1 to 1, so the person moves against the card. */
  drift?: number;
  botScale?: number;
  label?: React.ReactNode;
  botLift?: number;
  botSide?: "left" | "right";
  style?: React.CSSProperties;
}) {
  const p = PEOPLE[who];
  const h = width * 1.25;
  const bot = width * 0.36 * botScale;
  return (
    <div style={{ position: "relative", width, height: h, ...style }}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: width * 0.09,
          overflow: "hidden",
          background: `radial-gradient(120% 90% at 50% 20%, #fff8, transparent 60%), ${p.tint}`,
          boxShadow: "0 40px 80px -36px rgba(27,26,23,.45), 0 0 0 1px rgba(27,26,23,.04)",
        }}
      >
        <Img
          src={staticFile(`people/${who}.png`)}
          style={{ position: "absolute", width: "108%", left: "-4%", top: `${2 + drift * 2}%`, transform: `translateX(${drift * width * 0.025}px)` }}
        />
      </div>
      <div style={{ position: "absolute", [botSide]: -bot * 0.42, top: -bot * 0.38 - botLift }}>
        <Bot shape={p.shape} colour={p.colour} size={bot} eyes={eyes} glance={glance} />
      </div>
      {label ? (
        <div style={{ position: "absolute", top: h + width * 0.06, width: "100%", textAlign: "center", fontSize: width * 0.085, fontWeight: 700, color: PARLU.ink }}>{label}</div>
      ) : null}
    </div>
  );
}
