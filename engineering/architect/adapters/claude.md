<!-- Claude Code adapter for architect: publishing rendered artifacts outside the terminal.
     Optional. The markdown work package (with in-repo mermaid) is complete without any of this;
     this only covers sharing a rendered proposal or diagram with people who won't read markdown
     in a terminal. Other hosts (Codex, OpenCode) use their own rendering capability instead. -->

## Publishing rendered artifacts (Claude Code)

The work package is markdown-first and needs no publishing step. When a stakeholder wants a
rendered view, Claude Code offers two capabilities the portable skill deliberately does not name:

- **Diagrams.** The `artifact-diagramming` skill renders and publishes the C4-ladder diagrams and
  the execution DAG. Mermaid already renders in-repo, so publish only when someone needs a
  read-only link outside the repo.
- **A branded proposal page.** The `artifact-design` (and `frontend-design`) skills render the
  proposal as a self-contained, theme-aware HTML page, published with the `Artifact` tool. It is a
  rendering of `<slug>-proposal.md`, never a separate document: when the proposal changes, the
  markdown is authoritative and the page is regenerated.

Rules that carry across hosts:

- Publish read-only, and paste the URLs back into the README's "Visual artifacts" section.
- Artifacts start private. Sharing one outside the team is the human's call, not the agent's.
- Never let a rendered page drift from the markdown. The markdown is the source of truth; the
  render is disposable.
