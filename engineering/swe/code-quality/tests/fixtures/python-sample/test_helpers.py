from pkg.helpers import describe


def test_describe():
    assert describe(5) == "5 is small"
