"""Fixed synthetic client. Stdlib only; no owner/executor imports or authority.

stdin is the bounded supervisor command channel. stdout is exclusively restricted
JSON-RPC. Two extra anonymous descriptors carry RPC responses and step reports.
This is deliberately scripted, not an AI/provider or an operating-system sandbox.
"""
import json
import os
import sys

LIMIT = 65536


def read(stream):
    raw = stream.readline(LIMIT + 1)
    if not raw or len(raw) > LIMIT or not raw.endswith(b'\n'):
        raise ValueError('Incomplete or excessive frame')
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('Duplicate field')
            value[key] = item
        return value
    def constant(value):
        raise ValueError('Nonfinite value')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def emit(stream, value):
    raw = json.dumps(value, ensure_ascii=True, allow_nan=False).encode() + b'\n'
    if len(raw) > LIMIT:
        raise ValueError('Excessive frame')
    stream.write(raw)
    stream.flush()


def main():
    with os.fdopen(int(sys.argv[1]), 'rb') as replies, os.fdopen(int(sys.argv[2]), 'wb') as reports:
        config = read(sys.stdin.buffer)
        if type(config) is not dict or set(config) != {'envelope','proposal_id'}:
            raise ValueError('Unexpected configuration fields')
        envelope, proposal_id = config['envelope'], config['proposal_id']
        if type(envelope) is not dict or type(proposal_id) is not str or not 1 <= len(proposal_id) <= 64:
            raise ValueError('Invalid inert configuration')
        seq = 0
        def rpc(method, params=None, notification=False):
            nonlocal seq
            seq += 1
            message = {'jsonrpc':'2.0', 'method':method}
            if not notification:
                message['id'] = seq
            if params is not None:
                message['params'] = params
            emit(sys.stdout.buffer, message)
            if not notification:
                response = read(replies)
                if (type(response) is not dict or response.get('jsonrpc') != '2.0' or
                        type(response.get('id')) is not int or response['id'] != seq or
                        ('result' in response) == ('error' in response)):
                    raise ValueError('Unexpected response')
                return response
        initialized = False
        while True:
            command = read(sys.stdin.buffer)
            if command == {'step':'discover'} and not initialized:
                response = rpc('initialize', {'protocolVersion':'2025-06-18', 'capabilities':{},
                    'clientInfo':{'name':'fictional-scripted-peer', 'version':'1'}})
                if ('error' in response or type(response.get('result')) is not dict or
                        response['result'].get('protocolVersion') != '2025-06-18'):
                    raise ValueError('Handshake failed')
                rpc('notifications/initialized', notification=True)
                initialized = True
                response = rpc('tools/list')
            elif command == {'step':'discover'}:
                response = rpc('tools/list')
            elif command == {'step':'propose'}:
                response = rpc('tools/call', {'name':'propose', 'arguments':{
                    'proposal_id':proposal_id, 'envelope':envelope}})
            elif command == {'step':'status'}:
                response = rpc('tools/call', {'name':'proposal_status', 'arguments':{'proposal_id':proposal_id}})
            elif command == {'step':'inbox'}:
                response = rpc('tools/call', {'name':'inbox', 'arguments':{}})
            else:
                raise ValueError('Unknown fixed step')
            emit(reports, {'pid':os.getpid(), 'response':response})


if __name__ == '__main__':
    try:
        main()
    except (EOFError, OSError, ValueError, KeyError, TypeError, RecursionError):
        sys.exit(1)
