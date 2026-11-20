"""Channel (issue comments) and Tracker (issues) over `gh api`.

Hidden state rides in one HTML-comment trailer at the end of a body or comment:
`<!-- op:meta {...} -->`. Only the last trailer counts, and `<`, `>` are escaped inside it, so user
text cannot forge or close one. Item keys, links, message ids and channel names live there.
Senders in a trailer are labels, not identities: a comment author can name any sender.

A channel is a thread issue found by its trailer (`channel: <name>`), or an existing issue or
pull request addressed as `#<number>`. Message seq is the GitHub comment id.
Races between two writers (lookup, then create) are not guarded.
"""
import json
import re

from op_conformance import PortError

from .common import Adapter

OPEN = "<!-- op:meta "
TAIL = re.compile(r"<!-- op:meta (\{[^\n]*\}) -->\s*\Z")


def pack(text, meta):
    blob = json.dumps(meta, sort_keys=True).replace("<", "\\u003c").replace(">", "\\u003e")
    return f"{text}\n\n{OPEN}{blob} -->"


def unpack(body):
    """(text, meta). A body with no trailer, or a damaged one, has empty meta."""
    body = body or ""
    at = body.rfind(OPEN)
    m = TAIL.fullmatch(body[at:]) if at >= 0 else None
    if m:
        try:
            meta = json.loads(m.group(1))
        except ValueError:
            meta = None
        if isinstance(meta, dict):
            text = body[:at]
            return (text[:-2] if text.endswith("\n\n") else text), meta
    return body, {}


class _Github(Adapter):
    def __init__(self, gh):
        super().__init__()
        self.gh = gh
        self.base = f"repos/{gh.repo}/issues"

    def _issues(self):
        return [i for i in self.gh.api("GET", f"{self.base}?state=all&per_page=100", paginate=True)
                if "pull_request" not in i]

    def reopen(self):
        """Nothing is cached: every call reads GitHub."""


class GithubChannel(_Github):
    port = "Channel"
    unavailable = "channel-unavailable"

    def _thread(self, name, create):
        m = re.fullmatch(r"#([1-9]\d*)", name)
        if m:
            return int(m.group(1))
        for issue in self._issues():
            if unpack(issue.get("body"))[1].get("channel") == name:
                return issue["number"]
        if not create:
            return None
        made = self.gh.api("POST", self.base, {"title": f"channel: {name}", "body": pack("Channel thread.", {"channel": name})})
        return made["number"]

    def _messages(self, number):
        out = []
        for c in self.gh.api("GET", f"{self.base}/{number}/comments?per_page=100", paginate=True):
            text, meta = unpack(c.get("body"))
            out.append({"seq": c["id"], "message_id": meta.get("id") or f"gh-{c['id']}",
                        "sender": meta.get("sender") or (c.get("user") or {}).get("login", "unknown"), "text": text})
        return sorted(out, key=lambda m: m["seq"])

    def _op_send(self, i):
        number = self._thread(i["channel"], create=True)
        for m in self._messages(number):
            if m["message_id"] == i["message_id"]:
                return {"message_id": m["message_id"], "seq": m["seq"], "duplicate": True}
        made = self.gh.api("POST", f"{self.base}/{number}/comments",
                           {"body": pack(i["text"], {"id": i["message_id"], "sender": i["sender"]})})
        return {"message_id": i["message_id"], "seq": made["id"], "duplicate": False}

    def _op_subscribe(self, i):
        after = i.get("after", 0)
        number = self._thread(i["channel"], create=False)
        msgs = [m for m in (self._messages(number) if number else []) if m["seq"] > after]
        return {"messages": msgs, "cursor": msgs[-1]["seq"] if msgs else after}

    def _op_list_participants(self, i):
        number = self._thread(i["channel"], create=False)
        return {"participants": sorted({m["sender"] for m in (self._messages(number) if number else [])})}


class GithubTracker(_Github):
    port = "Tracker"
    unavailable = "tracker-unavailable"

    @staticmethod
    def _number(item_id):
        if not re.fullmatch(r"[1-9]\d*", item_id):
            raise PortError("not-found", "item ids are issue numbers")
        return item_id

    def _fetch(self, item_id):
        issue = self.gh.api("GET", f"{self.base}/{self._number(item_id)}")
        if "pull_request" in issue:
            raise PortError("not-found", "a pull request is not a tracker item")
        return issue

    @staticmethod
    def _item(issue):
        text, meta = unpack(issue.get("body"))
        return {"item_id": str(issue["number"]), "title": issue["title"], "body": text,
                "state": issue["state"], "links": [str(x) for x in meta.get("links", [])]}, meta

    def _op_create_item(self, i):
        for issue in self._issues():
            if unpack(issue.get("body"))[1].get("key") == i["key"]:
                return {"item_id": str(issue["number"]), "created": False}
        made = self.gh.api("POST", self.base, {"title": i["title"], "body": pack(i.get("body", ""), {"key": i["key"]})})
        return {"item_id": str(made["number"]), "created": True}

    def _op_update_item(self, i):
        issue = self._fetch(i["item_id"])
        patch = {k: i[k] for k in ("title", "state") if k in i}
        if "body" in i:
            patch["body"] = pack(i["body"], self._item(issue)[1])
        if patch:
            issue = self.gh.api("PATCH", f"{self.base}/{i['item_id']}", patch)
        item = self._item(issue)[0]
        return {k: item[k] for k in ("item_id", "title", "body", "state")}

    def _op_get_item(self, i):
        return self._item(self._fetch(i["item_id"]))[0]

    def _op_search_items(self, i):
        needle, want = i.get("text", "").casefold(), i.get("state")
        items = []
        for issue in self._issues():
            item, meta = self._item(issue)
            if "channel" in meta or (want and item["state"] != want):
                continue
            if needle in item["title"].casefold() or needle in item["body"].casefold():
                items.append({k: item[k] for k in ("item_id", "title", "state")})
        return {"items": items}

    def _op_link_items(self, i):
        self._fetch(i["to_id"])
        issue = self._fetch(i["from_id"])
        item, meta = self._item(issue)
        if i["to_id"] not in item["links"]:
            meta["links"] = item["links"] + [i["to_id"]]
            self.gh.api("PATCH", f"{self.base}/{i['from_id']}", {"body": pack(item["body"], meta)})
        return {"linked": True}
