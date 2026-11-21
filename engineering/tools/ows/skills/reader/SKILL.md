---
name: reader
description: >-
  Read and validate OWS workflow files (Serverless Workflow DSL 1.1.0) that carry `metadata.org`
  governance: list the tasks with their kinds, roles, acceptance items and metrics, list the floors a run
  may not skip, and check a workflow against its metric catalog and manifest. Use for "validate this OWS
  workflow", "list the tasks and floors of a workflow file", "why does this workflow fail validation", or
  before running or reviewing a workflow file. Not for authoring or changing policy, running a workflow,
  or plain Serverless Workflow files without `metadata.org`.
---

# OWS reader

Read-only. It never edits a file and never runs a task. Standard library Python 3.13 or newer; YAML needs PyYAML
(`uv run --with pyyaml`), or use the `.json` form.

## Commands

```bash
S=<this skill>/scripts
python3 $S/ows.py tasks WORKFLOW [--json]
python3 $S/ows.py floors WORKFLOW [--manifest MANIFEST] [--json]
python3 $S/ows.py validate --catalog METRICS [--catalog MORE] --manifest MANIFEST WORKFLOW... [--json]
```

- `tasks`: every task in pre-order. Text: `key<TAB>kind[<TAB>floor]`. JSON rows add `by`, `role`, `brief`,
  `acceptance`, `metrics` and `calls`.
- `floors`: the floor tasks. With `--manifest`, a call to a workflow whose manifest entry lists floors counts too.
- `validate`: prints `ERROR: <file>: <location>: <message>` per error; silent when valid. `--json` prints
  `{"errors": [...]}`.
- Exit 0 valid or listed, 1 invalid or a file that does not load, 2 usage error.

The manifest and the catalog have their own validators:
`python3 $S/ows/validate_manifest.py --root ORG_ROOT --catalog METRICS MANIFEST` and
`python3 $S/ows/validate_catalog.py --root ORG_ROOT METRICS...`.

## Library

```python
import sys; sys.path.insert(0, "<this skill>/scripts")
import ows
doc = ows.load("workflow.yaml")
ows.tasks(doc); ows.floors(doc, manifest); ows.validate(doc, catalog, manifest)
```

`validate` never raises and returns the error lines; `load` raises `ows.LoadError` or `ows.UsageError`.

## Reading an error

The location is the task path (`build/units/implement`), then the key. Look the rule up in
[references/format.md](references/format.md), which lists every rule the validators enforce. Fix the
workflow, not the validator: a rule exists because a run depends on it.
