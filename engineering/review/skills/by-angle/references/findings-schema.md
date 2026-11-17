# Findings schema

Each reviewer returns a JSON array and nothing else. An empty array means no findings.

```json
[
  {
    "angle": "reuse | simplification | efficiency | altitude | comments | staleness",
    "severity": "blocker | major | minor | nit",
    "file": "path/from/repo/root",
    "line": 42,
    "claim": "One sentence: what is wrong.",
    "evidence": "Proof in one of the three forms below.",
    "status": "proven | unverified",
    "suggested_fix": "Concrete replacement or approach. Never applied by the reviewer.",
    "confidence": 0.0
  }
]
```

Fields:

- `severity`: `blocker` breaks the spec or correctness; `major` is a clear defect in the angle;
  `minor` is worth fixing if cheap; `nit` is optional.
- `line`: first affected line; use `null` for a finding about a whole file or the diff.
- `confidence`: 0 to 1. Default low. A claim the reviewer could not check against the code scores
  under 0.5.
- `evidence` and `status`: see the evidence rule below. Both are required.

## Evidence rule

A finding must carry tangible proof in one of three forms:

1. **Failing test.** A test that fails on the current revision. Give its path and the failing output.
2. **Reproduction command.** A read-only command and its output that show the defect.
3. **Cited `file:line` plus reasoning chain.** The exact line, and the steps from that line to the
   wrong result (input or state, each step, the wrong result).

A finding with proof sets `status: "proven"`. A finding with none of the three sets
`status: "unverified"`. These do not count as proof:

- "It looks wrong."
- "I read it and believe so."
- A file with no line, or a line with no reasoning chain.
- A suspicion, a pattern match, or a tool warning that nobody checked.

Report an `unverified` finding; do not drop it. It cannot block a merge, and it is not counted as a
defect. To promote it, add proof and set `status: "proven"`. The orchestrator checks the cited code
of each `proven` `blocker` before acting.

Example, proven (cited line plus reasoning chain):

```json
{
  "angle": "efficiency",
  "severity": "major",
  "file": "src/sync.py",
  "line": 88,
  "claim": "Each item triggers a full table scan.",
  "evidence": "src/sync.py:88 calls find_all() inside the loop at line 85; find_all() at db.py:31 runs SELECT * with no filter. N items give N full scans.",
  "status": "proven",
  "suggested_fix": "Load the table once before the loop and index it by id.",
  "confidence": 0.9
}
```

Example, unverified (no proof):

```json
{
  "angle": "altitude",
  "severity": "minor",
  "file": "src/api.py",
  "line": null,
  "claim": "Retry policy may belong in the client layer.",
  "evidence": "Read the module; I believe the policy is duplicated. No test or command run.",
  "status": "unverified",
  "suggested_fix": "Move the policy into the client.",
  "confidence": 0.3
}
```

## Triage record

After merging, the orchestrator keeps one table per block so a fresh session can resume:

| id  | angle | severity | file:line | claim | decision (fix / defer / reject) | reason |
| --- | ----- | -------- | --------- | ----- | ------------------------------- | ------ |

A `reject` states why the finding is wrong, not only that it was skipped.
