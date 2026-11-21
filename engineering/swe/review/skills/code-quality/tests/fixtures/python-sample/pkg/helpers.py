from pkg.core import classify


def classify2(n: int) -> str:
    if n < 0:
        return "negative"
    elif n == 0:
        return "zero"
    elif n < 10:
        return "small"
    else:
        return "large"


def describe(n: int) -> str:
    return f"{n} is {classify(n)}"
