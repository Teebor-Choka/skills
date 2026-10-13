# Roadmap

What `project-docs` deliberately leaves out of v1, and why. Both items were designed and set aside to
keep the first version to the two halves that carry their weight: authoring and mechanical
enforcement.

## Staleness review knob

A review dimension that flags "a subsystem's code changed but its ADR, spec, or diagram did not."
This is the one thing the validator structurally cannot do: it checks that docs are _present_ and
well-formed, never that they are _current_. Presence is mechanical; currency is judgment, so it
belongs in a code-review pass, not the validator. Deferred until the authoring and enforcement
halves are in real use and the staleness actually bites.

## Cross-project docs dashboard

`validate_docs.py --all` already produces the data: which projects are undocumented or non-conformant,
ADR counts, and so on. Rendering that as a live HTML artifact (a coverage matrix across a
portfolio, with per-project architecture thumbnails) is a natural next step. It is the one place an
off-project interactive page beats mermaid-in-a-file. Deferred because the `--all` text output covers
the working need today.
