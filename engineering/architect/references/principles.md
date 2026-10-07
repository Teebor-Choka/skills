# Architect disciplines: what separates a work package from a design doc

These are the values visible in every artifact of the reference implementation; the document
templates are just where they land.

## 1. No information loss

The directory is the source of truth; the conversation that produced it is disposable. The test:
**a fresh session or a new agent can take over from the directory alone** and lose nothing. Every
brief is self-contained; every decision is logged; the README says where to start. If a fact lives
only in the chat, it isn't captured yet.

## 2. Ground truth over assumption: research actively

The hard part is knowing what is actually true, not writing it down. Never reason from memory or a
training snapshot on anything load-bearing, **research it**:

- **Web-search what's currently available** before committing to an approach. Tools, versions, licenses,
  and capabilities move; the reference implementation's entire escalation appendix (which off-the-
  shelf tool to reach for) came from a survey of the 2026 CDC-tool field.
- **Verify every load-bearing claim against official documentation** (and the real repo/config), not
  against recall. Docs are version-specific. Check the version you are on. The reference impl read
  the PG17 _and_ PG18 libpq docs specifically, which overturned a plausible-from-memory "just upgrade
  for compression" premise.
- **Cite every source with a URL or repo path.** The proposal ends with a numbered Sources list; the
  decision log's verified-facts table records _how_ each fact was checked. Traceability is what lets
  a later reader re-verify instead of re-trusting.
- **Flag what you couldn't verify** rather than asserting it: the reference proposal explicitly
  marked a docs page it could not fetch instead of stating its content as fact.

Keep a hard line between **verified fact** (checked against a doc / repo / search; record how) and
**domain knowledge** ("someone said so", a real constraint, but flag that no policy or code backs it
yet).

Never infer a fact from an absent log line, an empty grep, or a missing artifact. First confirm the
thing _could_ have been observed (log level, right target, artifact not deleted, non-stale binary),
then assert it.

## 3. Every decision carries rationale + grounding

The decision log exists so nothing is re-derived or re-litigated. Each decision is **Decision → Why
→ Grounding**. Rejected alternatives go in a "considered and set aside: do not re-propose without
new information" list, stated _fairly_ (a strong alternative dismissed unfairly invites re-opening).
When a decision corrects an earlier premise, say so explicitly and leave the superseded reasoning on
the record.

## 4. Adversarial by construction

Attack the design before reality does. This is a high-leverage habit.

- **Design level:** every proposal ends with a **validation pass**: "what did this direction open
  up?" A design change trades one set of problems for another; name the new ones and show each is
  fixed above or tracked as an open item. A validation pass that finds nothing did not run.
- **Block level:** every block carries **adversarial (negative) tests** beside its positive ones.
  A positive test with no negative counterpart is exactly where silent no-ops hide.
- **Assert the bad behaviour.** A zero limit, a disabled gate, a refused-unprotected slot, a silent
  drop must produce an _observable_ signal. A silent no-op is externally indistinguishable from
  correct behaviour. That is what makes bugs expensive. Name the fault-injection point for each.
- **Prove the change is in the component under test.** Name every participant and which build it
  runs before measuring; a "no effect" from a component never in the path reads like a broken fix.

## 5. Off-the-shelf over hand-built

The highest-risk work in any pipeline is the bespoke part (a custom decoder, an apply worker, a
hand-rolled buffer). Prefer a tool that already does it. When the primary design might prove
insufficient, carry an **escalation appendix** of off-the-shelf options, each matched to a
_different_ shortfall (compression vs DDL vs engine), with its license and footprint cost, rather
than a plan to build. Never hand-build what a maintained tool does.

## 6. Name the one hinge decision

Most designs turn on a single measurement or gate: the one number that decides
ship-native vs escalate, the one capacity ceiling nobody has measured. Find it, state it plainly in
the README, and if it is still open, say so and make closing it the top open item. An undefined gate
("does it fit?") is a judgment call, not a gate; pin sustained-vs-peak, the window, the margin, and
the exact inequality before calling it one.

## 7. Structurally complete ≠ finalized

A work package is internally consistent and executable long before every number is real. Keep the
two states distinct: list the open items with concrete close conditions, and let the README say
"structurally complete, NOT finalized". Reserved numbers (thresholds, retention, bounds, lag) are
produced by the pilot _by design_, not guessed on paper. Say which are TBD and where they'll come
from.

## 8. Execution order is the structure

The build order _is_ the plan; a flat list of features is not. Group preconditions as Block 0 and
number blocks in the order they run. Engineering the dependencies into a DAG (waves, barriers,
loops, elimination) is a separate step: planning the work for the agents; this principle is only the
reason it matters.

## 9. Design it twice, and know a wrong design when you see one

Do not ship the first structure that occurs to you. Sketch **at least two structurally distinct
designs** before committing, even when the first looks sufficient, and synthesize the strongest.

- **Selection criterion: interface depth.** Prefer the design that hides the most complexity behind
  the smallest, simplest interface. A deep module (a lot of function, a narrow surface) beats a
  shallow one whose interface is almost as complex as what it hides.
- **Screen candidates against structural red flags:** _information leakage_, where one block's
  internal detail is forced on its neighbours; _temporal coupling_, where block B works only because A
  ran just before and nothing enforces it; a _pass-through block_ that only forwards its input; a
  _boundary leak_, where a module or the site/central boundary exposes its internals.
- **Scrap signals.** When execution needs the same workaround across unrelated blocks, accumulates
  escape hatches, or throws up several independent deviations of the same shape, the decomposition is
  wrong. Re-derive it from first principles; do not patch a wrong design (see §7).

Source: John Ousterhout, _A Philosophy of Software Design_: deep modules, information hiding, the red
flags, and "design it twice".

## 10. Trade-offs, characteristics, and fitness functions (Ford & Richards)

The Ousterhout discipline shapes a module; these shape the whole-system choice. Source: Richards &
Ford, _Fundamentals of Software Architecture_, and Ford et al., _Building Evolutionary
Architectures_. The full style catalog with diagrams and scorecards is in `architecture-styles.md`.

- **Everything is a trade-off.** The First Law: "Everything in software architecture is a
  trade-off. If you think you've found something that isn't a trade-off, you likely just haven't
  identified the trade-off yet." Every recommendation names at least one thing it costs. A claimed
  pure win is a signal to look harder, not to celebrate.
- **Why over how.** The Second Law: "Why is more important than how." The decision log's rationale
  and grounding matter more than the diagram. A structure with no recorded why is not yet designed.
- **Answer "it depends," then discharge it.** The honest first answer to an architecture question
  is "it depends"; a recommendation is done only once the "it depends" is resolved into the
  specific drivers (which characteristics, at what scale, under what constraints) that made this
  option the least-worst here. Aim for the least-worst architecture, never the "best."
- **Name the driving characteristics, and keep them few.** Bucket each into operational
  (availability, scalability, elasticity, performance, recoverability), structural (modularity,
  deployability, testability, configurability), or cross-cutting (security, usability,
  observability). Then choose the fewest that let the system succeed. Supporting more "-ilities"
  than needed is generic overengineering: a design that tries to solve every problem solves none
  well. _Check:_ the driving list is short (roughly seven or fewer), and removing any one would
  break a stated requirement.
- **Every characteristic you claim gets a fitness function, or it is only an aspiration.** A
  fitness function is "any mechanism that provides an objective integrity assessment of some
  architecture characteristic." _Check:_ each driving characteristic has a test, metric, monitor,
  chaos experiment, or lint rule that returns pass/fail against a threshold. A characteristic with
  no fitness function is unfalsifiable; reject the claim or write the function. This is the same
  discipline as §4: **the fitness function is the architecture-level adversarial test, and the
  verification harness (`execution.md`) is where these functions live and run.** Prefer holistic,
  continual functions for the properties most likely to erode silently: scalability, security,
  coupling.
- **Contain the strongest coupling in the smallest boundary.** Reason about coupling with
  connascence: static forms (name, type, meaning, position) are weaker than dynamic ones (execution
  order, timing, value, identity). Reduce strength and degree, increase locality. _Check:_ the
  strongest connascence sits inside one module or service, never spread across a network hop.
- **Count the quanta before going distributed.** An architecture quantum is an independently
  deployable unit with high functional cohesion and synchronous coupling; the database usually
  belongs to it. _Check:_ if the system is one quantum, a multi-quantum style (microservices) is
  unjustified. See `architecture-styles.md` for the choice.

Sources: Richards & Ford, _Fundamentals of Software Architecture_ (O'Reilly, 2020/2025); Ford,
Parsons, Kua & Sadalage, _Building Evolutionary Architectures_, 2nd ed. (O'Reilly, 2022); Ford et
al., _Software Architecture: The Hard Parts_ (O'Reilly, 2021). Full URLs in `architecture-styles.md`.
