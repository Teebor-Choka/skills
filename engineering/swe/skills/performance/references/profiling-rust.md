# Profiling tools — Rust

**Benchmarking:**

```rust
#[cfg(test)]
mod benches {
    use criterion::{black_box, criterion_group, criterion_main, Criterion};

    fn benchmark_function(c: &mut Criterion) {
        c.bench_function("my_function", |b| {
            b.iter(|| my_function(black_box(42)))
        });
    }

    criterion_group!(benches, benchmark_function);
    criterion_main!(benches);
}
```

**Profiling:**

- `cargo bench` — criterion benchmarks
- `perf record` + `perf report` — Linux profiling
- `cargo flamegraph` — visual flamegraphs
- `cargo bloat` — binary size analysis
- `valgrind --tool=callgrind` — detailed profiling
- `heaptrack` — memory profiling

**Instrumentation:**

```rust
use std::time::Instant;

let start = Instant::now();
// ... code to measure
let duration = start.elapsed();
println!("Took: {:?}", duration);
```
