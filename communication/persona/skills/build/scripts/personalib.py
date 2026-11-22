"""Shared helpers for the persona scripts: state dir and guard, text measures, report math, runners.

Stdlib only. See ../references/spec.md for the contract each function implements.
"""

import hashlib
import json
import math
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

PERSONA_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SHORT_MAX_WORDS = 25
NEAR_DUP = 0.7
DIMS = ("voice", "length", "register", "habit", "temperament")
THRESHOLDS = {"max_id_rate": 0.65, "min_rubric": 3.5, "min_n": 20, "dim_floor": 3.0,
              "max_excluded": 0.2, "pos_bias": 0.8, "caricature": 0.35}
DEFAULT_MODELS = {"light": "haiku", "execution": "sonnet", "reasoning": "opus"}
ROLE_TIERS = {"extract": "execution", "generate": "reasoning", "judge": "reasoning"}
STUB_MARK = "[stub]"


class Fail(Exception):
    """A user-facing error with an exit code (2 input, 3 guard)."""

    def __init__(self, msg, code=2):
        super().__init__(msg)
        self.code = code


def main_wrapper(fn):
    try:
        sys.exit(fn() or 0)
    except Fail as e:
        print(f"persona: {e}", file=sys.stderr)
        sys.exit(e.code)


# --- state dir and guard ---------------------------------------------------------------------

def add_state_args(p):
    p.add_argument("--persona", help="persona name, [a-z0-9_-]")
    p.add_argument("--state-dir", type=Path, help="override the state dir")
    p.add_argument("--allow-git-worktree", action="store_true",
                   help="write even where git would track the files")


def state_dir(args):
    if args.state_dir:
        return Path(os.path.abspath(os.path.expanduser(str(args.state_dir))))
    if not args.persona:
        raise Fail("pass --persona or --state-dir")
    if not PERSONA_RE.match(args.persona):
        raise Fail(f"bad persona name {args.persona!r}: use [a-z0-9_-], 64 chars at most")
    # MIMIC_STATE_HOME is the old name, honoured for one release.
    base = os.environ.get("PERSONA_STATE_HOME") or os.environ.get("MIMIC_STATE_HOME") or os.path.join(
        os.path.expanduser("~"), ".config", "agents", "state", "persona")
    return Path(os.path.abspath(base)) / args.persona


def _git_marker(path):
    for p in [path, *path.parents]:
        if (p / ".git").exists():
            return p
    return None


def guard(target, allow=False):
    """Refuse (exit 3) a target git would track. Allowed: outside any work tree, or git-ignored."""
    if allow:
        return
    # realpath: a symlink into a repo must not hide the repo's .git
    target = Path(os.path.realpath(os.path.abspath(target)))
    existing = target
    while not existing.exists():
        existing = existing.parent
    root = _git_marker(existing)
    if root is None:
        return
    try:
        r = subprocess.run(["git", "-C", str(existing), "check-ignore", "-q", str(target)],
                           capture_output=True, text=True, timeout=30)
        ignored = r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ignored = False
    if not ignored:
        raise Fail(f"refusing to write personal data inside the git work tree {root}: {target} is not "
                   "git-ignored. Use the default state dir, ignore the path, or pass --allow-git-worktree.", 3)


def prepare(args):
    """Resolve the state dir, run the guard, create it 0700."""
    d = state_dir(args)
    guard(d, args.allow_git_worktree)
    make_dir(d)
    return d


def make_dir(d):
    missing, p = [], Path(d)
    while not p.exists():
        missing.append(p)
        p = p.parent
    for m in reversed(missing):
        m.mkdir(mode=0o700)
        os.chmod(m, 0o700)
    os.chmod(d, 0o700)  # tighten a state dir that already existed
    return Path(d)


def write_text(path, text):
    path = Path(path)
    make_dir(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, 0o600)


def write_json(path, data):
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def write_jsonl(path, rows):
    write_text(path, "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows))


def read_jsonl(path):
    path = Path(path)
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def require(path, step):
    if not Path(path).exists():
        raise Fail(f"missing {path}: run {step} first")
    return Path(path)


# --- text measures ---------------------------------------------------------------------------

def sha12(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def words(text):
    return len(text.split())


def band(text):
    return "short" if words(text) <= SHORT_MAX_WORDS else "long"


def canonical(text):
    """NFKC, lowercase, punctuation and symbols removed, whitespace collapsed (dedup key only)."""
    t = unicodedata.normalize("NFKC", text).lower()
    t = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in t)
    return " ".join(t.split())


def norm(text):
    """canonical(), or the NFKC text itself when nothing alphanumeric is left (emoji, '...')."""
    return canonical(text) or " ".join(unicodedata.normalize("NFKC", text).split())


def grams(text):
    c = f" {norm(text)} "
    return {c[i:i + 4] for i in range(max(1, len(c) - 3))}


def jaccard(a, b):
    return len(a & b) / len(a | b) if (a or b) else 1.0


def similarity(a, b):
    if norm(a) == norm(b):
        return 1.0
    return jaccard(grams(a), grams(b))


def near_dup_clusters(texts, threshold=NEAR_DUP):
    """Union-find over near-duplicate pairs. Returns the cluster root index for each text."""
    n = len(texts)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    canon = [norm(t) for t in texts]
    gs = [grams(t) for t in texts]
    first = {}
    for i, c in enumerate(canon):
        if c in first:
            union(first[c], i)
        else:
            first[c] = i
    order = sorted(range(n), key=lambda i: (len(gs[i]), i))
    for pos, i in enumerate(order):
        for j in order[pos + 1:]:
            if len(gs[i]) < threshold * len(gs[j]):
                break  # Jaccard <= |small| / |large|, and sizes only grow from here
            if jaccard(gs[i], gs[j]) >= threshold:
                union(i, j)
    return [find(i) for i in range(n)]


def _spans(tokens, k):
    return {" ".join(tokens[i:i + k]) for i in range(len(tokens) - k + 1)}


def point_leaks(point, original):
    """A point leaks when it shares 4+ consecutive canonical tokens with the original, or holds
    the whole of an original shorter than 4 tokens."""
    p = f" {canonical(point)} "
    toks = canonical(original).split()
    if not toks:
        raw = norm(original)
        return bool(raw) and raw in " ".join(unicodedata.normalize("NFKC", point).split())
    if len(toks) < 4:
        return f" {' '.join(toks)} " in p
    return any(f" {s} " in p for s in _spans(toks, 4))


def copied(generated, original):
    """Near-identical generation of an original of 8+ tokens (a short one may match honestly)."""
    if len(canonical(original).split()) < 8:
        return False
    return similarity(generated, original) >= 0.9


QUOTE_RE = re.compile(r'"[^"]*"|“[^”]*”|«[^»]*»|(?<!\w)\'[^\']+\'(?!\w)')


def sanitize_reasons(reasons, held_out):
    """Drop quoted spans; drop a reason that still shares a 4-token span with any held-out text."""
    held = set()
    for t in held_out:
        toks = canonical(t).split()
        if len(toks) >= 4:
            held |= _spans(toks, 4)
        elif len(toks) >= 2:
            held.add(" ".join(toks))
    out = []
    for r in reasons:
        r = " ".join(QUOTE_RE.sub(" ", r).split())
        c = f" {canonical(r)} "
        if r and not any(f" {h} " in c for h in held):
            out.append(r)
    return out


# --- judge order and report math -------------------------------------------------------------

def original_first(seed, rnd, item_id):
    """True when the original goes in position A for this item and round."""
    return random.Random(f"{seed}:{rnd}:{item_id}").random() < 0.5


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _item_mean(it):
    sc = it.get("scores") or {}
    return _mean([float(sc.get(d, 0)) for d in DIMS])


def _hit(it):
    """Identified, with an unparseable pick (None) counted against the persona."""
    return 0.0 if it["identified"] is False else 1.0


def _group(items):
    return {"n": len(items), "id_rate": round(_mean([_hit(it) for it in items]), 4),
            "mean_rubric": round(_mean([_item_mean(it) for it in items]), 4)}


def summarize(items, thresholds=None, groups=True):
    """Report math over judged items. Unparseable picks count as identified; unparseable scores as 0.
    Each band and channel row also carries the verdict the same rules give over its own items."""
    t = dict(THRESHOLDS, **(thresholds or {}))
    scored = [it for it in items if not it.get("excluded")]
    excluded = {}
    for it in items:
        if it.get("excluded"):
            excluded[it["excluded"]] = excluded.get(it["excluded"], 0) + 1
    n = len(scored)
    picks = [it["picked"] for it in scored if it.get("picked") in ("A", "B")]
    s = {
        "n_total": len(items), "n_scored": n, "n_excluded": len(items) - n, "excluded": excluded,
        "id_rate": round(_mean([_hit(it) for it in scored]), 4),
        "pos_a_rate": round(_mean([1.0 if p == "A" else 0.0 for p in picks]), 4) if picks else None,
        "dims": {d: round(_mean([float((it.get("scores") or {}).get(d, 0)) for it in scored]), 4) for d in DIMS},
        "unparseable": {"identify": sum(1 for it in scored if it["identified"] is None),
                        "score": sum(1 for it in scored if not it.get("scores"))},
        "thresholds": t, "warnings": [],
    }
    s["mean_rubric"] = round(_mean(list(s["dims"].values())), 4)
    for kind, key in (("by_band", "band"), ("by_channel", "channel")):
        s[kind] = {}
        for g in sorted({str(it.get(key)) for it in scored}):
            s[kind][g] = _group([it for it in scored if str(it.get(key)) == g])
            if groups:
                s[kind][g]["verdict"] = summarize([it for it in items if str(it.get(key)) == g], t, False)["verdict"]
    worst = sorted(scored, key=lambda it: (_item_mean(it), it["identified"] is False, it["id"]))
    s["worst"] = [it["id"] for it in worst[:5]]
    s["failed_dims"] = [d for d in DIMS if s["dims"][d] < t["dim_floor"]]
    # A separate signal, not a pass criterion: a short message regenerated word for word.
    shorts = [it for it in scored if it.get("band") == "short" and it.get("generated") is not None]
    hits = sum(1 for it in shorts if norm(it["generated"]) == norm(it.get("original", "")))
    s["short_exact_match"] = {"n": len(shorts), "matches": hits,
                              "rate": round(hits / len(shorts), 4) if shorts else 0.0}

    biased = s["pos_a_rate"] is not None and n >= t["min_n"] and not (
        1 - t["pos_bias"] <= s["pos_a_rate"] <= t["pos_bias"])
    if items and s["n_excluded"] / len(items) > t["max_excluded"]:
        verdict = "INVALID"
        s["warnings"].append(f"{s['n_excluded']} of {len(items)} items excluded: fix the extractor or generator")
    elif biased:
        verdict = "INVALID"
        s["warnings"].append(f"judge picked position A in {s['pos_a_rate']:.0%} of answers: degenerate judge")
    elif n < t["min_n"]:
        verdict = "INCONCLUSIVE"
        s["warnings"].append(f"only {n} scored items, {t['min_n']} needed for a verdict")
    elif t["caricature"] <= s["id_rate"] <= t["max_id_rate"] and s["mean_rubric"] >= t["min_rubric"]:
        verdict = "PASS"
    else:
        verdict = "FAIL"
    if n >= t["min_n"] and s["id_rate"] < t["caricature"]:
        s["warnings"].append("caricature: the judge reliably picks the generated message as the person's; "
                             "the profile overdoes habits (FAIL: the band is two-sided)")
    s["verdict"] = verdict
    return s


# --- revision rounds: stop rule and selection -------------------------------------------------

def band_se(n):
    """Binomial standard error of a rate at p = 0.5 over n items (the noise margin)."""
    return (0.25 / max(n, 1)) ** 0.5


def _bands(r):
    return {b: v for b, v in (r.get("by_band") or {}).items() if v.get("n")}


def _worst(r):
    """(distance from 0.5, n) of the worst length band; on a tie the smaller band (wider noise)."""
    return max(((abs(v["id_rate"] - 0.5), -v["n"]) for v in _bands(r).values()), default=(0.5, -1))


def worst_distance(r):
    """How far the worst length band of a round is from 0.5."""
    return _worst(r)[0]


def worst_se(r):
    return band_se(-_worst(r)[1])


def _band_rubric(r):
    return min((v["mean_rubric"] for v in _bands(r).values()), default=0.0)


def stop_rule(rounds, max_rounds=10, min_rubric=THRESHOLDS["min_rubric"],
              low=THRESHOLDS["caricature"], high=THRESHOLDS["max_id_rate"]):
    """(reason, detail) after the given dev rounds, reason None to go on.
    converged: in the last two rounds every band is in [low, high] with rubric >= min_rubric, and
      no band's rate moved by more than its standard error between them.
    plateau: in the last three rounds the worst band never beat the best earlier round by more
      than its standard error.
    cap: max_rounds rounds done."""
    if len(rounds) >= 2:
        prev, last = rounds[-2], rounds[-1]
        ok = all(low <= v["id_rate"] <= high and v["mean_rubric"] >= min_rubric
                 for r in (prev, last) for v in _bands(r).values())
        steady = set(_bands(prev)) == set(_bands(last)) and all(
            abs(_bands(last)[b]["id_rate"] - _bands(prev)[b]["id_rate"])
            <= band_se(min(_bands(last)[b]["n"], _bands(prev)[b]["n"])) for b in _bands(last))
        if ok and steady:
            return "converged", f"rounds {prev['round']} and {last['round']}: every band passes and holds"
    if len(rounds) >= 4:
        ref = min(rounds[:-3], key=worst_distance)
        se = worst_se(ref)
        if all(worst_distance(r) > worst_distance(ref) - se for r in rounds[-3:]):
            return "plateau", (f"rounds {rounds[-3]['round']} to {rounds[-1]['round']}: worst band no better "
                               f"than round {ref['round']} by more than {se:.3f}")
    if len(rounds) >= max_rounds:
        return "cap", f"{max_rounds} rounds done"
    return None, ""


def select_round(rounds, min_rubric=THRESHOLDS["min_rubric"]):
    """The dev round whose profile the sealed test uses (spec: Selection)."""
    if not rounds:
        raise Fail("no dev rounds to select from: run evaluate.py run --slice dev first")
    eligible = [r for r in rounds if _bands(r) and _band_rubric(r) >= min_rubric]
    if eligible:
        best = min(eligible, key=worst_distance)
        margin = worst_se(best)
        ties = [r for r in eligible if worst_distance(r) <= worst_distance(best) + margin + 1e-9]
    else:
        top = max(_band_rubric(r) for r in rounds)
        ties, margin = [r for r in rounds if _band_rubric(r) >= top - 1e-9], None
    pick = max(ties, key=lambda r: r["round"])
    return {"round": pick["round"], "fold": pick.get("fold"), "profile_hash": pick.get("profile_hash"),
            "floor_met": bool(eligible), "margin": round(margin, 4) if margin is not None else None,
            "worst_distance": round(worst_distance(pick), 4), "tie_set": sorted(r["round"] for r in ties),
            "rule": ("among rounds whose every length band has rubric >= min_rubric, the worst band's id "
                     "rate closest to 0.5; rounds within one standard error (p 0.5, n of that band in the "
                     "best round) tie and the latest wins; with no round at the floor, the highest "
                     "worst-band rubric, latest on a tie")}


# --- models and runners ----------------------------------------------------------------------

def _tier_map(env):
    harness = env.get("AGENT_HARNESS", "claude")
    out = dict(DEFAULT_MODELS)
    path = env.get("AGENT_TIERS_FILE")
    if path:
        try:
            tiers = json.loads(Path(path).read_text(encoding="utf-8")).get("tiers", {})
        except (OSError, ValueError, AttributeError):
            tiers = {}
        for tier in DEFAULT_MODELS:
            m = (tiers.get(tier) or {}).get(harness)
            if isinstance(m, str) and m and m != "TODO":
                out[tier] = m
    return out


def resolve_model(value, env=None):
    """A tier name or a model -> (model, tier, or None when the model is not in the map)."""
    m = _tier_map(os.environ if env is None else env)
    if value in m:
        return m[value], value
    for tier, model in m.items():
        if model == value:
            return value, tier
    return value, None


def claude_argv(model, system):
    """Isolated: no tools, no MCP, no user/project settings (CLAUDE.md, output style, hooks),
    no session history on disk. JSON output carries the cost of the call."""
    return ["claude", "-p", "--output-format", "json", "--model", model, "--no-session-persistence", "--tools", "",
            "--strict-mcp-config", "--setting-sources", "", "--system-prompt", system]


class RunnerError(Exception):
    usage = None  # the failed reply's usage, when it reported one
    attempts = ()  # usage of each failed paid attempt


class CommandRunner:
    """Prompt on stdin, reply on stdout. `claude` builds the isolated argv; `cmd:` runs any command."""

    def __init__(self, spec, timeout=300):
        self.spec, self.timeout = spec, timeout

    def argv(self, model, system):
        if self.spec == "claude":
            return claude_argv(model, system)
        return shlex.split(self.spec[len("cmd:"):])

    def check(self):
        exe = self.argv("m", "s")[0] if self.argv("m", "s") else ""
        if not exe or not shutil.which(exe):
            raise Fail(f"runner command not found: {exe!r}")

    def complete(self, role, model, system, prompt, meta):
        return self.invoke(role, model, system, prompt, meta)[0]

    max_attempts = 2

    def invoke(self, role, model, system, prompt, meta):
        """(reply text, usage). usage["prior"] lists the usage of failed paid attempts before the one
        that answered; a RunnerError carries .attempts. A cost not reported is None (charged its
        estimate by the ledger)."""
        env = dict(os.environ, PERSONA_ROLE=role, PERSONA_MODEL=model, PERSONA_SYSTEM=system)
        last, prior = "", []
        for _ in range(self.max_attempts):
            try:
                r = subprocess.run(self.argv(model, system), input=prompt, capture_output=True,
                                   text=True, timeout=self.timeout, env=env)
            except FileNotFoundError as e:
                raise Fail(f"runner not found: {e.filename}") from e
            except subprocess.TimeoutExpired:
                last = "timeout"
                prior.append(dict(NO_USAGE))
                continue
            if r.returncode == 0 and r.stdout.strip():
                try:
                    text, usage = parse_cli_reply(r.stdout, strict=self.spec == "claude")
                except RunnerError as e:
                    last = str(e)
                    prior.append(e.usage or dict(NO_USAGE))
                    continue
                if text:
                    return text, dict(usage, prior=prior)
                last = "empty result"
                prior.append(usage)
                continue
            last = (r.stderr or r.stdout).strip()[-300:]
            prior.append(dict(NO_USAGE))
        err = RunnerError(f"{role} failed twice: {last}")
        err.attempts = prior
        raise err


NO_USAGE = {"cost_usd": None, "input_tokens": None, "output_tokens": None}


def parse_cli_reply(stdout, strict=False):
    """(text, usage) from `claude -p --output-format json` (or a cmd runner printing the same object).
    Fields relied on: result, is_error, subtype, total_cost_usd, usage.{input,output}_tokens and
    usage.cache_{creation,read}_input_tokens. strict (the claude runner): anything but that object
    is an error. Otherwise anything else is plain text of unknown cost."""
    raw = stdout.strip()
    try:
        obj = json.loads(raw)
    except ValueError:
        obj = None
    if not isinstance(obj, dict) or not ("result" in obj or "is_error" in obj):
        if strict:
            raise RunnerError(f"not a claude JSON reply: {raw[:200]!r}")
        return raw, dict(NO_USAGE)
    u = obj.get("usage") if isinstance(obj.get("usage"), dict) else {}

    def num(v):
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None

    ins = [num(u.get(k)) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")]
    usage = {"cost_usd": num(obj.get("total_cost_usd")),
             "input_tokens": sum(x for x in ins if x is not None) if any(x is not None for x in ins) else None,
             "output_tokens": num(u.get("output_tokens"))}
    if obj.get("is_error") or obj.get("subtype", "success") != "success" or not isinstance(obj.get("result", ""), str):
        err = RunnerError(f"error reply: {obj.get('subtype')}: {str(obj.get('result', ''))[-200:]}")
        err.usage = usage
        raise err
    return str(obj.get("result") or "").strip(), usage


class BudgetExceeded(Fail):
    """The next call would pass --max-cost-usd (exit 4)."""

    def __init__(self, msg):
        super().__init__(msg, 4)


class Ledger:
    """Append-only cost log of model calls with a reservation-based cap.

    Before a call, reserve() adds the call's estimate to the open reservations under a lock and
    refuses when spent + reserved + estimate would pass the cap, so parallel calls cannot overshoot
    together. commit() replaces the reservation with the real cost, or the estimate when the cost
    is unknown (never 0)."""

    def __init__(self, path, max_cost=None, call_estimate=0.5, tool="evaluate", cap_basis="total"):
        self.path, self.max_cost, self.call_estimate, self.tool = Path(path), max_cost, call_estimate, tool
        self.cap_basis = cap_basis  # "total" counts estimated rows against the cap, "measured" does not
        self._lock = threading.Lock()
        self._rows = read_jsonl(self.path)
        self._reserved, self._next = {}, 0

    def rows(self):
        return list(self._rows)

    def total(self):
        return sum(float(r.get("cost_usd") or 0) for r in self._rows)

    def spent(self):
        """Spend the cap applies to: every row, or only the measured ones."""
        if self.cap_basis == "measured":
            return sum(float(r.get("cost_usd") or 0) for r in self._rows if not r.get("estimated"))
        return self.total()

    def estimate(self, role, model, chars):
        """1.5 x the larger of the top cost seen for this role and model and the top cost per prompt
        character times this prompt; the default with no history. Estimated rows do not count."""
        seen = [r for r in self._rows if r.get("role") == role and r.get("model") == model
                and not r.get("estimated")]
        if not seen:
            return self.call_estimate
        top = max(float(r["cost_usd"]) for r in seen)
        per = max(float(r["cost_usd"]) / max(1, int(r.get("prompt_chars") or 1)) for r in seen)
        return 1.5 * max(top, per * chars)

    def reserve(self, role, model, chars, attempts=1):
        """Hold the estimate of up to `attempts` paid attempts; refuse past the cap. Spend is re-read
        from the file, so another process's calls on the same state dir count too."""
        with self._lock:
            self._rows = read_jsonl(self.path)
            est = self.estimate(role, model, chars) * attempts
            spent, held = self.spent(), sum(self._reserved.values())
            if self.max_cost is not None and spent + held + est > self.max_cost + 1e-9:
                raise BudgetExceeded(
                    f"budget: the next {role} call ({model}, about ${est:.4f}) would pass --max-cost-usd "
                    f"{self.max_cost} (spent ${spent:.4f}, in flight ${held:.4f}); state is saved, rerun with "
                    "a higher cap to continue")
            self._next += 1
            self._reserved[self._next] = est
            return self._next

    def release(self, token):
        with self._lock:
            self._reserved.pop(token, None)

    def commit(self, token, role, model, chars, usages, tags=None):
        """One row per paid attempt; an attempt of unknown cost is charged one call's estimate."""
        with self._lock:
            self._reserved.pop(token, None)
            est = self.estimate(role, model, chars)
            rows = []
            for usage in usages:
                cost = usage.get("cost_usd")
                row = dict({"tool": self.tool}, **(tags or {}))
                row.update(ts=datetime.now(timezone.utc).isoformat(timespec="seconds"), role=role, model=model,
                           cost_usd=round(float(est if cost is None else cost), 6), estimated=cost is None,
                           input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
                           prompt_chars=chars)
                rows.append(row)
            make_dir(self.path.parent)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows))
            self._rows += rows
            return rows


class Metered:
    """A runner behind the ledger: reserve, call, record. `tags` go on every ledger row."""

    def __init__(self, runner, ledger):
        self.runner, self.ledger, self.tags = runner, ledger, {}

    def complete(self, role, model, system, prompt, meta):
        n = len(prompt)
        token = self.ledger.reserve(role, model, n, getattr(self.runner, "max_attempts", 1))
        try:
            text, usage = self.runner.invoke(role, model, system, prompt, meta)
        except RunnerError as e:
            self.ledger.commit(token, role, model, n, list(e.attempts) or [dict(NO_USAGE)], self.tags)
            raise
        except Fail:
            self.ledger.release(token)  # the runner never started (not found)
            raise
        except BaseException:
            # killed mid-call: the call may have been billed, charge its estimate
            self.ledger.commit(token, role, model, n, [dict(NO_USAGE)], self.tags)
            raise
        prior = usage.pop("prior", [])
        self.ledger.commit(token, role, model, n, prior + [usage], self.tags)
        return text


def preflight(ledger, calls, n_items, what, attempts=2, stand_in=None):
    """Refuse (exit 4) before a sealed run whose estimated cost would pass the cap. Counts every
    paid attempt a call may make, so a run that passes rarely meets the cap mid-way. `stand_in(role,
    model, chars)` may return an estimate for a call with no history of its own, else None."""
    if ledger is None or ledger.max_cost is None:
        return
    ledger._rows = read_jsonl(ledger.path)
    per = attempts * sum((stand_in(role, model, chars) if stand_in else None) or ledger.estimate(role, model, chars)
                         for role, model, chars in calls)
    spent = ledger.spent()
    if spent + per * n_items > ledger.max_cost + 1e-9:
        raise BudgetExceeded(
            f"budget: {what} needs about ${per * n_items:.4f} ({n_items} items x ${per:.4f}) on top of "
            f"${spent:.4f} spent, over --max-cost-usd {ledger.max_cost}; the sealed slice is untouched")


class StubRunner:
    """Deterministic offline test double. It reads meta (item id, original, position) only to
    follow a script; the real runners never receive meta."""

    def __init__(self, script=None):
        self.s = script or {}

    def invoke(self, role, model, system, prompt, meta):
        """(reply, usage) with the scripted cost: `cost` per role, else `cost_default` (0);
        roles in `cost_unknown` report no cost."""
        text = self.complete(role, model, system, prompt, meta)
        cost = None if role in self.s.get("cost_unknown", []) else \
            float(self.s.get("cost", {}).get(role, self.s.get("cost_default", 0.0)))
        return text, {"cost_usd": cost, "input_tokens": len(prompt) // 4, "output_tokens": len(text) // 4}

    def complete(self, role, model, system, prompt, meta):
        iid = meta.get("item_id", "")
        if role == "extract":
            mode = self.s.get("extract", {}).get(iid)
            if mode in ("quote_context", "quote_intent"):
                key = mode.split("_")[1]
                out = {"point": f"a message, item {iid}", "context": "", "intent": "inform"}
                out[key] = meta["original"]
                return json.dumps(out)
            if mode == "quote" or (mode == "quote_once" and meta.get("attempt") == 1):
                return json.dumps({"point": meta["original"], "context": "", "intent": "inform"})
            return json.dumps({"point": f"a {meta.get('band')} {meta.get('channel')} message, item {iid}",
                               "context": meta.get("context", ""), "intent": "inform"})
        if role == "generate":
            mode = self.s.get("generate", {}).get(iid)
            if mode == "copy":
                return meta["original"]
            if mode == "error":
                raise RunnerError("scripted generator error")
            return f"{STUB_MARK} {meta.get('point', '')}"
        if role == "identify":
            mode = self.s.get("identify", {}).get(iid, self.s.get("identify_default", "coin"))
            orig = meta["original_pos"]
            pick = {"correct": orig, "wrong": "B" if orig == "A" else "A", "A": "A", "B": "B"}.get(mode)
            if mode == "coin":
                pick = "AB"[int(hashlib.sha256(f"coin:{iid}".encode()).hexdigest(), 16) % 2]
            elif mode == "marker":
                pick = "B" if STUB_MARK in meta["candidates"][0] else "A"
            if pick is None:
                return "I cannot decide."
            return json.dumps({"original": pick, "why": "stub"})
        if role == "score":
            mode = self.s.get("score", {}).get(iid, self.s.get("score_default", 4))
            if mode == "garbage":
                return "no scores"
            reason = self.s.get("reasons", {}).get(iid, "stub reason")
            per = mode if isinstance(mode, dict) else {d: mode for d in DIMS}
            out = {d: {"score": per.get(d, 0), "reason": reason} for d in DIMS}
            out.update(missed=self.s.get("missed", {}).get(iid, []), entities=self.s.get("entities", {}).get(iid, []))
            return json.dumps(out)
        if role == "predict":
            if self.s.get("predict", {}).get(iid) == "error":
                raise RunnerError("scripted predictor error")
            return f"{STUB_MARK} {meta.get('point', '')}"
        if role == "update":
            mode = self.s.get("update", {}).get(iid, self.s.get("update_default", "add"))
            if mode == "garbage":
                return "no patches here"
            if mode == "error":
                raise RunnerError("scripted updater error")
            if mode == "add":
                mode = [{"op": "add", "node": {"id": f"n-{iid}", "type": "belief", "confidence": 0.5,
                                               "text": f"stub belief learned from item {iid}"}}]
            elif mode == "echo":  # copies test canaries (zqx...) it was shown into the map
                seen = " ".join(sorted(set(re.findall(r"zqx\w+", prompt))))
                mode = [{"op": "add", "node": {"id": f"n-{iid}", "type": "belief", "confidence": 0.5,
                                               "text": f"stub belief from item {iid} {seen}".strip()}}]
            return json.dumps({"patches": mode})
        if role == "consolidate":
            mode = self.s.get("consolidate", "halve")
            if mode == "garbage":
                return "nothing useful"
            nodes = sorted((meta.get("map") or {}).get("nodes", []), key=lambda n: (n["confidence"], n["id"]))
            return json.dumps({"patches": [{"op": "remove", "id": n["id"]} for n in nodes[:len(nodes) // 2]]})
        raise RunnerError(f"unknown role {role}")


def make_runner(spec, stub_script=None, ledger=None):
    """Build and preflight a runner, so a typo fails before the test slice is sealed. With a ledger,
    every call is metered and capped."""
    if spec == "stub":
        try:
            script = json.loads(Path(stub_script).read_text(encoding="utf-8")) if stub_script else {}
        except (OSError, ValueError) as e:
            raise Fail(f"bad --stub-script: {e}") from e
        r = StubRunner(script)
    elif spec == "claude" or spec.startswith("cmd:"):
        r = CommandRunner(spec)
        r.check()
    else:
        r = None
    if r is not None:
        return Metered(r, ledger) if ledger is not None else r
    raise Fail(f"unknown runner {spec!r}: use claude, stub or cmd:'<command>'")


def parse_json(text):
    """The first JSON object in a model reply, or None."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text or ""):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


# --- the sealed slice -------------------------------------------------------------------------

def seal_check(path, rerun):
    """Earlier runs of the sealed slice; refuse a second use without a rerun reason. A run stopped by
    the budget before any result was written does not count as a use."""
    path = Path(path)
    runs = json.loads(path.read_text(encoding="utf-8") or "{}").get("runs", []) if path.exists() else []
    if any(not r.get("aborted") for r in runs) and not rerun:
        raise Fail("the sealed slice was already used (by world.py final or evaluate.py --slice test); "
                   "pass --rerun-test REASON to run it again (it overfits)")
    return runs


def seal_write(path, runs, entry):
    runs = runs + [dict(entry, at=datetime.now(timezone.utc).isoformat(timespec="seconds"))]
    write_json(path, {"runs": runs})
    return runs


def seal_abort(path, runs, why):
    """Mark the last run aborted: no result was written, so the slice is not used up."""
    runs[-1] = dict(runs[-1], aborted=why)
    write_json(path, {"runs": runs})


# --- profile ---------------------------------------------------------------------------------

SECTIONS = ("Measured stats", "Mental model", "Habits", "Temperament", "Short messages", "Long messages",
            "Channels and audiences", "Lexicon", "Never", "Decisions and responses", "Worked examples")
MODEL_SUBSECTIONS = ("Beliefs and values", "Framing", "Reasoning moves", "Emotional range", "Stance",
                     "Compressed", "Expanded")
MAX_EXAMPLES = 6
PROFILE_MAX_BYTES = 16 * 1024
EXAMPLE_RE = re.compile(r"^- \[train:([^\]]*)\] (.*)$")


def sections(text):
    """{H2 title: body} in file order."""
    out, cur = {}, None
    for line in text.splitlines():
        mt = re.match(r"^## (.+?)\s*$", line)
        if mt:
            cur = mt.group(1)
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def example_text(s):
    return s.replace("\\n", "\n")


def example_ids(text):
    """TRAIN ids the profile quotes as worked examples."""
    return {e.group(1) for e in map(EXAMPLE_RE.match, sections(text).get("Worked examples", "").splitlines()) if e}


def fold_view(train, fold, keep=()):
    """(TRAIN without the fold, the fold's records) for the revision round on that fold. Ids in
    keep (the profile's worked examples) stay on the TRAIN side and are never judged."""
    if fold is None:
        return train, []
    held = lambda t: t.get("fold") == fold and t["id"] not in keep  # noqa: E731
    return [t for t in train if not held(t)], [t for t in train if held(t)]


def load_split(d):
    sd = Path(d) / "split"
    require(sd / "manifest.json", "split.py")
    return (json.loads((sd / "manifest.json").read_text(encoding="utf-8")),
            read_jsonl(sd / "train.jsonl"), read_jsonl(sd / "dev.jsonl"), read_jsonl(sd / "test.jsonl"))


def split_id(dev, test):
    """Identity of a split: which messages are held out."""
    ids = {"dev": sorted(r["id"] for r in dev), "test": sorted(r["id"] for r in test)}
    return hashlib.sha256(json.dumps(ids, sort_keys=True).encode()).hexdigest()[:16]


def validate_profile(d, text, fold=None):
    """Errors for a profile against the schema and the split in state dir d (empty list = valid).
    With a fold, that fold counts as held out: the profile judged on it must not carry its text."""
    manifest, train, dev, test = load_split(d)
    sid = split_id(dev, test)
    train, held_fold = fold_view(train, fold, example_ids(text))
    dev = dev + held_fold
    errs = []
    if len(text.encode("utf-8")) > PROFILE_MAX_BYTES:
        errs.append(f"profile is {len(text.encode('utf-8'))} bytes, over 16 KB")
    mh = re.search(r"^split: (\S+)\s*$", text, re.M)
    if not mh or mh.group(1) != sid:
        errs.append(f"split line missing or not {sid}: profile was built for another split")
    sec = sections(text)
    for s in SECTIONS:
        if s not in sec:
            errs.append(f"missing section: {s}")
        elif not sec[s]:
            errs.append(f"empty section: {s}")
        elif "TODO" in sec[s]:
            errs.append(f"TODO left in section: {s}")
    if "TODO" in text.split("\n## ", 1)[0]:
        errs.append("TODO left in the header")
    subs = {}
    cur = None
    for line in sec.get("Mental model", "").splitlines():
        mt = re.match(r"^### (.+?)\s*$", line)
        if mt:
            cur = mt.group(1)
            subs[cur] = []
        elif cur is not None:
            subs[cur].append(line)
    if "Mental model" in sec:
        for sub in MODEL_SUBSECTIONS:
            if sub not in subs:
                errs.append(f"missing mental model subsection: {sub}")
            elif not "\n".join(subs[sub]).strip():
                errs.append(f"empty mental model subsection: {sub}")

    by_id = {t["id"]: t for t in train}
    examples = [EXAMPLE_RE.match(ln) for ln in sec.get("Worked examples", "").splitlines()]
    examples = [e for e in examples if e]
    bands = set()
    for e in examples:
        tid, body = e.group(1), example_text(e.group(2))
        if tid not in by_id:
            errs.append(f"worked example {tid!r} is not in TRAIN")
        elif " ".join(body.split()) != " ".join(by_id[tid]["text"].split()):
            errs.append(f"worked example {tid} differs from TRAIN")
        else:
            bands.add(by_id[tid]["band"])
    if len(examples) < 3:
        errs.append(f"{len(examples)} worked examples: need at least 3 worked examples")
    elif len(examples) > MAX_EXAMPLES:
        errs.append(f"{len(examples)} worked examples: at most {MAX_EXAMPLES} worked examples (the mental "
                    "model carries the voice, not a pile of samples)")
    if any(t["band"] == "short" for t in train) and "short" not in bands:
        errs.append("no short worked example, but TRAIN has short messages")

    matrix = sec.get("Channels and audiences", "").lower()
    counts = {}
    for t in train:
        counts[t["channel"]] = counts.get(t["channel"], 0) + 1
    for ch, c in sorted(counts.items()):
        if c >= 3 and not re.search(rf"(?<![\w-]){re.escape(ch.lower())}(?![\w-])", matrix):
            errs.append(f"channel not in matrix: {ch} ({c} train messages)")

    prof = f" {canonical(text)} "
    train_c = [f" {canonical(t['text'])} " for t in train]
    for h in dev + test:
        toks = canonical(h["text"]).split()
        spans = _spans(toks, 6) if len(toks) >= 6 else ({" ".join(toks)} if len(toks) >= 3 else set())
        for s in sorted(spans):
            if f" {s} " in prof and not any(f" {s} " in t for t in train_c):
                errs.append(f"held-out text in profile (from {h['id']}): no dev or test words may appear")
                break
    return errs
