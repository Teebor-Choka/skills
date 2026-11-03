# Benchmark tooling — Rust

**criterion (recommended):**

```rust
use criterion::{black_box, criterion_group, criterion_main, Criterion, BenchmarkId};

fn benchmark_implementations(c: &mut Criterion) {
    let mut group = c.benchmark_group("comparison");

    for size in [10, 100, 1000].iter() {
        group.bench_with_input(BenchmarkId::new("fast", size), size, |b, &size| {
            b.iter(|| fast_implementation(black_box(size)));
        });

        group.bench_with_input(BenchmarkId::new("slow", size), size, |b, &size| {
            b.iter(|| slow_implementation(black_box(size)));
        });
    }

    group.finish();
}

criterion_group!(benches, benchmark_implementations);
criterion_main!(benches);
```

**cargo bench output:**

- Automatic outlier detection
- Statistical analysis included
- Regression detection across runs
- HTML reports with plots
