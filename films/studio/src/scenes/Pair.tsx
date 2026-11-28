import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { PARLU } from "../brand";
import { Bot, blinking, Face } from "./Bot";

/**
 * Ama and Joel, each with their assistant beside them (Pip and Wren).
 * "talk": Ama asks, then glass orbs carry the back and forth between the two
 * assistants while a counter ticks. "yes": one question comes to both of them,
 * they each say yes, and it's booked.
 */
const FACE = 300;
const BOT = 130;
const AMA = { face: "px_11215202", x: -600 };
const JOEL = { face: "px_40704337", x: 600 };
const ROW = 40; // offset from centre
const PIP = { x: AMA.x + FACE / 2 + 18 + BOT / 2, y: ROW + 80 };
const WREN = { x: JOEL.x - FACE / 2 - 18 - BOT / 2, y: ROW + 80 };

const TRIPS = 14;
const TRIP_LEN = 20;
const TRIP_GAP = 7;
const TALK_START = 34;
const CHIPS = ["Sunday 14th?", "1pm works", "Step-free?", "Yes, ramp", "The Orangery", "£60 each"];

function Orb({ x, y, r }: { x: number; y: number; r: number }) {
  return (
    <div
      style={{
        position: "absolute",
        left: x - r,
        top: y - r,
        width: r * 2,
        height: r * 2,
        borderRadius: "50%",
        background: `radial-gradient(circle at 35% 30%, #fff 0 8%, #f9b7a1 22%, ${PARLU.sun} 55%, #c4522f 100%)`,
        boxShadow: "0 8px 18px -8px rgba(196,82,47,.6)",
      }}
    />
  );
}

export function Pair({ phase }: { phase: "talk" | "yes" }) {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const cx = width / 2;
  const cy = height / 2;
  const fadeIn = phase === "talk" ? interpolate(frame, [0, 8], [0, 1], { extrapolateRight: "clamp" }) : 1;
  const exit = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  // ── talk ──
  const ask = phase === "talk" ? spring({ frame: frame - 6, fps, config: { damping: 14 } }) : 0;
  const askOut = interpolate(frame, [TALK_START + 40, TALK_START + 52], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const landed = phase === "talk"
    ? Array.from({ length: TRIPS }, (_, k) => frame >= TALK_START + k * TRIP_GAP + TRIP_LEN).filter(Boolean).length
    : TRIPS;
  const working = phase === "talk" && frame >= TALK_START;

  // ── yes ──
  const card = phase === "yes" ? spring({ frame: frame - 4, fps, config: { damping: 15, stiffness: 140 } }) : 0;
  const amaYes = phase === "yes" ? spring({ frame: frame - 34, fps, config: { damping: 10, stiffness: 220 } }) : 0;
  const joelYes = phase === "yes" ? spring({ frame: frame - 52, fps, config: { damping: 10, stiffness: 220 } }) : 0;
  const booked = phase === "yes" ? interpolate(frame, [66, 74], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0;

  const eyesFor = (seed: number, saidYes: number) =>
    saidYes > 0.5 ? "done" : blinking(frame, seed) ? "blink" : working ? "idle" : "idle";
  const pipBob = Math.sin(frame / 8) * 6;
  const wrenBob = Math.sin(frame / 8 + 2) * 6;

  const person = (p: typeof AMA, name: string, yes: number) => (
    <div style={{ position: "absolute", left: cx + p.x - FACE / 2, top: cy + ROW - FACE / 2, width: FACE, textAlign: "center" }}>
      <Face name={p.face} size={FACE} ring={yes > 0.5 ? 8 : 0} />
      <div style={{ marginTop: 22, fontSize: 40, fontWeight: 700, color: PARLU.ink, letterSpacing: "-0.03em" }}>{name}</div>
      {yes > 0 && (
        <div
          style={{
            position: "absolute",
            top: -26,
            left: "50%",
            transform: `translateX(-50%) scale(${yes})`,
            background: PARLU.accent,
            color: "#fff",
            fontWeight: 800,
            fontSize: 38,
            padding: "10px 28px",
            borderRadius: 999,
            boxShadow: "0 14px 30px -14px rgba(20,137,122,.8)",
          }}
        >
          Yes
        </div>
      )}
    </div>
  );

  return (
    <AbsoluteFill style={{ background: PARLU.bg, fontFamily: PARLU.font, opacity: fadeIn * exit }}>
      {person(AMA, "Ama", amaYes)}
      {person(JOEL, "Joel", joelYes)}
      <div style={{ position: "absolute", left: cx + PIP.x - BOT / 2, top: cy + PIP.y - BOT / 2 + pipBob }}>
        <Bot shape="pebble" colour="coral" size={BOT} eyes={eyesFor(1, amaYes)} glance={working ? 1 : 0} />
      </div>
      <div style={{ position: "absolute", left: cx + WREN.x - BOT / 2, top: cy + WREN.y - BOT / 2 + wrenBob }}>
        <Bot shape="cloud" colour="rose" size={BOT} eyes={eyesFor(3, joelYes)} glance={working ? -1 : 0} />
      </div>

      {/* Ama's ask */}
      {phase === "talk" && (
        <div
          style={{
            position: "absolute",
            left: cx + AMA.x - FACE / 2 + 10,
            top: cy + ROW - FACE / 2 - 150,
            transform: `scale(${ask})`,
            transformOrigin: "20% 100%",
            opacity: askOut,
            background: "#fff",
            border: `2px solid ${PARLU.line}`,
            borderRadius: 28,
            padding: "20px 28px",
            fontSize: 34,
            fontWeight: 600,
            color: PARLU.ink,
            whiteSpace: "nowrap",
            boxShadow: "0 20px 40px -24px rgba(27,26,23,.4)",
          }}
        >
          “Sort Mum's birthday lunch with Joel.”
        </div>
      )}

      {/* The back and forth */}
      {phase === "talk" &&
        Array.from({ length: TRIPS }, (_, k) => {
          const t = (frame - TALK_START - k * TRIP_GAP) / TRIP_LEN;
          if (t < 0 || t > 1) return null;
          const forward = k % 2 === 0;
          const e = Easing.inOut(Easing.cubic)(t);
          const edge = BOT / 2 + 30;
          const from = forward ? { x: PIP.x + edge, y: PIP.y } : { x: WREN.x - edge, y: WREN.y };
          const to = forward ? { x: WREN.x - edge, y: WREN.y } : { x: PIP.x + edge, y: PIP.y };
          const x = from.x + (to.x - from.x) * e;
          const lift = (forward ? -1 : 1) * Math.sin(Math.PI * e) * 150;
          const y = from.y + (to.y - from.y) * e + lift - 10;
          return <Orb key={k} x={cx + x} y={cy + y} r={26} />;
        })}
      {phase === "talk" &&
        CHIPS.map((chip, k) => {
          const mid = TALK_START + 46 + k * 10;
          const o = interpolate(frame, [mid - 4, mid + 2, mid + 22, mid + 30], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          const y = interpolate(frame, [mid - 4, mid + 30], [20, -30], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          const row = k % 3;
          return (
            <div
              key={chip}
              style={{
                position: "absolute",
                left: cx - 160 + (k % 2) * 60,
                width: 320,
                textAlign: "center",
                top: cy - 300 + row * 70 + y,
                opacity: o,
              }}
            >
              <span style={{ background: PARLU.raised, borderRadius: 999, padding: "10px 22px", fontSize: 30, fontWeight: 600, color: PARLU.ink }}>
                {chip}
              </span>
            </div>
          );
        })}
      {phase === "talk" && working && (
        <div
          style={{
            position: "absolute",
            bottom: 90,
            width: "100%",
            textAlign: "center",
            fontSize: 40,
            fontWeight: 600,
            color: PARLU.faint,
            letterSpacing: "-0.02em",
          }}
        >
          <span style={{ color: PARLU.ink, fontVariantNumeric: "tabular-nums" }}>{landed}</span> messages between their assistants.{" "}
          <span style={{ color: PARLU.ink }}>None from them.</span>
        </div>
      )}

      {/* The one question */}
      {phase === "yes" && (
        <div
          style={{
            position: "absolute",
            left: cx - 330,
            top: cy - 330,
            width: 660,
            transform: `translateY(${(1 - card) * 120}px)`,
            opacity: card,
            background: "#fff",
            borderRadius: 32,
            padding: "34px 38px",
            boxShadow: "0 30px 70px -30px rgba(27,26,23,.45), 0 0 0 2px #ebebe9",
            textAlign: "left",
          }}
        >
          <div style={{ fontSize: 26, fontWeight: 600, color: PARLU.faint }}>For Ama and Joel</div>
          <div style={{ fontSize: 46, fontWeight: 800, color: PARLU.ink, letterSpacing: "-0.035em", marginTop: 6 }}>
            Mum's birthday lunch
          </div>
          <div style={{ fontSize: 32, fontWeight: 500, color: PARLU.ink, marginTop: 14, lineHeight: 1.45 }}>
            Sunday 14th, 1pm
            <br />
            The Orangery (step-free)
            <br />
            £60 each
          </div>
          <div
            style={{
              marginTop: 22,
              fontSize: 34,
              fontWeight: 800,
              color: booked ? PARLU.accent : PARLU.ink,
            }}
          >
            {booked > 0 ? (
              <span style={{ opacity: booked }}>✓ Booked</span>
            ) : (
              "Book it?"
            )}
          </div>
        </div>
      )}
    </AbsoluteFill>
  );
}
