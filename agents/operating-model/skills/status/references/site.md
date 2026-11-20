# Organization site

Start it:

    python3 site/serve.py

Then open http://127.0.0.1:8765/. It listens on loopback only. To also see the rung of a change in flight,
start it with PyYAML: `uv run -q --with pyyaml python site/serve.py`.

Without the server, open `site/index.html` from disk. You get a read-only copy of the last generated
data (`data/data.js`), with no live feed and no refresh.

## Files

| File                   | Job                                                                                                                                                                                                                                                         |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `index.html`           | Page shell: sidebar and the scripts                                                                                                                                                                                                                         |
| `css/site.css`         | Tokens for light and dark (system, or `?theme=dark`, or the sidebar button), layout, graph node states. Color has three channels: segment hue for territory, state for a node's stroke and glyph (always with a shape), kind for shapes in operation graphs |
| `js/graph.js`          | Layout (layered graph, workflow flow) and SVG drawing; no DOM, so node can test it                                                                                                                                                                          |
| `js/views.js`          | Routes, one render function per view, the goal of every segment, workflow, step and unit, the jump index, live state per node, feedback per ledger event                                                                                                    |
| `js/app.js`            | Router, data loading, 30 s refresh, live feed, moving tokens and pulses, path highlight on hover or focus, legend filters, folding groups, jump palette (`/` or Ctrl-K), drill-down motion, Escape goes up one level                                        |
| `fonts/`               | Atkinson Hyperlegible Next and Atkinson Hyperlegible Mono (OFL), copied from nixpkgs                                                                                                                                                                        |
| `gen.py`               | Writes `data/*.json` and `data/data.js` (needs PyYAML)                                                                                                                                                                                                      |
| `live.py`              | Reads runtime ledgers and dispatcher state into run state (stdlib)                                                                                                                                                                                          |
| `live-sources.json`    | Which ledgers and org.py state directories to read                                                                                                                                                                                                          |
| `serve.py`             | Static files, `/api/refresh`, `/api/live`, `/api/events`, `POST /api/ingest` (stdlib)                                                                                                                                                                       |
| `ingest.py`            | The ingest log: validation, hash chain, append under a lock, latest state per unit, the build projection (stdlib)                                                                                                                                           |
| `emit.py`              | CLI a client calls to report a unit's state; falls back to the file when the server is down (stdlib)                                                                                                                                                        |
| `ingest/events.jsonl`  | The ingest log, append-only, written by `serve.py` and `emit.py` only                                                                                                                                                                                       |
| `check.py`             | Checks data, links, sources, color contrast (WCAG AA) in both themes, graph label sizes and the running server                                                                                                                                              |
| `tests/render.test.js` | Renders every route and follows every link (node)                                                                                                                                                                                                           |
| `tests/fixture/`       | Data with simulated building, failing and owner states, for the test                                                                                                                                                                                        |

## Where the data comes from

`gen.py` imports the readers of `work-package/status.py` (it does not change or run it) and reads the
org root (`ORG_ROOT` in status.py), `status-units.json`, `run-log.md`, `owner-decisions.md`,
`agent-plans/`, `findings/`, `../process-language.html`, `ingest/events.jsonl` and two `gh pr list` calls
(open and merged). Each file is written by an
atomic replace. `serve.py` runs it on `/api/refresh` at most every 25 s; the page asks every 30 s while
it is visible and redraws only when the data hash changes.

`live-sources.json` points at the ledgers of this session's test runs (a scratchpad that will go away).
Add the state directory of a real `org.py serve --state DIR` to `state_dirs` to follow the real organization.

The live layer comes from the application, not from the run log: `live.py` tails each ledger named in
`live-sources.json` (and `ledgers/*.ledger` plus `dispatcher.json` of each state directory) every 0.5 s,
and `serve.py` streams one message per new entry on `/api/events`. The ledger MAC is not checked (the
key belongs to the runtime); the seq and prev chain is.

Cost: the ledger carries cost only on step results; judge calls (reviewer, lead) are paid model calls that only the
runtime's journal `sessions/<run_id>.calls.jsonl` beside the ledger records. `live.py` takes a run's cost from that
journal when it exists, else from the ledger, and marks the run `cost_partial` when the ledger has judge calls and no
journal. The page then says "cost partial".

## Latest state only

The ledgers and the ingest log are append-only and never compacted. The page shows a projection of them:

- Runs: `runs(D)` in `js/views.js` keeps the newest run of each workflow (a running one first, then the latest
  start). The band, the sidebar counts, the run list, the segment graph badges, the cost line and the jump palette
  all read it. A failed run that a later run of the same workflow superseded is not failing any more. Older runs
  are listed only in the collapsed History of a run's own box; their links keep working.
- Units: `ingest.project_units` gives each unit one state, the newest of four sources: the work package
  (status-units.json, agent plans, run log; oldest), a merged pull request (at its merge time), an open pull
  request (at its last update; `ci` while checks run or fail, else `review`) and the ingest log (at the server's
  time). A merged pull request marks its unit merged with no report. A unit reported merged while its pull
  request is still open shows the conflict in its panel. Totals, the band, item and segment states come from the
  projected units.
- Metrics: the last `org.metric` ledger entry per metric, across every ledger in `live-sources.json`, newest by
  time then seq. Without one the metric says "no collector". The assumed entry shape is
  `{type: 'org.metric', metric, value, reason?}`, as the entry body, as `body.event`, or under ledger kind
  `org.metric`; `org_metric()` in `live.py` is the one place to change when the collectors land.

Unit states and where they count: `building`, `review`, `ci` are building now; `needs-owner` and `blocked` need
you; `failed` is failing; `merged` and `done` are done; `queued` is queued.

## Reporting unit state (ingest)

    python3 site/emit.py --unit U20 --state building --title 'Metric collectors' --pr 176
    python3 site/emit.py --unit U22 --state review --deps U21 --wave 8 --branch kauki/feat/operating-model/x

`emit.py` posts to `POST /api/ingest`. When nothing listens on 127.0.0.1:8765 it appends to
`ingest/events.jsonl` itself, with the same validation and lock. A refused report is never written.
`ORG_SITE` and `ORG_INGEST` point it at another server or log (the tests use them).

The endpoint takes one JSON object, `Content-Type: application/json`, at most 4096 bytes, from a loopback Host,
with no foreign `Origin` and `Sec-Fetch-Site` same-origin or none, at most 30 a minute. Fields: `unit` (U20, U13a,
H1), `state` (queued, building, review, ci, merged, done, blocked, failed, needs-owner), optional `title`, `text`,
`pr`, `branch`, `agent`, `wave` (1 to 99), `deps` (unit ids). Unknown fields are refused. The server adds `seq`,
`prev`, `at`, `src` and `hash` (sha256 over the previous hash and the line). Answers: 201 with the stored line,
400, 403, 409 (broken chain), 411, 413, 415, 429.

The chain has no key: it catches a hand edit, a reordered line or a torn write, not someone who rewrites the whole
file. Lines after the first break are ignored and shown as a warning on the build page; new reports are refused
(409) until the file is moved aside. `python3 site/ingest.py verify` checks the log.

When the log grows (a POST or a direct append), `serve.py` generates the data again and sends a `build` message
on `/api/events`; open pages reload the data at once.

A new unit appears when it is first reported. Its wave is `--wave`, else one more than its deepest dependency.
A dependency on an unknown unit is dropped with a generator warning.

### Claude Code hook (not installed)

To report subagents automatically, an orchestrator could add this to its settings. It is not installed here.
`--hook` reads the hook payload on stdin and takes the unit from `--unit` or from the first unit id (U20, U13a)
in the payload's `agent_type`, `description` or `prompt`; with no unit it does nothing. Which of those fields a
SubagentStart payload carries is not verified here; check the hooks reference before you rely on it.

```json
{
  "hooks": {
    "SubagentStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/Fun/plans/process-runtime/site/emit.py --hook --state building"
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/Fun/plans/process-runtime/site/emit.py --hook --state review"
          }
        ]
      }
    ]
  }
}
```

`--hook` always exits 0, so a down server or a refused report never blocks the session.

Routes: `#/`, `#/s/<segment>`, `#/w/<workflow>[/r/<run>][/ops][/n/<node>]`, `#/c/<component>[/u/<unit>]`,
`#/build[/<unit>]`, `#/language[/<section>]`, `#/decisions[/<item>]`.

## Checks

    python3 site/check.py
    uv run -q --with pyyaml python site/gen.py --simulate-active U19,U3 --fail-pr 175 --needs-seg software-engineering \
      --ingest site/tests/fixture/ingest.jsonl --out site/tests/fixture

`check.py` also runs the ingest checks on temporary logs (validation, tamper, reorder, torn tail, latest wins,
projection, fallback append, rate cap) and, when the server runs, sends it only refused reports, so the real
log is never written. The fixture's ingest log (`tests/fixture/ingest.jsonl`) holds a failed, a needs-owner, a
building and a queued-after-blocked unit, written through `emit.py`'s fallback.

To watch the live feed move without a real run, replay a finished ledger into a file that
`live-sources.json` names:

    python3 site/live.py replay <finished.ledger> <scratchpad>/live-demo/demo.ledger --rate 4
