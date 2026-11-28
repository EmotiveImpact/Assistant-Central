import { Img, staticFile } from "remotion";
import { PARLU } from "../brand";

/** Parlu bot shapes and colours from the design system (viewBox 0 0 100 100). */
export const SHAPES = {
  pebble: "M50 7C77 7 94 23 94 51S77 94 49 94 6 79 6 51 23 7 50 7Z",
  bean: "M28 12C48 4 60 18 76 20 92 22 96 40 92 56 86 82 66 94 44 92 20 90 6 72 8 52 10 32 14 17 28 12Z",
  cloud:
    "M27 36C27 22 39 12 52 14 62 6 80 10 84 26 96 30 98 50 90 58 96 72 86 90 70 88 62 96 42 96 34 88 16 92 4 76 10 62 2 52 10 36 27 36Z",
  drop: "M50 6C68 26 90 44 90 64A40 32 0 0 1 10 64C10 44 32 26 50 6Z",
  squircle: "M50 6C84 6 94 16 94 50S84 94 50 94 6 84 6 50 16 6 50 6Z",
} as const;
export const BOT_COLOURS = {
  coral: "#ee7b5b",
  rust: "#c4522f",
  rose: "#d9668a",
  amber: "#e08a2e",
  clay: "#a8441f",
  berry: "#9c4a6b",
} as const;

export type Eyes = "idle" | "look" | "done" | "blink";

/** A bot blob with two eyes. Eyes carry state: idle, look (worried), done (happy). */
export function Bot({
  shape,
  colour,
  size,
  eyes = "idle",
  glance = 0,
}: {
  shape: keyof typeof SHAPES;
  colour: keyof typeof BOT_COLOURS;
  size: number;
  eyes?: Eyes;
  /** Horizontal eye shift, -1 (left) to 1 (right). */
  glance?: number;
}) {
  const c = BOT_COLOURS[colour];
  const g = glance * 5;
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} style={{ overflow: "visible" }}>
      <path d={SHAPES[shape]} fill={c} />
      {eyes === "done" ? (
        <path d="M33 52q7-9 14 0M55 52q7-9 14 0" stroke="#fff" strokeWidth={5.5} fill="none" strokeLinecap="round" />
      ) : eyes === "blink" ? (
        <path d={`M${34 + g} 47h10M${56 + g} 47h10`} stroke="#fff" strokeWidth={5} strokeLinecap="round" />
      ) : eyes === "look" ? (
        <g fill="#fff">
          <rect x={35 + g} y={38} width={10} height={17} rx={5} />
          <rect x={56 + g} y={38} width={10} height={17} rx={5} />
        </g>
      ) : (
        <g fill="#fff">
          <rect x={36 + g} y={38} width={8} height={15} rx={4} />
          <rect x={56 + g} y={38} width={8} height={15} rx={4} />
        </g>
      )}
    </svg>
  );
}

/** A person: a photo in a circle (people are circles; their bots sit beside them). */
export function Face({ name, size, ring = 0 }: { name: string; size: number; ring?: number }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        overflow: "hidden",
        boxShadow: ring ? `0 0 0 ${ring}px ${PARLU.accent}` : "0 20px 40px -24px rgba(27,26,23,.45)",
        flex: "none",
      }}
    >
      <Img src={staticFile(`faces/${name}.jpg`)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
    </div>
  );
}

/** Blink every ~2.5s, offset per bot. */
export const blinking = (frame: number, seed: number) => (frame + seed * 17) % 75 < 4;
