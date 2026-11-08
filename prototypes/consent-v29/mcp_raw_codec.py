"""Strict bounded JSON records for the offline MCP adapter; no transport setup."""
import json
from dataclasses import dataclass

from mcp import types
from mcp.shared.message import SessionMessage
from mcp_proposal_adapter import _valid_id
from restricted_host_protocol import (MAX_INPUT, MAX_OUTPUT, bounded_tree,
                                      unique_object, invalid_constant)

ERROR_TEXT = 'Restricted protocol error; outcome may be unknown'


@dataclass(frozen=True)
class DecodedRecord:
    message: object = None
    error: bytes | None = None


def encode_record(value, limit=MAX_OUTPUT):
    """Bounded UTF-8 JSON, with no literal LF; delimiter excluded from limit."""
    bounded_tree(value)
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False,
                         separators=(',', ':')).encode('utf-8')
    if len(encoded) > limit:
        raise ValueError('Bounded output exceeded')
    return encoded


def _error(code, ident=None):
    return DecodedRecord(error=encode_record({'jsonrpc':'2.0', 'id':ident,
        'error':{'code':code, 'message':ERROR_TEXT}}))


def _check_depth(text):
    # Scan before recursive JSON decoding. Strings/escapes cannot add nesting.
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '[{':
            depth += 1
            if depth > 33:
                raise ValueError('Bounded depth exceeded')
        elif char in ']}':
            depth -= 1


def decode_record(data):
    """Parse one LF-free record, preserving int/float/bool argument types.

    No batch support. Parsed operational notifications are silently ignored,
    even if their envelope is invalid. Undecodable JSON has no trusted identity.
    """
    try:
        if type(data) is not bytes or len(data) > MAX_INPUT:
            raise ValueError('Bounded input exceeded')
        text = data.decode('utf-8')
        _check_depth(text)
        raw = json.loads(text, object_pairs_hook=unique_object,
                         parse_constant=invalid_constant)
        bounded_tree(raw)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return _error(-32700)
    notification = (type(raw) is dict and 'id' not in raw
                    and type(raw.get('method')) is str)
    try:
        if (type(raw) is not dict or raw.get('jsonrpc') != '2.0'
                or type(raw.get('method')) is not str
                or ('params' in raw and type(raw['params']) is not dict)):
            raise ValueError('Invalid envelope')
        if (raw['method'] == 'notifications/cancelled'
                and not _valid_id(raw.get('params', {}).get('requestId'))):
            raise ValueError('Invalid cancellation identifier')
        if 'id' in raw and not _valid_id(raw['id']):
            raise ValueError('Invalid identifier')
        # Envelope extras are inert protocol metadata; args remain closed by
        # the application boundary. Never use model_validate_json coercion.
        message = types.JSONRPCMessage.model_validate(raw)
        return DecodedRecord(message=SessionMessage(message))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return DecodedRecord() if notification else _error(
            -32600, raw['id'] if type(raw) is dict and _valid_id(raw.get('id')) else None)
