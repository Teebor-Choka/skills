# Benchmark tooling: Rust

## Pick a harness

| Tool | Use for |
|------|---------|
| Criterion | statistical microbenchmarks with outlier detection, regression detection across runs, HTML reports |
| Divan | a more sophisticated alternative to the built-in bench, like Criterion |
| Hyperfine | timing a whole command or binary |
| Gungraun | `cargo bench` integration with high-precision measurements |
| Bencher | continuous benchmarking in CI, tracking results over time |

Built-in `#[bench]` needs nightly and is a starting point only.

## Criterion

```rust
use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};

fn compare(c: &mut Criterion) {
    let mut group = c.benchmark_group("comparison");
    for size in [10, 100, 1000] {
        group.bench_with_input(BenchmarkId::new("fast", size), &size, |b, &n| {
            b.iter(|| fast_implementation(black_box(n)));
        });
        group.bench_with_input(BenchmarkId::new("slow", size), &size, |b, &n| {
            b.iter(|| slow_implementation(black_box(n)));
        });
    }
    group.finish();
}

criterion_group!(benches, compare);
criterion_main!(benches);
```

`black_box` keeps the compiler from removing the work. Use real input sizes, not one value.

## Noise

Wall time varies with layout, frequency scaling and other load. When the gain is small, also record
instruction or cycle counts, which vary less.

Sources: Rust Performance Book, Benchmarking (`sources.md`).
