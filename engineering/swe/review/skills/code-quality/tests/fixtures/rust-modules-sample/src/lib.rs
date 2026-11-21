//! Fixture for the module-graph metrics: a public API surface (rust:api),
//! cross-module `uses` edges (rust:fanio: widgets and make_gadget both use
//! Gadget), and an on-disk file never linked as a module (rust:orphans:
//! src/orphan.rs). No external dependencies, so it builds offline.

pub mod widgets;
mod internal;

pub struct Gadget {
    pub id: u32,
}

pub fn make_gadget(id: u32) -> Gadget {
    internal::helper();
    Gadget { id }
}
