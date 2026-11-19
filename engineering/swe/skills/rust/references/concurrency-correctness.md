# Concurrency correctness

Use this when async or threaded Rust hangs, deadlocks, loses data, leaks tasks, races, or fails to
compile with a `Send` error. For latency, throughput and memory, read `concurrency-performance.md`.

`overrides.md` section 5 still applies and is not contradicted here: native `async fn` in traits,
`Send` bounds in `where` clauses, runtime-agnostic mutex choice, atomic swap or CAS for shared state.

Entry format: `Symptom`, `Fix`, optional `Test` and `Status`, `Source`, `Accessed`. Docs pages were
opened on the access date (tokio 1.54.1, Rust std 1.100.0, loom 0.7.3, parking_lot 0.13.0). Rust
snippets are sketches, not compiled. `Status` marks a fix that production reverted or that is
version-specific. `hoprnet` links are commits in github.com/hoprnet/hoprnet; their figures were
re-read with `gh api` from the commit message (and diff where noted) on the access date.

## 1. Locks and deadlock

### Never hold a lock guard across `.await`, and keep non-`Send` values out of the future

Symptom: compile error "future cannot be sent between threads safely" on `tokio::spawn` (an `Rc` or
a `std` `MutexGuard` "used across an await"); or, with a `Send` guard type, a deadlock ("The code
compiles, but it deadlocks!").
Fix: a task is `Send` only if all data held across `.await` is `Send`. Wrap the guard or the
non-`Send` value in an inner block so it drops before the await, or hide the mutex in a type whose
sync methods lock inside. On a public trait, bare `async fn` cannot let callers require `Send`: use
`trait_variant::make` or `-> impl Future<Output = T> + Send`, as `overrides.md` section 5 requires.
Status: version-specific. The Tokio tutorial says an explicit `drop(lock)` "fails too" because the
compiler judges `Send` "based on scope information only" (the page names no Rust version). Rust 1.74
release notes list "Enable MIR-based drop-tracking for `async` blocks". On rustc 1.95.0 (sketch below)
a bare `let g = m.lock().unwrap(); drop(g); other().await;` compiled, but `*g += 1; drop(g);` before
the await was still rejected. Use the inner block. Trait-bound advice needs Rust 1.75 or later.
Test: on a `current_thread` runtime, a second task needs the same lock and retries
`try_lock` with `yield_now().await` under `tokio::time::timeout`. A guard held across an await,
including a `Send` one such as `parking_lot`, makes the timeout fire and fails the test (sketch below, not compiled).
Source: https://tokio.rs/tokio/tutorial/shared-state ;
https://tokio.rs/tokio/tutorial/spawning ;
https://github.com/rust-lang/rust/blob/master/RELEASES.md (Version 1.74.0, Language) ;
https://blog.rust-lang.org/2023/12/21/async-fn-rpit-in-traits/
Accessed: 2026-11-19

```rust
// sketch, not compiled against a tokio version
let m = std::sync::Arc::new(parking_lot::Mutex::new(0));
let m2 = m.clone();
tokio::spawn(async move { work_that_must_not_hold_the_lock(&m2).await });
tokio::task::yield_now().await;
tokio::time::timeout(std::time::Duration::from_millis(200), async {
    loop {
        if let Some(_g) = m.try_lock() { break; }
        tokio::task::yield_now().await;
    }
})
.await
.expect("lock still held across an await");
```

### Never re-lock on the same thread, and never nest reads behind a queued writer

Symptom: a thread or task hangs on a lock it already holds, or on a second read lock.
Fix: lock once per scope and pass the guard down. `std` says re-locking a `Mutex` "might panic or
deadlock", and `RwLock::read` may panic if the thread already holds the lock. Whether a waiting
writer blocks new readers is OS-dependent for `std::sync::RwLock`. `tokio::sync::RwLock` is
write-preferring and FIFO, so a second read in the same task after a writer queued can deadlock.
For `DashMap`, drop every reference before calling `insert`, `remove`, `get_mut` or `entry`, or use
`try_get`, `try_get_mut` and `try_entry`.
Source: https://doc.rust-lang.org/std/sync/struct.Mutex.html ;
https://doc.rust-lang.org/std/sync/struct.RwLock.html ;
https://docs.rs/tokio/latest/tokio/sync/struct.RwLock.html ;
https://docs.rs/dashmap/latest/dashmap/struct.DashMap.html
Accessed: 2026-11-19

### Take locks in one global order, and detect deadlocks in test builds

Symptom: two threads each hold one lock and wait for the other, and the process hangs.
Fix: document one lock order and follow it. In test or debug builds, enable
`parking_lot`'s `deadlock_detection` feature and run `deadlock::check_deadlock()` on a background
thread; it returns the deadlocked threads with backtraces.
Status: experimental feature. Reporting is destructive: detected threads stay blocked, and waits
with a deadline are not reported.
Source: https://docs.rs/parking_lot/latest/parking_lot/deadlock/index.html
Accessed: 2026-11-19

### Handle mutex poisoning on purpose

Symptom: after one thread panics under a lock, every later `lock().unwrap()` panics too.
Fix: decide per lock. Propagating the panic is the default and keeps a possibly broken invariant
from being seen. If the data is still consistent, recover with `PoisonError::into_inner` or
`clear_poison()` (Rust 1.77).
Source: https://doc.rust-lang.org/std/sync/struct.Mutex.html
Accessed: 2026-11-19

### Avoid futurelock when a task stops polling a future it started

Symptom: a task hangs forever with no panic and no busy CPU. A future queued for a fair lock was
handed the lock, but its task now polls a different future and never runs it again.
Fix: do not `select!` on `&mut future` and, in the same `select!`, await another future that needs
the same lock. Spawn the future as its own task and select on its `JoinHandle`.
For streams use `JoinSet`. For a full bounded channel the RFD suggests a larger capacity with
`try_send`, propagating failure; a `send_timeout` does not help because it still needs polling. `join_all` is not affected.
Test: a `select!` plus fair-mutex repro, run under a timeout; it fails on the old shape.
Source: https://rfd.shared.oxide.computer/rfd/0609 (Oxide RFD 609; page shows no publication date;
tokio 1.48.0 docs linked)
Accessed: 2026-11-19

## 2. Cancellation and `select!`

### Make every `select!` branch cancel safe, and create the future once

Symptom: data is lost or restarted when another branch wins; a lock or permit loses its queue place.
Fix: check each branch against the `select!` docs. Cancel safe: `mpsc::Receiver::recv`,
`watch::changed`, `TcpListener::accept`. Unsafe: `read_exact` and `write_all`
(can lose data). `Mutex::lock`, `RwLock` locks, `Semaphore::acquire` and `Notify::notified` lose
their queue position when dropped. A lost `Sender::send` drops the message, so `reserve().await`
first and send with the `Permit`. Build a long operation once outside the loop, `tokio::pin!` it and
select on `&mut operation`, so it resumes. With `biased;` you own fairness: put shutdown first.
Oxide's RFD 400 says "task aborts should be avoided entirely".
Test: drive the losing branch to completion in a loop and assert no message or permit is lost.
Source: https://docs.rs/tokio/latest/tokio/macro.select.html ;
https://docs.rs/tokio/latest/tokio/sync/mpsc/struct.Sender.html ;
https://tokio.rs/tokio/tutorial/select ; https://rfd.shared.oxide.computer/rfd/0400
Accessed: 2026-11-19

### Register interest before you check, with `Notify`

Symptom: a waiter sleeps forever although a notification was sent: a lost wakeup.
Fix: create the `Notified` future before you check the condition, call `enable()` on it, check the
condition, and only then `.await` the future. In the docs' mpmc example: `let future =
notify.notified(); tokio::pin!(future);` then in a loop `future.as_mut().enable();`, then
`try_recv()`, then `future.as_mut().await`, then `future.set(notify.notified())`. A `Notified` that
was not yet polled is "not guaranteed to receive wakeups from calls to `notify_one()`". `notify_one`
stores one permit if nobody waits, so a single consumer that checks the condition and then awaits
cannot lose a wakeup (the docs' mpsc example skips `enable`). `notify_waiters` stores no permit, but a
`Notified` "is guaranteed to receive wakeups from `notify_waiters()` as soon as it has been created".
Test: spawn `notify_waiters()` between the condition check and the `.await`; with
`notified()` created first the waiter wakes, and with `notified()` created after the check it hangs
under `tokio::time::timeout` (sketch, not compiled).
Source: https://docs.rs/tokio/latest/tokio/sync/struct.Notify.html
Accessed: 2026-11-19

### Time out on lack of progress, and mind bounded-channel cycles

Symptom: a pump over a peer-controlled sink parks on `Pending` forever and eviction never runs; or
a full bounded channel blocks a reader that the writer is waiting on.
Fix: arm an idle deadline when the sink first returns `Pending`, reset it on each `Ready`, and
error on expiry. For a cycle, break it: the hoprnet case used an unbounded channel, which is safe
only when another limit bounds the data.
Source: https://github.com/hoprnet/hoprnet/commit/3889e2bb69 ;
https://github.com/hoprnet/hoprnet/commit/c4ace897aa (both commit messages re-read 2026-11-19)
Accessed: 2026-11-19

## 3. Task lifecycle

### Own your tasks: handle panics and cancellation, do not detach by accident

Symptom: a task panics and nobody notices, work continues after its owner is gone, or a
`JoinSet` drop cancels work unexpectedly.
Fix: dropping a `JoinHandle` detaches the task. Tokio catches a panic and returns it as a
`JoinError` (`is_panic()`) only to whoever awaits the handle. Collect handles in a `JoinSet` and loop
on `join_next`. Dropping a `JoinSet` aborts all its tasks; `detach_all` keeps them running;
`abort_all` does not remove tasks from the set, so keep calling `join_next` until it is empty.
`JoinSet::join_all` panics if any task fails.
Test: spawn a task that panics and assert the supervisor sees `JoinError::is_panic`.
Source: https://docs.rs/tokio/latest/tokio/task/struct.JoinHandle.html ;
https://docs.rs/tokio/latest/tokio/task/struct.JoinSet.html
Accessed: 2026-11-19

### Shut down in three steps and wait for blocking work

Symptom: the process exits with work in flight, or hangs on exit.
Fix: decide when to stop, tell every task (a cloned `CancellationToken` in a `select!`), then wait
(`TaskTracker`: call `close()` after spawning, then `wait().await`). Dropping a runtime waits
"forever" for `spawn_blocking` tasks; use `shutdown_timeout` to bound it (late work and its threads
leak) or `shutdown_background`. `Runtime::block_on` panics inside an async context.
Source: https://tokio.rs/tokio/topics/shutdown ;
https://docs.rs/tokio/latest/tokio/runtime/struct.Runtime.html
Accessed: 2026-11-19

### Do not rely on async cleanup in `Drop`

Symptom: a connection or file is not flushed when its owner is dropped inside async code.
Fix: give the type an explicit `async fn close(self)` or `shutdown` and call it on every path, or
hand cleanup to a task. Async drop is still unstable behind `feature(async_drop)` and unfinished for
`dyn Trait`. Keep `Drop` free of blocking calls: the Tokio docs say avoiding blocking includes
destructors of objects dropped in async code.
Status: version-specific. The tracking issue is open; recheck before relying on it.
Source: https://github.com/rust-lang/rust/issues/126482 ;
https://docs.rs/tokio/latest/tokio/task/index.html
Accessed: 2026-11-19

## 4. Memory model and library bugs

### Match atomic ordering to what the data needs

Symptom: a reader sees a flag set but stale data, or code uses `SeqCst` everywhere and slows down.
Fix: `Relaxed` gives only a per-variable total order, enough for an independent counter. When data
passes between threads, pair a `Release` store with an `Acquire` load. "SeqCst ordering is almost
never necessary in practice", and a stronger ordering "might even slow your program down".
For shared shadow state use swap or CAS, not a load then a store (`overrides.md` section 5).
Test: write the publish pattern with `Release` and `Acquire` and check it under loom and under Miri
with `-Zmiri-many-seeds`. Neither tool models every `Relaxed` behaviour, so a pass is not proof for
`Relaxed` code.
Source: https://doc.rust-lang.org/std/sync/atomic/enum.Ordering.html ;
http://mara.nl/atomics/memory-ordering.html ;
https://docs.rs/loom/latest/loom/ ; https://github.com/rust-lang/miri/blob/master/README.md
Accessed: 2026-11-19

### Pin patched versions of concurrency libraries

Symptom: memory corruption or a double free in a channel, with no bug in your own code.
Fix: upgrade and add `cargo audit` to CI. Tokio `oneshot::Receiver::close` raced with `send` plus
`await` or `try_recv`. `crossbeam-channel` double-freed in `Drop` on 0.5.12 to 0.5.14.
Status: version-specific. Tokio fixed in `>=1.8.4, <1.9.0` and `>=1.13.1` (RUSTSEC-2021-0124);
crossbeam-channel fixed in `>=0.5.15` (RUSTSEC-2025-0024), a regression from a leak fix in 0.5.12.
Source: https://rustsec.org/advisories/RUSTSEC-2021-0124.html ;
https://rustsec.org/advisories/RUSTSEC-2025-0024.html
Accessed: 2026-11-19

### Cover lock-free code with loom and Miri

Symptom: a rare interleaving corrupts data and ordinary tests pass.
Fix: model-test with loom: route all synchronisation through a crate-local `sync` module that
re-exports `loom` types under `--cfg loom` and `std` types otherwise. Bound large models with
`LOOM_MAX_PREEMPTIONS` (2 or 3 catches most bugs). Loom "can't fully model" `Relaxed`, so a loom
pass is not proof for `Relaxed` code. Cross-check with Miri (`cargo miri test`), which detects data
races and emulates "some" weak memory effects, using `MIRIFLAGS="-Zmiri-many-seeds"` to try other
interleavings. A Miri pass is not proof either; its README says weak memory emulation "is not
complete".
Test: one loom test per lock-free structure, run in CI on the `loom` cfg, plus the same tests under
`cargo miri test` with `-Zmiri-many-seeds=0..16`. A failure in either fails CI.
Source: https://docs.rs/loom/latest/loom/ ;
https://github.com/rust-lang/miri/blob/master/README.md
Accessed: 2026-11-19
