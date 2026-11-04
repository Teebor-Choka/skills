# Concurrency performance fixes

Use this when async or threaded Rust has a measured latency, throughput, memory or stall problem.
Profile first (`swe:performance`). Apply the fix that matches the symptom, then measure again.

`overrides.md` section 5 still applies. This file adds the performance reasons behind it.

Sources: a Tokio or library page (URL), or a hoprnet commit (`hoprnet <hash>`, read in the repo).
Every commit was checked against its diff or message. A fix that production later reverted is
marked.

## 1. Keep the runtime's workers free

**Keep time between awaits short.** Symptom: unrelated tasks stall, tail latency grows, timers fire
late. Fix: split long loops with `.await` points. A good limit is 10 to 100 microseconds between
awaits. For sync-per-item stream stages, add `tokio::task::consume_budget().await` or `yield_now()`.
A stage that never returns `Pending` starves its executor thread.
Sources: [Ryhl, What is blocking?](https://ryhl.io/blog/async-what-is-blocking/);
hoprnet `9abf25458d` (a dispatch loop built on `future::ready` monopolised its thread; fixed with
`consume_budget` and a `current_thread` test with a canary task); guideline `M-YIELD-POINTS`.

**Route blocking work by kind.** Symptom: workers stall on file, database or heavy CPU work. Fix:
blocking I/O goes to `spawn_blocking`. CPU-bound work goes to a rayon pool, awaited through a
`tokio::sync::oneshot`. Work that never ends goes to a dedicated thread. `spawn_blocking` can grow
to about 500 threads, which is wrong for heavy CPU work.
Source: [Ryhl, What is blocking?](https://ryhl.io/blog/async-what-is-blocking/).

```rust
// adapted: CPU-bound work on rayon, result back through a oneshot
let (tx, rx) = tokio::sync::oneshot::channel();
rayon::spawn(move || { let _ = tx.send(expensive(input)); });
let out = rx.await?;
```

**Use `block_in_place` for a short blocking section inside a task.** It moves the worker's other
tasks to another thread. It exists only on the multi-thread runtime.
Source: [tokio::task](https://docs.rs/tokio/latest/tokio/task/index.html).

**Cap blocking jobs and do not rely on abort.** A `spawn_blocking` task cannot be aborted. The
blocking pool defaults to 512 threads. Guard CPU-heavy jobs with a `Semaphore`.
Sources: [spawn_blocking](https://docs.rs/tokio/latest/tokio/task/fn.spawn_blocking.html),
[runtime::Builder](https://docs.rs/tokio/latest/tokio/runtime/struct.Builder.html).

**Keep storage I/O off the CPU pool and the hot path.** Symptom: pool workers block on a database
read per packet. Fix: cache the derived value in memory, make the fast path do no backend call, and
add a test that fails if the backend is called.
Source: hoprnet `daea01c4c4` (a per-packet redb read on a crypto worker removed).

**Busy polling.** A `poll` that loops without registering a waker spins one core. Return `Pending`
and let the inner future's waker drive the next poll.
Source: hoprnet `eb21c1354c` (idle nodes at 100% CPU: a flush `continue`d in a loop when the delay
was zero).

## 2. Locks and shared state

**Never hold a `std` mutex guard across `.await`.** Symptom: compile error (guard not `Send`) or a
deadlock. Fix: end the guard's scope before the await, or hide the mutex in a type whose sync
methods lock inside.
Sources: [Tokio tutorial, shared state](https://tokio.rs/tokio/tutorial/shared-state),
[tokio::sync::Mutex](https://docs.rs/tokio/latest/tokio/sync/struct.Mutex.html).

```rust
{ let mut g = mutex.lock().unwrap(); *g += 1; } // guard dropped here
do_something_async().await;
```

**Prefer a blocking mutex for short critical sections, even in async code.** The async mutex costs
more. Use `tokio::sync::Mutex` only when the lock must stay held across an `.await`. The docs say
the blocking mutex "should be preferred in the cases where it can be used".
Source: [tokio::sync::Mutex](https://docs.rs/tokio/latest/tokio/sync/struct.Mutex.html).

**Shard a contended map.** Symptom: one `Mutex<HashMap>` is the bottleneck. Fix: a fixed `Vec` of
mutexes indexed by key hash, or a concurrent map. The shard count cannot change later.
Source: [Tokio tutorial, shared state](https://tokio.rs/tokio/tutorial/shared-state).

**Give an I/O resource one owner task.** Symptom: contention on a lock around a handle. Fix: spawn
a task that owns it and talk to it over a channel.
Source: [tokio::sync::Mutex](https://docs.rs/tokio/latest/tokio/sync/struct.Mutex.html).

**Use `ArcSwap` for read-mostly data.** `RwLock<Arc<T>>` suffers CPU-level contention on the lock and
the `Arc` count, and a steady stream of readers can block a writer. Check the crate's notes on
memory ordering before you adopt a version.
Source: [arc-swap](https://docs.rs/arc-swap/latest/arc_swap/).

**Do not re-take a read lock while you hold one.** `tokio::sync::RwLock` queues first in, first out.
A queued writer blocks new readers, and a second read in the same task can deadlock.
Source: [tokio::sync::RwLock](https://docs.rs/tokio/latest/tokio/sync/struct.RwLock.html).

**Drop `DashMap` refs before you call the map again.** Holding a reference while calling `insert`,
`remove`, `get_mut` or `entry` may deadlock.
Source: [DashMap](https://docs.rs/dashmap/latest/dashmap/struct.DashMap.html).

**Do not hold a sync lock across many items.** Yield or release between chunks.
Source: hoprnet `eb21c1354c` (a flush held a write lock across consecutive upserts; fixed by
yielding every 8).

**Admit before you take a shared slot.** Symptom: a bounded handler pool fills with requests that
wait on a peer-controlled condition, and all other traffic drops. Fix: check admission cheaply
before queueing.
Source: hoprnet `9947bd29b5` (about 110 forged start requests per second parked every handler).

## 3. Queues and backpressure

**Bound every queue, and make a full queue push back.** Symptom: memory grows until OOM under
sustained load. Fix: a hard capacity, `poll_ready` returns `Pending` when full, and the consumer
wakes senders after each pop.
Sources: [Tokio tutorial, channels](https://tokio.rs/tokio/tutorial/channels);
hoprnet `5639d4c891` (a heap whose capacity was only a pre-allocation hint grew until OOM).

**Check what "bounded" means.** `futures::channel::mpsc::channel(n)` has capacity `n` plus one per
sender clone. Use a strict-capacity channel when clones multiply.
Source: hoprnet `ac365f2b82` (commit body).

**Size a buffer in front of a CPU pool to the pool, not to "large".** A 200 000 item buffer let a
burst hit the pool at once. Tail items passed a 150 ms encode timeout and dropped silently. A small
buffer applies backpressure early. Pin the constant with a test.
Source: hoprnet `e576e99553`.

**Never await one slow consumer inside a shared drain loop.** Symptom: one dead peer delays all
others. Fix: `try_send` into a per-destination bounded queue with an explicit overflow policy
(drop-newest, or drop-oldest for freshness), and one spawned task per destination for slow opens.
Sources: hoprnet `d670a6c505`, `5639d4c891`.

**Time out on lack of progress, not on total time.** A pump over a peer-controlled sink can park on
`Pending` forever, and cleanup that fires on completion never runs. Fix: arm an idle deadline when
the sink first returns `Pending`, reset it on each `Ready`, and error on expiry so eviction runs.
Source: hoprnet `3889e2bb69`.

**Give every future inside `.buffered(n)` a deadline.** `buffered` keeps input order, so one stuck
item withholds all later items. Bound retry loops and count the drops.
Source: hoprnet `adefa298ad` (one unresolved packet stopped all origination for about 1 h 44 min with
a green healthcheck).

**Pick the channel by job.** `mpsc` for many values, `oneshot` for one, `broadcast` when every
receiver needs every value, `watch` when only the latest matters. From sync code use
`blocking_send` and `blocking_recv`.
Source: [Tokio tutorial, channels](https://tokio.rs/tokio/tutorial/channels).

**Counter-case.** A bound can create a deadlock cycle: a full channel blocked a reader, which
blocked delivery that the writer was waiting for. An unbounded channel fixed it, which is safe only
when another limit bounds the data.
Source: hoprnet `c4ace897aa`.

## 4. Task count and limits

**Bound in-flight work.** Symptom: tens of thousands of futures, memory spikes, overloaded
downstream. Fix: `stream.map(f).buffer_unordered(n)` (completion order) or `buffered(n)` (input
order), a `JoinSet`, or an `Arc<Semaphore>` for outgoing requests. Dropping a `JoinSet` aborts its
tasks. `for_each_concurrent` adds concurrency, not threads. A large `acquire_many` at the head of a
`Semaphore` blocks later small requests, because the queue is fair.
Sources: [StreamExt](https://docs.rs/futures/latest/futures/stream/trait.StreamExt.html),
[JoinSet](https://docs.rs/tokio/latest/tokio/task/struct.JoinSet.html),
[Semaphore](https://docs.rs/tokio/latest/tokio/sync/struct.Semaphore.html).

**Never derive a cap by subtracting from a small pool.** A decode limit of `pool - reserved`
evaluated to `2 - 2 = 0`, clamped to 1, and collapsed relay throughput on 4-core nodes. Production
reverted it: the defaults are ready-queue depths feeding the pool, not thread counts. Clamp to a sane
minimum and calibrate on the real deployed pool size.
Sources: hoprnet `8ff6bec7ca` (the cap), `3579344dd2` (the revert).

**When two directions share one pool, protect the priority path.** Decode filled the shared queue
and starved encode work. A cheap admission gate that reads one atomic count of outstanding tasks and
delays ingress above a high-water mark kept encode moving. The reserved-thread cap was the part that
failed, so reuse the gate and not the cap.
Source: hoprnet `8ff6bec7ca`.

## 5. Atomics and cache lines

**Pad hot atomics with `CachePadded`.** Symptom: threads that write different variables on one cache
line slow each other, with no lock in the profile. Fix: wrap each hot value, such as per-thread
counters and queue head and tail, in `crossbeam_utils::CachePadded`. A background thread writing to a
neighbouring atomic raised one test from about 300 ms to about 3 s.
Sources: [CachePadded](https://docs.rs/crossbeam-utils/latest/crossbeam_utils/struct.CachePadded.html),
[Rust Atomics and Locks, hardware](http://mara.nl/atomics/hardware.html).

**Use `Relaxed` for independent counters.** A stronger ordering does not make data move faster and
can slow the program. Use acquire and release when data passes between threads. `SeqCst` is almost
never needed.
Source: [Rust Atomics and Locks, memory ordering](http://mara.nl/atomics/memory-ordering.html).

## 6. `select!`

**Create the future once.** A future built inside the loop restarts on every iteration. `tokio::pin!`
it outside and select on `&mut operation`.
Source: [Tokio tutorial, select](https://tokio.rs/tokio/tutorial/select).

**Check cancel safety of every branch.** `mpsc::Receiver::recv`, `watch::changed` and
`TcpListener::accept` are safe to drop. `read_exact` and `write_all` can lose data. `Mutex::lock`,
`RwLock` locks, `Semaphore::acquire` and `Notify::notified` lose their queue position when dropped.
With `biased;`, order branches so that shutdown is not starved.
Source: [tokio::select!](https://docs.rs/tokio/latest/tokio/macro.select.html).

## 7. Find the cause, then prove the fix

| Question | Tool |
|----------|------|
| Which tasks never yield, or wake themselves? | [tokio-console](https://github.com/tokio-rs/console) (build with `--cfg tokio_unstable`) |
| Are tasks waiting long in the run queue? | [tokio-metrics](https://docs.rs/tokio-metrics/latest/tokio_metrics/struct.TaskMetrics.html) task metrics (a rising mean scheduled time) |
| Is a shared cache line contended? | `perf c2c record`, then `perf c2c report` (Linux): [man page](https://man7.org/linux/man-pages/man1/perf-c2c.1.html) |
| Is the lock-free fix correct? | [loom](https://docs.rs/loom/latest/loom/) model test; it cannot model every `Relaxed` behaviour |

The tokio-metrics docs do not say that a rising scheduled time proves blocking. Treat it as a lead to
confirm with a profile.

**Guard a fix with a test that fails on the old behaviour.** Patterns that worked in hoprnet: a
`current_thread` runtime with a canary task to prove a stage yields (`9abf25458d`); a test that the
backend is never called on the fast path (`daea01c4c4`); an assertion on a buffer-size constant
(`e576e99553`).
