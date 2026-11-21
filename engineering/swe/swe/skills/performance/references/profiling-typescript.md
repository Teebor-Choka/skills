# Profiling: TypeScript and Bun

## CPU

```sh
bun --cpu-prof script.ts           # writes a .cpuprofile
bun --cpu-prof-md script.ts        # also a markdown profile that is easy to grep
```

Open a `.cpuprofile` in Chrome DevTools (Performance tab) or VS Code. Tune output with
`--cpu-prof-name` and `--cpu-prof-dir`. For Node, use `node --cpu-prof` or `--inspect` with
DevTools.

## Memory

```sh
bun --heap-prof script.ts          # V8-format heap snapshot on exit
bun --heap-prof-md script.ts       # markdown version
```

In code: `heapStats()` from `bun:jsc` for the JS heap, `Bun.gc()` to force a collection before
you compare two heap sizes, `Bun.generateHeapSnapshot()` for a snapshot. In Node: heap snapshots in
DevTools, `process.memoryUsage()` for RSS and heap totals.

## Timing

`performance.now()` or `Bun.nanoseconds()` for spans. For repeatable microbenchmarks use `mitata`
(see `benchmark-tooling-typescript.md`). For a whole command use `hyperfine`.

## Load tests

Drive an HTTP server with a client at least as fast as the server: `bombardier`, `oha`. A Node-based
load tool such as `autocannon` can become the bottleneck. Use a fixed arrival rate for latency tests.

Sources: Bun, Benchmarking (`sources.md`).
