"""Turn an inbound channel message into an event, without letting an adapter mint an owner decision.

A decision event must be signed by the owner key (spec section 1). An adapter only carries text, so
a decision-shaped message becomes an event only when `verify_owner(event)` returns exactly True.
The default verifier refuses everything, and a verifier that raises refuses too. Any other message
is chat: an `org.channel-message` event with the text untouched.
"""
import json

RESERVED = "org.owner-"


class ForgedDecision(Exception):
    pass


def _decision_shaped(obj):
    kind = obj.get("type")
    if isinstance(kind, str) and kind.strip().casefold().startswith(RESERVED):
        return True
    data = obj.get("data")
    return any(isinstance(d, dict) and "decision" in d and ("run" in d or "task" in d)
               for d in (data, obj))


def ingest(message, verify_owner=None):
    try:
        parsed = json.loads(message["text"])
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, dict) and _decision_shaped(parsed):
        try:
            ok = verify_owner is not None and verify_owner(parsed) is True
        except Exception:  # noqa: BLE001  a broken verifier must refuse, not crash the caller
            ok = False
        if not ok:
            raise ForgedDecision(f"message {message.get('message_id')!r}: decision event without a valid owner signature")
        return {**parsed, "source": "adapter"}
    data = {k: message[k] for k in ("seq", "message_id", "sender", "text")}
    return {"type": "org.channel-message", "source": "adapter", "data": data}
