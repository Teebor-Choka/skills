#!/usr/bin/env python3
"""Split <state>/corpus.jsonl into train, dev and test, seeded and stratified, with no leakage.

Near-duplicate clusters move as one unit; a held-out cluster keeps only its first member and the
rest are dropped, never put in train. Test size: max(round(N*test_frac), min(min_test, N*0.4)).
A dev slice exists from --dev-min clusters up.

  split.py --persona NAME [--seed 1337] [--test-frac 0.2] [--dev-frac 0.1] [--min-test 20] [--force]
"""

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mimiclib as m  # noqa: E402


def allocate(strata, total):
    """Largest remainder: {key: [clusters]} -> {key: count}, summing to total."""
    n = sum(len(v) for v in strata.values())
    if n == 0 or total == 0:
        return {k: 0 for k in strata}
    exact = {k: total * len(v) / n for k, v in strata.items()}
    out = {k: int(x) for k, x in exact.items()}
    rest = total - sum(out.values())
    for k in sorted(strata, key=lambda k: (-(exact[k] - out[k]), str(k)))[:rest]:
        out[k] += 1
    return out


def cover_bands(strata, quota):
    """A band with 2+ clusters but no slot takes one from the stratum holding the most."""
    for b in sorted({k[0] for k in strata}):
        keys = [k for k in strata if k[0] == b]
        if sum(len(strata[k]) for k in keys) >= 2 and sum(quota[k] for k in keys) == 0:
            donor = max(quota, key=lambda k: (quota[k], str(k)))
            if quota[donor] > 0:
                quota[donor] -= 1
                quota[max(keys, key=lambda k: (len(strata[k]), str(k)))] += 1
    return quota


def take(clusters, total, rng):
    """Pick `total` clusters stratified by (band, channel, audience) of their first member."""
    strata = {}
    for c in clusters:
        head = c[0]
        strata.setdefault((head["band"], head["channel"], head["audience"]), []).append(c)
    for k in strata:
        strata[k].sort(key=lambda c: c[0]["id"])
        rng.shuffle(strata[k])
    quota = cover_bands(strata, allocate(strata, total))
    picked = []
    for k in sorted(strata, key=str):
        picked += strata[k][:quota[k]]
    chosen = {id(c) for c in picked}
    return picked, [c for c in clusters if id(c) not in chosen]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    m.add_state_args(p)
    p.add_argument("--seed", type=int, default=1337)
    p.add_argument("--test-frac", type=float, default=0.2)
    p.add_argument("--dev-frac", type=float, default=0.1)
    p.add_argument("--min-test", type=int, default=20)
    p.add_argument("--dev-min", type=int, default=100, help="clusters needed before a dev slice exists")
    p.add_argument("--near-dup", type=float, default=m.NEAR_DUP)
    p.add_argument("--force", action="store_true", help="re-split even after a test run (overfits)")
    a = p.parse_args()
    d = m.state_dir(a)
    m.guard(d, a.allow_git_worktree)
    corpus_path = m.require(d / "corpus.jsonl", "ingest.py")
    sd = d / "split"
    if (sd / "test.sealed").exists() and not a.force:
        raise m.Fail("the test slice was already used; re-splitting now leaks it into training. Pass --force to start over.")
    corpus = m.read_jsonl(corpus_path)
    if not corpus:
        raise m.Fail("corpus.jsonl is empty")

    roots = m.near_dup_clusters([r["text"] for r in corpus], a.near_dup)
    groups = {}
    for r, root in zip(corpus, roots):
        groups.setdefault(root, []).append(r)
    clusters = [groups[k] for k in sorted(groups)]
    n = len(clusters)
    n_test = max(round(n * a.test_frac), min(a.min_test, int(n * 0.4)))
    n_dev = round(n * a.dev_frac) if n >= a.dev_min else 0

    rng = random.Random(a.seed)
    clusters.sort(key=lambda c: c[0]["id"])
    test_c, rest = take(clusters, n_test, rng)
    dev_c, train_c = take(rest, n_dev, rng)
    train = [r for c in train_c for r in c]
    dev = [c[0] for c in dev_c]
    test = [c[0] for c in test_c]
    dropped = sum(len(c) - 1 for c in test_c + dev_c)

    max_sim = 0.0
    train_keys = [(t, m.canonical(t["text"]), m.grams(t["text"])) for t in train]
    for h in dev + test:
        hc, hg = m.canonical(h["text"]), m.grams(h["text"])
        for t, tc, tg in train_keys:
            s = 1.0 if hc == tc else m.jaccard(hg, tg)
            max_sim = max(max_sim, s)
            if s >= a.near_dup:
                raise m.Fail(f"leak: held-out {h['id']} and train {t['id']} are near duplicates ({s:.2f})")

    order = {r["id"]: i for i, r in enumerate(corpus)}
    for rows in (train, dev, test):
        rows.sort(key=lambda r: order[r["id"]])
    m.write_jsonl(sd / "train.jsonl", train)
    m.write_jsonl(sd / "dev.jsonl", dev)
    m.write_jsonl(sd / "test.jsonl", test)
    (sd / "test.sealed").unlink(missing_ok=True)
    strata = {}
    for name, rows in (("train", train), ("dev", dev), ("test", test)):
        for r in rows:
            key = f"{r['band']}/{r['channel']}/{r['audience']}"
            strata.setdefault(key, {"train": 0, "dev": 0, "test": 0})[name] += 1
    manifest = {
        "corpus_hash": hashlib.sha256(corpus_path.read_bytes()).hexdigest()[:16],
        "seed": a.seed, "clusters": n, "messages": len(corpus),
        "counts": {"train": len(train), "dev": len(dev), "test": len(test)},
        "dropped_near_duplicates": dropped, "max_cross_similarity": round(max_sim, 4),
        "near_dup_threshold": a.near_dup, "strata": strata,
    }
    m.write_json(sd / "manifest.json", manifest)
    print(json.dumps({k: manifest[k] for k in ("counts", "clusters", "dropped_near_duplicates", "max_cross_similarity")}))
    if n_dev == 0:
        print(f"no dev slice ({n} clusters < {a.dev_min}): build the profile once, then run the test.")
    if len(test) < a.min_test:
        print(f"only {len(test)} test items: the verdict will be INCONCLUSIVE (needs {a.min_test}).")


if __name__ == "__main__":
    m.main_wrapper(main)
