"""An MCP App (io.modelcontextprotocol/ui) that shows a mission card inside the assistant.

``card_app(book, owner_id)`` returns an ``Apps`` extension with one display-only tool,
``show_mission_card``, bound to ``ui://assistant-central/mission-card.html``. Hosts that
support MCP Apps render the card in a sandboxed frame; others get the same card as text.
The app has no buttons that commit anything: acknowledging and accepting still go
through the elicitation tools in ``tools.py``, so the confirmation code step stays.
"""
from pathlib import Path

from typing import Any

from pydantic import BaseModel

from mcp.server.apps import Apps, ResourceCsp
from mcp.types import ToolAnnotations

from .tools import CardBook

# Explicit hints for every tool, as assistant directories require. Nothing here reaches the
# open internet: tools act only inside the owner's own Parlu.
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)

APP_URI = 'ui://assistant-central/mission-card.html'
APP_HTML = (Path(__file__).with_name('card_app.html')).read_text(encoding='utf-8')


class CardView(BaseModel):
    mission_id: str
    snapshot: dict[str, Any]
    card_digest: str
    state: str
    waiting_on_you: list[str]
    text: str


def card_app(book: CardBook, owner_id: str) -> Apps:
    apps = Apps()

    @apps.tool(annotations=READ_ONLY, resource_uri=APP_URI, name='show_mission_card',
               description='Show a mission card visually: goal, every owner\'s constraints, status and what is '
                           'waiting on you. Constraint text is written by the people on the mission.')
    def show_mission_card(mission_id: str) -> CardView:
        card = book.get(mission_id)
        return CardView(mission_id=mission_id, snapshot=card.snapshot(), card_digest=card.digest(),
                        state=card.state(), waiting_on_you=card.outstanding(owner_id), text=card.render())

    apps.add_html_resource(APP_URI, APP_HTML, title='Mission card', prefers_border=True,
                           csp=ResourceCsp(connect_domains=[], resource_domains=[]))
    return apps
