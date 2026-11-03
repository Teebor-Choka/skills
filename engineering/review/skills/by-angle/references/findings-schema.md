# Findings schema

Each reviewer returns a JSON array and nothing else. An empty array means no findings.

```json
[
  {
    "angle": "reuse | simplification | efficiency | altitude | comments",
    "severity": "blocker | major | minor | nit",
    "file": "path/from/repo/root",
    "line": 42,
    "claim": "One sentence: what is wrong.",
    "evidence": "Cited code, or output of a read-only command that shows it.",
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
- `evidence` is required. The orchestrator drops findings without it.

## Triage record

After merging, the orchestrator keeps one table per block so a fresh session can resume:

| id  | angle | severity | file:line | claim | decision (fix / defer / reject) | reason |
| --- | ----- | -------- | --------- | ----- | ------------------------------- | ------ |

A `reject` states why the finding is wrong, not only that it was skipped.
