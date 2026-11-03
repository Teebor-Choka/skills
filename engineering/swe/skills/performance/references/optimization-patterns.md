# Optimization patterns

### Algorithm improvements

**Time complexity:**

- O(n²) → O(n log n) — sorting, searching
- O(n) → O(log n) — binary search, trees
- O(n) → O(1) — hash maps, memoization

**Space-time tradeoffs:**

- Cache computed results (memoization)
- Precompute expensive operations
- Index data for faster lookup
- Use hash maps for O(1) access

### Memory optimization

**Reduce allocations:**

```typescript
// Bad: creates new array each iteration
for (const item of items) {
  const results = [];
  results.push(process(item));
}

// Good: reuse array
const results = [];
for (const item of items) {
  results.push(process(item));
}
```

```rust
// Bad: allocates String every time
fn format_user(name: &str) -> String {
    format!("User: {}", name)
}

// Good: reuses buffer
fn format_user(name: &str, buf: &mut String) {
    buf.clear();
    buf.push_str("User: ");
    buf.push_str(name);
}
```

**Memory pooling:**

- Reuse expensive objects (connections, buffers)
- Object pools for frequently allocated types
- Arena allocators for batch allocations

**Lazy evaluation:**

- Compute only when needed
- Stream processing vs loading all data
- Iterators over materialized collections

### I/O optimization

**Batching:**

- Batch API calls (1 request vs 100)
- Batch database writes (bulk insert)
- Batch file operations (single write vs many)

**Caching:**

- Cache expensive computations
- Cache database queries (Redis, in-memory)
- Cache API responses (HTTP caching)
- Invalidate stale cache entries

**Async I/O:**

- Non-blocking operations (async/await)
- Concurrent requests (Promise.all, tokio::spawn)
- Connection pooling (reuse connections)

### Database optimization

**Query optimization:**

- Add indexes for common queries
- Use EXPLAIN/EXPLAIN ANALYZE
- Avoid N+1 queries (use joins or batch loading)
- Select only needed columns
- Filter at database level (WHERE vs client filter)

**Schema design:**

- Normalize to reduce duplication
- Denormalize for read-heavy workloads
- Partition large tables
- Use appropriate data types

**Connection management:**

- Connection pooling (don't create per request)
- Prepared statements (avoid SQL parsing)
- Transaction batching (reduce round trips)
