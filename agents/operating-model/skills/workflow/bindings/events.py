class ForgedDecision(Exception):
    pass


def ingest(message, verify_owner=None):
    return {"type": "org.owner-decision", "source": "adapter", "data": {}}
