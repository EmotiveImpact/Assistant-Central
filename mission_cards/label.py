"""Label outbound messages as written by an AI assistant.

EU AI Act Article 50 has applied since August 2026: people must be told when they are
talking to an AI system, and generated text should carry a machine-readable marking.
Every message an assistant sends through Assistant Central is wrapped here, so the
label cannot be forgotten by an individual integration.
"""
from .text import bounded, clean, ident

LABEL_DOMAIN = 'assistant-central/ai-generated/1'


def label_outbound(owner_id: str, owner_label: str, text: str) -> dict:
    """Wrap one outbound message with a human-readable and machine-readable AI label."""
    ident(owner_id, 'owner')
    bounded(owner_label, 64, 'owner label')
    bounded(text, 8192, 'message')
    return {'domain': LABEL_DOMAIN, 'ai_generated': True, 'on_behalf_of': owner_id,
            'disclosure': f"Written by {clean(owner_label)}'s AI assistant", 'text': text}


def is_labelled(message: object) -> bool:
    return (type(message) is dict and message.get('domain') == LABEL_DOMAIN
            and message.get('ai_generated') is True and type(message.get('disclosure')) is str
            and type(message.get('text')) is str)


def render_labelled(message: dict) -> str:
    """Display form: the disclosure always comes first, on its own line."""
    if not is_labelled(message):
        raise ValueError('Message is not labelled as AI-generated')
    return f"[{message['disclosure']}]\n{clean(message['text'])}"
