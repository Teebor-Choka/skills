# Project Overrides

These rules **supersede** the base [guidelines.txt](guidelines.txt) where they conflict.
Always apply these first; fall back to guidelines.txt for topics not covered here.

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

---

## 2. Naming & Style

**Follow Rust conventions:** `snake_case` for variables/functions, `CamelCase` for types/traits.

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

**Write `///` doc comments for all public items.** First sentence: one line, ~15 words (reinforces `M-FIRST-DOC-SENTENCE`).

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

---

## 8. Error Handling

**Application crates** may use `anyhow`/`eyre` (overrides `M-ERRORS-CANONICAL-STRUCTS`). **Library crates** must use canonical error structs.

**Always use `.context()`, never raw `unwrap()`** in production code. Tests with fallible operations must return `anyhow::Result<()>`:

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

## 12. Build & Release Workflow

Run at the end of each code iteration:

1. `nix fmt`
2. `cargo shear --fix`
3. `cargo build ...`
4. `cargo test`

**Bump crate versions per PR** following semver:
- **Patch** (1.2.x → 1.2.y): bug fixes, internal changes
- **Minor** (1.2.x → 1.3.0): new features, **deprecations**
- **Major** (1.x → 2.0.0): breaking changes


**Minimal scope** — only touch crates you changed with cargo utilities.
