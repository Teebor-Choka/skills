# Check scripts

A check is code that judges one acceptance item and returns pass or fail (spec 6.1). The runtime runs
`checks/<name>.py <full task key>`.

## Contract

- The runtime writes the evidence file from `by: code` step results only, never from agent output. It sets
  `ORG_EVIDENCE` (absolute path), `ORG_KEY` (the full execution key) and `ORG_RUN` (the run id). The key also
  arrives as `argv[1]`.
- Evidence file: `{"run": <run id>, "key": <full key>, "steps": {<relative key>: {"exit": <int>, "stdout": <str>}}}`.
- A check reads one step. If the task is itself a code step, it reads that step. Otherwise it reads the code step
  named `<relative key>-evidence`. The stdout of that step is a JSON object; the tables below list its fields.
  A step with a non-zero exit fails the check.
- Exit 0 is pass. Exit 1 is fail, with reasons on stderr. Exit 2 means the evidence is missing or unreadable, or
  its `key` differs from `ORG_KEY` or its `run` differs from `ORG_RUN`; the runtime counts exit 2 as fail.
- `every-proposal-is-within-its-rung` also reads `ORG_ALLOWED_RUNGS` (comma-separated rungs the runtime allows).
  It is never read from evidence. A missing or empty value fails.
- `_lib.py` holds the shared loading and binding code. Every file in this directory is frozen (spec section 10):
  only the owner changes it.

Trust boundary: a check on a model step is only as strong as the code step that builds its evidence. A step that
copies agent text into stdout makes the check judge the agent's own claim.

## Evidence fields per check

Source step: the task itself (self) or `<relative key>-evidence` (sibling).

| Check                                                | Source step | Fields in stdout                                      |
| ---------------------------------------------------- | ----------- | ----------------------------------------------------- |
| `spec-check`                                         | sibling     | `item`                                                |
| `spec-coverage`                                      | sibling     | `item`, `spec_criteria_ids`, `tests`                  |
| `every-acceptance-test-fails-on-an-assertion`        | self        | `runs`, `expected_tests`                              |
| `red-evidence`                                       | sibling     | `runs`                                                |
| `new-test-fails-on-an-assertion-not-a-compile-error` | self        | `runs`                                                |
| `green-evidence`                                     | sibling     | `suite`, `tests_edited`                               |
| `suite-green-and-no-test-edited`                     | self        | `suite`, `tests_edited`                               |
| `suite-still-green-and-no-test-edited`               | sibling     | `suite`, `tests_edited`                               |
| `write-sets-are-disjoint`                            | sibling     | `units`, `item_criteria_ids`, `acceptance_test_paths` |
| `unit-verdict-is-pass`                               | self        | none (the call step's exit 0 is the verdict)          |
| `acceptance-suite-green`                             | self        | `suite`, `tests_edited`, `expected_count`             |
| `checks-green-and-gate-approved`                     | self        | `head`, `ci`, `gate`                                  |
| `report-has-every-required-section`                  | self        | `report`                                              |
| `every-proposal-is-within-its-rung`                  | sibling     | `proposals`                                           |

Field shapes:

- `item`: the object of `schemas/org/item.json`. `spec_criteria_ids`: the criterion ids of the `spec` step output.
- `tests`: list of `{id, criteria: [criterion id]}`. `runs`: list of `{test, outcome}`, outcome one of
  `assertion`, `compile-error`, `import-error`, `timeout`, `pass`. `expected_tests`: test ids from `spec-coverage`.
- `suite`: `{passed, failed}`, integers. `tests_edited`: list of paths, empty when none. `expected_count`: the
  suite size recorded at red; a smaller `passed + failed` fails.
- `units`: the cut of `schemas/org/units.json`. Units are built one after another (a sequential `for`).
  `acceptance_test_paths`: paths no unit may write.
- `head`: the change's head commit. `ci`: `{state, head}`. `gate`: `{decision, signature_verified, signer_role, head}`,
  set by the runtime from the verified decision event.
- `report`: the report text. Required sections, each with a non-empty body: Summary, Acceptance, Tests, Defects,
  Metrics, Not verified. A heading inside a code fence does not count.
- `proposals`: list of `{id, base, new}`. `base` and `new` map an org-root path to file text or null. The check
  classifies them with `check_change` from `scripts/check_change.py`. A proposal declares no rung.

## Code steps still to build (U14)

The workflows name `bin/tdd-evidence` and `bin/merge-change`; both are stubs that exit 3. The sibling
`<task>-evidence` steps (`spec`, `acceptance-tests`, `cut`, `cycle/red`, `cycle/green`, `cycle/refactor`,
`propose`) do not exist yet in the workflows. Until U14 adds them, the matching checks exit 2.

## Defaults taken by the orchestrator

The owner may change these. They are not owner decisions.

- `manifest.json` follows the spec 8.5 illustration: the role ladder, the `escalates-to` chain and the vetoes.
- Targets are the Appendix A fixture values: `spec-rework` at most 1 per item, `red-for-wrong-reason` at most 0 per
  unit, `acceptance-coverage` at least 1.0.
- `improve.yaml` is a one-step placeholder for the improvement workflow.
