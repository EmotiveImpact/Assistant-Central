"""Keep one owner's phone bot running while Parlu is open.

Opt-in only: the host names a mode in its private configuration and puts the
bot token in ``TELEGRAM_BOT_TOKEN``. The runner long-polls Telegram for the
owner's pairing message and answer taps, and sends each new question once to
the paired chat. It never reads or sends anything else, and stops with Parlu.
"""
import threading

from .telegram import TelegramError, TelegramPhone

POLL_SECONDS = 20
FIRST_DELAY = 5
MAX_DELAY = 300


class PhoneRunner:
    def __init__(self, questions, mode, *, token=None, post=None):
        options = {'mode': mode, 'token': token}
        if post is not None:
            options['post'] = post
        self.phone = TelegramPhone(questions, **options)
        self.mode = mode
        self.bot = None
        self.reachable = None  # Unknown until the first call returns.
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name='parlu-phone', daemon=True)

    def start(self):
        self._thread.start()
        return self

    def close(self):
        self._stop.set()
        # A long poll may still be waiting on Telegram; the thread is a daemon and exits after it.
        self._thread.join(timeout=1)

    def status(self):
        return {'available': True, 'mode': self.mode, 'bot': self.bot, 'reachable': self.reachable}

    def step(self):
        """One round: learn the bot's name once, send new questions, then wait for taps."""
        if self.bot is None:
            self.bot = self.phone.bot_name()
        self.phone.send_waiting()
        self.phone.poll_once(timeout=POLL_SECONDS)

    def _run(self):
        delay = FIRST_DELAY
        while not self._stop.is_set():
            try:
                self.step()
            except TelegramError:
                self.reachable = False
                self._stop.wait(delay)
                delay = min(delay * 2, MAX_DELAY)
            except Exception:
                # Never let one odd update stop the phone; wait before trying again.
                self.reachable = False
                self._stop.wait(MAX_DELAY)
            else:
                self.reachable = True
                delay = FIRST_DELAY
