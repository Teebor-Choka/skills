# Benchmarking Methodology

Rigorous performance measurement techniques for reliable optimization decisions.

## Reporting the result

A benchmark write-up is not a fixed form to fill in — it fits what you measured. It is done
when a reader can reproduce the run and trust the conclusion without talking to you.

It has to establish:

- The goal and the operation under test — the metric and threshold the change is judged against.
- The environment in enough detail to reproduce it — hardware, OS, runtime/build, and the load
  during the run.
- The methodology — the workload and how realistic it is, data size, warm-up, run count, cache state.
- Baseline and optimized results as distributions, each tagged with its commit — never a lone mean.
- The significance of the difference — the test used and its p-value, plus the effect size; no gain
  is claimed that the variance can't support.
- The tradeoffs the change takes on (memory, complexity, readability).
- An explicit accept or reject against the goal, following from the data above.

Report every run, not the favorable ones. If a number isn't reproducible from what you wrote down,
the report isn't done.

## Measuring — load what you need

The mechanics behind those requirements live in focused references; read only the one for the step
and language you're on rather than carrying it all at once:

- **Designing the measurement and computing the numbers** — `references/benchmark-measurement.md`:
  success criteria, representative workload, environment isolation, warm-up, multiple runs,
  variance, statistical significance and effect size, the before/after · A/B · scaling comparisons
  (with worked examples), and the measurement pitfalls to avoid.
- **Harness code — read only the language you're measuring:**
  `references/benchmark-tooling-typescript.md` (mitata, Benchmark.js) or
  `references/benchmark-tooling-rust.md` (criterion, `cargo bench` output).

## Resources

**Papers:**

- "Statistically Rigorous Java Performance Evaluation" (Georges et al.)
- "Producing Wrong Data Without Doing Anything Obviously Wrong!" (Mytkowicz et al.)

**Tools:**

- Criterion (Rust) — statistical benchmarking
- mitata (JavaScript) — modern benchmarking
- perf (Linux) — low-level profiling
- Flamegraph — visualization

**Validation:**

- Always review benchmark methodology with team
- Reproduce results on different hardware
- Document assumptions and limitations
- Update benchmarks as codebase evolves
