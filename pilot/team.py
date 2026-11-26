"""Team mission records carried inside ordinary signed proposals.

A team mission is the lead owner's task proposals that share one context and go
to two or more assistants. Three structured texts add what a team needs without
a new packet type, so each record is signed, reviewed and decided exactly like
any other proposal:

- a **part** (task, lead to helper): the brief, the rules for this part (must and
  must not) and an optional compute limit. Accepting it agrees to those exact
  rules; changing a rule needs a new part, so agreement restarts.
- a **result** (artifact, helper to lead): a summary, one honest check per rule
  of the part, and the compute the helper reports using. Accepting it is the
  lead's merge approval; the helper's signed release is the other.
- an **access request** (task, helper to lead): what one part needs to read,
  why, and for how long. Accepting it is the lead's grant, for that part only.

Nothing here runs code, moves money or opens a resource. Compute figures are
what the helper reports, and are shown as such.
"""
import json

PART = 'parlu/team-part/1\n'
RESULT = 'parlu/team-result/1\n'
ACCESS = 'parlu/team-access/1\n'
PREFIXES = (PART, RESULT, ACCESS)
CURRENCIES = ('GBP', 'USD', 'EUR')
MAX_RULES = 8
MAX_COMPUTE = 1_000_000_000  # Whole millionths of one currency unit.
MAX_HOURS = 168


class TeamDenied(ValueError):
    pass


def check(condition, message='Invalid team mission record'):
    if not condition:
        raise TeamDenied(message)


def _text(value, limit):
    check(type(value) is str and value.strip() == value and value and len(value.encode('utf-8')) <= limit)
    return value


def _rules(value):
    check(type(value) is dict and set(value) == {'must', 'must_not'})
    seen = set()
    for side in ('must', 'must_not'):
        check(type(value[side]) is list and len(value[side]) <= MAX_RULES)
        for rule in value[side]:
            _text(rule, 200)
            check(rule not in seen, 'Each rule appears once')
            seen.add(rule)
    return value


def _money(value, amount_key):
    check(type(value) is dict and set(value) == {amount_key, 'currency'})
    check(type(value[amount_key]) is int and 0 <= value[amount_key] <= MAX_COMPUTE and value['currency'] in CURRENCIES)
    return value


def _load(text, prefix, keys):
    check(type(text) is str and text.startswith(prefix))
    try:
        value = json.loads(text[len(prefix):])
    except (ValueError, RecursionError):
        raise TeamDenied('Invalid team mission record') from None
    check(type(value) is dict and set(value) == keys)
    return value


def kind_of(text):
    """Which team record a proposal text is, or None for an ordinary proposal."""
    return next((prefix for prefix in PREFIXES if type(text) is str and text.startswith(prefix)), None)


def read_part(text):
    value = _load(text, PART, {'brief', 'rules', 'compute'})
    _text(value['brief'], 4096)
    _rules(value['rules'])
    if value['compute'] is not None:
        _money(value['compute'], 'cap_micro')
        check(value['compute']['cap_micro'] > 0)
    return value


def read_result(text, part):
    """A result must report on exactly the rules of its own part, in the part's currency."""
    value = _load(text, RESULT, {'summary', 'checks', 'compute_used'})
    _text(value['summary'], 4096)
    expected = [(rule, side) for side in ('must', 'must_not') for rule in part['rules'][side]]
    check(type(value['checks']) is list and len(value['checks']) == len(expected), 'Report on every rule of the part')
    for entry, (rule, side) in zip(value['checks'], expected):
        check(type(entry) is dict and set(entry) == {'rule', 'side', 'kept'} and entry['rule'] == rule
              and entry['side'] == side and type(entry['kept']) is bool, 'Report on every rule of the part, in order')
    if value['compute_used'] is not None:
        _money(value['compute_used'], 'micro')
        check(part['compute'] is not None and value['compute_used']['currency'] == part['compute']['currency'],
              'Compute is reported in the part\'s own currency')
    return value


def read_access(text):
    value = _load(text, ACCESS, {'part_task_id', 'what', 'why', 'hours'})
    check(type(value['part_task_id']) is str and 1 <= len(value['part_task_id']) <= 96)
    _text(value['what'], 200)
    _text(value['why'], 1000)
    check(type(value['hours']) is int and 1 <= value['hours'] <= MAX_HOURS)
    return value


def part_text(brief, must=(), must_not=(), compute=None):
    value = {'brief': brief, 'rules': {'must': list(must), 'must_not': list(must_not)}, 'compute': compute}
    text = PART + json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    read_part(text)
    return text
