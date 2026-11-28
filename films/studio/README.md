# Parlu film studio (Remotion)

Code-made films for Parlu, built with [Remotion](https://www.remotion.dev) and
components from [snapcn](https://snapcn.dev) (MIT). The snapcn sources are
copied into `src/components/snap-cn/` and `src/lib/snap-cn-ui/`, so this
project owns and can edit them.

## Films

- `OrbFlicker` (21.4s, 1920x1080, 30fps): the orb and flicker sting.
  Hello Zoom, Drop Line, a hand-built group chat scene, Text Rewrite,
  Orb Swarm, Text Reveal and Logo Flicker, in Parlu's colours and type.

- `OrbFlickerV2` (43.3s): the slower cut after Edem's feedback ("way too
  fast", "more interaction with photos"). Real people and their assistants
  from the start (`scenes/PeopleIntro.tsx`), Ama and Joel's assistants doing
  the back and forth and both saying yes (`scenes/Pair.tsx`), every snapcn
  scene slowed with its `speed` prop. Render with
  `npx remotion render src/index.ts OrbFlickerV2 out/v2.mp4`.

## Use

```bash
npm install
npm run studio        # preview and scrub in the browser
npm run render        # writes out/parlu-orb-flicker.mp4 (silent)
npm run typecheck
```

The render is silent. Music is muxed afterwards with ffmpeg (see the PR for
the exact command and the music's licence status).

In a cloud container whose proxy uses its own certificate authority, render
with the full Chromium so Google Fonts load:
`--browser-executable=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome --chrome-mode=chrome-for-testing`.

`src/Player.tsx` exports `OrbFlickerPlayer`, a `@remotion/player` wrapper for
showing the film inside a React page.

## Adding more snapcn components

```bash
npx shadcn@latest add @snapcn/<name>
```

The registry is set in `components.json`; `@/` resolves to `src/` through
`remotion.config.ts`.

## Assets and licences

- Photos in `public/photos/` are from Pexels (free commercial use, no credit
  needed).
- Remotion is free for individuals and companies of up to three people;
  larger companies need a Remotion company licence.

## Photosensitivity

Full-screen photo flicker is held to at least six frames a photo at 30fps
(five changes a second, so under three flashes a second), and photos run from
darker to brighter. Check any new flicker against the WCAG three-flashes rule
before sharing.

## Embedding the Player

`OrbFlickerPlayer` loads photos through `staticFile()`, so a host page must
serve `films/studio/public/` at its root (or copy `public/photos/` there).

## Launch film (`Launch`)

The top level launch film: 62.6 seconds, nine beats on white in one typeface,
with the Parlu app rebuilt as components (`src/launch/App.tsx`) so the camera
can move through it. Scenes are in `src/launch/scenes.tsx` and shared pieces
(blur-in words, the scene blur dip, the pointer) in `src/launch/kit.tsx`.
Photo cards in `public/cards/` come from the website mock (Pexels, free licence).

Music is an ElevenLabs track at 120 bpm, not stored here. To fit it: start at
1.0s and repeat 22.04 to 30.04s once after 30.04s, so the drop lands on
"Introducing" (frame 511) and the break lands on the hold to say yes (the beat
returns on "Booked", frame 1233). The flash check measures at most one flash
per second.
