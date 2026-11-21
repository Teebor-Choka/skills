//! Fixture for the structural metrics: one keyword-flagged block (for the
//! density count) and one genuinely dead private function (for dead-code
//! detection). No external dependencies, so `cargo check` runs offline.
//! (Comments here deliberately avoid the raw keyword so the count is exact.)

/// A used public function whose body dereferences a raw pointer.
///
/// # Safety
/// `p` must be a valid, aligned pointer to an initialized `u8`.
pub unsafe fn first_byte(p: *const u8) -> u8 {
    unsafe { *p }
}

// Never called from anywhere reachable, and private -- rustc flags it.
fn dead_helper() -> i32 {
    42
}
