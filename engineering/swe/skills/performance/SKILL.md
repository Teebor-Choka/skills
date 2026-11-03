---
name: performance
description: >
  Profile code, optimize bottlenecks, and benchmark implementations. Use when the user
  mentions performance, profiling, optimization, or --perf; when diagnosing slow code
  paths, memory leaks, or excessive allocations; when reducing latency (P95/P99), CPU
  usage, or improving throughput (RPS, ops/sec); when benchmarking competing
  implementations; or when working on database query optimization. Read
  references/benchmarking.md before starting any benchmark.
---

# Performance engineering

Evidence-based performance optimization: measure, profile, optimize, then validate.

## Use when

- Profiling slow code paths or bottlenecks
- Identifying memory leaks or excessive allocations
- Optimizing latency-critical operations (P95, P99)
- Benchmarking competing implementations
- Database query optimization
- Reducing CPU usage in hot paths
- Improving throughput (RPS, ops/sec)

**Not for:** premature optimization, optimization without measurement, guessing at
bottlenecks.

## Iron law

**NO OPTIMIZATION WITHOUT MEASUREMENT**

Required workflow:

1. Measure baseline performance with realistic workload
2. Profile to identify actual bottleneck
3. Optimize the bottleneck (not what you think is slow)
4. Measure again to verify improvement
5. Document gains and tradeoffs

Optimizing unmeasured code wastes time and introduces bugs.

## Stages

Load the **maintain-tasks** skill for stage tracking:

**Stage 1: Establishing baseline**

- content: "Establish performance baseline with realistic workload"
- activeForm: "Establishing performance baseline"

**Stage 2: Profiling bottlenecks**

- content: "Profile code to identify actual bottlenecks"
- activeForm: "Profiling code to identify bottlenecks"

**Stage 3: Analyzing root cause**

- content: "Analyze profiling data to determine root cause"
- activeForm: "Analyzing profiling data"

**Stage 4: Implementing optimization**

- content: "Implement targeted optimization for identified bottleneck"
- activeForm: "Implementing optimization"

**Stage 5: Validating improvement**

- content: "Measure performance gains and verify no regressions"
- activeForm: "Validating performance improvement"

## Key performance indicators

Metric definitions and what to watch (latency P50–P99.9, throughput, memory/GC, CPU): read [references/kpis.md](references/kpis.md) when setting a target or reporting results.

## Profiling tools

Profiler setup and commands — read only your language: [references/profiling-typescript.md](references/profiling-typescript.md) (TypeScript/Bun) or [references/profiling-rust.md](references/profiling-rust.md) (Rust).

## Optimization patterns

Catalog — algorithm, memory, I/O, and database, with TS and Rust code — once profiling has named the bottleneck class: read [references/optimization-patterns.md](references/optimization-patterns.md).

## Workflow

Loop: measure, profile, analyze, optimize, then validate.

1. **Define performance goal** — target metric (e.g., P95 < 100ms)
2. **Establish baseline** — measure current performance under realistic load
3. **Profile systematically** — identify actual bottleneck (not guesses)
4. **Analyze root cause** — understand why code is slow
5. **Design optimization** — plan targeted improvement
6. **Implement optimization** — make focused change
7. **Measure improvement** — verify gains, check for regressions
8. **Document results** — record baseline, optimization, gains, tradeoffs

At each step:

- Document measurements with methodology
- Note profiling tool output
- Track optimization attempts (what worked/failed)
- Update performance documentation

## Validation

Before declaring optimization complete:

**Check gains:**

- Measured improvement meets target?
- Improvement statistically significant?
- Tested under realistic load?
- Multiple runs confirm consistency?

**Check regressions:**

- No degradation in other metrics?
- Memory usage still acceptable?
- Code complexity still manageable?
- Tests still pass?

**Check documentation:**

- Baseline measurements recorded?
- Optimization approach explained?
- Gains quantified with numbers?
- Tradeoffs documented?

## Rules

Always:

- Measure before optimizing (baseline)
- Profile to find actual bottleneck
- Use realistic workload (not toy data)
- Measure multiple runs (account for variance)
- Document baseline and improvements
- Check for regressions in other metrics
- Consider readability vs performance tradeoff
- Verify statistical significance

Never:

- Optimize without measuring first
- Guess at bottleneck without profiling
- Benchmark with unrealistic data
- Trust single-run measurements
- Skip documentation of results
- Sacrifice correctness for speed
- Optimize without clear performance goal
- Ignore algorithmic improvements

## References

- [references/benchmarking.md](references/benchmarking.md) — rigorous benchmarking
  methodology (read before starting any benchmark)
- [references/kpis.md](references/kpis.md) — metric definitions and targets
- [references/profiling-typescript.md](references/profiling-typescript.md) — profiler setup/commands (TypeScript/Bun)
- [references/profiling-rust.md](references/profiling-rust.md) — profiler setup/commands (Rust)
- [references/optimization-patterns.md](references/optimization-patterns.md) — algorithm/memory/I/O/database optimization catalog

Related skills: codebase-recon, debugging, typescript-dev.
