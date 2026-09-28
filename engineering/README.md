# Engineering skills

Skills for designing and building systems. Portable Agent Skills (`SKILL.md`) that run on Claude
Code, Codex, and OpenCode. Language- and code-level skills live under [`swe/`](./swe/README.md);
this directory holds the cross-cutting architecture skill.

| Skill                             | What it does                                                                                                 | Reach for it when                                                                             |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- |
| [architect](./architect/SKILL.md) | Turn a fuzzy systems/infra requirement into a self-contained, agent-executable work package, then execute it | designing a non-trivial system or infra change, an RFC or design doc, "how should we build X" |

`architect` is markdown-first: it produces a directory of linked documents (research notes,
proposal, decision log, spec with positive and adversarial tests, build DAG, per-node agent briefs)
that a fleet of agents can execute with no information loss, plus an execution phase (unattended
deploy orchestrator, verification harness, observability). Three standard-library scripts make the
mechanical parts deterministic: `scripts/scaffold.py` generates the skeleton, `scripts/graph.py`
engineers the work-division graph (waves, critical path, transitive reduction, write-set collisions)
from a node spec, and `scripts/lint.py` checks completeness and internal consistency before dispatch.
It is grounded in Ousterhout's _A Philosophy of Software Design_ and Ford & Richards' architecture
canon; the architecture-style catalog is in `references/architecture-styles.md`, and the
graph-engineering pattern catalog (how to divide work so agents self-collaborate) is in
`references/graph-patterns.md`. Grounding the current state can optionally run through a code graph
(codegraph preferred), single- or multi-repo, per `references/code-graphing.md`, falling back to
manual reading when no such tool is present.
