# Parlu on your phone

The Parlu phone app, built with Expo for iPhone and Android. It follows the approved full
app mock and the phone direction: "calm on the surface, deep on demand".

Your assistant does the back and forth with other people's assistants. The phone brings you
only the decisions:

- **Floating layers**, as in the approved mock: decisions rise in a sheet over a dimmed Home
  (drag it down to put it away), the + button fans out a menu, your circle drops a menu,
  search floats at the top, and short notes rise above the frosted glass bar. Pages slide
  in, cards swipe and spring, and assistants blink while they wait. Motion runs on the UI
  thread with Reanimated and Gesture Handler.
- **Home**: a short, honest paragraph with each person and their assistant inline, then one
  card at a time. Swipe right or tap to open it, left for the next. A swipe never agrees to
  anything by itself.
- **Decide**: one sheet for every kind of decision. It leads with who is asking and what will
  happen (Spends, Shares, Keeps), shows the exact text, and asks you to **hold** for money and
  consent. Letting go early does nothing, and there is always a plain button instead.
- **Agreed**: both assistants light up side by side, each beside its owner, then the receipt.
- **Questions from your assistant**, answered with a tap. An answer is information, never an
  approval.
- **Messages your assistant wants to send**, with the exact text.
- **Team missions**: parts, people and receipts, with "Review and send" and "Check the result".
- **Invite and join**: make an invite with a QR code and a short code to check, scan someone
  else's, or paste their link.
- **Recents**, **Money and assistants**, **Settings** and the **evening story**.

Customers never bring an AI key. Their own assistant does the thinking; Parlu runs no AI.

## Try it now

You need Node 22 and the free Expo Go app on your phone. No Expo account is needed.

```sh
cd phone_app
npm ci
npx expo start
```

Scan the QR code with your phone's camera (iPhone) or Expo Go (Android), then choose
**Try it with made-up people**. The demo runs entirely on the phone with fictional people,
in exactly the shapes the real owner API returns. Its password, when it asks again, is `demo`.

`npx expo start --web` opens the same app in a browser for a quick look.

## Connect your own Parlu

The phone talks to the Parlu on your computer through the same owner API as the desktop app.
It signs in with your password and gets the same 15-minute session. The session and password
live only in memory; only the address is remembered. Your keys never leave the computer.

The computer's Parlu only listens on its own loopback address, so the phone reaches it through
a private, encrypted link. The simplest is [Tailscale](https://tailscale.com) on both devices:

```sh
# On the computer
tailscale serve --bg 8877
python -m workspace_ui.server serve --directory ~/parlu --port 8877 \
  --relay https://parlu-relay.vercel.app --phone-host my-mac.tail1234.ts.net
```

Then type `my-mac.tail1234.ts.net` (your machine's Tailscale name) into **Connect your Parlu**.
`--phone-host` adds that one name to what the server accepts, for the owner API only: no web
page, no peer inbox, and a request from any web page (anything sending an Origin) is refused.
The app refuses plain `http` addresses except loopback, so a password never crosses a network
unencrypted.

## How it shares code with the desktop

The phone imports the desktop's own pure modules straight from the repository
(`src/shared/web.ts`): what Home says and the order of the queue, the Spends, Shares and Keeps
rows, when a hold is needed, team mission steps, invite links, the QR encoder, bot shapes and
colours, and the review checks from `pilot/web/model.mjs`. So the phone and the desktop always
say the same thing about the same saved state. `metro.config.js` lets the bundler read those
two folders.

## Checks

```sh
npx tsc --noEmit
npx jest
npx expo export --platform android
```

CI runs these on every change to `phone_app/` or the shared modules
(`.github/workflows/phone-app.yml`).

## Not in this version

- **Notifications.** Telling your phone something is waiting needs a push service that is
  always on. That means a new hosted piece and an Expo account, so it waits for a decision.
- **Store builds.** Putting the app in the App Store and Google Play needs an Expo (EAS)
  account, an Apple developer account ($99 a year) and a Google Play account ($25 once).
  The bundle identifier is set to `app.parlu.phone` ready for that.
- Starting a new team mission, conversations, shared draft authoring and app drafts still
  open on the computer. Home says so when one of those is waiting.
