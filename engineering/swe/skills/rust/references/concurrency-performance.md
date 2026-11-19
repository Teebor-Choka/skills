# Concurrency performance fixes

Use this when async or threaded Rust has a measured latency, throughput, memory or stall problem.
Profile first (`swe:performance`). Apply the fix that matches the symptom, then measure again.
For hangs, lost data and shutdown bugs, read `concurrency-correctness.md`.

`overrides.md` section 5 still applies. This file adds the performance reasons behind it.

Entry format and caveats: see `concurrency-correctness.md`. Versions read on the access date: tokio
1.54.1, futures 0.3.34, arc-swap 1.9.5, crossbeam-utils 0.8.23. `hoprnet <hash>` entries: their claims
come from PR #98's read of each diff; on 2026-11-19 only the hash and commit title were re-checked.

## 1. Keep the runtime's workers free

### Keep the time between awaits short

Symptom: unrelated tasks stall, tail latency grows, timers fire late.
Fix: split long loops with `.await` points. Ryhl suggests no more than 10 to 100 microseconds
between awaits. For a sync-per-item stream stage, call `tokio::task::consume_budget().await` or
`yield_now()`. Tokio's per-task budget was 128 operations per tick (2020 post) and Tokio library
functions have explicit yield points; a stage built on `future::ready` has none.
Test: a `current_thread` runtime with a canary task; the test fails if the canary never runs.
Source: https://ryhl.io/blog/async-what-is-blocking/ ;
https://tokio.rs/blog/2020-04-preemption ;
https://docs.rs/tokio/latest/tokio/task/coop/index.html ;
https://github.com/hoprnet/hoprnet/commit/9abf25458d (a dispatch loop built on `future::ready`
monopolised its thread; fixed with `consume_budget`); guideline `M-YIELD-POINTS`.
Accessed: 2026-11-19

### Route blocking work by kind, and cap it

Symptom: workers stall on file, database or heavy CPU work; the blocking pool fills with CPU jobs.
Fix: blocking I/O goes to `spawn_blocking`. CPU-bound work goes to a rayon pool, awaited through a
`tokio::sync::oneshot`. Work that never ends gets a dedicated thread. `block_in_place` suits a short
blocking section and exists only on the multi-thread runtime. The `spawn_blocking` limit is large
(512 by default), so limit CPU jobs with a `Semaphore`. A started `spawn_blocking` task cannot be
aborted.
Source: https://ryhl.io/blog/async-what-is-blocking/ ;
https://docs.rs/tokio/latest/tokio/task/fn.spawn_blocking.html ;
https://docs.rs/tokio/latest/tokio/task/index.html ;
https://docs.rs/tokio/latest/tokio/runtime/struct.Builder.html
Accessed: 2026-11-19

```rust
// sketch: CPU-bound work on rayon, result back through a oneshot
let (tx, rx) = tokio::sync::oneshot::channel();
rayon::spawn(move || { let _ = tx.send(expensive(input)); });
let out = rx.await?;
```

### Keep storage reads off the hot path

Symptom: pool workers block on one database read per packet.
Fix: cache the derived value in memory so the fast path calls no backend.
Test: a mock backend that fails the test if the fast path calls it.
Source: https://github.com/hoprnet/hoprnet/commit/daea01c4c4 (a per-packet redb read on a crypto
worker removed).
Accessed: 2026-11-19

### Never loop in `poll` without a waker

Symptom: idle nodes use 100% of one core.
Fix: return `Pending` and let the inner future's waker drive the next poll.
Source: https://github.com/hoprnet/hoprnet/commit/eb21c1354c (a flush `continue`d in a loop when the
delay was zero).
Accessed: 2026-11-19

## 2. Locks and shared state

### Prefer a blocking mutex for short sections, and release it between items

Symptom: lock overhead in async code, or a writer that blocks others for a whole batch.
Fix: use `std::sync::Mutex` (or `parking_lot`) when the guard never crosses an `.await`. The Tokio
docs say the blocking mutex "should be preferred in the cases where it can be used"; the tutorial
calls it fine "as long as contention remains low". Use `tokio::sync::Mutex` only to hold a lock
across an `.await`. Do not hold a lock across many items: release or yield between chunks.
Source: https://docs.rs/tokio/latest/tokio/sync/struct.Mutex.html ;
https://tokio.rs/tokio/tutorial/shared-state ;
https://github.com/hoprnet/hoprnet/commit/eb21c1354c (a flush held a write lock across consecutive
upserts; fixed by yielding every 8).
Accessed: 2026-11-19

### Shard a contended map, or give the resource one owner task

Symptom: one `Mutex<HashMap>` is the bottleneck, or contention on a lock around an I/O handle.
Fix: use a fixed `Vec<Mutex<HashMap<..>>>` indexed by key hash, or a concurrent map. The shard
count is fixed at creation. For an I/O resource, "spawn a task to manage the state and use message
passing" instead of sharing a lock.
Source: https://tokio.rs/tokio/tutorial/shared-state ;
https://docs.rs/tokio/latest/tokio/sync/struct.Mutex.html
Accessed: 2026-11-19

### Use `ArcSwap` for read-mostly data

Symptom: `RwLock<Arc<T>>` shows CPU-level contention on the lock and the `Arc` count, and a steady
stream of readers delays writers.
Fix: `arc_swap::ArcSwap`; the docs say it performs better "both in contended and non-contended
scenarios".
Status: version-specific. arc-swap 1.9 strengthened orderings that were "too weak" and "probably
introduces some performance degradation". Pin the version and measure.
Source: https://docs.rs/arc-swap/latest/arc_swap/
Accessed: 2026-11-19

## 3. Queues and backpressure

### Bound every queue and make a full queue push back

Symptom: memory grows until OOM under sustained load.
Fix: give each queue a hard capacity. The Tokio tutorial warns that "Unbounded queues will
eventually fill up all available memory". A queue built on a `Vec`/heap needs `poll_ready` to return
`Pending` when full, and the consumer must wake senders after each pop.
Test: push past capacity and assert the sender is pending, not that memory grew.
Source: https://tokio.rs/tokio/tutorial/channels ;
https://github.com/hoprnet/hoprnet/commit/5639d4c891 (a heap whose capacity was only a
pre-allocation hint grew until OOM).
Accessed: 2026-11-19

### Check what "bounded" means for your channel

Symptom: a channel holds more than its stated capacity, so memory or latency exceeds the budget.
Fix: read the capacity rule. `futures::channel::mpsc::channel(n)` holds `n` plus one per sender
clone. `tokio::sync::broadcast` rounds capacity up to a power of two (`channel(3)` holds 4) and
overwrites the oldest value. Use a strict-capacity channel when clones multiply.
Source: https://github.com/hoprnet/hoprnet/commit/ac365f2b82 (commit body) ;
https://docs.rs/tokio/latest/tokio/sync/broadcast/index.html
Accessed: 2026-11-19

### Size a buffer in front of a CPU pool to the pool

Symptom: a burst reaches the pool at once, tail items pass a timeout and drop silently.
Fix: a small buffer applies backpressure early. A 200 000 item buffer was the cause in hoprnet.
Test: assert the buffer-size constant.
Source: https://github.com/hoprnet/hoprnet/commit/e576e99553
Accessed: 2026-11-19

### Give each slow consumer its own bounded queue and drop policy

Symptom: one dead peer delays every other peer in a shared drain loop.
Fix: `try_send` into a per-destination bounded queue with an explicit overflow policy (drop-newest,
or drop-oldest when freshness matters). Use one spawned task per destination for slow opens. With
`broadcast`, a slow receiver gets `RecvError::Lagged` and may skip ahead.
Source: https://github.com/hoprnet/hoprnet/commit/d670a6c505 ;
https://github.com/hoprnet/hoprnet/commit/5639d4c891 ;
https://docs.rs/tokio/latest/tokio/sync/broadcast/index.html
Accessed: 2026-11-19

### Admit before a request takes a shared slot

Symptom: a bounded handler pool fills with requests that wait on a peer-controlled condition, and
all other traffic drops; or an accept queue grows without bound.
Fix: check admission cheaply before queueing. In h2, a flood of paired `HEADERS` and `RST_STREAM`
frames grew the accept queue; the fix caps remote reset streams by default.
Status: h2 fix is version-specific (patched in `>=0.3.17`).
Source: https://github.com/hoprnet/hoprnet/commit/9947bd29b5 (about 110 forged start requests per
second parked every handler) ; https://rustsec.org/advisories/RUSTSEC-2023-0034.html
Accessed: 2026-11-19

### Bound in-flight work

Symptom: tens of thousands of futures, memory spikes, an overloaded downstream.
Fix: `stream.map(f).buffer_unordered(n)` (completion order) or `buffered(n)` (input order), a
`JoinSet` with a cap, or an `Arc<Semaphore>`. `for_each_concurrent` runs futures "concurrently (but
not in parallel)". A large `acquire_many` at the head of a fair `Semaphore` blocks later small
requests. `buffered` keeps input order, so one stuck future withholds all later items: give each a
deadline.
Source: https://docs.rs/futures/latest/futures/stream/trait.StreamExt.html ;
https://docs.rs/tokio/latest/tokio/sync/struct.Semaphore.html ;
https://github.com/hoprnet/hoprnet/commit/adefa298ad (one unresolved packet stopped all origination
for about 1 h 44 min with a green healthcheck).
Accessed: 2026-11-19

## 4. Pools shared by two directions

### Never derive a cap by subtracting from a small pool, and gate the priority path

Symptom: throughput collapses on small hosts.
Fix: a decode limit of `pool - reserved` evaluated to `2 - 2 = 0`, clamped to 1, and collapsed relay
throughput on 4-core nodes. Clamp to a sane minimum and calibrate on the deployed pool size. The same
commit also fixed decode starving encode on a shared pool: a cheap gate that reads one atomic count of
outstanding tasks and delays ingress above a high-water mark kept encode moving. Reuse that gate, not
the reverted reserved-thread cap.
Status: the reserved-thread cap was reverted in production. The defaults were ready-queue depths, not
thread counts.
Source: https://github.com/hoprnet/hoprnet/commit/8ff6bec7ca (the cap) ;
https://github.com/hoprnet/hoprnet/commit/3579344dd2 (the revert)
Accessed: 2026-11-19

## 5. Cache lines

### Pad hot atomics with `CachePadded`

Symptom: threads that write different variables on one cache line slow each other, with no lock in
the profile.
Fix: wrap each hot value, such as per-thread counters and queue head and tail, in
`crossbeam_utils::CachePadded` (128 bytes on x86-64 and aarch64, 64 on most others). In the
Rust Atomics and Locks benchmark, a background thread storing next to a hot atomic moved a test from
about 300 ms to several seconds on x86-64.
Source: https://docs.rs/crossbeam-utils/latest/crossbeam_utils/struct.CachePadded.html ;
http://mara.nl/atomics/hardware.html
Accessed: 2026-11-19

## 6. Find the cause, then prove the fix

| Question                                     | Tool                                                                                                                                               |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Which tasks never yield, or wake themselves? | [tokio-console](https://github.com/tokio-rs/console): `never-yielded` and `self-wakes` lints; build with `--cfg tokio_unstable`                    |
| Are tasks waiting long in the run queue?     | [tokio-metrics](https://docs.rs/tokio-metrics/latest/tokio_metrics/struct.TaskMetrics.html) `mean_scheduled_duration` and `slow_poll_ratio`        |
| Is a shared cache line contended?            | `perf c2c record`, then `perf c2c report` (Linux): [man page](https://man7.org/linux/man-pages/man1/perf-c2c.1.html)                               |
| Is the runtime saturated?                    | tokio-metrics [RuntimeMetrics](https://docs.rs/tokio-metrics/latest/tokio_metrics/struct.RuntimeMetrics.html) `busy_ratio()`, `global_queue_depth` |

The tokio-metrics docs say rising scheduled time means tasks "spent longer in the runtime's queues".
They do not say it proves blocking. Confirm with a profile. Off-CPU profiles and sanitizers: see
`swe:performance`.
