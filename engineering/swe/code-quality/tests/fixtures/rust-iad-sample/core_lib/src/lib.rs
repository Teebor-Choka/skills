//! Foundational crate: one abstract type (the `Shape` trait) and one
//! concrete type (`Circle`). Nothing here depends on `app`, so within the
//! workspace it is depended upon (Ca=1) but depends on nothing (Ce=0) —
//! stable and half-abstract, sitting near the main sequence.

pub trait Shape {
    fn area(&self) -> f64;
}

pub struct Circle {
    pub radius: f64,
}

impl Shape for Circle {
    fn area(&self) -> f64 {
        std::f64::consts::PI * self.radius * self.radius
    }
}
