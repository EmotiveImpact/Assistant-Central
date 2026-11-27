"""Room records carried inside ordinary signed task proposals.

A room is the place where several people's assistants talk a piece of work
through. It is not a new packet type and not a new store: a room is every
proposal that shares one exact context, and two structured texts add what a
room needs. Each is signed, reviewed and decided exactly like any other
proposal, and the customer's own assistant writes them. Parlu runs no model.

- a **note** (task, any member to another): something an assistant found,
  thought or plans, with the room's name, the thread it belongs to (for
  example "Food"), where it stands on the room's board, and optionally the
  task id of an earlier note it replaces. A note of type ``change`` is a change
  of mind: it must name the note it replaces and say why.
- a **vote** (task, one member to each other member): a yes or no question
  with the room's rule (``most`` or ``all``), the asker's own stance and a
  ``vote_id`` shared by every copy. Each recipient's signed acceptance is a yes
  and a signed refusal is a no. Nobody can vote for anyone else, and the asker
  sees only the answers sent back to them.

Nothing here runs code, moves money or grants access. Reading a record never
changes what any other record means.
"""
import json
import re

NOTE = 'parlu/room-note/1\n'
VOTE = 'parlu/room-vote/1\n'
PREFIXES = (NOTE, VOTE)
NOTE_TYPES = ('finding', 'idea', 'plan', 'change')
STAGES = ('researching', 'doing', 'done')
RULES = ('most', 'all')
STANCES = ('yes', 'no', 'abstain')
TOKEN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$')


class RoomDenied(ValueError):
    pass


def check(condition, message='Invalid room record'):
    if not condition:
        raise RoomDenied(message)


def _text(value, limit):
    check(type(value) is str and value.strip() == value and value and len(value.encode('utf-8')) <= limit)
    return value


def _token(value):
    check(type(value) is str and TOKEN.match(value) is not None)
    return value


def _load(text, prefix, keys):
    check(type(text) is str and text.startswith(prefix))
    try:
        value = json.loads(text[len(prefix):])
    except (ValueError, RecursionError):
        raise RoomDenied('Invalid room record') from None
    check(type(value) is dict and set(value) == keys)
    return value


def kind_of(text):
    """Which room record a proposal text is, or None for any other proposal."""
    return next((prefix for prefix in PREFIXES if type(text) is str and text.startswith(prefix)), None)


def read_note(text):
    value = _load(text, NOTE, {'room', 'thread', 'note', 'stage', 'summary', 'replaces', 'why'})
    _text(value['room'], 120)
    _text(value['thread'], 80)
    check(value['note'] in NOTE_TYPES and value['stage'] in STAGES)
    _text(value['summary'], 2000)
    if value['note'] == 'change':
        check(value['replaces'] is not None and value['why'] is not None,
              'A change of mind names the note it replaces and says why')
    if value['replaces'] is not None:
        _token(value['replaces'])
    if value['why'] is not None:
        _text(value['why'], 1000)
    return value


def read_vote(text):
    value = _load(text, VOTE, {'room', 'thread', 'question', 'rule', 'stance', 'vote_id', 'why'})
    _text(value['room'], 120)
    _text(value['thread'], 80)
    _text(value['question'], 400)
    check(value['rule'] in RULES and value['stance'] in STANCES)
    _token(value['vote_id'])
    if value['why'] is not None:
        _text(value['why'], 1000)
    return value


def read(text):
    record = kind_of(text)
    return read_note(text) if record == NOTE else read_vote(text) if record == VOTE else None


def _encode(prefix, value):
    return prefix + json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def note_text(room, thread, summary, note='finding', stage='researching', replaces=None, why=None):
    text = _encode(NOTE, {'room': room, 'thread': thread, 'note': note, 'stage': stage,
                          'summary': summary, 'replaces': replaces, 'why': why})
    read_note(text)
    return text


def vote_text(room, thread, question, vote_id, rule='most', stance='yes', why=None):
    text = _encode(VOTE, {'room': room, 'thread': thread, 'question': question, 'rule': rule,
                          'stance': stance, 'vote_id': vote_id, 'why': why})
    read_vote(text)
    return text


def summary(text):
    """What a view needs from a stored record, already checked when it was stored."""
    record = kind_of(text)
    value = read(text)
    if record == NOTE:
        return {'record': 'note', **{key: value[key] for key in ('room', 'thread', 'note', 'stage', 'summary', 'replaces', 'why')}}
    return {'record': 'vote', **{key: value[key] for key in ('room', 'thread', 'question', 'rule', 'stance', 'vote_id', 'why')}}
