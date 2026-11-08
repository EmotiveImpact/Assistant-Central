"""Synthetic memory streams only, for tests and the offline demo."""
import anyio
from .codec import encode_record
from .transport import RawBridge

class Reader:
    def __init__(self, data, fragment=4096):
        self.data, self.position, self.fragment = data, 0, fragment
        self.requests = []
    async def receive(self, n):
        self.requests.append(n)
        await anyio.lowlevel.checkpoint()
        if self.position == len(self.data): raise anyio.EndOfStream
        end = min(len(self.data), self.position + min(n, self.fragment))
        value = self.data[self.position:end]
        self.position = end
        return value

class Writer:
    def __init__(self): self.records = []
    async def send(self, data):
        await anyio.lowlevel.checkpoint()
        self.records.append(data)

async def exchange(facade, messages, fragment=4096):
    import json
    writer = Writer()
    bridge = RawBridge(facade)
    await bridge.run(Reader(b''.join(encode_record(m) for m in messages), fragment), writer)
    return [json.loads(record) for record in writer.records], bridge.facts

def handshake():
    return [{'jsonrpc':'2.0','id':0,'method':'initialize','params':{
        'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'synthetic','version':'1'}}},
        {'jsonrpc':'2.0','method':'notifications/initialized'}]

def call(i, name, args):
    return {'jsonrpc':'2.0','id':i,'method':'tools/call','params':{'name':name,'arguments':args}}
