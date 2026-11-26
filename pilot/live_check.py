"""One real model call through the full owner-approval gate, with fictional text.

Run only when you mean to spend a few tokens:

    pip install -r pilot/requirements.txt -r pilot/requirements-live.txt
    ANTHROPIC_API_KEY=... python -B -m pilot.live_check --yes-make-one-real-call

It prepares a run, shows the exact request, approves that exact review, makes
one request with SDK retries off, and prints the result and run status. The key
is read from the environment at send time and is never printed or stored.
"""
from contextlib import contextmanager
import argparse
import json
import os
import sqlite3
import sys
import time

from .provider import AnthropicMessagesSDK, ProviderBudget, ResponsesAdapter

TASK = 'SYNTHETIC ONLY: In one short sentence, describe a fictional picnic on the Moon.'
BINDING = {'item_id': 'live-check-1', 'context': 'c' * 64, 'payload_digest': 'd' * 64,
           'provider': 'anthropic', 'model': 'claude-opus-5-5', 'max_output_tokens': 1024}


class _Owner:
    """A one-process stand-in for the owner session, for this check only."""

    def authenticate(self, token):
        if token != 'live-check-session':
            raise PermissionError('owner session required')
        return {'owner_id': 'live-check-owner', 'agent_id': 'live-check-assistant'}

    @contextmanager
    def authorised(self, token):
        yield self.authenticate(token)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--yes-make-one-real-call', action='store_true')
    parser.add_argument('--model', default=BINDING['model'])
    args = parser.parse_args(argv)
    if not args.yes_make_one_real_call:
        parser.error('refusing to call a real model without --yes-make-one-real-call')
    if not os.environ.get('ANTHROPIC_API_KEY'):
        parser.error('ANTHROPIC_API_KEY is not set')
    try:
        import anthropic  # noqa: F401  Checked before approval, so a missing package never burns a run.
    except ImportError:
        parser.error('the anthropic package is missing: pip install -r pilot/requirements-live.txt')
    binding = {**BINDING, 'model': args.model}
    owner = _Owner()
    db = sqlite3.connect(':memory:', isolation_level=None)

    def authorise(token, value):
        owner.authenticate(token)
        if value != binding:
            raise PermissionError('route changed')
        return {'task_text': TASK, 'context': binding['context'], 'recipient': 'live-check-assistant',
                'synthetic_only': True}

    transport = AnthropicMessagesSDK(lambda: os.environ['ANTHROPIC_API_KEY'], enabled=True)
    adapter = ResponsesAdapter(db, authorise, owner.authenticate, budget=ProviderBudget(max_output_tokens=1024),
                               transport=transport, allow_live=True, legacy_storage_fixture=True)
    session = 'live-check-session'
    prepared = adapter.prepare(session, 'live-check-run', binding)
    review = adapter.review(session, 'live-check-run')
    print('Exact request the owner approves:')
    print(json.dumps(review['review']['request'], indent=2))
    adapter.approve(session, 'live-check-run', prepared['review_digest'], expires=time.time() + 300)
    status = adapter.dispatch(session, 'live-check-run')
    print('\nResult:', adapter.result(session, 'live-check-run')['text'])
    print('Run state:', status['state'], '| response id:', status['response_id'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
