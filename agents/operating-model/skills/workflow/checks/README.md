# Check scripts

A check is code that judges one acceptance item and returns pass or fail (spec 6.1). The runtime runs
`checks/<name>.py <full task key>`.

## Contract

- The runtime writes the evidence file itself. It never copies anything an agent wrote into `steps` or
  `decisions`: those hold results of `by: code` steps and verified decision events, never from agent output.
  Agent output appears only in `output` and `outputs`, which a check treats as claims.
- Environment: `ORG_EVIDENCE` (absolute path), `ORG_KEY` (full execution key), `ORG_RUN` (run id).
  `ORG_ALLOWED_RUNGS` (comma-separated rungs of the task's role) is set for every check; the rung check reads it.
  It is never read from evidence. A missing, empty or unknown value fails.
- Evidence file: `run`, `key`, `output` (the checked task's own entry), `steps` and `outputs` (entries by relative
  key), `decisions` (verified decision events by gate key) and `change` (`head`, `worktree`).
  An entry is `{"exit": int, "stdout": str}`. A check parses `stdout` as one JSON object.
- Exit 0 is pass. Exit 1 is fail, with reasons on stderr; a checked task that ended with a non-zero exit fails.
  Exit 2 means the evidence is missing or unreadable, or its `key` differs from `ORG_KEY` (also `argv[1]`) or its
  `run` differs from `ORG_RUN`; the runtime counts exit 2 as fail.
- Every file in this directory is frozen (spec section 10): only the owner changes it. `_lib.py` holds the shared
  loading and binding code.

## Classes

The manifest `checks` map declares each check as `shape` or `fact`.

- shape: validates `output` (and may read `outputs` and `change`). It never trusts what it reads, so it may sit on
  a model step.
- fact: establishes a fact from the checked code step's own `output`, from `steps` or from `decisions`. It sits
  only on a `by: code` task.

Trust boundary: a fact check is as strong as the code step whose result it reads. A check on a model step sees only
claims, and `steps` holds code steps that ended before the checked task started.

## What each check reads

| Check                                                | Class | Task                                                       | Reads                                                                                                                                                                                                 |
| ---------------------------------------------------- | ----- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `spec-check`                                         | shape | `spec`                                                     | `output.title`, `output.criteria`, `output.valid_inputs`, `output.expected_outputs`, `output.failure_definition`, `output.performance`, `output.dependencies`, `output.out_of_scope`, `output.ai_gap` |
| `spec-coverage`                                      | shape | `acceptance-tests`                                         | `output.tests`, `outputs.spec`                                                                                                                                                                        |
| `every-acceptance-test-fails-on-an-assertion`        | fact  | `acceptance-red`                                           | `output.runs`, `outputs.acceptance-tests` (the claimed test ids, compared by id with the real runs)                                                                                                   |
| `red-evidence`                                       | fact  | `cycle/red-evidence`                                       | `output.runs`                                                                                                                                                                                         |
| `new-test-fails-on-an-assertion-not-a-compile-error` | fact  | `cycle/red-evidence`                                       | `output.runs`                                                                                                                                                                                         |
| `green-evidence`                                     | fact  | `cycle/green-evidence`                                     | `output.suite`, `output.tests_edited`                                                                                                                                                                 |
| `suite-green-and-no-test-edited`                     | fact  | `cycle/green-evidence`                                     | `output.suite`, `output.tests_edited`                                                                                                                                                                 |
| `suite-still-green-and-no-test-edited`               | fact  | `cycle/refactor-evidence`                                  | `output.suite`, `output.tests_edited`                                                                                                                                                                 |
| `write-sets-are-disjoint`                            | shape | `cut`                                                      | `output.units`, `outputs.spec`, `outputs.acceptance-tests`                                                                                                                                            |
| `unit-verdict-is-pass`                               | shape | `build/units/tdd`                                          | `output.exit` (a call entry is exit 0 when the subflow ended in success)                                                                                                                              |
| `acceptance-suite-green`                             | fact  | `build/acceptance-run`                                     | `output.suite`, `output.tests_edited`, `steps.acceptance-red` (the suite may not shrink below the tests that ran red)                                                                                 |
| `checks-green-and-gate-approved`                     | fact  | `merge`                                                    | `output.ci`, `decisions.merge-gate`, `change.head`                                                                                                                                                    |
| `report-has-every-required-section`                  | shape | `report`                                                   | `output.report`                                                                                                                                                                                       |
| `every-proposal-is-within-its-rung`                  | shape | `improve`                                                  | `change.head`, `change.worktree`, `ORG_ALLOWED_RUNGS`                                                                                                                                                 |
| `feasibility-holds`                                  | fact  | `spec-cycle/design-cycle/feasibility`                      | `output.feasible`, `output.failed`, `output.reasons`                                                                                                                                                  |
| `deploy-verified`                                    | fact  | `verify`                                                   | `output.verified`, `output.exit`                                                                                                                                                                      |
| `failing-test-committed`                             | fact  | `reproduce-evidence`                                       | `output.runs`, `output.committed`, `output.files`, `output.uncommitted`, `output.base`, `output.head`                                                                                                 |
| `phase-acceptance-green`                             | fact  | `spec-cycle/design-cycle/system-run` (also on `layer-run`) | `output.suite`, `output.tests_edited`, `output.layer_fault` or `output.system_fault` (must be `none`), `output.expected_count`                                                                        |
| `event-names-its-subject`                            | shape | `reflect`, `bug-report`                                    | `output.run`, `output.subject` (the emitted event's data)                                                                                                                                             |

Field shapes:

- `output` of `spec` is the object of `schemas/org/item.json`. `output` of `cut` is `schemas/org/units.json`.
- `outputs.acceptance-tests` is `{tests: [{id, criteria: [criterion id], path}]}`. `path` is a test file no unit
  may write.
- `runs`: list of `{test, outcome}`, outcome one of `assertion`, `compile-error`, `import-error`, `timeout`,
  `pass`. `suite`: `{passed, failed}`, integers. `tests_edited`: list of paths, empty when none.
- `ci`: `{state, head}`. `decisions.merge-gate` carries `decision`, `signer_role`, `signature_verified`, `run`,
  `task` and `head`; the runtime builds it from the verified decision event.
- `report`: the report text. Required sections, each with a non-empty body: Summary, Acceptance, Tests, Defects,
  Metrics, Not verified. A heading inside a code fence (backticks or tildes) does not count; `n/a` is not a body.
- `write-sets-are-disjoint`: units are built one after another (a sequential `for`), yet write-sets must stay
  disjoint. A write-set may not cover `checks/`, `criteria/`, `bin/`, `collectors/`, a manifest or a metric
  catalog file (any case, json or yaml), or an acceptance test path.
- Rung check: the check derives `base` (files at `change.head`) and `new` (files in `change.worktree`) itself and
  classifies the difference with `check_change` from `scripts/check_change.py`. An agent writes files only. An
  empty change, an unusable `change` or a missing `check_change` fails.

## Task keys inside loops

The checks name a task by its own name (`spec`, `acceptance-tests`, `acceptance-red`, `merge-gate`). In
`sw-development` several sit inside rework loops, so their relative key is a path such as `spec-cycle/spec`.
`_lib.py` finds an entry by its exact key, else by the one key that ends in the name. Two matches exit 2.

## Code steps (U14)

`bin/tdd-evidence` prints the facts the fact checks read. Its header lists the phases. `bin/merge-change`
prints `head`, `ci` (`{state, head}`) and `merged`. Red outcomes are `assertion`, `compile-error`,
`import-error`, `timeout`, `pass`, and `error` (any other exception, such as a `NameError` in the test body).
`layer_fault` is `none`, `unit` or `design`; `system_fault` is `none`, `design` or `spec`. Both come from the
faults file the architect writes, never from agent output: the keys of the file are also the tests that step
runs. Acceptance tests are claimed by test id: the ids in the `acceptance-tests` output are pytest node ids.

## Environment of the bin programs

The stack document's `bin-env` (spec 8.6) lists these per workflow; the runtime forwards exactly those names and nothing else. `TDD_TEST_CMD` and `TDD_VERIFY_CMD` take a JSON list of strings or a plain command line.

| Variable                    | Read by                        | Meaning                                                                                     | Default                       |
| --------------------------- | ------------------------------ | ------------------------------------------------------------------------------------------- | ----------------------------- |
| `TDD_WORKTREE`              | `tdd-evidence`, `merge-change` | The project working tree (a git repository)                                                 | current directory             |
| `TDD_BASE`                  | `tdd-evidence`                 | The commit the change started from; `bug red` needs it                                      | `HEAD`                        |
| `TDD_TEST_CMD`              | `tdd-evidence`                 | JSON argv or command line of the test command; it prints pytest `-rA` summary lines         | pytest                        |
| `TDD_TIMEOUT`               | `tdd-evidence`                 | Seconds for one test run or the verification command                                        | 600                           |
| `TDD_FAULTS`                | `tdd-evidence`                 | Faults file                                                                                 | `<worktree>/.org/faults.json` |
| `TDD_VERIFY_CMD`            | `tdd-evidence`                 | JSON argv or command line of the deploy verification command; absent fails the verification | none                          |
| `TDD_CHANGE_BRANCH`         | `merge-change`                 | The branch to fast-forward into the target branch                                           | none (required)               |
| `POLICY_VCS_DEFAULT_BRANCH` | `merge-change`                 | Resolves the policy name `vcs.default-branch` given to `--into`                             | none (required)               |

The names are not a manifest key (spec 8.1 is a closed set); the stack carries them (spec 8.6).

## Defaults taken by the orchestrator

The owner may change these. They are not owner decisions.

- `manifest.json` follows the spec 8.5 illustration: the role ladder, the `escalates-to` chain and the vetoes.
  `improver` declares `rungs: [free, ordinary]`, the default.
- Targets are the Appendix A fixture values: `spec-rework` at most 1 per item, `red-for-wrong-reason` at most 0 per
  unit, `acceptance-coverage` at least 1.0.
- `sample: 0.2` and `judge: reviewer` on the `red`, `green` and `refactor` rubric items.
- `improve.yaml` is a one-step placeholder for the improvement workflow.
