# The OWS `metadata.org` format

An OWS workflow is a [Serverless Workflow DSL 1.1.0](https://github.com/serverlessworkflow/specification/blob/v1.1.0/dsl.md)
document. This reader accepts a subset of the DSL and adds governance under `metadata.org`. Every rule
below is one the validators enforce; the message each one prints starts with the location in the left
column of the error line (`<location>: <message>`). The command line prefixes `ERROR: <file>: `.

Three files take part:

- the **workflow** (`validate_org`),
- the **metric catalog**, one or more files merged into one map (`validate_catalog`),
- the **manifest**, which lists roles, workflows, checks, targets and vetoes (`validate_manifest`).

## Loading

- `.json`, `.yaml` or `.yml`. Any other extension is a usage error (exit 2). YAML needs PyYAML.
- Duplicate keys, `NaN`, `Infinity`, a float that overflows and an integer longer than 4300 digits are refused.
- JSON nested deeper than 512 brackets is refused before parsing.
- YAML: aliases (`*x`) and merge keys (`<<`) are refused. Only `true`, `True`, `TRUE`, `false`, `False`
  and `FALSE` are booleans; `on`, `yes`, `no` and dates stay strings.
- After loading, a document holds only string keys and JSON values, finite numbers, at most 128 levels,
  no value that contains itself, and at most 1,000,000 values.

## Workflow document

| Key                                       | Rule                                                                                           |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------- |
| top level                                 | only `document`, `input`, `output`, `timeout`, `schedule`, `evaluate`, `do`; `use` is refused  |
| `document.name`                           | a key of `manifest.workflows`                                                                  |
| `document.namespace`                      | equals `manifest.namespace`                                                                    |
| `document.metadata`                       | a map whose only namespace is `org`                                                            |
| `document.metadata.org`                   | only `policy`: a list of unique dotted names such as `vcs.remote`                              |
| `schedule`                                | `every`, `cron` and `after` are refused; each `schedule.on` filter needs a literal `with.type` |
| `evaluate`                                | `language: jq` and `mode: strict` only                                                         |
| `timeout`                                 | an inline map with `after`; a named timeout (`use`) is refused                                 |
| `input`, `output` (and a task's `export`) | a `schema.resource.endpoint` is a relative path under `schemas/` ending `.json`                |

A **duration** is a literal map of `days`, `hours`, `minutes`, `seconds`, `milliseconds` with
non-negative integers, greater than zero and at most 30 days.

## Tasks

Task names are kebab-case and unique in the workflow. A task's key in an error is its path:
`build/units/implement`. Lists nest at most 16 deep, and a workflow holds at most 10000 tasks.

The **kind** comes from the task key and is never declared:

| Task key                   | Kind         |
| -------------------------- | ------------ |
| `run.shell`                | `step`       |
| `run.workflow`             | `call`       |
| `listen`                   | `gate`       |
| `emit`                     | `emit`       |
| `raise`                    | `escalation` |
| `do`, `for`, `try`, `fork` | `container`  |
| `switch`                   | `branch`     |
| `set`                      | `assign`     |
| `wait`                     | `wait`       |

`run.container`, `run.script` and `call` (HTTP, gRPC and the rest) are refused.

### `metadata.org` per kind

| Kind                                    | Required                              | Also allowed                |
| --------------------------------------- | ------------------------------------- | --------------------------- |
| `step`                                  | `by`, `role`, `metrics`, `acceptance` | `brief`, `floor`, `network` |
| `call`, `emit`                          | `by`, `role`, `metrics`, `acceptance` | `brief`, `floor`            |
| `gate`                                  | `by`, `role`, `metrics`, `acceptance` | `brief`, `floor`, `signer`  |
| `escalation`                            | `to`                                  | `metrics`                   |
| `container`, `branch`, `assign`, `wait` |                                       | `metrics`                   |

- `by`: `code`, `human` or `model`. Role `owner` requires `by: human`.
- `role`, `to`, `signer`: a role in `manifest.roles`, or `owner`.
- `metrics`: a non-empty list of unique catalog metric names.
- `brief`: a relative path under `briefs/` ending `.md`.
- `network`: a dotted policy name such as `research.source-allowlist`.
- `floor`: `true` or `false`.
- The only namespace under a task's `metadata` is `org`.

### Acceptance items

`acceptance` is a non-empty list. Each item has exactly one of:

- `check: <name>`: a kebab-case name in `manifest.checks`. A `fact` check may sit only on a `by: code` task.
- `rubric: criteria/<file>.md` with `judge: <role>` and an optional `sample` in (0, 1]. A floor's rubric
  is judged every run, so a floor item has no `sample` below 1.
- `human: <text>`: a non-empty string, allowed only on a gate.

### Kind rules

- **step**: `run.shell.command` is a bare command name. Shells and wrappers (`sh`, `bash`, `env`, `sudo`,
  `xargs` and the like) are refused. A step that runs `agent-run` needs a `brief`, may not run as
  `owner`, sets no `environment`, `stdin` or `directory`, and takes only `--isolated`, once: the runtime
  sets `--role`, `--brief`, `--network` and `--input`.
- **call**: `run.workflow` names a workflow in the manifest's namespace, never itself.
- **gate**: needs an inline `timeout`; `foreach` is refused. A decision gate (role `owner`, a `signer`, or
  a `human` item) listens with `to.one` only, on a literal event type.
- **emit**: a literal event type that does not start with `org.owner-` or `org.task-` and is not a type
  a decision gate of the same workflow listens on.
- **escalation**: `raise.error` is written inline.
- **container**: a `for` with a `while` needs an inline `in` array. `for.each`, `for.at` and `catch.as`
  may not use a reserved variable name (`accepted`, `authorization`, `context`, `input`, `output`,
  `runtime`, `secrets`, `task`, `workflow`, `events`). `catch.retry` is inline, with
  `limit.attempt.count` from 1 to 100; `delay`, `limit.duration` and `limit.attempt.duration` are durations.

## Floors

A floor is a task the run may not skip: a leaf (`step`, `call`, `gate`, `emit`) with `floor: true`.
A call to a workflow whose manifest entry lists floors is held to the same rules.

- `manifest.workflows.<name>.floors` lists exactly the tasks with `floor: true`.
- A floor has no `if` and no `run.await: false`, and sits inside no task with `if`, `fork` or `try`.
- `then` is a string. `continue` is free. `end` (and `exit` at the top level) may not skip a later floor.
  `exit` may not skip a floor later in its list. A named target is a later task in the same list (a
  backward jump is an unbounded loop) and the jump may not skip a floor.

## Manifest

Keys: `owner`, `namespace`, `roles`, `workflows`, `vetoes`, `checks` (all required) and `targets`.

- `owner`: a non-empty string. `namespace`: the OWS namespace pattern.
- `roles.<kebab-name>`: `escalates-to` (required, a role or `owner`), `may-spawn` (roles below it on the
  ladder, or itself), `summary` (a string), `rungs` (a non-empty unique list of `free`, `ordinary`,
  `protected`; `frozen` cannot be granted). `owner` is reserved and never declared. Every chain reaches `owner`.
- `workflows.<kebab-name>`: `path` (under `workflows/`, ending `.yaml`, `.yml` or `.json`, a file under
  the root) and `floors` (a list of task names, possibly empty). The file's `document.name` equals the key.
  The start graph (calls, and emits of a type another workflow's `schedule.on` starts on) has no cycle.
  An emit of a type that a decision gate in another workflow listens on is refused.
- `checks.<kebab-name>`: `fact` or `shape`, with a file `checks/<name>.py`. Every `checks/*.py` that does
  not start with `_` is listed.
- `targets.<metric>`: a catalog metric with exactly one of `at-least`, `at-most` (a finite number) and an
  optional `per` of `item`, `run` or `unit`.
- `vetoes`: a non-empty list of non-empty strings.

## Metric catalog

A map of kebab-case metric names, unique across all catalog files. Each entry has exactly these keys:

| Key         | Rule                                                                |
| ----------- | ------------------------------------------------------------------- |
| `scope`     | `node`, `stage` or `process`                                        |
| `unit`      | a non-empty string                                                  |
| `better`    | `lower`, `higher` or `context`                                      |
| `formula`   | a non-empty string                                                  |
| `collector` | a file under the root: `collectors/<name>.py`                       |
| `reads`     | a non-empty list of unique source names (`run-ledger`, `item.json`) |

## Runtime expressions

`expr` evaluates the strict-mode `${ ... }` subset of jq: paths, bound variables, JSON and array literals,
comparisons, `and`, `or`, `X | not`, `X | length` and `+` on objects. Anything else is refused by name.
`$ENV`, `$secrets` and `$authorization` never resolve.
