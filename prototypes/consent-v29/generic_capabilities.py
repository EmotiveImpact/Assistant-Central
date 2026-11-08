"""Closed, inert application schemas. Declarations never authorize execution.

No tool dispatch, URL fetching, file access, dynamic registration or provider SDK
is available here. Public-resource claims are synthetic data, not verified facts.
"""
from network import Denied

PUBLIC_SHORTLIST = 'public-resource-shortlist-v1'
BOUNDED_TEXT = 'bounded-text-exchange-v1'
CAPABILITIES = (PUBLIC_SHORTLIST, BOUNDED_TEXT)


def text(value, maximum):
    if type(value) is not str or not value or len(value) > maximum:
        raise Denied('Invalid bounded application text')
    try:
        value.encode('utf-8')
    except UnicodeError as exc:
        raise Denied('Invalid application Unicode') from exc


def validate_payload(capability, kind, payload):
    if capability not in CAPABILITIES or type(payload) is not dict:
        raise Denied('Unknown capability or payload')
    if capability == BOUNDED_TEXT:
        if kind == 'request':
            if set(payload) != {'prompt', 'max_reply_chars'}:
                raise Denied('Unknown text exchange request fields')
            text(payload['prompt'], 512)
            if type(payload['max_reply_chars']) is not int or not 1 <= payload['max_reply_chars'] <= 512:
                raise Denied('Invalid reply character bound')
        elif kind == 'result':
            if set(payload) != {'text'}:
                raise Denied('Unknown text exchange result fields')
            text(payload['text'], 512)
        else:
            raise Denied('Unsupported capability message kind')
        return
    if kind == 'request':
        if set(payload) != {'query', 'max_items'}:
            raise Denied('Unknown shortlist request fields')
        text(payload['query'], 512)
        if type(payload['max_items']) is not int or not 1 <= payload['max_items'] <= 5:
            raise Denied('Invalid shortlist bound')
    elif kind == 'result':
        if set(payload) != {'items'} or type(payload['items']) is not list or len(payload['items']) > 5:
            raise Denied('Invalid shortlist result fields')
        for item in payload['items']:
            if type(item) is not dict or set(item) != {'title', 'url', 'summary'}:
                raise Denied('Invalid shortlist item fields')
            text(item['title'], 128)
            text(item['url'], 256)
            text(item['summary'], 512)
            # URLs remain inert text; this is not an allowlist for navigation.
            if not item['url'].startswith('https://'):
                raise Denied('Only HTTPS-shaped resource references are supported')
    else:
        raise Denied('Unsupported capability message kind')


def validate_result_against_request(capability, request, result):
    """Validate both closed payloads and their request-relative limit."""
    validate_payload(capability, 'request', request)
    validate_payload(capability, 'result', result)
    if capability == PUBLIC_SHORTLIST:
        if len(result['items']) > request['max_items']:
            raise Denied('Result exceeds requested item limit')
    elif len(result['text']) > request['max_reply_chars']:
        raise Denied('Result exceeds requested reply character limit')
