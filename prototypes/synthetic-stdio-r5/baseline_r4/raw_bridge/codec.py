"""Strict bounded JSON records. No framing, SDK coercion, or owner operations."""
import json
import re
from mcp_bridge.bridge import bounded, MAX_MESSAGE_BYTES, MAX_OUTPUT_BYTES

RECORD_CAP = 16384  # Excludes LF; includes a CR in CRLF.
OUTPUT_CAP = 32768  # Includes terminating LF.

class Rejected(ValueError):
    def __init__(self, code=-32600, request_id=None, silent=False):
        super().__init__('Request rejected.')
        self.code, self.request_id, self.silent = code, request_id, silent

def safe_id(value):
    return ((type(value) is int and 0 <= value < 2**31) or
            (type(value) is str and re.fullmatch('[A-Za-z0-9_-]{1,64}', value) is not None))

def pairs(items):
    result = {}
    for key, value in items:
        if key in result: raise ValueError()
        result[key] = value
    return result

def constant(_):
    raise ValueError()

def lexical_depth(text):
    # Root collection has tree depth zero; at most nine open collections.
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped: escaped = False
            elif char == '\\': escaped = True
            elif char == '"': quoted = False
        elif char == '"': quoted = True
        elif char in '[{':
            depth += 1
            if depth > 9: raise ValueError()
        elif char in ']}':
            depth -= 1
            if depth < 0: raise ValueError()

def decode_record(record):
    if type(record) is not bytes or len(record) > RECORD_CAP:
        raise Rejected(-32700)
    # CRLF is accepted; bare CR elsewhere follows JSON whitespace grammar.
    try:
        text = record.decode('utf-8', errors='strict')
        lexical_depth(text)
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise Rejected(-32700) from None
    rid = value.get('id') if type(value) is dict else None
    rid = rid if safe_id(rid) else None
    silent = (type(value) is dict and 'id' not in value and
              value.get('jsonrpc') == '2.0' and type(value.get('method')) is str)
    try:
        # Traversal includes keys, scalar Unicode, finite numbers and normalized bytes.
        bounded(value, MAX_MESSAGE_BYTES)
        if type(value) is not dict: raise ValueError()
        if set(value) - {'jsonrpc', 'id', 'method', 'params'}: raise ValueError()
        if value.get('jsonrpc') != '2.0' or type(value.get('method')) is not str: raise ValueError()
        if 'id' in value and not safe_id(value['id']): raise ValueError()
    except (ValueError, UnicodeError):
        raise Rejected(-32600, rid, silent) from None
    if 'params' in value and type(value['params']) is not dict:
        # Unknown methods keep r3's method-not-found distinction.
        code = -32602 if value['method'] in {'initialize','notifications/initialized','ping','tools/list','tools/call'} else -32601
        raise Rejected(code, rid, silent)
    return value

def encode_record(value):
    try:
        output = bounded(value, MAX_OUTPUT_BYTES).encode('utf-8') + b'\n'
        if len(output) > OUTPUT_CAP: raise ValueError()
        return output
    except (ValueError, UnicodeError):
        raise Rejected(-32603) from None

def error_record(error):
    return encode_record({'jsonrpc':'2.0','id':error.request_id,
                         'error':{'code':error.code,'message':'Request rejected.'}})
