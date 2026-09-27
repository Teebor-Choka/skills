# Methodology: the standards behind the artifacts

The document set (`document-set.md`) says what each artifact must carry. This file says which
established standard each part maps to, so the structure is grounded rather than invented, and so
the positive/adversarial test split is _derivable and greppable_ instead of by convention. Cite
these in the artifacts you produce.

## Requirements: EARS + RFC 2119

Write every spec requirement as an EARS sentence carrying an RFC 2119 keyword. EARS gives five
sentence templates; the "unwanted behaviour" template is the adversarial-test generator.

- **Ubiquitous:** The system SHALL <response>.
- **Event-driven:** When <trigger>, the system SHALL <response>.
- **State-driven:** While <state>, the system SHALL <response>.
- **Unwanted behaviour:** If <condition>, then the system SHALL <response>. (This is where the
  adversarial tests come from.)
- **Optional:** Where <feature>, the system SHALL <response>.

RFC 2119 keywords carry normative force in uppercase only: MUST, MUST NOT, SHOULD, MAY. The rule
that makes tests derivable: **every MUST becomes a positive (verification) test row; every MUST NOT
becomes an adversarial (negative) test row.** Give each requirement an id (REQ-1, REQ-2) so blocks
can back-link to it.

- EARS: https://alistairmavin.com/ears/
- RFC 2119: https://www.rfc-editor.org/rfc/rfc2119 · RFC 8174 (uppercase-only): https://www.rfc-editor.org/rfc/rfc8174

## Test tables: Gherkin Given/When/Then

Each test row is a Given/When/Then case: Given <setup>, When <action or injection>, Then <expected
result>. Positive rows assert the good behaviour; adversarial rows assert the bad behaviour is
observable (a silent no-op is a failure). The "Three Amigos" idea (business, dev, test) is why the
adversarial verifier is a _distinct_ agent that never sees the implementation.

- Gherkin: https://cucumber.io/docs/gherkin/reference
- Specification by Example (Gojko Adzic): https://gojko.net/books/specification-by-example/

## Decisions: MADR + Nygard ADR

Each decision-log entry is a MADR record with a machine-parseable **Status** and a **Confirmation**
field:

- **Status:** one of Proposed, Accepted, Deprecated, Superseded. A superseded decision points to
  the one that replaced it and keeps its reasoning on the record.
- **Confirmation:** how the decision is verified in the harness (which test or fitness function
  would fail if the decision were violated). This wires each decision to `execution.md`.
- Nygard's rule: the Consequences must state the bad as well as the good. An ADR with no negative
  consequence is incomplete.

- MADR 4.0: https://adr.github.io/madr/
- Nygard, "Documenting Architecture Decisions" (2011): https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions

## Completeness: arc42

Use arc42's section set as a gap-check on the whole package, not as a rival template. The one
section teams most often miss and arc42 forces is **§11 Risks & Technical Debt**; the proposal
carries it. A glossary (arc42 §12) stops term drift across per-node briefs.

- arc42: https://arc42.org/overview

## Diagrams: C4

Give visuals a defined ladder, one abstraction per diagram: L1 Context (README), L2 Container /
component (the block graph), Deployment (what the orchestrator and observability need), and the
execution DAG (`development-graph.md`). Details in `deliverable-formats.md`.

- C4 model: https://c4model.com/

## Build order: DAG, Kahn, critical path

The development graph must be a valid DAG. `scripts/lint.py` runs a topological sort (Python
`graphlib`), so a cyclic plan is a hard fail. Kahn's algorithm gives the waves (each level runs in
parallel); the critical path is the longest dependency chain and sets the irreducible wall-clock
time. Adding agents past the critical-path width is wasted, so annotate it in
`development-graph.md`.

- Topological sorting / Kahn: https://en.wikipedia.org/wiki/Topological_sorting
- Critical path method: https://en.wikipedia.org/wiki/Critical_path_method
- Python graphlib: https://docs.python.org/3/library/graphlib.html

## Traceability: task to requirement

Every DAG node (and its spec block) names the requirement id it satisfies (Kiro-style
`Satisfies: REQ-n`). `scripts/lint.py` warns when a block declares no backlink. This keeps the
build honest: no block exists that no requirement asked for, and no requirement ships with no block.

- Kiro specs: https://kiro.dev/docs/specs/feature-specs/
