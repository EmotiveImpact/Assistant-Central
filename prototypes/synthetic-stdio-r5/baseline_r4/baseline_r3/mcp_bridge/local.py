"""Caller-owned in-memory stream composition for the offline demo/tests only."""
from contextlib import asynccontextmanager
import anyio
from mcp import ClientSession
from .bridge import OfflineBridge

@asynccontextmanager
async def client(facade):
    send, incoming = anyio.create_memory_object_stream(0)
    outgoing, receive = anyio.create_memory_object_stream(0)
    async with send, incoming, outgoing, receive, anyio.create_task_group() as group:
        group.start_soon(OfflineBridge(facade).run, incoming, outgoing)
        async with ClientSession(receive, send) as session:
            initialized = await session.initialize()
            yield session, initialized
        group.cancel_scope.cancel()
