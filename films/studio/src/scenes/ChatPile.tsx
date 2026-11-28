import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { PARLU } from "../brand";

/**
 * The group chat that never stops. A phone pulls back from close up while the
 * unread count races, and the messages everyone has sent burst out around it,
 * each from a real face. Motion idea taken from a hype-reel reference (counter
 * plus pop-out bubbles around a phone), rebuilt for Parlu.
 */

const MESSAGES: { text: string; face: string; x: number; y: number; at: number; side: "l" | "r" }[] = [
  { text: "Who's free Sunday?", face: "px_11215202", x: -520, y: -300, at: 10, side: "l" },
  { text: "Can't do Saturday", face: "px_13120070", x: 470, y: -220, at: 14, side: "r" },
  { text: "Has anyone booked yet?", face: "px_38602608", x: -600, y: -40, at: 18, side: "l" },
  { text: "What about the 14th?", face: "px_40899157", x: 520, y: 40, at: 22, side: "r" },
  { text: "Who owes who?", face: "px_33323689", x: -480, y: 220, at: 26, side: "l" },
  { text: "Sorry, only just seen this", face: "px_8868795", x: 500, y: 290, at: 30, side: "r" },
  { text: "Can someone just decide?", face: "px_40704337", x: -170, y: 420, at: 36, side: "l" },
];

const THREAD = [
  "Mum's 70th!! Ideas?",
  "Lunch somewhere nice?",
  "Sunday works for me",
  "I'm away Sunday",
  "Saturday then?",
  "Can't do Sat",
  "Who's booking?",
  "I can, what budget?",
  "Not too pricey pls",
  "The Orangery?",
  "Is it step-free?",
  "No idea",
  "Has anyone asked Dad?",
  "??",
];

export function ChatPile() {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Phone pulls back from close up, like the reference.
  const pull = interpolate(frame, [0, 18], [2.4, 1], {
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  // Unread counter races and tops out.
  const raw = Math.floor(
    interpolate(frame, [0, 46], [3, 140], {
      extrapolateRight: "clamp",
      easing: Easing.in(Easing.quad),
    }),
  );
  const count = raw >= 99 ? "99+" : String(raw);
  const exit = interpolate(frame, [durationInFrames - 6, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  // Thread scrolls as new lines arrive every three frames.
  const shown = Math.min(THREAD.length, Math.floor(frame / 3) + 4);
  const shake = frame > 40 ? Math.sin(frame * 2.1) * 3 : 0;

  return (
    <AbsoluteFill style={{ background: PARLU.bg, fontFamily: PARLU.font, opacity: exit }}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <div
          style={{
            width: 430,
            height: 860,
            borderRadius: 64,
            background: PARLU.raised,
            border: `10px solid ${PARLU.ink}`,
            boxShadow: "0 40px 80px -30px rgba(27,26,23,.35)",
            transform: `scale(${pull}) translateX(${shake}px)`,
            overflow: "hidden",
            position: "relative",
          }}
        >
          <div
            style={{
              padding: "48px 28px 18px",
              borderBottom: `2px solid ${PARLU.line}`,
              background: "#fff",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div style={{ fontWeight: 700, fontSize: 26, color: PARLU.ink }}>Mum's 70th</div>
            <div
              style={{
                background: PARLU.sun,
                color: "#fff",
                fontWeight: 800,
                fontSize: 24,
                borderRadius: 999,
                padding: "6px 16px",
                minWidth: 64,
                textAlign: "center",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {count}
            </div>
          </div>
          <div
            style={{
              position: "absolute",
              left: 20,
              right: 20,
              bottom: 24,
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            {THREAD.slice(0, shown).slice(-9).map((line, i, arr) => {
              const mine = (THREAD.indexOf(line) % 3) === 1;
              const isNew = i === arr.length - 1;
              return (
                <div
                  key={line}
                  style={{
                    alignSelf: mine ? "flex-end" : "flex-start",
                    background: mine ? PARLU.accent : "#fff",
                    color: mine ? "#fff" : PARLU.ink,
                    fontSize: 22,
                    fontWeight: 500,
                    padding: "12px 18px",
                    borderRadius: 22,
                    maxWidth: "80%",
                    boxShadow: "0 1px 2px rgba(27,26,23,.08)",
                    transform: isNew ? `scale(${interpolate(frame % 3, [0, 2], [0.85, 1])})` : undefined,
                  }}
                >
                  {line}
                </div>
              );
            })}
          </div>
        </div>
      </AbsoluteFill>

      {MESSAGES.map((m) => {
        const s = spring({ frame: frame - m.at, fps, config: { damping: 12, stiffness: 220, mass: 0.6 } });
        if (frame < m.at) return null;
        return (
          <div
            key={m.text}
            style={{
              position: "absolute",
              left: "50%",
              top: "50%",
              transform: `translate(-50%, -50%) translate(${m.x}px, ${m.y}px) scale(${s})`,
              display: "flex",
              flexDirection: m.side === "l" ? "row" : "row-reverse",
              alignItems: "center",
              gap: 14,
            }}
          >
            <Img
              src={staticFile(`photos/${m.face}.jpg`)}
              style={{ width: 76, height: 76, borderRadius: 999, objectFit: "cover", border: `4px solid ${PARLU.accent}` }}
            />
            <div
              style={{
                background: "#fff",
                color: PARLU.ink,
                fontSize: 30,
                fontWeight: 600,
                padding: "16px 24px",
                borderRadius: 26,
                whiteSpace: "nowrap",
                boxShadow: "0 18px 40px -18px rgba(27,26,23,.35), 0 0 0 2px #ebebe9",
              }}
            >
              {m.text}
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
}
