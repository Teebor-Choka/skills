# Authoring flow

How to take a project from undocumented to conformant. The contract (`contract.md`) says what the
output must be; this says how to produce it well. Diagrams have their own file (`diagrams.md`);
enforcement has `enforcement.md`.

## Before writing

Read `contract.md`. Then explore the project until you can answer, from evidence, not guesses:

- What is this project for, in one sentence?
- Its layout: the top-level directories and what each holds.
- Its stack and how it builds, runs, and deploys.
- The real decisions someone made, and _why_ — the choices that had a live alternative.

Prefer a code-graph tool over a blind file sweep (it is faster and finds the real seams). For a
large or multi-part project, fan the exploration out to subagents and work from their findings. The
goal is enough grounding that every line you write traces to something in the project.

## Describe, don't propose

`overview.md` and `spec.md` document a system that already exists. Write in the present tense about
what is there. This is the opposite stance from the architect skill, which proposes a system that
does not exist yet. Reach into architect for two things only:

- **ADR discipline** — the decision-log shape: context, the decision, its consequences, and the
  alternative set aside. An ADR without the set-aside alternative is usually not recording a real
  choice; make the absence explicit instead of dropping the section.
- **Spec-test discipline** — a `spec.md` states, per subsystem, the decisions and the tests that
  verify them, including **adversarial** tests (what would prove it wrong), not only happy-path.

Do not run architect's full scaffold/graph/dispatch pipeline. That builds new work; here the work
is built and you are recording it.

## Voice

Every doc's prose is written at the strictest de-slop depth and the tersest length budget. Lead
with the fact. Cut canned openers, filler, and the hook-evidence-bow template shape. No em dashes.
Apply the unslop skill where it is available. Terse is the default; a subsystem that genuinely
needs more gets more, nothing else does.

## The documents

Fill the skeletons in `assets/` (they are starting shapes to adapt, not forms to match — the
content is yours to fit the project):

- `assets/overview.skeleton.md` — purpose, a layout table, the stack, build/run/deploy, pointers
  to decisions and deeper docs, and the mandatory context-or-component diagram. If you omit
  `spec.md`, record the one-line reason here ("no deep spec: static single-file page").
- `assets/spec.skeleton.md` — one section per subsystem: its decisions, its tests (positive and
  adversarial), and a diagram. Only when the opt-in test in the contract says the project needs it.
- `assets/adr.skeleton.md` — one decision, in architect's shape. One file per decision under
  `decisions/`, kebab-named for the decision.
- `assets/decisions-README.skeleton.md` — the index: a table linking every ADR. Keep it in sync
  with the directory; the validator checks both directions.
- `assets/AGENTS.pointer.md` — the root pointer. Create it, or splice its pointers into an existing
  `AGENTS.md`. It points into `docs/`; it does not restate the overview.

Frontmatter for each is specified in the contract; copy the keys exactly, they are checked.

## Finish

Run `python3 scripts/validate_docs.py <project>` and clear every finding before reporting done. The
validator only proves the structure is right; you are still responsible for the content being true
and the diagrams being accurate.

## Multi-project runs

To document or audit many projects at once: `validate_docs.py --all <root>` lists which projects are
undocumented or non-conformant, giving you the work queue. Document them one at a time (each is its
own judgment call), re-running the validator per project. A project that parents other projects also wants a
portfolio-level diagram showing how they relate; that has no generated source, so draw it by hand
in the parent's `overview.md`.
