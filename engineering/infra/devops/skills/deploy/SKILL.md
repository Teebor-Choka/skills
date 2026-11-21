---
name: deploy
description: >
  Deploy stage of a delivery pipeline: take a released or integrated revision, deploy it to a
  target, and prove it works from real logs or state, with the diff shown first where the repo
  defines one. A failed verification leaves the stage open with the evidence attached. Use when a
  pipeline has a deploy stage, when asked to "deploy this revision", "roll this out", "verify the
  deploy", or when a design from architect names what to verify and observe and someone must run
  it. Not for cutting the release (the release stage), not for designing what to verify (architect),
  not for authoring CI workflows (github-actions).
license: MIT
metadata:
  version: "1.0.1"
---

# deploy

Optional stage, separate from release. A repo inserts it into its pipeline with `needs: [release]`
or `needs: [integrate]`. `architect` states what to verify and observe (criteria, technology). This
stage owns the how: the orchestrator, the verification harness and the observability.

## Consumes

A released or integrated revision, its check results, and the target to deploy to. The criteria and
signals to verify come from the design's spec (`architect` `references/execution.md`), or from the
repo's own deploy notes when no design exists.

## Produces

A deployed target plus verification evidence: the commands run and their output, taken after the
deploy.

## In scope

1. Confirm the revision's checks passed. Read the check state; do not assume it.
2. Run the repo's diff-before-deploy step when it defines one, and read the diff.
3. Deploy with the repo's own command or orchestrator.
4. Read real logs or state after the deploy: service status, health endpoints, the metrics the spec
   names. Do not report success from reading code.
5. Prove each signal the spec names moves when its input moves, and that the check can fail.

## Must not

- Deploy a revision whose checks did not pass.
- Skip a diff-before-deploy step where the repo defines one.
- Report success from reading code, config or a clean exit code alone.
- Reach a target the run was not given, or change what the design's spec says to verify.

## Hand-off

Pass: the stage closes and hands the revision, the target and the evidence (commands and output) to
the next stage or to the owner.

Fail: the stage stays open. Attach the evidence of the failed verification (commands and output) to
the stage and stop. Do not retry past the repo's own retry wall, and do not roll forward silently.
Rollback follows the repo's own procedure and is a separate recorded action.

## Escalation

Escalate to the stage owner when: the checks did not pass, the diff shows a change the spec does not
explain, a signal is absent so the target cannot be verified, or the target needs access the run does
not hold. Name the missing fact and the exact command that would settle it.

## Tier

execution. Verification reads and reports; it does not decide. Escalate to reasoning only for a
failure whose cause is unclear after the evidence is read.
