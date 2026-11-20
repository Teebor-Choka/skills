# Status site reference

## Files

| File                     | Job                                                                                                                                                                                                                                               |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `assets/index.html`      | Page shell: sidebar and the scripts                                                                                                                                                                                                               |
| `assets/css/site.css`    | Tokens for light and dark (system, or `?theme=dark`, or the sidebar button), layout, graph node states. Color has three channels: segment hue for territory, state for a node's stroke and glyph (always with a shape), kind for operation shapes |
| `assets/js/graph.js`     | Layout (layered graph, workflow flow) and SVG drawing; no DOM, so node can test it                                                                                                                                                                |
| `assets/js/views.js`     | Routes, one render function per view, the goal of every segment, workflow, step and unit, the jump index, live state per node, feedback per ledger event                                                                                          |
| `assets/js/app.js`       | Router, data loading, 30 s refresh, live feed, moving tokens and pulses, path highlight, legend filters, folding groups, jump palette (`/` or Ctrl-K), drill-down motion, Escape goes up one level                                                |
| `assets/fonts/`          | Atkinson Hyperlegible Next and Mono (OFL 1.1, `OFL.txt`), copied from nixpkgs, 292 KB                                                                                                                                                             |
| `assets/org-layout.json` | Default segments, platform components (files in the org root), workflow descriptions, inferred edges                                                                                                                                              |
| `scripts/config.py`      | The source options every script shares, and the defaults                                                                                                                                                                                          |
| `scripts/orgdata.py`     | Readers for the org root, the layout and the work package                                                                                                                                                                                         |
| `scripts/gen.py`         | Writes `<data-dir>/data/*.json` and `data.js` (needs PyYAML)                                                                                                                                                                                      |
| `scripts/live.py`        | Reads run ledgers and dispatcher state into run state                                                                                                                                                                                             |
| `scripts/serve.py`       | Static files, `/data/*`, `/api/refresh`, `/api/live`, `/api/events`, `POST /api/ingest`                                                                                                                                                           |
| `scripts/ingest.py`      | The ingest log: validation, hash chain, append under a lock, latest state per unit, the build projection                                                                                                                                          |
| `scripts/emit.py`        | CLI a client calls to report a unit's state; falls back to the log file when the server is down                                                                                                                                                   |
| `scripts/check.py`       | Checks data, links, sources, color contrast (WCAG AA) in both themes, graph label sizes and a running server                                                                                                                                      |
| `tests/`                 | pytest suite and `render.test.js` (renders every route and follows every link); `fixture/` holds a ledger, an ingest log and a small work package                                                                                                 |

The page fetches nothing from the network. Opening `assets/index.html` from disk shows "No data": the data
lives in the data dir and only the server serves it.

## Where the data comes from

`gen.py` reads the org root, the layout, the optional work package, the optional language page, the ingest
log and two `gh pr list` calls (open and merged; none with `--no-gh`), and writes each output file by an
atomic replace. `serve.py` runs it on `/api/refresh` at most every 25 s; the page asks every 30 s while it is
visible and redraws only when the data hash changes.

The live layer comes from the runtime, not from a run log: `live.py` tails each `--ledger` glob and the
`ledgers/*.ledger` plus `dispatcher.json` of each `--state-dir` every 0.5 s, and `serve.py` streams one message
per new entry on `/api/events`. The ledger MAC is not checked (the key belongs to the runtime and this viewer
never reads it); the seq and prev chain is. An entry that is not an object or has fields of the wrong type
becomes a run problem; it never stops the poller.

A ledger's `change` host result names a worktree. `live.py` runs `git status` there (and classifies the rung of
each change) only when the worktree's real path is under a `--worktree-root`; there is none by default, since
the ledger, not the user, names the path. git runs with `core.fsmonitor=false`, no hooks and no optional locks,
and classification stops at 2000 files and skips symlinks and files over 1 MiB.

Cost: the ledger carries cost only on step results; judge calls (reviewer, lead) are paid model calls that only the
runtime's journal `sessions/<run_id>.calls.jsonl` beside the ledger records. `live.py` takes a run's cost from that
journal when it exists, else from the ledger, and marks the run `cost_partial` when the ledger has judge calls and
no journal. The page then says "cost partial".

## The work package

Every file is optional. Without the folder the site has no decisions and builds its unit view from ingest and
pull requests only.

| File                  | Read as                                                                                                       |
| --------------------- | ------------------------------------------------------------------------------------------------------------- |
| `status-units.json`   | `[{id, w, name, st, note, dep, what, tgt}]`, the planned units                                                |
| `agent-plans/<id>.md` | a unit brief: `# Brief <id>: <name>`, `## Objective`, `## Acceptance` (numbered), a branch name, `Depends on` |
| `run-log.md`          | table rows `\| <date> \| <entry> \|`; `<id> verified` and `<id> ... pushed as PR #<n>` close a unit           |
| `owner-decisions.md`  | shown under "Your decisions so far"                                                                           |
| `findings/*.md`       | listed on the unit whose id starts the file name                                                              |
| `site.json`           | `unit_map`, `component_units` and `decisions`, below                                                          |

```json
{
  "unit_map": { "tdd-unit": ["U3"] },
  "component_units": { "cli": ["U19"] },
  "decisions": [
    {
      "title": "Merge grant",
      "state": "waits for you",
      "seg": ["software-engineering"],
      "text": "What the owner has to decide.",
      "src": "owner-decisions.md",
      "quote": "text that must still be in src",
      "updates": [["regex on run-log rows", "resolved", "new text"]]
    }
  ]
}
```

`unit_map` ties units to workflows and `component_units` to the layout's platform components. A decision is
open while its state is "waits for you" or "for review"; the last run-log row an `updates` pattern matches
sets its state and text. A decision whose `quote` is no longer in `src` is flagged as possibly stale.

## Latest state only

The ledgers and the ingest log are append-only and never compacted. The page shows a projection of them:

- Runs: `runs(D)` in `views.js` keeps the newest run of each workflow (a running one first, then the latest
  start). The band, the sidebar counts, the run list, the segment graph badges, the cost line and the jump palette
  all read it. A failed run that a later run of the same workflow superseded is not failing any more. Older runs
  are listed only in the collapsed History of a run's own box; their links keep working.
- Units: `ingest.project_units` gives each unit one state, the newest of four sources: the work package
  (oldest), a merged pull request (at its merge time), an open pull request (at its last update; `ci` while
  checks run or fail, else `review`) and the ingest log (at the server's time). A merged pull request marks its
  unit merged with no report. A unit reported merged while its pull request is still open shows the conflict in
  its panel.
- Metrics: the last `org.metric` ledger entry per metric, across every ledger, newest by time then seq. Without
  one the metric says "no collector". The assumed entry shape is `{type: 'org.metric', metric, value, reason?}`,
  as the entry body, as `body.event`, or under ledger kind `org.metric`; `org_metric()` in `live.py` is the one
  place to change when the collectors land.

Unit states and where they count: `building`, `review`, `ci` are building now; `needs-owner` and `blocked` need
you; `failed` is failing; `merged` and `done` are done; `queued` is queued.

## Ingest

`POST /api/ingest` takes one JSON object, `Content-Type: application/json`, at most 4096 bytes, at most 30
reports a minute across every client. Fields: `unit` (U20, U13a, H1), `state`, optional `title`, `text`, `pr`,
`branch`, `agent`, `wave` (1 to 99), `deps` (unit ids). Unknown fields are refused. The server adds `seq`, `prev`,
`at`, `src` and `hash` (sha256 over the previous hash and the line). Answers: 201 with the stored line, 400, 403,
409 (broken chain), 411, 413, 415, 429.

The chain has no key: it catches a hand edit, a reordered line or a torn write, not someone who rewrites the whole
file. Lines after the first break are ignored and shown as a warning on the build page; new reports are refused
(409) until the file is moved aside. `python3 scripts/ingest.py verify [FILE]` checks the log. A new log file is
created with mode 0600. `read` also re-validates every line, so a writer that recomputes the hash for a bad
report breaks the chain instead of the generator.

A new unit appears when it is first reported. Its wave is `--wave`, else one more than its deepest dependency.
A dependency on an unknown unit is dropped with a generator warning.

## Server rules

- Binds 127.0.0.1 only. The port is `--port` (default 8765, 0 picks a free one).
- Every request needs a `Host` of `127.0.0.1:<port>` or `localhost:<port>` (stops DNS rebinding), no
  `Origin` other than those two, and `Sec-Fetch-Site` absent, `same-origin` or `none` (stops a foreign page
  reading the data or posting). Anything else is 403.
- Files: `assets/` only, resolved and checked to stay inside it, no dotfiles, no directory listing, a fixed
  list of content types. `/data/<name>` serves only the generated files by name, never another path in the data
  dir, so the ingest log is never served.
- Responses carry `no-store`, `nosniff`, `X-Frame-Options: DENY`, `frame-ancestors 'none'` and no referrer.
- Sockets time out after 20 s; at most 64 connections and 16 event streams are open at once (more are closed
  or get 503). HEAD on the event stream is 405.
- `/api/refresh` runs the generator at most every 25 s, one run at a time; a growing ingest log triggers at
  most one rebuild every 5 s.
- Generated data files are mode 0600 in a 0700 folder; a symlink in the data folder is not followed.
- No secret is read or served: the ledger key stays with the runtime.

## Routes

`#/`, `#/s/<segment>`, `#/w/<workflow>[/r/<run>][/ops][/n/<node>]`, `#/c/<component>[/u/<unit>]`,
`#/build[/<unit>]`, `#/language[/<section>]`, `#/decisions[/<item>]`.

## Simulations and replay

    python3 scripts/gen.py --simulate-active U19,U3 --fail-pr 175 --needs-seg software-engineering --out DIR
    python3 scripts/live.py replay FINISHED.ledger DEMO.ledger --rate 4

Simulated states and another ingest log (`--ingest FILE`) need `--out DIR`, so the served data never holds them.
`replay` copies a finished ledger entry by entry into a file that `--ledger` names, to watch the live feed move.
