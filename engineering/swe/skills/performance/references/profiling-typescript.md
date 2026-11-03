# Profiling tools — TypeScript/Bun

**Built-in timing:**

```typescript
console.time("operation");
// ... code to measure
console.timeEnd("operation");

// High precision
const start = Bun.nanoseconds();
// ... code to measure
const elapsed = Bun.nanoseconds() - start;
console.log(`Took ${elapsed / 1_000_000}ms`);
```

**Performance API:**

```typescript
const mark1 = performance.mark("start");
// ... code to measure
const mark2 = performance.mark("end");
performance.measure("operation", "start", "end");
const measure = performance.getEntriesByName("operation")[0];
console.log(`Duration: ${measure.duration}ms`);
```

**Memory profiling:**

- Chrome DevTools → Memory tab → heap snapshots
- Node.js `--inspect` flag + Chrome DevTools
- `process.memoryUsage()` for RSS/heap tracking

**CPU profiling:**

- Chrome DevTools → Performance tab → record session
- Node.js `--prof` flag + `node --prof-process`
- Flamegraphs for visualization
