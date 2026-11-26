# Ask the owner by phone

When an assistant is unsure what its owner wants, it can ask a short question
with two to four answers. The owner answers from their phone (Telegram) or in
Assistant Central.

## What an answer means

An answer is information for the assistant. It never approves sending,
sharing, running or paying for anything: those keep their own exact owner
reviews in Central, with the owner's own session.

## Privacy

Questions and answers are encrypted to the owner's own key at rest and never
enter the conversation. Telegram bot chats are **not** end-to-end encrypted, so
the adapter has two modes:

| Mode | What reaches Telegram |
| --- | --- |
| `notice` (default) | Only "Your assistant has a question". The owner answers in Central. |
| `full` | The question and its answers, with a button for each. |

Reminders about waiting reviews (`nudge`) never include any content.

## Setting it up

1. Create a bot with Telegram's @BotFather and put its token in the host's
   `TELEGRAM_BOT_TOKEN` environment variable.
2. In Central, start pairing. You get a one-time code that lasts ten minutes.
3. Send `/start <code>` to your bot in a private chat. Only that chat is accepted
   from then on. Unpair at any time.
4. The host runs `TelegramPhone.poll_once()` in a loop and calls
   `send_waiting()` after an assistant asks. Long polling needs no public
   web address.

Each answer button carries a keyed tag bound to one question and one answer,
so a forged or altered button is refused. Taps from any other chat are ignored.

## Assistant tools

When the host passes a `QuestionAccess` to `mission_approvals.server.build_server`
as `owner_questions`, the assistant gets `ask_my_owner` and `owner_answer`.
