# Return contract

Every agent that returns a finding, verdict, or result returns the same core fields. Review,
forge-style stress tests, validators and workers all specialise this record. A skill may add
fields. It must not drop these.

| Field      | Meaning                                                                      |
| ---------- | ---------------------------------------------------------------------------- |
| claim      | One sentence: what is true, wrong, or done.                                  |
| evidence   | Cited file and line, or the output of a command that shows it. **Required.** |
| revision   | The version of the work this return judged or produced.                      |
| confidence | 0 to 1. A claim not checked against the work scores under 0.5.               |
| scenario   | For a defect: the input or state, then the wrong result.                     |
| fix        | A concrete suggested change. A reviewer never applies it.                    |

Rules:

1. **No evidence, no claim.** The receiver drops a return with no evidence.
2. **Pin the revision.** A verdict without a revision is void (`mechanics.md` rule 7).
3. **Structured, not prose.** Return the fields above, or the specialised schema that includes
   them, so the receiver can dedupe, tally and triage mechanically.
4. **Zero findings is valid.** Do not prompt a reviewer to find something. Name what was checked.
5. **A reject states why.** "Wrong because X", not only "skipped".

Specialisations kept in their own skills: review-gauntlet's `findings-schema.md` (adds angle,
severity, file, line), and forge-idea's verdict schema.
