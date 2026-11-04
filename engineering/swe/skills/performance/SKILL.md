---
name: performance
description: >
  Find and fix performance problems with measurement: profile slow code paths, memory growth
  and allocation churn, cut latency (P95/P99) or CPU, raise throughput, tune database queries,
  and benchmark competing implementations or catch a regression. Use when the user mentions
  performance, profiling, a flame graph, optimization, latency, throughput, or "why is this
  slow". Read references/benchmarking.md before any benchmark. Not for guessing at
  bottlenecks or for optimizing code with no measured problem.
---

# Performance

Measure first. Change only what the measurement names. Measure again.

Sources for every rule below are in [references/sources.md](references/sources.md).

## Rule

Do not optimize without a measurement that shows the problem. Knuth's point is that about 97%
of small efficiencies are not worth the effort, and the critical 3% is found by measuring.

## Procedure

1. State the goal as a number: metric, workload, threshold (for example "P99 under 100 ms at
   500 requests per second").
2. Measure the baseline on a realistic workload, on the same machine and build you will compare
   against. Record the commit.
3. Locate the bottleneck, top down:
   1. Check each resource for utilization, saturation and errors (the USE method).
   2. Profile the code that owns the busy or saturated resource. Read the flame graph from the
      widest frames down. Use an off-CPU profile when the time is spent waiting.
4. State the cause in one sentence that the profile supports. If the profile names no cause,
   return to step 3. Do not guess.
5. Make one change. Keep it small enough to revert on its own.
6. Measure again with the same method. Keep the change only if the gain is larger than the
   run-to-run noise and the metric moves toward its threshold.
7. Check for regressions in the other metrics: memory, tail latency, binary size, correctness.
8. Record baseline, change, result and trade-offs where the next reader looks (commit body, PR,
   or the project docs).

Stop when the goal is met. Further gains need a new goal.

## Choosing what to read

| Need                                                      | Read                                                                                     |
| --------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Metric definitions, targets, how to report a distribution | [references/kpis.md](references/kpis.md)                                                 |
| Any benchmark (always, before you write one)              | [references/benchmarking.md](references/benchmarking.md)                                 |
| Run design, variance, significance, pitfalls              | [references/benchmark-measurement.md](references/benchmark-measurement.md)               |
| Rust profiling, build settings                            | [references/profiling-rust.md](references/profiling-rust.md)                             |
| Rust benchmark harness                                    | [references/benchmark-tooling-rust.md](references/benchmark-tooling-rust.md)             |
| TypeScript or Bun profiling                               | [references/profiling-typescript.md](references/profiling-typescript.md)                 |
| TypeScript benchmark harness                              | [references/benchmark-tooling-typescript.md](references/benchmark-tooling-typescript.md) |
| A bottleneck class is named and you need options          | [references/optimization-patterns.md](references/optimization-patterns.md)               |

Read only the file for your language and step.

## Measurement traps

- A mean hides the tail. Report the distribution (P50, P95, P99, max) as a histogram or buckets.
- A load generator that waits for each reply before it sends the next hides queueing delay
  (coordinated omission). Drive latency tests at a fixed arrival rate.
- Setup details shift results: environment size, link order and memory layout can move a
  benchmark by more than the change under test. Repeat runs and vary the setup.
- Noisy wall time needs many runs. Instruction or cycle counts are stable but do not equal
  user-visible time. Use both when the gain is small.
- A benchmark that does nothing observable can be optimized away. Consume the result.
- Poor measurement still beats none. Start with a rough benchmark and improve it when a
  decision depends on a small difference.

## Done when

- The goal metric meets its threshold on the realistic workload.
- The gain exceeds the noise across repeated runs, with the data kept.
- No tracked metric got worse without a stated reason.
- Tests pass and the behavior is unchanged.
- Baseline, change, result and trade-offs are recorded.

## Related skills

- `swe:rust` and `swe:typescript` for the language rules a change must still follow.
- `review:code-quality` to check the cost in complexity before you merge an optimization.
