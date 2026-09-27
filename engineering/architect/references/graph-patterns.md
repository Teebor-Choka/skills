# Graph-engineering patterns: shapes for dividing work

Graph engineering is the discipline of splitting a settled design into a shape a fleet of agents
can execute together. Its job ends at the division: pick the shape, name the nodes and their true
dependencies, and hand off. It does not oversee how the agents then do the work; a good split lets
them collaborate on their own.

Most of the mechanical part is deterministic and belongs to `scripts/graph.py`: given the nodes,
their dependencies, and their write-sets, the script computes the waves, removes redundant edges,
finds the critical path and barriers, catches write-set collisions, and draws the graph. This file
is the judgment the script cannot make: which _shape_ fits the kind of work, and whether the agents
coordinate through a controller or among themselves.

Contents: [choosing a shape](#choosing-a-shape) · [1 parallelization](#1-parallelization--splitting)
· [2 sequential / routing](#2-sequential--routing) · [3 loops](#3-loops--iteration)
· [4 coordination](#4-coordination--collaboration) · [5 elimination](#5-elimination--graph-shaping)
· [6 structural](#6-structural--meta)
· [foundational research](#foundational-research-graph-engineering-for-multi-agent-workflows) · [sources](#sources)

Each coordination entry is tagged **[C]** choreography (agents self-coordinate, no boss), **[O]**
orchestration (a controller owns the plan), or **[either]**. The skill's philosophy leans **[C]**:
split the work so the pieces collaborate through shared conventions, and reach for a controller only
when ordering, merging, or compensation genuinely need one.

## Choosing a shape

- **Independent, homogeneous items** (many files, many docs): fan-out / sectioning / map-reduce, then
  synchronize. Add speculative race only if stragglers hurt.
- **Independent, heterogeneous sources** (query several services or experts): scatter-gather; add
  voting/ensemble when you need one trusted answer.
- **A hard single task, verifiable in steps**: prompt chaining (fixed steps) or a ReAct loop
  (unknown steps).
- **Quality matters and is judgeable**: wrap the producer in an evaluator-optimizer loop, bounded by
  a count or a milestone.
- **Input types need different handling**: routing, or peer handoff between specialists.
- **A big goal, subtasks unknown at design time**: orchestrator-workers, or hierarchical
  decomposition down a tree.
- **A big goal, subtasks discoverable by peers, wanting scale**: contract-net (bidding), a blackboard
  (shared workspace), or pub-sub choreography.
- **Open-ended reasoning or cross-checking**: group chat or debate, then vote.
- **Multi-step work that must not half-complete**: a saga with compensations.
- **Before scheduling any graph**: topological order for sequence, critical path to find what to
  shorten, transitive reduction and dedup to shrink it. `scripts/graph.py` does these for you.

## 1. Parallelization / splitting

| Pattern                       | Also known as                | What it is / when                                                                                      | Src     |
| ----------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------ | ------- |
| **Parallel split**            | AND-split, fork, concurrency | one thread diverges into N branches that run at once; independent, order-free subtasks                 | [1]     |
| **Synchronization**           | AND-join, barrier            | wait for all N branches, then continue; the mandatory partner of a split when results combine          | [1]     |
| **Fan-out / fan-in**          | scatter-gather, sectioning   | dispatch many independent units, then collect; the general shape behind map-reduce                     | [3]     |
| **Map-reduce**                | —                            | same map on each shard in parallel, then reduce; large homogeneous corpora, uniform per-item work      | [9]     |
| **Scatter-gather**            | broadcast-aggregate          | broadcast one request to many providers, aggregate replies; querying heterogeneous sources             | [10]    |
| **Fork-join**                 | divide and conquer           | recursively fork subtasks, join results, work-steal over idle workers; uneven subtask sizes            | [11]    |
| **Static vs dynamic fan-out** | multiple instances           | branch count fixed at design time vs decided at runtime from data (one worker per discovered item)     | [1]     |
| **Speculative / race**        | hedged requests              | launch redundant attempts, take the first, cancel the rest; cut tail latency or a stall-prone approach | [12]    |
| **Voting / ensemble**         | N-version, self-consistency  | run N solvers on the same input and vote; correctness-critical or high-variance work                   | [3][13] |
| **Bulkhead**                  | isolation                    | partition workers into isolated pools so one branch's failure can't sink the rest                      | [14]    |

`scripts/graph.py` enforces the constraint that makes a parallel wave valid: the nodes' write-sets
must be disjoint. Two nodes that mutate the same resource are serialized or split, never run together.

## 2. Sequential / routing

| Pattern                                | Also known as                                              | What it is / when                                                                               | Src        |
| -------------------------------------- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ---------- |
| **Sequence**                           | chain                                                      | B runs only after A; step k needs step k-1's output                                             | [1]        |
| **Prompt chaining**                    | —                                                          | one task as a fixed series of calls with checks between; a hard task broken into verified steps | [3]        |
| **Routing**                            | exclusive choice, XOR-split, content-based router, handoff | classify input, send it down exactly one path; input types need different handling              | [1][3][15] |
| **Pipeline**                           | pipes-and-filters, producer-consumer                       | staged hand-off where stages overlap on a stream; throughput work on flowing data               | [16]       |
| **Multi-choice + synchronizing merge** | OR-split / OR-join                                         | activate one-or-more branches by condition, merge the ones that fired                           | [1]        |
| **Topological order**                  | —                                                          | order a DAG so each dependency precedes its dependents; the scheduling backbone                 | [7]        |
| **Critical path**                      | longest path                                               | the longest dependency chain sets the minimum end-to-end time; shorten _this_, not elsewhere    | [17]       |

## 3. Loops / iteration

| Pattern                        | Also known as                               | What it is / when                                                                                        | Src     |
| ------------------------------ | ------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------- |
| **Evaluator-optimizer**        | generator-critic, maker-checker, reflection | a producer paired with a separate critic, loop until it passes; quality is judgeable and iterable        | [3][18] |
| **ReAct / agentic loop**       | reason-act-observe                          | interleave reason, act, observe until the goal is met; tools needed, step count unknown                  | [19]    |
| **Structured loop**            | while / repeat-until                        | single entry and exit, explicit condition; the safe way to repeat                                        | [1]     |
| **Loop-until-count**           | —                                           | iterate a bounded number of times; a guaranteed-termination guard on any loop                            | [1]     |
| **Loop-until-dry**             | drain a queue                               | pull from a work queue until empty; dynamic fan-out that feeds itself (a crawl frontier)                 | [1]     |
| **Milestone / temporal guard** | —                                           | allow or stop iteration on a state or deadline; bound reflection by wall-clock or budget, not only count | [1]     |
| **Recursion**                  | —                                           | a node re-instantiates the same shape on a subproblem; tree-structured problems                          | [1]     |

Avoid **arbitrary cycles** (goto, multi-entry loops): they defeat termination reasoning. Every loop
gets an exit condition and a bound. Record loops in the spec's `loops` list so `graph.py` registers
each with its exit and bound. [20]

## 4. Coordination / collaboration

The heart of "split work, agents collaborate themselves." Prefer the **[C]** forms: they need only a
shared convention (a workspace, an event schema, a bidding protocol), not a controller.

| Pattern                              | Lean     | What it is / when                                                                                                                                                   | Src      |
| ------------------------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| **Orchestrator-workers**             | [O]      | a central agent decomposes at runtime, delegates, synthesizes; subtasks unknown upfront, results must merge coherently                                              | [3]      |
| **Handoff / agents-as-tools**        | [C]      | an agent transfers control to whichever peer suits, no central boss; dynamic peer-to-peer routing                                                                   | [15]     |
| **Hierarchical decomposition**       | [O]      | recursively break a goal into subgoals down a tree of sub-agents; large goals with sub-structure                                                                    | [21]     |
| **Group chat / debate / consensus**  | [C]      | agents share one thread, a turn policy picks the next speaker, answers emerge from discussion and voting; open-ended reasoning, cross-checking                      | [22][23] |
| **Blackboard**                       | [C]      | independent specialists read and write a shared workspace, contributing when the state lets them; no fixed pipeline                                                 | [24]     |
| **Contract-net / market / auction**  | [C]      | a manager announces a task, agents bid, the best bid wins; dynamic allocation across capable-but-heterogeneous agents                                               | [25][26] |
| **Publish-subscribe / event-driven** | [C]      | producers emit events, subscribers react, decoupled in time and space; the substrate under choreography                                                             | [27]     |
| **Saga**                             | [either] | a sequence of local steps each with a compensating undo, so partial failure rolls back; multi-step work that must be all-or-nothing without a global lock           | [28]     |
| **Stigmergy / self-organization**    | [C]      | agents coordinate indirectly through traces in a shared environment, no messaging or controller; large swarms, emergent coordination                                | [29]     |
| **Orchestration vs choreography**    | [either] | the axis itself: central control buys observability and ordering but is a bottleneck; self-coordination buys scale and loose coupling but makes global state harder | [30]     |

The practical middle ground most fleets use: a thin split-and-merge at the edges, with choreographed
collaboration (a shared workspace or events) among the workers in between.

## 5. Elimination / graph-shaping

The cheapest work is the work removed. Do this before scheduling. `scripts/graph.py` performs
transitive reduction automatically and reports the cut edges; the rest is judgment.

| Pattern                      | Also known as                    | What it is / when                                                                                                | Src     |
| ---------------------------- | -------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------- |
| **Transitive reduction**     | minimum equivalent graph         | remove edges a longer path already implies, keeping reachability but maximizing parallelism (done by `graph.py`) | [8]     |
| **Dead-node elimination**    | dead-code elimination            | drop nodes whose output nothing downstream consumes                                                              | classic |
| **Redundancy / dedup**       | common-subexpression elimination | collapse duplicate nodes so shared work runs once                                                                | classic |
| **Cancellation**             | kill speculative siblings        | once a racing branch wins, cancel the losers to reclaim resources                                                | [1]     |
| **Subsume by off-the-shelf** | build to adopt                   | replace a whole subgraph with an existing tool that already solves it; verify the claim first                    | [3]     |

**Subsume is the highest-value cut**, and it rests on a claim about the outside world. Verify a
"a tool already does this" cut against current docs before deleting the node, per the skill's
research-don't-recall discipline. Record the source next to the cut.

## 6. Structural / meta

- **Start simplest.** Use the least machinery that works: a single call, then a workflow, then
  agents. Add structure only when it demonstrably helps. Manufactured parallelism with colliding
  write-sets is slower and wronger than an honest sequence. [3]
- **Composability.** The shapes nest: a worker inside an orchestrator can itself be an
  evaluator-optimizer loop; a route can feed a chain. Build from small shapes, not one mega-pattern. [3]
- **Static vs dynamic graph.** Fix the graph at design time (predictable, analyzable) or let an agent
  grow it at runtime from intermediate results (flexible). Static for reliability and audit, dynamic
  for open-ended work. [5]
- **Decomposition granularity.** Match a node to a unit one agent can own end to end. Too coarse
  loses parallelism; too fine drowns in coordination overhead. [3]

## Foundational research: graph engineering for multi-agent workflows

The patterns above are the working vocabulary; this is the peer-reviewed research behind treating a
multi-agent system as an engineered graph. Read the survey first for the map, then GPTSwarm and AFlow
for the two core ideas (a multi-agent system is an optimizable graph; a workflow is a searchable
space), and van der Aalst for the rigorous pattern language. Each is tagged by authority; the one
preprint-only source and the two single-agent-reasoning ones are flagged so they are not overclaimed.

**Start here (the field map)**

- Guo et al., "Large Language Model based Multi-Agents: A Survey of Progress and Challenges",
  _IJCAI 2024_ (survey track, peer-reviewed). The best single entry point. https://doi.org/10.24963/ijcai.2024/890
- Tran et al., "Multi-Agent Collaboration Mechanisms: A Survey of LLMs" (2025). The best taxonomy of
  collaboration _structure_ (peer-to-peer / centralized / distributed). **Preprint, not yet
  peer-reviewed.** https://arxiv.org/abs/2501.06322

**Agents as graphs, and workflows as a searchable space (the core of graph engineering)**

- Zhuge et al., "GPTSwarm: Language Agents as Optimizable Graphs", _ICML 2024_ (oral). The canonical
  "a multi-agent system is an editable, optimizable computational graph" formulation. https://proceedings.mlr.press/v235/zhuge24a.html
- Zhang et al., "AFlow: Automating Agentic Workflow Generation", _ICLR 2025_ (oral). The reference for
  searching the space of workflow graphs (MCTS over code-with-edges). https://arxiv.org/abs/2410.10762
- Hu, Lu & Clune, "Automated Design of Agentic Systems (ADAS)", _ICLR 2025_. A meta-agent programs new
  agents in code; the design-vs-optimize companion to AFlow. https://arxiv.org/abs/2408.08435
- Qian et al., "Scaling Large-Language-Model-based Multi-Agent Collaboration (MacNet)", _ICLR 2025_.
  Organizes 1000+ agents as DAGs and shows topology itself drives performance. https://arxiv.org/abs/2406.07155
- Liu et al., "A Dynamic LLM-Powered Agent Network (DyLAN)", _COLM 2024_. Canonical reference for
  _dynamic_ graph structure that prunes low-value agents at runtime. https://arxiv.org/abs/2310.02170

**Framework papers behind the coordination patterns** (cite these, not the repos)

- Wu et al., "AutoGen", _COLM 2024_ (group chat). https://arxiv.org/abs/2308.08155
- Hong et al., "MetaGPT", _ICLR 2024_ (oral; SOP-encoded assembly line). https://arxiv.org/abs/2308.00352
- Li et al., "CAMEL", _NeurIPS 2023_ (role-playing communicative agents). https://arxiv.org/abs/2303.17760
- Du et al., "Improving Factuality and Reasoning through Multiagent Debate", _ICML 2024_. https://arxiv.org/abs/2305.14325
- Khattab et al., "DSPy", _ICLR 2024_ (declarative, compilable LM pipelines). https://arxiv.org/abs/2310.03714

**Classic theory, authoritative and underused**

- van der Aalst, ter Hofstede, Kiepuszewski & Barros, "Workflow Patterns", _Distributed and Parallel
  Databases_ 14(1):5–51, 2003. The definitive control-flow pattern language, the actual paper behind
  workflowpatterns.com. https://doi.org/10.1023/A:1022883727209
- Kwok & Ahmad, "Static Scheduling Algorithms for Allocating Directed Task Graphs to
  Multiprocessors", _ACM Computing Surveys_ 31(4):406–471, 1999. The authoritative survey of DAG
  task-graph scheduling (list scheduling, critical path, NP-completeness). https://doi.org/10.1145/344588.344618

**Graph-structured reasoning (single-agent; topology priors, not orchestration)**

- Yao et al., "Tree of Thoughts", _NeurIPS 2023_. https://arxiv.org/abs/2305.10601
- Besta et al., "Graph of Thoughts", _AAAI 2024_. https://arxiv.org/abs/2308.09687

These two structure one agent's _reasoning_, not a fleet's coordination; they inform edge semantics
(aggregation, feedback) but are not multi-agent orchestration. Do not cite them as the latter.

## Sources

1. Workflow Control-Flow Patterns (Russell, ter Hofstede, van der Aalst, Mulyar): http://www.workflowpatterns.com/patterns/control/
2. Anthropic, "Building Effective Agents" (chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer, start-simplest, composability): https://www.anthropic.com/engineering/building-effective-agents
3. Dapr Agents patterns (static vs LLM-grown graphs): https://docs.dapr.io/developing-ai/dapr-agents/dapr-agents-patterns/
4. Topological sorting: https://en.wikipedia.org/wiki/Topological_sorting
5. Transitive reduction — Aho, Garey & Ullman, _SIAM J. Computing_ 1(2):131–137, 1972 (primary): https://doi.org/10.1137/0201008 (overview: https://en.wikipedia.org/wiki/Transitive_reduction)
6. Dean & Ghemawat, MapReduce (OSDI 2004): https://research.google/pubs/mapreduce-simplified-data-processing-on-large-clusters/
7. Enterprise Integration Patterns, Scatter-Gather: https://www.enterpriseintegrationpatterns.com/patterns/messaging/BroadcastAggregate.html
8. Doug Lea, A Java Fork/Join Framework: https://gee.cs.oswego.edu/dl/papers/fj.pdf
9. Dean & Barroso, The Tail at Scale, _CACM_ 56(2):74–80, 2013: https://doi.org/10.1145/2408776.2408794 (https://cacm.acm.org/research/the-tail-at-scale/)
10. N-version programming — Avizienis, "The N-Version Approach to Fault-Tolerant Software", _IEEE TSE_ SE-11(12):1491–1501, 1985 (primary): https://doi.org/10.1109/TSE.1985.231893 (overview: https://en.wikipedia.org/wiki/N-version_programming)
11. Bulkhead pattern (Nygard, Release It!): https://en.wikipedia.org/wiki/Bulkhead_pattern
12. Agent handoffs — OpenAI Agents SDK: https://github.com/openai/openai-agents-python (supersedes the experimental Swarm: https://github.com/openai/swarm)
13. Enterprise Integration Patterns, Pipes and Filters: https://www.enterpriseintegrationpatterns.com/patterns/messaging/PipesAndFilters.html
14. Critical path method: https://en.wikipedia.org/wiki/Critical_path_method
15. Shinn et al., Reflexion: https://arxiv.org/abs/2303.11366
16. Yao et al., ReAct (2022): https://arxiv.org/abs/2210.03629
17. Structured programming — Dijkstra, "Go To Statement Considered Harmful", _CACM_ 11(3):147–148, 1968 (primary): https://doi.org/10.1145/362929.362947 (overview: https://en.wikipedia.org/wiki/Structured_programming)
18. Hierarchical task network: https://en.wikipedia.org/wiki/Hierarchical_task_network
19. AutoGen multi-agent conversation: https://microsoft.github.io/autogen/stable/ (paper: Wu et al., COLM 2024, https://arxiv.org/abs/2308.08155)
20. Du et al., multi-agent debate: https://arxiv.org/abs/2305.14325
21. Nii, The Blackboard Model of Problem Solving (AI Magazine 1986): https://ojs.aaai.org/aimagazine/index.php/aimagazine/article/view/537
22. Smith, "The Contract Net Protocol", _IEEE Transactions on Computers_ C-29(12):1104–1113, 1980: https://doi.org/10.1109/TC.1980.1675516
23. FIPA agent communication standards — Communicative Act Library (SC00037J, 2002) and Message Structure (SC00061G, 2002). The fipa.org domain has lapsed and now serves unrelated content; cite via the IEEE FIPA standards or a web archive, e.g. https://web.archive.org/web/2020*/http://www.fipa.org/specs/fipa00037/SC00037J.html
24. Eugster et al., The Many Faces of Publish/Subscribe (ACM Computing Surveys 2003): https://dl.acm.org/doi/10.1145/857076.857078
25. Garcia-Molina & Salem, "Sagas", _ACM SIGMOD_ 1987, pp.249–259: https://doi.org/10.1145/38713.38742 (PDF: https://www.cs.cornell.edu/andru/cs711/2002fa/reading/sagas.pdf · secondary: https://microservices.io/patterns/data/saga.html)
26. Stigmergy: https://en.wikipedia.org/wiki/Stigmergy
27. Orchestration vs choreography (Camunda): https://camunda.com/blog/2023/02/orchestration-vs-choreography/

"classic" = a standard compiler/graph technique (dead-code and common-subexpression elimination) with no single canonical source.
