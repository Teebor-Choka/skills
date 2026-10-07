---
name: ramble
description: Turn a rough idea or ramble into an aligned, gap-closed brief for the architect. A relentless grilling interview that resolves every open decision, sharpens the glossary as it goes, and emits a structured brief. User-invoked.
disable-model-invocation: true
metadata:
  version: "1.0.0"
---

Take whatever rough thing is brought — a ramble, a half-formed plan, a one-line intent — and align on
it until nothing load-bearing is left unsaid, then hand the architect a structured brief. The job is
alignment, not output: resolve the decisions, don't write the thing.

## The interview: a design tree, worked in rounds

Map the idea as a **design tree** — every decision branches into the decisions that hang off it.

- The **frontier** is every decision whose prerequisites are already settled: the questions you can
  answer _now_ without guessing at answers you haven't heard yet. A question whose answer depends on
  another still-open question belongs to a later round, not this one.
- **Facts are your job, never the user's.** When a frontier question needs a fact from the environment
  (files, tools, the web), dispatch a sub-agent to find it. Don't block the rest of the frontier on it:
  a running exploration is just an unsettled prerequisite, so only the questions downstream of it wait.
- **Decisions are the user's.** Put each to them with your recommended answer, and wait.
- Each answer reshapes the tree: settled decisions push the frontier outward and unblock what depended
  on them. Recompute the frontier and continue.

**Persist until the frontier is empty** — every branch visited, nothing silently assumed. This is the
point of the skill: do not let a gap slip through as an assumption. A gap you genuinely cannot close
now becomes an **explicit open item in the brief**, owned by whoever can close it — never a silent
default. Do not act on the idea until the user confirms you have reached a shared understanding.

## Interaction: batch or dialog (configurable)

Read `interaction` from the repo's `.agents/policy` (default `batch`); a per-invocation flag overrides
it (`--dialog` / `--batch`).

- **`batch`** (default): ask the whole frontier in one round — numbered questions, each with your
  recommended answer — then wait and recompute. Fast; fewest round-trips.
- **`dialog`**: the same frontier computation, surfaced **one question at a time**, conversational,
  waiting for each answer before the next. Higher-touch, for thinking out loud.

Format a batch round:

```
❓ **Q1 — <title>**: <body, including any options>

➡️ <your recommended answer>

---

❓ **Q2 — <title>**: <body>

➡️ <your recommended answer>
```

In `dialog` mode, surface `Q1` alone, wait, then the next — still computed from the frontier, just not
dumped at once.

## Capture as you go: glossary

Sharpen the language while you interview, writing it down the moment it crystallises — only where the
project has a docs home; create the file lazily.

- **Sharpen fuzzy terms** to one canonical meaning; when a term conflicts with an existing
  `GLOSSARY.md`, surface the conflict and resolve it. Update `GLOSSARY.md` inline the moment a term
  settles — a glossary only, devoid of implementation detail. Format and rules:
  [`references/glossary-format.md`](references/glossary-format.md).

Decisions are **not** recorded here. A decision worth keeping goes to the **architect's decision-log**
(where it belongs with its grounding and status); the brief's open items name any decision still
unresolved. This skill aligns and captures vocabulary; the architect owns the decision record.

## Output: the brief

When the frontier is empty and the user confirms, emit the brief the architect consumes — full
structure, rules, and a worked example in [`references/brief-format.md`](references/brief-format.md):

- **Problem** — one paragraph.
- **Intent** — bullets; every claim traced to something said in the interview (no invented
  requirement; if it wasn't said or grounded, it isn't here).
- **Open items** — the gaps that stayed open, explicit, each with who or what would close it.

Hand this to the architect. The resolved terms and decisions seed the architect's glossary and
decision-log.

<!-- Modelled closely on mattpocock/skills (grill-with-docs = grilling + domain-modeling):
     https://github.com/mattpocock/skills/tree/main/skills/engineering/grill-with-docs — adapted,
     not copied. Additions: the explicit "gap → open item, never a silent assumption" rule, the
     configurable batch/dialog interaction (read from .agents/policy), and the typed brief output. -->
