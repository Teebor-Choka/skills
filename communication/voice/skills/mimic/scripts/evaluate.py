#!/usr/bin/env python3
"""Run one eval round: extract the point of each held-out message, generate it from the profile,
then a blind judge picks the original and a second judge call scores the generated one.

  evaluate.py run --persona NAME --slice dev|test [--runner claude|stub|cmd:'<command>']

Dev rounds (at most 3) write aggregates-only feedback.json for revision. The test slice runs once;
a second run needs --rerun-test REASON. See ../references/spec.md.
"""

import argparse
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mimiclib as m  # noqa: E402

MAX_DEV_ROUNDS = 3

RUBRIC = """Score the CANDIDATE against how this person writes, 0 to 5 per dimension:
- voice: would someone who knows them believe they wrote it (word choice, rhythm, idiolect)
- length: right length for this person in this channel; a one-liner stays a one-liner
- register: formality, casing, politeness right for this audience and channel
- habit: openers, closers, punctuation, emoji, signature phrases at their rate, not more
- temperament: directness, hedging, humor, and the reaction fit them
5 indistinguishable, 4 close with one slip, 3 recognisably theirs with a clear slip, 2 generic,
1 wrong for them, 0 missing or caricature (habits overdone)."""

SYS_EXTRACT = "You describe what a message communicates without quoting it. Reply with JSON only."
SYS_GENERATE = ("You write one message as a specific person, following their voice profile. "
                "Output only the message text.")
SYS_JUDGE = "You are a careful judge of personal writing style. Reply with JSON only."


def extract_prompt(it, strict):
    p = (f"Message (channel {it['channel']}, audience {it['audience']}):\n<<<\n{it['text']}\n>>>\n"
         f"Context it responds to: {it['context'] or 'none given'}\n\n"
         'Return JSON: {"point": "what it communicates: facts, decision, request, feeling", '
         '"intent": "inform|ask|agree|decline|thank|react|decide|other", '
         '"context": "the situation it responds to"}.\n'
         "Paraphrase. Never reuse 4 or more consecutive words of the message. For a very short "
         "message describe the act (agrees, declines, thanks), never repeat its words.")
    if strict:
        p += "\nYour previous answer reused the message's wording. Describe it abstractly this time."
    return p


def generate_prompt(profile, it, ext):
    return (f"Voice profile:\n{profile}\n\nWrite the message this person would send.\n"
            f"Channel: {it['channel']}\nAudience: {it['audience']}\n"
            f"Context: {ext.get('context') or it['context'] or 'none given'}\n"
            f"What it must communicate: {ext.get('point', '')}\nIntent: {ext.get('intent', '')}\n"
            "Output only the message, no quotes, no commentary.")


def exemplar_block(ex):
    return "\n".join(f"- <<<{t['text']}>>> ({t['channel']}, {t['band']})" for t in ex)


def identify_prompt(it, ext, ex, a, b):
    return (f"Known messages by this person:\n{exemplar_block(ex)}\n\n"
            f"Situation: {ext.get('context') or it['context'] or 'none given'}\n"
            f"What the message communicates: {ext.get('point', '')}\n\n"
            "One of these two messages was written by the person, the other by a model imitating them.\n"
            f"A:\n<<<\n{a}\n>>>\nB:\n<<<\n{b}\n>>>\n"
            'Which did the person write? JSON: {"original": "A" or "B", "why": "one line naming a feature, no quotes"}')


def score_prompt(it, ex, generated):
    return (f"{RUBRIC}\n\nKnown messages by this person:\n{exemplar_block(ex)}\n\n"
            f"REFERENCE (what the person actually wrote here):\n<<<\n{it['text']}\n>>>\n"
            f"CANDIDATE (a model's imitation):\n<<<\n{generated}\n>>>\n"
            'JSON: {"voice": {"score": 0-5, "reason": "one line naming a feature, never quoting"}, '
            '"length": {...}, "register": {...}, "habit": {...}, "temperament": {...}}')


def pick_exemplars(train, it, k, seed):
    rng = random.Random(f"{seed}:ex:{it['id']}")
    chosen, seen = [], set()
    for cond in (lambda t: t["channel"] == it["channel"] and t["band"] == it["band"],
                 lambda t: t["channel"] == it["channel"], lambda t: t["band"] == it["band"], lambda t: True):
        pool = sorted((t for t in train if cond(t) and t["id"] not in seen), key=lambda t: t["id"])
        for t in rng.sample(pool, min(len(pool), k - len(chosen))):
            chosen.append(t)
            seen.add(t["id"])
        if len(chosen) >= k:
            break
    return chosen


def parse_scores(text):
    obj = m.parse_json(text)
    if not obj:
        return None, {}
    scores, reasons = {}, {}
    for d in m.DIMS:
        v = obj.get(d)
        s = v.get("score") if isinstance(v, dict) else v
        try:
            scores[d] = max(0.0, min(5.0, float(s)))
        except (TypeError, ValueError):
            scores[d] = 0.0
        if isinstance(v, dict) and isinstance(v.get("reason"), str):
            reasons[d] = v["reason"]
    return scores, reasons


def run_item(runner, models, it, profile, train, seed, rnd, k_ex):
    rec = {"id": it["id"], "band": it["band"], "channel": it["channel"], "audience": it["audience"],
           "context": it["context"], "original": it["text"], "excluded": None, "identified": None,
           "picked": None, "scores": None, "reasons": {}}
    meta = {"item_id": it["id"], "original": it["text"], "band": it["band"], "channel": it["channel"],
            "context": it["context"]}
    ext = None
    for attempt in (1, 2):
        rec["extract_attempts"] = attempt
        try:
            out = runner.complete("extract", models["extract"], SYS_EXTRACT, extract_prompt(it, attempt > 1),
                                  dict(meta, attempt=attempt))
        except m.RunnerError:
            continue
        ext = m.parse_json(out)
        if ext and isinstance(ext.get("point"), str) and not m.point_leaks(ext["point"], it["text"]):
            break
        rec["excluded"] = "point_leak" if ext and isinstance(ext.get("point"), str) else "error"
        ext = None
    if ext is None:
        rec["excluded"] = rec["excluded"] or "error"
        return rec
    rec["excluded"] = None
    rec["point"] = ext["point"]
    try:
        gen = runner.complete("generate", models["generate"], SYS_GENERATE, generate_prompt(profile, it, ext),
                              dict(meta, point=ext["point"])).strip()
    except m.RunnerError:
        rec["excluded"] = "error"
        return rec
    rec["generated"] = gen
    if m.copied(gen, it["text"]):
        rec["excluded"] = "copied"
        return rec
    ex = pick_exemplars(train, it, k_ex, seed)
    rec["exemplars"] = [t["id"] for t in ex]
    first = m.original_first(seed, rnd, it["id"])
    a, b = (it["text"], gen) if first else (gen, it["text"])
    rec["original_pos"] = "A" if first else "B"
    try:
        out = runner.complete("identify", models["judge"], SYS_JUDGE, identify_prompt(it, ext, ex, a, b),
                              dict(meta, original_pos=rec["original_pos"], candidates=(a, b)))
        obj = m.parse_json(out) or {}
        pick = str(obj.get("original", "")).strip().upper()
    except m.RunnerError:
        pick = ""
    if pick in ("A", "B"):
        rec["picked"] = pick
        rec["identified"] = pick == rec["original_pos"]
    try:
        out = runner.complete("score", models["judge"], SYS_JUDGE, score_prompt(it, ex, gen), meta)
        rec["scores"], rec["reasons"] = parse_scores(out)
    except m.RunnerError:
        pass
    return rec


def feedback(summary, items, held_out, floor):
    """Aggregates only: no message text, judge reasons sanitized against every held-out message."""
    reasons = {}
    for d in m.DIMS:
        raw = [it["reasons"].get(d, "") for it in items
               if it.get("scores") and it["scores"].get(d, 0) < floor and it.get("reasons")]
        reasons[d] = m.sanitize_reasons([r for r in raw if r], held_out)[:8]
    keep = ("n_scored", "id_rate", "pos_a_rate", "mean_rubric", "dims", "failed_dims", "by_band",
            "by_channel", "verdict", "warnings", "excluded")
    return dict({k: summary[k] for k in keep}, judge_reasons=reasons)


def report_md(rep):
    t = rep["thresholds"]
    lines = [
        f"# mimic report: {rep['persona']} {rep['slice']}-{rep['round']}", "",
        f"verdict: {rep['verdict']}",
        f"items: {rep['n_scored']} scored of {rep['n_total']} (excluded: "
        + (", ".join(f"{k} {v}" for k, v in rep["excluded"].items()) or "none") + ")",
        f"identification rate: {rep['id_rate']:.2f} (0.50 = indistinguishable; pass <= {t['max_id_rate']})",
        f"judge picked A: {rep['pos_a_rate'] if rep['pos_a_rate'] is not None else 'n/a'}",
        f"mean rubric: {rep['mean_rubric']:.2f} (pass >= {t['min_rubric']}, min n {t['min_n']})",
        "dimensions: " + ", ".join(f"{d} {v:.2f}" for d, v in rep["dims"].items()),
        "failed dimensions: " + (", ".join(rep["failed_dims"]) or "none"),
        f"unparseable judge replies: identify {rep['unparseable']['identify']}, score {rep['unparseable']['score']}",
        "",
        "| group | n | id rate | rubric |",
        "| ----- | - | ------- | ------ |",
    ]
    for kind in ("by_band", "by_channel"):
        for g, v in rep[kind].items():
            lines.append(f"| {kind[3:]}: {g} | {v['n']} | {v['id_rate']:.2f} | {v['mean_rubric']:.2f} |")
    lines += ["", "worst items (ids; text stays in items.jsonl): " + ", ".join(rep["worst"])]
    lines += ["models: " + ", ".join(f"{k} {v}" for k, v in rep["models"].items()) + f" (runner {rep['runner']})"]
    if rep.get("test_runs"):
        lines.append(f"test runs: {rep['test_runs']}" + (f" (rerun: {rep['rerun_reason']})" if rep.get("rerun_reason") else ""))
    lines += [f"warning: {w}" for w in rep["warnings"]]
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["run"])
    m.add_state_args(p)
    p.add_argument("--slice", choices=["dev", "test"], required=True)
    p.add_argument("--runner", default="claude", help="claude, stub, or cmd:'<command>'")
    p.add_argument("--stub-script", type=Path, help="scripted verdicts for --runner stub")
    p.add_argument("--seed", type=int, default=1337)
    p.add_argument("--extract-model", default=m.ROLE_TIERS["extract"], help="tier or model")
    p.add_argument("--generator-model", default=m.ROLE_TIERS["generate"], help="tier or model")
    p.add_argument("--judge-model", default=m.ROLE_TIERS["judge"], help="tier or model")
    p.add_argument("--exemplars", type=int, default=4, help="TRAIN exemplars shown to the judge")
    p.add_argument("--rerun-test", metavar="REASON", help="run the sealed test slice again, recording why")
    p.add_argument("--max-id-rate", type=float, default=m.THRESHOLDS["max_id_rate"])
    p.add_argument("--min-rubric", type=float, default=m.THRESHOLDS["min_rubric"])
    p.add_argument("--min-n", type=int, default=m.THRESHOLDS["min_n"])
    p.add_argument("--dim-floor", type=float, default=m.THRESHOLDS["dim_floor"])
    a = p.parse_args()
    d = m.state_dir(a)
    m.guard(d, a.allow_git_worktree)
    manifest, train, dev, test = m.load_split(d)
    prof_path = m.require(d / "profile.md", "profile.py skeleton")
    profile = prof_path.read_text(encoding="utf-8")
    errs = m.validate_profile(d, profile)
    if errs:
        raise m.Fail("profile invalid, fix it first:\n" + "\n".join(errs))

    rounds = d / "rounds"
    done = sorted(rounds.glob(f"{a.slice}-*")) if rounds.is_dir() else []
    rnd = len(done) + 1
    sealed = d / "split" / "test.sealed"
    seal = {}
    if a.slice == "dev":
        if not dev:
            raise m.Fail("no dev slice (corpus under the dev minimum): skip revision and run --slice test once")
        if rnd > MAX_DEV_ROUNDS:
            raise m.Fail(f"dev revision is capped at {MAX_DEV_ROUNDS} rounds; run --slice test now")
        items_in = dev
    else:
        if sealed.exists():
            seal = json.loads(sealed.read_text(encoding="utf-8") or "{}")
            if not a.rerun_test:
                raise m.Fail("the test slice was already used; pass --rerun-test REASON to run it again (it overfits)")
        items_in = test
    if not items_in:
        raise m.Fail(f"the {a.slice} slice is empty")

    env_models = {role: m.resolve_model(getattr(a, flag)) for role, flag in
                  (("extract", "extract_model"), ("generate", "generator_model"), ("judge", "judge_model"))}
    models = {role: mt[0] for role, mt in env_models.items()}
    warnings = []
    if env_models["judge"][1] != "reasoning":
        warnings.append(f"judge model {models['judge']} is not the reasoning tier: the verdict is weaker")

    prof_hash = hashlib.sha256(profile.encode("utf-8")).hexdigest()[:16]
    if a.slice == "test":
        runs = seal.get("runs", []) + [{"round": rnd, "profile": prof_hash, "reason": a.rerun_test,
                                         "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}]
        m.write_json(sealed, {"runs": runs})

    runner = m.make_runner(a.runner, a.stub_script)
    items = [run_item(runner, models, it, profile, train, a.seed, rnd, a.exemplars) for it in items_in]
    th = {"max_id_rate": a.max_id_rate, "min_rubric": a.min_rubric, "min_n": a.min_n, "dim_floor": a.dim_floor}
    rep = m.summarize(items, th)
    rep["warnings"] = warnings + rep["warnings"]
    rep.update(persona=a.persona or d.name, slice=a.slice, round=rnd, seed=a.seed, runner=a.runner,
               models=models, profile_hash=prof_hash, corpus_hash=manifest["corpus_hash"])
    if a.slice == "test":
        rep.update(test_runs=rnd, rerun_reason=a.rerun_test)
    out = rounds / f"{a.slice}-{rnd}"
    m.write_jsonl(out / "items.jsonl", items)
    m.write_json(out / "report.json", rep)
    md = report_md(rep)
    m.write_text(out / "report.md", md)
    if a.slice == "dev":
        m.write_json(out / "feedback.json",
                     feedback(rep, items, [t["text"] for t in dev + test], a.dim_floor))
    print(md, end="")
    print(f"\nwritten to {out}" + (" (feedback.json: the only file revision may read)" if a.slice == "dev" else ""))
    return 0


if __name__ == "__main__":
    m.main_wrapper(main)
