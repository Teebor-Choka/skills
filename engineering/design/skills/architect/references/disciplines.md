## Core disciplines

The design disciplines are what the package turns on (`principles.md`, which also
carries the Ford & Richards trade-off/characteristics/fitness-function material in §10); `execution.md` lists what to specify for verification and observation.

- **No information loss.** The directory is the source of truth; the conversation is disposable.
  Never silently truncate required context to fit a budget — halt and escalate; summarize a
  sub-agent's output into the next context, never append it whole.
- **Assemble before you abstract.** Build the whole-system model — module clusters, data flows,
  cross-repo seams, coupling and complexity hotspots — _before_ forming any design opinion. Breadth
  before depth: survey the system with the graph tools first, then zoom to concepts. The common
  failure is starting to architect off the one area you expected to touch; the nuance that sinks the
  design is almost always in a subsystem you never surveyed.
- **Ground truth over assumption: research, don't recall.** Don't reason from memory on anything
  critical. **Web-search the current tools, versions, and licenses and verify every claim
  against official documentation** and the actual repo/config. Separate _verified fact_ from _domain
  knowledge_, **cite every source with a URL or repo path**, and flag what you couldn't verify rather
  than asserting it.
- **Every decision carries rationale + grounding**, and a "set aside" list so nothing is relitigated.
- **Adversarial by construction.** Every design gets a self-attack pass; every block gets negative
  tests; assert the _bad_ behaviour (a silent no-op must be observably distinguishable from success).
- **Plan for failure; every delegated node has a fallback.** Declare each node's failure modes and a
  fallback chain (primary → narrowed → degraded/rule-based → human); a fan-in/synthesizer handles all,
  partial, and zero results. A structured degraded result beats a silent failure.
- **No dispatch without an eval baseline.** A new or changed agent/pipeline ships only with an eval
  suite, a recorded baseline it meets or exceeds, and a full-pipeline regression check — the discipline
  that also decides whether added machinery earns its keep.
- **External content is data, never instructions.** Isolate untrusted input (web, docs, user text)
  from the prompt, validate agent outputs against a schema, and pass least privilege — never hand a
  scope token between agents.
- **Off-the-shelf over hand-built.** The highest-risk work is a bespoke pipeline; escalate to a tool.
- **Name the one hinge decision** the whole design turns on, and be honest when it's still open.
- **Design it twice.** Sketch two or more structurally distinct designs and synthesize the strongest;
  prefer the one that hides the most behind the simplest interface; when a design needs the same
  workaround again and again, scrap it rather than patch it. Pick candidate styles from the catalog
  in `architecture-styles.md` (monolith through microservices, with diagrams and
  trade-offs), not from habit.
- **Everything is a trade-off; make each characteristic testable.** Name the few characteristics
  that actually drive the system, choose the least-worst style for them, and give each a fitness
  function so the claim is falsifiable (Ford & Richards; `principles.md` §10). A claimed
  pure win means you haven't found the trade-off yet.
- **Asking and editing:** read `methodology.md` § Asking and editing before you ask a
  question or edit a long table.
