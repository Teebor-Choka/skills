from pkg.core import classify, trivial


def test_classify_small():
    assert classify(5) == "small"


def test_trivial():
    assert trivial() == 42
