---
name: status
description: >
  Serve a local, live web page of an organization of OWS workflows: the segment and workflow graphs from the
  workflow skill's org root, runs followed from their ledgers as they happen, build units reported by agents
  through an ingest endpoint, pull requests from gh, and the owner's open items from an optional work package.
  Use when asked to show, watch or report the state of the organization or of a multi-unit build, to start
  the status site, or to report a unit's state to it. Not for validating or running workflows (use workflow),
  and not for a hosted or shared page: it binds to loopback only.
license: MIT
compatibility: Python 3.10 or newer; PyYAML to read the workflow YAML; gh for pull requests (optional); node to run the render test (optional)
metadata:
  version: "0.1.0"
---

# status: the organization site

A local site with no network at view time. It draws the org root (the `workflow` skill beside this one by
default), follows run ledgers live, and shows build units and the owner's open items.

## Start it

```
uv run --with pyyaml python scripts/serve.py \
    [--ledger 'RUNS/*.ledger'] [--state-dir ORG_STATE] [--work-package DIR] [--port 8765]
```

Open http://127.0.0.1:8765/. It listens on 127.0.0.1 only. The first start generates the data; the page
asks for fresh data every 30 s and reloads at once when a unit report arrives.

Sources (all scripts take the same options; `--config FILE` holds them as JSON, details in `scripts/config.py`):

| Option                         | Default                                                        | What                                                        |
| ------------------------------ | -------------------------------------------------------------- | ----------------------------------------------------------- |
| `--org-root DIR`               | `../workflow` beside this skill                                | `manifest.json`, `workflows/*.yaml`, metrics, checks        |
| `--data-dir DIR`               | `$XDG_STATE_HOME/org-status`, else `~/.local/state/org-status` | generated `data/` and `ingest/events.jsonl`                 |
| `--ledger GLOB`                | none                                                           | run ledgers to follow (repeatable)                          |
| `--state-dir DIR`              | none                                                           | an `org.py serve --state DIR` folder (repeatable)           |
| `--work-package DIR`           | none                                                           | optional: unit plans, run log, owner decisions, `site.json` |
| `--repo OWNER/NAME`, `--no-gh` | the org root's GitHub origin                                   | pull requests from `gh pr list`                             |
| `--layout FILE`                | `assets/org-layout.json`                                       | segments, components, workflow descriptions                 |
| `--language-page FILE`         | none                                                           | an HTML page whose sections the language view shows         |

Without a work package the site still builds: no decisions, and the build view shows only units reported
through ingest and their pull requests. A workflow no segment names goes to an "Other workflows" segment.

## Report a unit's state

```
python3 scripts/emit.py --unit U20 --state building --title 'Metric collectors' --pr 176
python3 scripts/emit.py --unit U22 --state review --deps U21 --wave 8 --branch kauki/feat/x/y
```

States: queued, building, review, ci, merged, done, blocked, failed, needs-owner. It posts to the server;
when nothing listens it appends to the same log under `--data-dir` with the same validation and lock.

A Claude Code hook can report subagents. It is documented here, not installed. Replace `<skill-dir>` with
this skill's path:

```json
{
  "hooks": {
    "SubagentStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 <skill-dir>/scripts/emit.py --hook --state building"
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 <skill-dir>/scripts/emit.py --hook --state review"
          }
        ]
      }
    ]
  }
}
```

`--hook` reads the payload on stdin, takes the unit from `--unit` or the first unit id in `agent_type`,
`description` or `prompt`, does nothing without one, and always exits 0. Which fields a SubagentStart
payload carries is not verified here; check the hooks reference before relying on it.

## Check it

```
uv run --with pyyaml --with pytest python -m pytest tests     # generates fixture data, runs every check
python3 scripts/check.py [--port 8765] [source options]        # the checks on your own data and server
```

The pytest suite runs the render test (`tests/render.test.js`) when `node` is on PATH and skips it with
that reason otherwise.

## Files and security

`references/site.md` covers the data model (latest state only, the ingest log and its hash chain, cost,
metrics), the work package format, the routes, and the server's rules: what it serves, the Host, Origin and
Sec-Fetch-Site checks, the size and rate caps, and what is never written.
