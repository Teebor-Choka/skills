# Execution: from work package to a running, verified, observable system

The rest of this skill stops at "dispatch the agents." This file is what the reference
implementation learned by actually _deploying_ the package, unattended, on real clusters, with the
author not watching. The design disciplines (`principles.md`) still hold; these are the ones that
only surface at runtime, where the boundary moves from _what you wrote_ to _what actually runs_.

The offsite DB-replication design is again the running example: a publisher cluster (site), a mirror
cluster (central), and the logical-replication link between them.

## 1. The unattended deployment orchestrator

One script owns the whole bring-up end to end (`deploy.sh`): **preflight → waves → gates → verify →
self-heal**. The operator runs one command and walks away.

- **Waves mirror the DAG.** Bring up in the build order the development graph already computed
  (site → central → link), each wave gated GREEN before the next starts. The orchestrator is the DAG
  made executable.
- **Two kinds of gate, never conflated.** A _readiness gate_ waits for a thing to exist and settle
  (`wait_cluster`, `wait_job`, `wait_lb`, `wait_loadgen_schema`). A _verify gate_ asserts it behaves
  (calls the verification harness for that layer). "It's up" is not "it's correct", a cluster can be
  Ready and replicating nothing.
- **Idempotent by construction.** Every step must be safe to re-run: SQL guarded with `WHERE NOT
EXISTS … \gexec`, jobs that no-op if their effect is present. A retry after a wall must not
  double-apply.
- **Retry-until-wall with a budget, not infinity.** A `retry()` helper loops against a wall clock
  (`wall`), not forever. Hitting the wall is the _one_ time an unattended run contacts a human:
  "keep retrying until deemed impossible; prompt once at a wall." Everything short of the wall
  self-heals silently.
- **Report on a fixed cadence.** Emit progress every N minutes so an absent operator sees
  _convergence toward the goal_, not just liveness. Report pace, not a heartbeat.
- **Late-bound config needs an explicit settle step.** A component that reads config once at start
  (an exporter reading an RBAC-granted ConfigMap) will miss a grant that lands after it. Bake the
  reload into the orchestrator after the grant (`cnpg reload`), don't hope the timing works.

## 2. The executable verification harness (ATDD)

The spec's per-block test tables are the contract; the harness is their machine form. Authoring the
tests _from the spec_ (not from the code) is the ATDD discipline, the same rule as `specification.md`:
whoever wrote the code does not get to write its only tests.

- **Three-part shape.** A dispatcher (`verify.sh <layer|all|list>`), one script per block/PR
  (`checks/<layer>.sh`), and a shared assertion library (`_lib.sh`: `assert_eq/ge/match/nonempty/
metric`, cluster wrappers, `finish`). One block ↔ one layer ↔ one script keeps the mapping to the
  spec exact.
- **`all` prints a matrix; destructive is opt-in.** `verify.sh all` runs every non-destructive layer
  in stack order and prints a PASS/FAIL summary. Destructive layers (failover, fault injection) are
  excluded from `all` and run only behind an explicit flag, and only against the non-pilot env.
- **Positive AND adversarial in the same harness** (mirrors `principles.md` §4). Assert the _bad_
  behaviour, not just the good: a boolean cast to `::int` so a silent `false` is visible, an
  `assert_slot_protection` that fails loudly if the slot is unprotected.
- **The operator runs the same harness the orchestrator gates on**, same scripts, same env
  contract, no separate "test mode." The deploy gate and the manual check are one code path.
- **Distinguish operator error from system failure.** A mass-FAIL of "VAR unset" is a missing env
  contract, not a broken system. The orchestrator exports the contract; a human running the harness
  by hand must too, so the harness states its env contract up front rather than failing cryptically.
- **Test the test harness.** A dispatcher that iterates `"$@"` but only ran the first layer is a real
  bug the reference impl shipped. The harness is code; it gets the same scrutiny.

## 3. Observability as a first-class deliverable

Metrics and alerts are spec artifacts with their own blocks, tests, and gates, not a bolt-on.

- **Own your metric names.** Default exporters don't expose domain state (logical-slot health,
  subscription lag, `wal_level`, publication presence). Define custom queries so the alert
  expressions are _exact_, not guesses at what some built-in metric might be called
  (`cnpg_offsite_slot_*`, `cnpg_offsite_subscription_*`, `cnpg_offsite_config_*`).
- **Split the exposition gate from the stack gate.** `metrics` (series exposed at `:9187`, always
  live, needs no Prometheus) is separate from `enabled` (the full scrape + alert stack). The pilot
  tests real metrics on a cluster that has no monitoring stack at all.
- **Test presence AND working.** A metric that exists but never moves is a silent no-op, the
  observability version of the bug `principles.md` §4 warns about. Assert the series is served, _then_
  assert it reflects reality (`wal_level_logical == 1`, `subscription_state_enabled == 1`, worker
  count ≥ 1). Run these on the live infra, not just against a render.
- **Move the input, watch the signal.** The observability equivalent of "assert the bad behaviour":
  turn the load generator off (`set-load off`), watch the dashboard change, turn it back on. A board
  that looks identical loaded vs idle is observing nothing.
- **Trace across the hops.** For a path that crosses several agents or services, every call emits a
  structured log carrying a shared trace id (correlation id) threaded end to end. If a wrong answer
  cannot be traced back to the hop that produced it, the system is not observable yet — per-node logs
  without a shared id are noise at the boundary.
- **A separate human view.** A high-level live status board for the end consumer (`dashboard.sh
--watch / --html`) is distinct from the raw metrics: resolve pods once, fold the SELECTs into one
  query per cluster, derive component states (slot / link / mirror / load / pipeline) once, and show
  _what is where_ at a glance. Metrics are for alerts; the board is for a person.

## 4. Delivery & artifacting

- **Consolidate a review stack when review is the goal.** A tower of stacked PRs is right for
  building; collapse it into one PR for review, keeping _layered history plus the fixes on top_ so the
  reviewer sees both the intended shape and every correction. Make sure the single PR is
  self-deployable, nothing left behind in the stack.
- **Push rendered artifacts into the PR itself.** Diagrams and HTML renderings go into the PR
  description or a comment so a reviewer never has to build them, but artifacts start private, and
  _sharing_ them is the human's call, not the agent's.
- **The run-guide lives in the README, compressed** (deploy / watch / toggle load / read metrics), so
  the next operator never has to read the conversation transcript to run the thing.
- **Durable auth across ephemeral sandboxes.** Unattended runs die if credentials die with the
  sandbox. Symlink the token cache to a durable, repo-adjacent location and re-link it with a script
  that first _asserts the toolchain is in scope_ (fail with a clear message if the OIDC-capable
  `kubectl` isn't on PATH) rather than hard-coding a directory.

## 5. Running the agent fleet: shared baseline and merge discipline

The build DAG says what can run in parallel; this is how a fleet executing it stays coherent
against one git history.

- **Workers branch from the same baseline, and each can move it far.** Give every worker enough
  context to rebase onto the new baseline after a sibling lands, not just to produce its own diff.
- **Serialize the rebases through a merge queue.** Parallel execution is not parallel merges — a
  queue lands one worker at a time, so each rebases onto a known-good tree.
- **Some work is irreducibly serial.** A directory restructuring or a shared-interface change
  blocks every other worker; sequence it alone rather than forcing a merge storm.
- **Projects cycle between swarmable and serialize-only phases.** Recognize which phase you are in
  and staff accordingly; a serialize-only phase staffed like a swarm just manufactures conflicts.
- **Well-formed nodes make smoother swarms.** The disjoint-resource rule for DAG nodes (one owner
  per resource, no two nodes mutating the same file) is what keeps parallel merges clean — a swarm
  is only as conflict-free as the work division that fed it.

## 6. Execution-time failure catalog (first-contact lessons)

The walls the reference implementation actually hit on the way to GREEN. Each generalizes past its
specifics, the right column is the transferable rule.

| Symptom                                                                   | Root cause                                                                                                                                          | Fix                                                                                                       | General lesson                                                                                                                                                 |
| ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SQL breaks in a container: `$` collapses, `$(VAR)` expands                | k8s args expansion transforms the command string before the shell sees it                                                                           | named `$tag$` dollar-quote + `\gexec`; assert no literal `$` survives in the render                       | The runtime between your file and the process transforms it, render the _final_ form and inspect it, don't trust the source.                                   |
| `CREATE EXTENSION` fails, no `.control` file                              | the lib is preload-only in the operand image, not an installable extension                                                                          | drop the SQL; preload it, and let the guard assert the preload                                            | Verify a capability the way it's actually shipped (`Cimg`), not the way you assumed it ships.                                                                  |
| LoadBalancer stuck `<pending>`                                            | the requested IP was already taken by another service                                                                                               | move to a free IP in the pool; delete the stale service so it can rebind                                  | Inventory a shared resource pool before claiming from it; a pool is not yours by default.                                                                      |
| `CREATE SUBSCRIPTION … create_slot=true` fails inside a function/DO block | the statement must run at top level, not in a transaction/function                                                                                  | emit it top-level via `\gexec`                                                                            | Some statements are context-sensitive; check the statement's own execution-context constraints.                                                                |
| Custom metrics present on one side, absent on the other                   | the exporter's service account raced the RBAC/ConfigMap grant                                                                                       | `reload` after the grant; bake the reload into the orchestrator                                           | A component that reads config at startup needs an explicit reload after late-bound config; a race is fixed by a settle step, not luck.                         |
| `verify all` ran only the first of several layers                         | loop iterated `"$@"` incorrectly                                                                                                                    | iterate every arg                                                                                         | Test the test harness, it is code.                                                                                                                             |
| Whole suite FAILs with "VAR unset"                                        | run without the env contract the orchestrator normally exports                                                                                      | export the contract; document it in the harness                                                           | Rule out operator error before diagnosing a system failure.                                                                                                    |
| Generated HTML artifact is contaminated with junk at the top              | a shell `shellHook` wrote to stdout, mixing into the captured output                                                                                | redirect _inside_ `bash -c '… > file'`                                                                    | When generating an artifact, capture only the intended stream.                                                                                                 |
| Container won't exec a present binary (`exec: no such file or directory`) | a broken _upstream image release_, the binary is dynamically linked and that tag shipped without its interpreter (one bad version; neighbours fine) | pin a known-good tag; confirm the exact tag execs before building on it                                   | A published dependency can be broken at a _specific_ version, verify the version you pin actually runs; don't trust `:latest` or assume a tag is fine.         |
| Config edit has no effect (stale behaviour, `Unimplemented`)              | the ConfigMap changed but the Deployment mounting it was never restarted                                                                            | `rollout restart` the consumer, or a config-hash annotation on the pod template                           | Config lives in two places, the source object and the running process's mounted copy; changing one doesn't change the other.                                   |
| Fault-injection drill "never fires"                                       | a reconciler (ArgoCD `selfHeal`) reverted the injected fault before the alert could fire                                                            | suspend the reconciler for the drill, restore it after (via a trap)                                       | When testing failure on a self-healing system, pause the healer, or the test races the controller and you measure the heal, not the fault.                     |
| Verification reads empty while the system is healthy                      | a long-held `port-forward` died when the short-lived auth token expired mid-run; quick calls refreshed fine                                         | run the checks from _inside_ the system (quick calls only), don't hold a stream across the token lifetime | Don't infer failure from an absent signal the harness itself couldn't observe, move the probe off the fragile hop and confirm it _could_ have observed a pass. |

## The throughline

Every runtime surprise was a place where the paper design met a _transform_ (args expansion), a
_race_ (RBAC vs exporter start), a _shared resource it hadn't named_ (the IP pool), or a
_context constraint_ (top-level-only SQL). The disciplines don't change from design to execution;
_research, don't recall_, _assert the bad behaviour_, _prove the change is in the component under
test_. Execution just moves where they bite. Bring them across the boundary.
