//! Glue crate: its one type (`App`) holds a `core_lib::Circle`, so it
//! depends on `core_lib` (Ce=1) while nothing depends on it (Ca=0) — fully
//! unstable and concrete, correct for a leaf application crate.

use core_lib::Circle;

pub struct App {
    pub shape: Circle,
}

impl App {
    pub fn total_area(&self) -> f64 {
        use core_lib::Shape;
        self.shape.area()
    }
}
