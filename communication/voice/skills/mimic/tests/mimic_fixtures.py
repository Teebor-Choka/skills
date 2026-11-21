"""Shared fixtures for the mimic tests: a synthetic persona corpus and a script runner.

The persona is invented ("Pat Example"); no real person's messages appear anywhere.
Unique module name on purpose: the repo runs every tests/ dir in one pytest call.
"""

import json
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

TOPICS = [
    "the staging db", "release notes", "the flaky login test", "q3 budget sheet", "the onboarding doc",
    "invoice batch", "dns cutover", "the hiring loop", "kafka lag alert", "vendor contract",
    "board deck", "pricing page copy", "the offsite venue", "laptop refresh", "sso rollout",
    "customer escalation", "api rate limits", "the roadmap draft", "backup restore drill", "office wifi",
    "ux research notes", "cost report", "on-call rotation", "the demo video", "partner webinar",
    "security questionnaire", "data retention policy", "mobile crash spike", "travel bookings", "team retro",
]
CHAT_TAILS = [
    "is fine now", "looks good to me", "can wait till monday", "needs one more pass", "is on me",
    "shipped", "blocked on legal", "done, merging", "is weird, looking", "slipped a day",
]
ACKS = ["yep", "ok", "sgtm", "on it", "nope", "hm", "thx", "kk", "lol yes", "fair"]
EMAIL_LINES = [
    "I went through {t} this morning and the numbers hold up, with one gap in the March column.",
    "Quick update on {t}: we are two days behind because the supplier changed the format again.",
    "Can you take a look at {t} before Thursday? I would rather not walk into the review blind.",
    "Thanks for pushing {t} over the line, that saved the team a long week of follow-ups.",
    "I disagree with the plan for {t}; moving it now costs us more than it saves, in my view.",
    "Bad news on {t}: the vendor pulled out, so I am looking for a second option today.",
]


def synth_records(n=60, seed=0):
    """n distinct fake messages: chat one-liners plus longer emails, across two channels."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        topic = TOPICS[i % len(TOPICS)]
        lap = i // len(TOPICS)  # second pass over the topics must not repeat a message
        if i % 3 == 2:
            body = EMAIL_LINES[(i + lap) % len(EMAIL_LINES)].format(t=topic)
            follow = EMAIL_LINES[(i + 3 + 2 * lap) % len(EMAIL_LINES)].format(
                t=TOPICS[(i * 7 + 3 + 11 * lap) % len(TOPICS)])
            text = f"Hi team,\n\n{body} {follow}\n\nCheers,\nP"
            out.append({"text": text, "channel": "email", "audience": "team", "ts": f"2026-01-{i % 28 + 1:02d}"})
        else:
            ack = ACKS[rng.randrange(len(ACKS))]
            tail = CHAT_TAILS[(i * 3 + lap) % len(CHAT_TAILS)]
            text = f"{ack} {topic} {tail} #{i}" if i % 5 == 0 else f"{ack} {topic} {tail}"
            if i % 4 == 0:
                text = text + " 👍"
            out.append({
                "text": text, "channel": "chat", "audience": "peers", "ts": f"2026-02-{i % 28 + 1:02d}",
                "reply_to": f"what about {topic}?",
            })
    return out


def write_jsonl(path, records):
    Path(path).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


class Sandbox:
    """A temp HOME outside any git work tree; state lands in the default ~/.config/agents/state."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.env = dict(os.environ, HOME=str(self.home))
        for k in ("AGENT_TIERS_FILE", "AGENT_HARNESS", "MIMIC_STATE_HOME", "GIT_DIR", "GIT_WORK_TREE"):
            self.env.pop(k, None)

    def state(self, persona="pat"):
        return self.home / ".config" / "agents" / "state" / "voice" / persona

    def run(self, script, *args, env=None):
        e = dict(self.env, **(env or {}))
        return subprocess.run([sys.executable, "-I", str(SCRIPTS / script), *map(str, args)],
                              capture_output=True, text=True, env=e, cwd=str(self.root))

    def close(self):
        self._tmp.cleanup()


def fill_profile(text):
    """Replace each TODO the skeleton leaves with plausible persona text (no held-out text)."""
    filler = (
        "Lowercase chat, no final period, emoji rare; email opens 'Hi team,' and signs 'Cheers, P'. "
        "Channels: chat with peers is terse, email with team is full sentences."
    )
    return text.replace("TODO", filler)


def build_state(sb, n=60, seed=0, persona="pat", fill=True):
    """ingest + split + skeleton (+ fill) a synthetic corpus; return the state dir."""
    src = sb.root / "samples.jsonl"
    write_jsonl(src, synth_records(n, seed))
    for script, args in (("ingest.py", ["--persona", persona, src]),
                         ("split.py", ["--persona", persona]),
                         ("profile.py", ["skeleton", "--persona", persona])):
        r = sb.run(script, *args)
        if r.returncode != 0:
            raise AssertionError(f"{script} failed: {r.stdout}\n{r.stderr}")
    p = sb.state(persona) / "profile.md"
    if fill:
        p.write_text(fill_profile(p.read_text(encoding="utf-8")), encoding="utf-8")
    return sb.state(persona)
