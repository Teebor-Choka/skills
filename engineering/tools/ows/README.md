# ows

Reader and validator for OWS workflow files: [Serverless Workflow DSL 1.1.0](https://github.com/serverlessworkflow/specification/blob/v1.1.0/dsl.md)
documents that carry governance under `metadata.org` (who runs each task, its acceptance items, metrics
and floors).

| Skill    | What it does                                                            |
| -------- | ----------------------------------------------------------------------- |
| `reader` | `ows.py validate \| tasks \| floors`, plus the importable `ows` library |

Standard library Python, 3.13 or newer. PyYAML is optional and only needed to read `.yaml` files.
The format rules are in [skills/reader/references/format.md](skills/reader/references/format.md).

Tests: `python3 -m pytest skills/reader/tests`.
