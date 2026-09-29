# Project Overrides

These rules **supersede** the base [guidelines.txt](guidelines.txt) where they conflict.
Always apply these first; fall back to guidelines.txt for topics not covered here.

**Contents:** 1 Immutability & Type Safety · 2 Naming & Style · 3 Pattern Matching & Iteration · 4 Documentation · 5 Async & Concurrency · 6 Tracing & Logging · 7 Testing · 8 Error Handling · 9 Crate Layout & Features · 10 Configurability · 11 Builder Pattern · 12 Build & Release Workflow · 13 Blanket Impls for Smart Pointers · 14 Tooling & Gotchas

---

## 1. Immutability & Type Safety

**Prefer immutable structures.** Default to `let` bindings, owned values, and `&self` receivers.
Use `mut` only when mutation is the clearest solution.

**Use `Result` and `Option` — never sentinel values.**

```rust
// Do
fn find_peer(id: &PeerId) -> Option<&Peer> { ... }

// Don't
fn find_peer(id: &PeerId) -> *const Peer { ... } // null = not found
```

**Use the strongest type available** (extends `M-STRONG-TYPES`).
Use `BiMap` for bidirectional mappings instead of two separate `HashMap`s.

**Prefer `TryFrom`/`Into`/`From`** over ad-hoc `from_u8()`/`to_x()` conversion methods.

---

## 2. Naming & Style

**Follow Rust conventions:** `snake_case` for variables/functions, `CamelCase` for types/traits.

**Place `use` imports at the top** of the file, module, or test block — never inline in a function body.

**Test fixtures:** use descriptive names like `stubbed`, `not_running`, `with_default_config` — not `test_fixture` or `setup`.

**Test modules and integration test files:** name by scenario/component, not generically (`stubbed`, `probe_content` — not `tests`).

**Test function names use `<component>_should_..._when_...`.** No `test_` prefix. Mimics given/then logic:

```rust
#[test]
fn parser_should_return_none_when_input_is_empty() { ... }
// Not: fn test_empty_input_returns_none()
```

**Custom `Debug`:** use `debug_struct(...).finish_non_exhaustive()`.

**Names are free of weasel words** (reinforces `M-CONCISE-NAMES`).

---

## 3. Pattern Matching & Iteration

**Prefer `match` over chains of `if let` / `else`.**

**Match errors explicitly** — avoid premature `return Err(...)` when `match` with `Ok`/`Err` arms is clearer:

```rust
// Do
match connection.send(packet).await {
    Ok(ack) => process_ack(ack),
    Err(e) => handle_send_error(e),
}

// Don't — premature abort hides the happy path
let ack = connection.send(packet).await.map_err(|e| { ... })?;
```

**Prefer functional/iterator style** over manual loops (`find_map`, `filter_map`, `take(n).map(...).collect()`).

**Use `VecDeque` over `Vec::remove(0)`** for queue-like access — `Vec::remove(0)` is O(n).

**Destructure tuples and structs accessed more than twice** in the same scope instead of repeating `.0` / `.1` or field access:

```rust
// Do
let (offchain, chain) = &peer_keys[i];
let graph = ChannelGraph::new(*offchain.public());
let chain_inst = StubChain::new(offchain, chain);

// Don't — repeated indexing obscures which key is which
let graph = ChannelGraph::new(*peer_keys[i].0.public());
let chain_inst = StubChain::new(&peer_keys[i].0, &peer_keys[i].1);
```

---

## 4. Documentation

**Make every public item's contract discoverable to its callers** via `///` docs — a caller who can't read the impl should still know how to use it correctly. First sentence: one line, ~15 words (reinforces `M-FIRST-DOC-SENTENCE`).

**Document the "why" for constraints and limits**, not just the value:

```rust
/// Must be less or equal to 2^24 - 1.
///
/// Constrained by the 24-bit encoding in the on-chain ticket format.
pub const MAX_CHANNEL_EPOCH: u32 = (1 << 24) - 1;
```

**Use proper code block syntax** (`/// ```rust`) in doc examples.

---

## 5. Async & Concurrency

**Default to native `async fn` in traits** (Rust 1.75+). Reserve `async-trait` for `dyn Trait` or MSRV < 1.75.

**Handle Send bounds explicitly on public traits** via `trait-variant` or `-> impl Future<Output = T> + Send`.

**Place `Send + Sync` bounds in `where` clauses**, not on trait definitions:

```rust
// Do
trait TagAllocator { fn allocate(&self) -> Tag; }
impl<A> SessionManager<A> where A: TagAllocator + Send + Sync { ... }

// Don't
trait TagAllocator: Send + Sync { fn allocate(&self) -> Tag; }
```

**Remove unnecessary generic bounds from struct definitions.** Only add bounds on `impl` blocks.

**Prefer async runtime-agnostic code.** Use `tokio` behind a `runtime-tokio` feature when needed.

**Pick the Mutex by runtime:** `parking_lot::Mutex` (sync), `tokio::Mutex` (tokio async),
`async_lock::Mutex` (runtime-agnostic async).

**Use `futures_time::stream::interval`** over `sleep` loops:

```rust
// Do
futures_time::stream::interval(duration)
    .for_each(|_| async { do_work().await }).await;

// Don't
loop { do_work().await; tokio::time::sleep(duration).await; }
```

**Use atomic swap/CAS for concurrent shadow state**, not separate load + store.

---

## 6. Tracing & Logging

**Prefix tracing macros with `tracing::`** — always `tracing::info!(...)`, never bare `info!(...)`.

**Use structured fields, not bracket prefixes:** `tracing::info!(direction = "forward", ...)`
over `[forward] ...`. Tracing renders string fields quoted (`direction="forward"`).

**In a `macro_rules!` matcher forwarded to a `tracing::*` message argument, use `$label:literal`,
not `$label:expr`.** The message position requires a string literal; `expr` compiles at the macro
definition but fails at expansion when a caller passes anything other than a bare literal.

---

## 7. Testing

**Tests with fallible operations must return `anyhow::Result<()>`** with `.context()` — see §8 for details and examples.

**Use `rstest` with `#[case]` for 2+ similar cases.** Don't copy-paste tests with different inputs:

```rust
#[rstest]
#[case(0, false)]
#[case(1, true)]
#[case(42, true)]
fn validator_should_accept_positive_numbers(#[case] input: u32, #[case] expected: bool) {
    assert_eq!(is_valid(input), expected);
}
```

**Use `insta` snapshots for complex assertions.** Prefer `assert_yaml_snapshot!` for nested structures; use `assert_debug_snapshot!` for flat types.

**Error assertions:** use `matches!()` or `match` — see §8 for rules and examples.

**Generate reusable static test data** — shared constants, builders, or `rstest` fixtures for common objects.

**Always consider boundary and edge cases:** empty inputs, single-element, duplicates, max/min values.

**After editing tests or code, rerun the closest package test suite.**

**Poll the actual precondition for async convergence** (channel propagation, probe warmup,
cache population) in a retry loop with a timeout — not a fixed `sleep()`, which is too short on
slow CI and wastefully long on fast machines.

**Activate a crate feature for tests only** with a self-referencing dev-dependency:
`crate-name = { path = ".", features = ["feature"] }` in `[dev-dependencies]`.

**Don't combine rstest `#[case]` with `insta::assert_*_snapshot!`** — the case→snapshot-file
mapping is non-deterministic across parallel runs. Collect the cases into one `Vec` and snapshot
once. Never `assert_yaml_snapshot!(format!("{:?}", obj))`.

**Regenerate insta snapshots** with `cargo insta test --accept -p <crate>`, not
`INSTA_UPDATE=always` (which can overwrite with wrong content during parallel runs). Before
deleting a `.snap` file, grep for the snapshot name or its producing test first.

**Build e2e/integration test binaries `--release`** — never a slow custom profile for the test
binary itself.

---

## 8. Error Handling

**Application crates** may use `anyhow`/`eyre` (overrides `M-ERRORS-CANONICAL-STRUCTS`). **Library crates** must use canonical error structs.

**Surface fallible errors with context** (`.context()`) in production code; reserve `unwrap`/`expect` for values you can prove infallible or for asserting a broken invariant, and say why. Tests with fallible operations must return `anyhow::Result<()>`:

```rust
#[test]
fn config_should_parse_valid_input() -> anyhow::Result<()> {
    let cfg = Config::from_str(INPUT).context("failed to parse")?;
    let addr = cfg.listen_addr().context("missing listen addr")?;
    assert_eq!(addr.port(), 9091);
    Ok(())
}
```

**Match error variants structurally, never by string.** Use `matches!()` for simple variants, `match` for complex ones:

```rust
// Simple variant
assert!(matches!(result, Err(MyError::NotFound)));

// Complex variant with data to inspect
match result {
    Err(MyError::Timeout { duration }) => assert!(duration > MIN_TIMEOUT),
    other => panic!("expected Timeout, got {other:?}"),
}

// Don't — fragile string matching
assert!(format!("{}", result.unwrap_err()).contains("not found"));
```

**Check the `Error` associated type** of the relevant `TryFrom`/`From` impl before pattern-matching
on it with `matches!`.

**Use `anyhow::ensure!()` for boolean guards in tests** — not `matches!().then_some(()).context()`:

```rust
// Do
anyhow::ensure!(
    matches!(msg, Message::Probe(Ping(_))),
    "expected Probe(Ping)"
);

// Don't — awkward bool→Option→Result chain
matches!(msg, Message::Probe(Ping(_)))
    .then_some(())
    .context("expected Probe(Ping)")?;
```

---

## 9. Crate Layout & Features

**Standard crate layout:** `lib.rs` (imports/re-exports), `config.rs` (configuration), `errors.rs` (error types).

**Config objects** should implement `validator::Validate` and use `smart-default`.

**Features must be additive** (reinforces `M-FEATURES-ADDITIVE`). Don't default features that force a choice:

```toml
# Do — user chooses runtime
[features]
runtime-tokio = ["dep:tokio"]

# Don't
[features]
default = ["runtime-tokio"]
```

**Use `features = ["inline"]` for dashmap** when performance matters.

**Prefer orthogonal features** composed via `#[cfg(all(feature = "a", feature = "b"))]` over a
compound `"a-b"` feature. Compound features explode combinatorially and obscure which dependency
each gate needs; keep a compound name only as a backward-compat alias when removing it would
break downstream consumers.

---

## 10. Configurability

**Make intervals, thresholds, and tuning parameters configurable.** Use `serde` + `humantime` for durations:

```rust
#[derive(Debug, Deserialize)]
pub struct ProtocolConfig {
    #[serde(with = "humantime_serde")]
    pub counter_flush_interval: Duration,
}
```

---

## 11. Builder Pattern

**Use `with_` prefix for builder setters.** Without it, `epoch()` reads as a getter. `with_` signals a chainable setter:

```rust
// Do
pub fn with_epoch(mut self, epoch: u32) -> Self { self.channel_epoch = epoch; self }

// Don't — ambiguous
pub fn epoch(mut self, epoch: u32) -> Self { ... }
```

**Never silently clamp invalid input.** Return an error for out-of-range values — silent clamping hides bugs:

```rust
// Do
if self.ticket_index > MAX_TICKET_INDEX {
    return Err(InvalidInputData("ticket index exceeds maximum".into()));
}

// Don't
ticket_index: self.ticket_index.min(MAX_TICKET_INDEX), // bug hidden
```

---

## 13. Blanket Impls for Smart Pointers

**Use `#[auto_impl::auto_impl(&, Box, Arc)]`** on traits that should work transparently through reference-like wrappers, instead of writing three identical blanket impls by hand:

```rust
// Do — one attribute generates &T, Box<T>, Arc<T> impls automatically
#[auto_impl::auto_impl(&, Box, Arc)]
pub trait Logger {
    fn log(&self, msg: &str);
}

// Don't — repetitive boilerplate that drifts when the trait changes
impl<T: Logger> Logger for &T     { fn log(&self, msg: &str) { (**self).log(msg) } }
impl<T: Logger> Logger for Box<T> { fn log(&self, msg: &str) { (**self).log(msg) } }
impl<T: Logger> Logger for Arc<T> { fn log(&self, msg: &str) { (**self).log(msg) } }
```

For **static methods** (no `self` receiver), add `where Self: Sized` so `auto_impl` can delegate to the inner type:

```rust
#[auto_impl::auto_impl(&, Box, Arc)]
pub trait Protocol {
    fn version() -> u32 where Self: Sized;
    fn send(&self, payload: &[u8]);
}
```

Add the dependency once per workspace: `auto_impl = "1"`.

---

## 12. Build & Release Workflow

Run these at the end of each code iteration, in this exact order:

1. `nix fmt` — format first, so later steps don't re-flag formatting churn.
2. `cargo shear` — check-only at the workspace root, or `cargo shear --fix -p <crate>` for a
   single package. Never `--fix` at the workspace root without `-p` (it strips workspace deps);
   even with `-p`, run `git diff Cargo.toml` afterward — the tool can wrongly touch root
   workspace deps and can remove a dep another member still uses, so follow up with a
   full-workspace `cargo check`.
3. `cargo machete` — catches deps `cargo shear` misses. serde helper crates used via
   `#[serde(with = "...")]` are false positives; add them to
   `[package.metadata.cargo-machete] ignored`. hoprnet-org CI runs `cargo-machete` specifically,
   so run both locally before pushing.
4. `cargo build ...`
5. `cargo clippy --lib --tests` — full workspace, not package-scoped.
6. `cargo test`

Use the narrowest cargo scope that covers your changes (`-p <crate>`) for building and testing.
Clippy (step 5) is the deliberate exception — run it across the full workspace, since a change in
one crate can surface lints in its dependents.

**Update `Cargo.lock` with `cargo update -p <crate>`** after a version bump — never
`cargo generate-lockfile`, which re-resolves the whole workspace and can silently upgrade
unrelated crates to breaking versions.

**Bump crate versions per PR** following semver:

- **Patch** (1.2.x → 1.2.y): bug fixes, internal changes
- **Minor** (1.2.x → 1.3.0): new features, **deprecations**
- **Major** (1.x → 2.0.0): breaking changes

**Minimal scope** — only touch crates you changed with cargo utilities.

---

## 14. Tooling & Gotchas

**Design:** use TDD to drive new modules and features; when the design is unclear, ask rather
than guess.

**Typed atomics over stringly state.** Use `#[atomic_enum::atomic_enum]` for a typed atomic enum
instead of `AtomicU8` + a manual `TryFrom<u8>` — it gives typed `load`/`store`/`compare_exchange`
with no hand-written conversion (as `HoprState` does in hopr-api). Prefer it over
`RwLock<String>` when the string is only a rendering of underlying state.

**`Cow<'static, str>` in enum payloads** carrying fixed diagnostic messages avoids a heap
allocation on every read while still allowing dynamic messages via `Cow::Owned`.

**Mocking with `mockall`:**

- Async trait methods expect `Pin<Box<dyn Future<Output = T>>>`, not `T` — use
  `Box::pin(async { ... })` in `returning` closures.
- `mockall::mock!` can't handle generic methods or two same-named methods across different traits
  — hand-roll a stub/composite struct in those cases.

**Clippy and imports:**

- A trait must be in scope for method resolution (`graph.identity()` needs `use NetworkGraphView`)
  even when clippy marks the import unused — confirm it isn't needed for dispatch before removing.
- If an import's only use is inside a `#[cfg(feature = "...")]` block, gate the import with the
  matching `#[cfg]` rather than removing it; clippy without the feature will otherwise flag it.

**Misc:**

- `debug_assert!(false, ...)` panics in test/debug builds — use `tracing::warn!` for a soft
  fallback in a production path that tests exercise.
- A `#![...]` inner attribute on line 1 looks like a shebang to pre-commit — put a `//` comment
  above any module-level `#![cfg(...)]`/`#![allow(...)]` at the start of a new test file to avoid
  `check-shebang-scripts-are-executable` failures.
- For a `tokio::time::timeout` result used in an assertion, prefer `result.unwrap_or_default()`
  over `result.is_err() || result.unwrap().is_empty()`.
- Enforce const-generic constraints at compile time with `const _ASSERT: () = assert!(...);`
  inside the `impl<const N: usize>` block — an invalid `N` then fails the build instead of
  panicking at runtime (e.g. divide-by-zero on `N = 0`).
- Trait definitions for git dependencies live in `~/.cargo/git/checkouts/<crate>-<hash>/<rev>/`.
- With Criterion's `iter_batched`, the setup closure must produce everything the timed closure
  consumes — don't clone data inside the timed closure that setup could generate.
