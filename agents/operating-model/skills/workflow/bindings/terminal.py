"""Channel on a terminal: messages print to `out` and persist in one JSON-lines file."""
import json
import os
import sys
from pathlib import Path

from .common import Adapter


class TerminalChannel(Adapter):
    port = "Channel"
    unavailable = "channel-unavailable"

    def __init__(self, path, out=None):
        super().__init__()
        self._path = Path(path)
        self._out = out or (lambda line: print(line, file=sys.stdout))
        self.reopen()

    def reopen(self):
        self._log = {}
        if self._path.exists():
            for line in self._path.read_text().splitlines():
                m = json.loads(line)
                self._log.setdefault(m["channel"], []).append(m)

    def _op_send(self, i):
        log = self._log.setdefault(i["channel"], [])
        for m in log:
            if m["message_id"] == i["message_id"]:
                return {"message_id": m["message_id"], "seq": m["seq"], "duplicate": True}
        m = {"channel": i["channel"], "seq": len(log) + 1, "message_id": i["message_id"],
             "sender": i["sender"], "text": i["text"]}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(m) + "\n")
            f.flush()
            os.fsync(f.fileno())
        log.append(m)
        self._out(f"[{m['channel']}] {m['sender']}: {m['text']}")
        return {"message_id": m["message_id"], "seq": m["seq"], "duplicate": False}

    def _op_subscribe(self, i):
        after = i.get("after", 0)
        msgs = [{k: m[k] for k in ("seq", "message_id", "sender", "text")}
                for m in self._log.get(i["channel"], []) if m["seq"] > after]
        return {"messages": msgs, "cursor": msgs[-1]["seq"] if msgs else after}

    def _op_list_participants(self, i):
        return {"participants": sorted({m["sender"] for m in self._log.get(i["channel"], [])})}
