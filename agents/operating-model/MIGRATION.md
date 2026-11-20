# Migration to organization 2.0.0

The plugin `operating-model` is now `organization` (2.0.0). The directory stays `agents/operating-model/`.
The old procedure format (a stage graph in a markdown file, run by a reducer) is deleted. Its replacement is
an organization of workflows in the Open Workflow Specification, held by the `workflow` skill.

## Deleted skills

| Deleted                                                             | Replaced by                                                                                                                                    |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `procedure` (skill)                                                 | `workflow`                                                                                                                                     |
| `agents-dir` (skill: layout validator, resolver, iteration records) | `workflow` manifest and `validate_manifest.py`; run start is `org_runtime.py`; a change to the organization is classified by `check_change.py` |

## Deleted scripts

| Deleted script                                                            | Replaced by (in `workflow/scripts/`)                                                                                                       |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| the procedure validator (the `validate_*` script in `procedure/scripts/`) | `validate_org.py` (one workflow), `validate_manifest.py` (roles, workflows, floors), `validate_catalog.py` (metrics and the shared loader) |
| `runtime.py` (pure reducer over an event log)                             | `interpreter.py` (control flow)                                                                                                            |
| `executor.py` (drives the reducer)                                        | `org_runtime.py` (`OrgRuntime.run`, `resume`, `replay`)                                                                                    |
| `ledger.py` (hash-chained run log)                                        | `org_runtime.py` (`RunLedger`, HMAC chain with a head file)                                                                                |
| `conformance.py` (port contract tests)                                    | `op_conformance.py`                                                                                                                        |
| `check_translation.py` (prose-to-procedure coverage check)                | none; the prose is now the workflow's task briefs and criteria                                                                             |
| `agents-dir/scripts/agents_dir.py` (layout and change-record check)       | `validate_manifest.py` and `check_change.py`                                                                                               |
| `agents-dir/scripts/resolver.py` (project over user document resolution)  | none; the organization root is explicit                                                                                                    |

## Kept

`policy` is unchanged: `policy_loader.py` is still used by `project-docs` (components settings) and read by
`orchestrate` through the policy keys `work.tracker` and `work.isolation`.

## Other changes

- `project-docs`: `docs/process.md` is optional, has no `procedure` key and is no longer checked against
  `.agents/` files. The rules `process-doc-missing`, `process-procedure`, `process-procedure-missing` and
  `process-procedure-invalid`, and the `PROCEDURE_VALIDATOR` setting, are removed.
- A project that kept the old documents (old procedure files, the charter, iteration records) must move its
  process into workflows, or drop those files. `policy.md` stays valid.
