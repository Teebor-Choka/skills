pub fn classify(n: i32) -> &'static str {
    if n < 0 {
        "negative"
    } else if n == 0 {
        "zero"
    } else if n < 10 {
        "small"
    } else {
        "large"
    }
}

pub fn trivial() -> i32 {
    42
}

pub fn classify2(n: i32) -> &'static str {
    if n < 0 {
        "negative"
    } else if n == 0 {
        "zero"
    } else if n < 10 {
        "small"
    } else {
        "large"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classify_should_return_small_when_in_range() {
        assert_eq!(classify(5), "small");
    }
}
