"""Carry Assistant Central mission cards, receipts and labelled messages over A2A.

An agent that speaks the extension declares it in its Agent Card. Mission traffic is
then sent as A2A messages whose single part is structured data of one known kind:

- ``card``: a mission card snapshot, checked against its fingerprint on arrival;
- ``receipt``: an owner-signed step receipt (in-toto Statement in a DSSE envelope);
- ``message``: a chat message carrying the AI-generated label.

The A2A context id is the mission's task anchor. A message for any other mission, a
message with free text parts, or one without the extension is refused, which closes the
"agent session smuggling" route reported by Palo Alto Networks Unit 42 in 2025, where a
remote agent slips extra instructions into an ongoing multi-turn conversation.
"""
import uuid

from google.protobuf import json_format, struct_pb2

import a2a.types as a2a
from a2a.extensions.common import find_extension_by_uri

from mission_cards.label import is_labelled
from mission_cards.receipts import verify
from mission_cards.text import CardError, ident, need
from pilot.crypto import digest

EXTENSION_URI = 'https://github.com/EmotiveImpact/Assistant-Central/a2a/missions/v1'
MEDIA_TYPE = 'application/vnd.assistant-central.mission+json'
KINDS = ('card', 'receipt', 'message')
CARD_KEYS = {'domain', 'mission_id', 'goal', 'owners', 'constraints'}


def declaration(receipt_key_ids: list[str]) -> a2a.AgentExtension:
    """The Agent Card entry announcing support for Assistant Central missions."""
    params = struct_pb2.Struct()
    params.update({'kinds': list(KINDS), 'receipt_key_ids': list(receipt_key_ids),
                   'ai_generated_label': True})
    return a2a.AgentExtension(
        uri=EXTENSION_URI, required=False, params=params,
        description='Assistant Central missions: owner constraints, owner-signed receipts and labelled messages.')


def agent_card(name: str, url: str, receipt_key_ids: list[str]) -> a2a.AgentCard:
    return a2a.AgentCard(
        name=name, description=f'{name}, reachable for Assistant Central missions', version='1.0.0',
        supported_interfaces=[a2a.AgentInterface(url=url, protocol_binding='JSONRPC', protocol_version='1.0')],
        capabilities=a2a.AgentCapabilities(extensions=[declaration(receipt_key_ids)]),
        default_input_modes=[MEDIA_TYPE], default_output_modes=[MEDIA_TYPE])


def supports_missions(card: a2a.AgentCard) -> bool:
    return find_extension_by_uri(card, EXTENSION_URI) is not None


def _payload_check(kind: str, payload: object) -> None:
    need(type(payload) is dict, 'Mission payload must be an object')
    if kind == 'card':
        need(set(payload) == CARD_KEYS and 'fingerprint' not in payload, 'Invalid mission card')
    elif kind == 'message':
        need(is_labelled(payload), 'Mission messages must carry the AI-generated label')
    else:
        need(set(payload) == {'payloadType', 'payload', 'signatures'}, 'Invalid receipt envelope')


def mission_message(mission_id: str, kind: str, payload: dict) -> a2a.Message:
    """Build one outbound mission message for the given mission (the A2A context id)."""
    ident(mission_id, 'mission')
    need(kind in KINDS, 'Unknown mission message kind')
    _payload_check(kind, payload)
    if kind == 'card':
        need(payload['mission_id'] == mission_id, 'Card belongs to a different mission')
    data = json_format.ParseDict(payload, struct_pb2.Value())
    meta = struct_pb2.Struct()
    meta.update({'kind': kind, **({'fingerprint': digest(payload)} if kind == 'card' else {})})
    part = a2a.Part(data=data, media_type=MEDIA_TYPE, metadata=meta)
    return a2a.Message(message_id=str(uuid.uuid4()), context_id=mission_id, role=a2a.Role.ROLE_AGENT,
                       parts=[part], extensions=[EXTENSION_URI])


def read_mission_message(message: a2a.Message, mission_id: str, owner_keys: dict | None = None) -> tuple[str, dict]:
    """Validate an inbound mission message and return (kind, payload) as untrusted data.

    ``owner_keys`` (owner id to Ed25519 public key) is required to accept receipts.
    """
    need(EXTENSION_URI in message.extensions, 'Message does not use the Assistant Central extension')
    need(message.context_id == mission_id, 'This message belongs to a different mission; refused')
    need(len(message.parts) == 1, 'Mission messages carry exactly one part')
    part = message.parts[0]
    need(part.WhichOneof('content') == 'data' and part.media_type == MEDIA_TYPE,
         'Mission messages carry structured data only, never free text')
    meta = json_format.MessageToDict(part.metadata)
    kind = meta.get('kind')
    need(kind in KINDS, 'Unknown mission message kind')
    payload = json_format.MessageToDict(part.data)
    _payload_check(kind, payload)
    if kind == 'card':
        need(payload['mission_id'] == mission_id, 'Card belongs to a different mission')
        need(meta.get('fingerprint') == digest(payload), 'Card fingerprint does not match its content')
    if kind == 'receipt':
        need(owner_keys is not None, 'No owner keys to check the receipt against')
        statement = verify(payload, owner_keys)
        need(statement['predicate']['mission_id'] == mission_id, 'Receipt belongs to a different mission')
    return kind, payload


__all__ = ['EXTENSION_URI', 'agent_card', 'declaration', 'mission_message', 'read_mission_message',
           'supports_missions', 'CardError']
