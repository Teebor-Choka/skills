# Key performance indicators

Pick the few that match the goal. Report each as a distribution or a rate, never a lone mean.

## Resources: USE

For each resource (CPU, memory, disk, network, a lock, a pool, a queue), check:

- **Utilization**: share of time the resource is busy.
- **Saturation**: work waiting because the resource is full (queue length, run-queue depth).
- **Errors**: error events on the resource.

Many systems slow down before utilization reaches 100%, so set a utilization target below it.

## Services: four golden signals

- **Latency**: time to serve a request. Track failed requests apart from successful ones, because a
  slow error is worse than a fast error.
- **Traffic**: demand, for example requests per second.
- **Errors**: explicit, implicit and policy failures.
- **Saturation**: how full the service is.

## Latency

Record counts in latency buckets or a histogram. Report P50, P95, P99, P99.9 and max. The mean hides
the tail, and one backend's P99 can become a frontend's median when a request fans out. Histograms
add across processes. Percentiles do not.

Also track TTFB (time to first byte) and TTLB (time to last byte) for streaming responses.

## Throughput

Requests, operations, bytes or queries per second, at a stated latency. Throughput without a latency
bound is not a result.

## Memory

Heap size, resident set size, allocation rate, and for managed runtimes GC frequency and pause time.

## CPU

CPU time, wall time, utilization, and the hot paths a profile shows. Wall time is what users see but
is noisy. Cycle and instruction counts are stable and make small changes visible.

## Always

Measure before and after, on a realistic workload, over repeated runs. See `benchmarking.md`.

Sources: `sources.md` (USE method, SRE golden signals, Tene, Rust Performance Book).
