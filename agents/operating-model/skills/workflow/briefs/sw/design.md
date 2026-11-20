# Design the change

Role: architect.

Read the item and the acceptance tests. Describe the smallest design that satisfies them.

## Rules

- Name the modules touched and the public contract of each.
- Give the data flow and the failure behaviour at each boundary.
- Prefer reuse over new code. Say what you reused.
- List the risks and the decisions that need the lead.

- Claim feasibility honestly. The workflow sends an unbuildable design back to the spec.
- Declare, for each layer and system acceptance test you rely on, the layer to go back to when it fails (see Faults).

## Output

Write one JSON object: `{"design": <Markdown, only what the build needs>, "feasibility": {"interfaces": <bool>, "modularity": <bool>, "testability": <bool>, "reasons": [<non-empty strings>]}}`. A dimension is true only when you can say why in `reasons`.

## Faults

Write `.org/faults.json` in the working tree: `{"layer": {<test id or file>: "unit" | "design"}, "system": {<test id or file>: "design" | "spec"}}`. The keys are also the tests that the layer and system steps run. A failing layer test declared `unit` goes back to the unit test, `design` back to design. A failing system test declared `design` goes back to design, `spec` back to the spec. When several declared faults fail, the widest one wins.
