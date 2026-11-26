# Ask the owner by phone

When an assistant is unsure what its owner wants, it can ask a short question
with two to four answers. The owner answers from their phone (Telegram) or in
Parlu.

## What an answer means

An answer is information for the assistant. It never approves sending,
sharing, running or paying for anything: those keep their own exact owner
reviews in Parlu, with the owner's own session.

## Privacy

Questions and answers are encrypted to the owner's own key at rest and never
enter the conversation. Telegram bot chats are **not** end-to-end encrypted, so
the adapter has two modes:

| Mode | What reaches Telegram |
| --- | --- |
| `notice` (default) | Only "Your assistant has a question". The owner answers in Parlu. |
| `full` | The question and its answers, with a button for each. |

Reminders about waiting reviews (`nudge`) never include any content.

## Setting it up

1. Create a bot with Telegram's @BotFather and put its token in the host's
   `TELEGRAM_BOT_TOKEN` environment variable.
2. Add `"phone": {"telegram": "notice"}` (or `"full"`) to Parlu's private
   conversation configuration and start Parlu as usual. While Parlu runs, it
   long-polls the bot (no public web address needed) and sends each new
   question once to the paired chat. Only the person who runs that copy of
   Parlu gets the bot.
3. In Parlu, open **Settings**, then **Questions on your phone**, then
   **Pair your phone**. Scan the QR code or tap **Open Telegram**, and press
   Start. The one-time code lasts ten minutes, and only that chat is accepted
   from then on. Unpair at any time from the same panel.

Hosts that run their own loop can still call `TelegramPhone.poll_once()` and
`send_waiting()` directly; `owner_phone/runner.py` is that loop.

Each answer button carries a keyed tag bound to one question and one answer,
so a forged or altered button is refused. Taps from any other chat are ignored.

## Assistant tools

When the host passes a `QuestionAccess` to `mission_approvals.server.build_server`
as `owner_questions`, the assistant gets `ask_my_owner` and `owner_answer`.
