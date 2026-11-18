# Verification and observability criteria: what architect specifies

The architect does not build, run or deploy anything. It states **what** must be verified and
**what** must be observed, with the technology and the criteria. **How** to deploy, run the checks
and watch the system belongs to the deploy stage (tracked in Teebor-Choka/skills issue #109). Put the
items below in the spec, as acceptance criteria and constraints.

## 1. What to verify

- **Criteria come from the spec's test tables.** Every verification and adversarial test is a
  criterion the deploy stage can turn into a check. Author the criteria from the spec, not from code.
- **State the bad behaviour.** For each criterion, name the failure that must be visible (a silent
  `false`, an unprotected slot). A silent no-op must look different from success.
- **Separate readiness from correctness.** State "it exists and is settled" and "it behaves" as two
  criteria. A component can be Ready and do nothing.
- **Mark destructive checks.** Name the checks that inject faults. Name the environment where they
  may run (never the pilot).
- **State the env contract.** List the inputs a check needs (variables, credentials, endpoints), so
  a missing input is not read as a system failure.
- **State the capability, not the assumption.** For each capability, say how it is shipped and how
  to confirm it is active at runtime. Do not infer it from the absence of an error.
- **Order by dependency.** The development graph gives the order. State which criteria gate which
  layer.

## 2. What to observe

- **Own the metric names.** Default exporters miss domain state. Name each custom series (for example
  `cnpg_offsite_slot_*`) and the alert expression that uses it, so the alert is exact.
- **Two criteria per signal.** The series is present. The series reflects reality (a gauge that
  never moves is a silent no-op).
- **Move the input, watch the signal.** State the input to change (for example, load on or off) and
  the signal that must change with it. A board that looks the same loaded and idle observes nothing.
- **Trace across hops.** For a path that crosses several agents or services, require a shared trace
  id in every structured log, so a wrong answer traces back to the hop that made it.
- **Name the human view.** State what the end consumer must see at a glance (what is where, and
  its state). Metrics serve alerts. The view serves a person.
- **Separate the exposition gate from the stack gate.** State which series are served without a
  monitoring stack, and which need the full scrape and alert stack.

## 3. Technology and constraints

State the technology and version for each verification and observation tool, verified against
official documentation. State the constraints the deploy stage must keep:
idempotent steps, a wall-clock budget instead of endless retry, contact with a human only at a wall,
and no credentials that outlive the sandbox. These are constraints. The architect does not write
the orchestrator, the harness or the dashboard.

## 4. Failure lessons that become criteria

These first-contact failures show what a spec should name up front. Each gives the criterion to add.

| Failure seen at runtime                          | Criterion to state in the spec                                       |
| ------------------------------------------------ | -------------------------------------------------------------------- |
| A runtime rewrote the command (args expansion)   | Verify the final rendered form, not the source.                      |
| A capability was missing from the shipped image  | Confirm the capability the way it ships, not the way it was assumed. |
| A shared pool (IPs, ports) was already claimed   | List the shared resources, and require an inventory before a claim.  |
| Late-bound config missed by a component at start | Require an explicit reload after the config lands.                   |
| A config edit changed nothing                    | Require the consumer to restart after a config change.               |
| A fault drill never fired                        | Require the self-healing controller to pause during the drill.       |
| A check read empty while the system was healthy  | Require the probe to confirm that it could have observed a pass.     |
| Every check failed with "VAR unset"              | Require the env contract (section 1) to be stated.                   |
| A pinned upstream version was broken             | Require a check that the exact pinned version runs.                  |
