## Scaling

Match the package to the work; step 1's risk tier decides. A reversible change one agent will just do
is a single `<slug>-plan.md` (`scaffold.py --tier note`), nothing else. A small, reversible design
that will still be handed off is proposal + decision-log + a short spec, no agent fleet (`--tier
small`). A large or irreversible multi-agent epic warrants the full set (`--tier full`). When you drop
an artifact from a tier that would normally carry it, say why in the README rather than leaving a
reader to wonder if it was forgotten. Don't manufacture blocks, waves, documents, or a hinge decision
that the problem doesn't actually have.

## Running across agents

One portable `SKILL.md` and its `` and `../scripts/` run unchanged on Claude Code, Codex, and
OpenCode. The scripts need only Python 3.13 or newer (standard library, no third-party packages). Install the
skill directory at `~/.claude/skills/architect/` (Claude Code), `~/.agents/skills/architect/`
(Codex), or `~/.config/opencode/skills/architect/` (OpenCode, which also reads `.claude/skills` and
`.agents/skills`, so one directory serves all three).

The only host-specific piece is publishing a rendered proposal or diagram outside the terminal;
`adapters/claude.md` wires that to Claude Code's `Artifact` tool and the `artifact-diagramming` /
`artifact-design` skills. On other hosts, use their own rendering capability. The markdown work
package, including in-repo mermaid, is complete without any of it.
