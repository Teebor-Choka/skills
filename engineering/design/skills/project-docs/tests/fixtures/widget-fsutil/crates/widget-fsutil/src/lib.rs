//! Fixture sources: only the exported names matter to the validator tests.
pub mod secret;

pub const STALE_STAGING_PREFIXES: &[&str] = &["widget-"];

pub enum FsError {
    Io,
    NotDurable,
    Unsafe,
}

pub struct Beneath;
pub struct Entries;
pub enum EntryKind {
    File,
    Dir,
}

pub fn current_uid() -> u32 {
    0
}
pub fn fsync_dir() {}
pub fn private_staging_dir() {}
pub fn ensure_widget_staging_base() {}
pub fn ensure_staging_base_in() {}
pub fn sweep_stale_staging_dirs() {}
