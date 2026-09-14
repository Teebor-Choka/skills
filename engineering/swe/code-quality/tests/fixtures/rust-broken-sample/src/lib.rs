// Deliberately does not compile — a syntax error. The manifest is valid, so
// cargo metadata succeeds and the metrics all run, but the build/AST-based ones
// (crap, deadcode, iad, …) fail hard on it while the tree-sitter and text
// metrics (cognitive, unsafe, …) still produce output. Used to prove one
// failing metric doesn't break the collect pipeline.
pub fn broken( -> i32 {
    1
}
