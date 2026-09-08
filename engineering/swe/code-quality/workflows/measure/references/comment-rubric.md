# Comment rubric

The single source of truth for judging comment quality in one file. Read by the
`comments` workflow's subagent on every host — Claude Code's
`assets/comments.workflow.js` and OpenCode's `opencode/agent/comment-quality.md` both
point their agent at this file instead of embedding the rule text, so there's exactly
one copy of the actual criteria (same reason `verify-rubric.md` exists for `measure`).

## The rule

Comments justify only what naming and structure cannot: a hidden constraint, a
non-obvious invariant, a workaround, or behavior that would otherwise surprise a
reader. If removing a comment loses no information a careful reader could recover
from the code itself, the comment shouldn't exist.

**Exception: public API surface.** Public functions, types, and modules get doc
comments describing contract and usage regardless of whether the implementation is
obvious — a caller can't read the implementation to infer it, so the "obvious from
the code" test doesn't apply there.

Where a comment is warranted, it should use the minimum wording that conveys the
necessary information: precise, technical, free of restatement or narrative framing.
A comment that could say the same thing in fewer words is too long — every extra
clause is cognitive load a reader pays for nothing.

A comment must never work against the code's own intent — it shouldn't contradict,
hedge against, or cast doubt on what the code actually does. A comment that reads
like it's arguing with or defending the code is a signal the code needs to change,
not the comment.

## What to do

You are given one file (and, if provided, which lines changed — treat unchanged
lines as lower priority, not out of scope). Read every comment in it and judge each
against the rule above. For each comment that violates it, note: the line, the
comment's text (or a short excerpt if long), which failure it is — restates the
obvious, could be shorter, missing where required (undocumented public API), or
contradicts/hedges against the code — and a proposed fix.

The proposed fix is concrete, not a description of what to do: for "restates the
obvious," propose deletion (say so explicitly, don't just imply it); for "could be
shorter" or "contradicts/hedges," propose the actual replacement wording; for
"missing where required," propose the actual doc comment to add, in this language's
own doc-comment convention (`///` for Rust, a docstring for Python, etc.). A reader
should be able to apply your proposal without having to compose it themselves — that
still isn't you editing the file, only reporting what an edit would look like.

Don't flag a comment just because it's long if the length is doing real work (e.g. a
non-obvious invariant that genuinely needs a few sentences) — judge information
density, not line count alone. Don't invent a violation to have something to report;
an empty result is a valid, common outcome.

Return only the violations found, each with: line, excerpt, failure, proposed_fix.
