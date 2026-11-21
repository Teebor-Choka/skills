# Sources

Each rule in the skill traces to one of these. "Opened" means the page was read when this skill was
written; the others were found through search and are cited by title and venue.

## Method

- Brendan Gregg, [The USE Method](https://www.brendangregg.com/usemethod.html) (opened). For
  every resource, check utilization, saturation and errors. Basis for step 3.1 of the procedure.
- Brendan Gregg, "The Flame Graph", Communications of the ACM, 2016 (not opened). Basis for
  reading the widest frames of a CPU profile first. Slides:
  [ACM Applicative 2016, System Methodology](https://brendangregg.com/Slides/ACMApplicative2016_SystemMethodology.pdf)
  (found by search).
- Donald Knuth, "Structured Programming with go to Statements", Computing Surveys 6(4), 1974
  (not opened). The "97%" and "critical 3%" passage behind the first rule.
- Google SRE book, [Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/)
  (opened). The four golden signals (latency, traffic, errors, saturation), buckets instead of
  averages, and tracking failed-request latency apart from successful requests.

## Measurement

- Mytkowicz, Diwan, Hauswirth, Sweeney, "Producing Wrong Data Without Doing Anything Obviously
  Wrong!", ASPLOS 2009, [DOI 10.1145/1508244.1508275](https://doi.org/10.1145/1508244.1508275)
  (abstract read through search). Environment size and link order bias results.
- Georges, Buytaert, Eeckhout, "Statistically Rigorous Java Performance Evaluation", OOPSLA 2007
  (not opened). Repeated runs and confidence intervals.
- Gil Tene, [Coordinated Omission](https://groups.google.com/g/mechanical-sympathy/c/icNZJejUHfE)
  (found by search). Closed-loop load generators hide queueing delay. The
  [HdrHistogram](https://github.com/HdrHistogram/HdrHistogram) library records the full
  distribution and has a correcting mode.
- Rust Performance Book, [Benchmarking](https://nnethercote.github.io/perf-book/benchmarking.html)
  (opened). Names Criterion, Divan, Hyperfine, Bencher, Gungraun. Wall time is noisy. Cycles or
  instruction counts have lower variance. "Mediocre benchmarking is far better than no benchmarking."

## Tools

- Rust Performance Book, [Profiling](https://nnethercote.github.io/perf-book/profiling.html)
  (opened). Profiler list, `debug = "line-tables-only"`, `-C force-frame-pointers=yes`,
  demangling with `rustfilt` or `-C symbol-mangling-version=v0`.
- Rust Performance Book, [Build Configuration](https://nnethercote.github.io/perf-book/build-configuration.html)
  (found by search). LTO and profile-guided optimization change speed without a code change.
- Bun, [Benchmarking](https://bun.com/docs/project/benchmarking) (opened). `--cpu-prof`,
  `--cpu-prof-md`, `--heap-prof`, `bun:jsc` `heapStats()`, mitata, hyperfine, and fast HTTP load
  tools (bombardier, oha).
