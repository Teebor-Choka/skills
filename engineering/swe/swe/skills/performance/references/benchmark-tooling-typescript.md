# Benchmark tooling — TypeScript/Bun

**microbench (recommended):**

```typescript
import { bench, run } from "mitata";

bench("fast implementation", () => {
  // code to benchmark
});

bench("slow implementation", () => {
  // code to benchmark
});

await run();
```

**Benchmark.js:**

```typescript
import Benchmark from "benchmark";

const suite = new Benchmark.Suite();

suite
  .add("implementation A", () => {
    /* code */
  })
  .add("implementation B", () => {
    /* code */
  })
  .on("cycle", (event) => console.log(String(event.target)))
  .on("complete", function () {
    console.log("Fastest is " + this.filter("fastest").map("name"));
  })
  .run({ async: true });
```
