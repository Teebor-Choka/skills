# Key Performance Indicators

**Latency (response time):**

- P50 (median) — typical case
- P95 — most users
- P99 — tail latency
- P99.9 — outliers
- TTFB — time to first byte
- TTLB — time to last byte

**Throughput:**

- RPS — requests per second
- ops/sec — operations per second
- bytes/sec — data transfer rate
- queries/sec — database throughput

**Memory:**

- Heap usage — allocated memory
- GC frequency — garbage collection pauses
- GC duration — stop-the-world time
- Allocation rate — memory churn
- Resident set size (RSS) — total memory

**CPU:**

- CPU time — total compute
- Wall time — elapsed time
- Hot paths — frequently executed code
- Time complexity — algorithmic efficiency
- CPU utilization — percentage used

**Always measure:**

- Before optimization (baseline)
- After optimization (improvement)
- Under realistic load (not toy data)
- Multiple runs (account for variance)
