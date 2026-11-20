---
name: workflow
description: >
  Check the governance metadata of an OWS workflow file (`metadata.org` on each task: who acts, role,
  metrics, acceptance items, floors) against the metric catalog and the manifest. Use when asked to
  write, change or validate an organization workflow, to add a task with its acceptance and metrics,
  or to find out why a workflow is refused. Not for the OWS schema check itself, and not for GitHub
  Actions workflow YAML.
license: MIT
compatibility: Python 3.10 or newer; PyYAML only to read YAML files
metadata:
  version: "0.1.0"
---

# workflow: validate `metadata.org`

A workflow is an OWS 1.1.0 document. Governance sits under `metadata.org` on each task. The kind of a
task comes from its OWS task key and is never declared. The rules are in the org-documents spec
(sections 3 to 7); this skill ships the checker for them.

## Run it

```
python3 scripts/validate_org.py --catalog metrics.json [--catalog more.json ...] \
    --manifest manifest.json workflows/sw-development.json
```

- Inputs are JSON. YAML needs PyYAML (`uv run --with pyyaml ...`); without it the command exits 2.
- A valid run prints nothing and exits 0. Each error is `ERROR: <file>: <task path>: <message>` on stderr, exit 1.
- Exit 2 is a usage error: bad arguments, an unknown file extension, YAML without PyYAML.
- Catalog files merge. A metric name in two files is an error with no file prefix.

From Python: `validate_org(doc, catalog, manifest) -> list[str]`. An empty list means valid. It never raises.

## What it checks

- Every nested task list: `do`, `for.do`, `fork.branches`, `try.try`, `try.catch.do`, to 16 lists deep.
- Leaf tasks (step, call, gate, emit) need `by`, `role`, non-empty `metrics` and non-empty `acceptance`.
  Containers carry none of `by`, `role`, `acceptance`. Escalations (`raise`) carry `to`.
- An acceptance item is exactly one of `check`, `rubric` with `judge`, `human` (gates only).
- Metrics must be in the catalog. Roles, judges and escalation targets must be in the manifest or `owner`.
- Floors both ways against `manifest.workflows.<name>.floors`; a floor may not sit under `if`, `fork` or `try`.
- Loops and retries are bounded, durations are inline literals, gates have an inline `timeout`.
- Task names are unique kebab-case. `then` may only jump forward and may not skip a floor.

It does not check that briefs, rubrics, check scripts or collectors exist, and it does not validate the
manifest or the catalog.

## Metrics at run time

The org runtime (`scripts/org_runtime.py`) computes metrics in-process with `scripts/metric_collectors.py`: a
registry with one collector per `reads` source (`run-ledger`, `session-record`). A catalog `collector` file is a
named shim that exits 3 on its own. Every result goes to the run ledger as an appended entry, never a rewrite:

- after each accepted node, a `metric` row per metric the task names;
- at run end, one `org.metric` entry per catalog metric;
- at a turn boundary (`OrgRuntime.turn_boundary()`), the export, one `org.metric` per metric, the reflection and
  `org.turn-complete`, in that order (spec 13.3). `compaction_allowed(turn)` reads the ledger.

Each row holds a `value`, a `reason` (for example `no collector for git-diff`) or an `error`, never a silent zero.
`metrics.runtime.json` adds run metrics (duration, model calls, cost, tokens, reruns, gate wait, session tool
calls). The entry shapes are in the org-documents spec, update 13.
