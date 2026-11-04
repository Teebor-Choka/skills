# Profiling: Rust

Profile a release build with symbols, not a debug build. Debug builds have different hot spots.

## Set up the build

Add line tables to the release profile so a profile shows source lines:

```toml
[profile.release]
debug = "line-tables-only"
```

Keep frame pointers so stack traces stay complete:

```sh
RUSTFLAGS="-C force-frame-pointers=yes" cargo build --release
```

The shipped standard library has no debug info, so frames inside it show without lines. Mangled
names (`_ZN`, `_R`) read better through `rustfilt`, or build with `-C symbol-mangling-version=v0`.

## Pick the tool by question

| Question                                            | Tool                                                                                       |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Where does CPU time go?                             | `perf record` and `perf report` (Linux), Instruments (macOS), `samply`, `cargo flamegraph` |
| Where is the time spent waiting?                    | an off-CPU profile (`perf`, tracing)                                                       |
| Where do allocations come from?                     | DHAT (`dhat-rs`), `heaptrack`, `bytehound`                                                 |
| Is the cache or branch predictor the cost?          | Cachegrind, Callgrind, `perf stat`                                                         |
| What does speeding this function up buy end to end? | Coz (causal profiler)                                                                      |
| How many times does it run?                         | `counts`                                                                                   |

## Change the build before the code

LTO, `codegen-units = 1` and profile-guided optimization change speed with no code edit. Measure
them like any other change.

## Instrumentation

Use `std::time::Instant` for a quick span check. Do not use it as a benchmark: it has no warm-up,
repetition or outlier handling. Use the harness in `benchmark-tooling-rust.md`.

Sources: Rust Performance Book, Profiling and Build Configuration (`sources.md`).
