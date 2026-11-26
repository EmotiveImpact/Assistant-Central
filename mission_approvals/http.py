"""Serve an assistant's Parlu tools over HTTP, for assistants that connect remotely.

The host builds the server with ``build_server`` (its leases fix the owner,
assistant and conversation), then calls ``http_app`` to serve it. Every
request must carry ``Authorization: Bearer <token>``, a secret the host gave
that one assistant. By default it listens on this computer only; putting it on
the internet (for ChatGPT, for example) needs HTTPS in front of it.

If an inbox access is passed, a watcher publishes ``parlu://inbox`` updates so
listening assistants wake up when something arrives.
"""
import contextlib
import hmac

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount

from .server import watch_inbox

MIN_TOKEN = 32


class _Bearer:
    def __init__(self, app, token: str):
        self.app, self.expected = app, ('Bearer ' + token).encode()

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            given = dict(scope.get('headers') or []).get(b'authorization', b'')
            if not hmac.compare_digest(given, self.expected):
                await JSONResponse({'error': 'unauthorised'}, status_code=401,
                                   headers={'WWW-Authenticate': 'Bearer'})(scope, receive, send)
                return
        await self.app(scope, receive, send)


def http_app(server, token: str, *, inbox_access=None, watch_interval: float = 5.0, path: str = '/mcp'):
    """An ASGI app serving ``server`` at ``path`` behind a bearer token."""
    if type(token) is not str or len(token) < MIN_TOKEN:
        raise ValueError('Use a random token of at least 32 characters.')
    inner = server.streamable_http_app(streamable_http_path=path, json_response=True)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        import anyio
        async with inner.router.lifespan_context(inner):
            async with anyio.create_task_group() as group:
                if inbox_access is not None:
                    group.start_soon(lambda: watch_inbox(server, inbox_access, interval=watch_interval))
                yield
                group.cancel_scope.cancel()

    return _Bearer(Starlette(routes=[Mount('/', app=inner)], lifespan=lifespan), token)
