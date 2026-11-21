"""IM-56: hand-computed golden values for four synthetic transcripts (metrics 1, 2, 3, 9, 10, 12)."""
import json
import pathlib

import pytest

from helpers import record_of

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
GOLDEN = json.loads((FIXTURES / "golden.json").read_text())


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_record_matches_golden(name):
    got = record_of(FIXTURES / f"{name}.jsonl")
    want = GOLDEN[name]["record"]
    assert set(got) == set(want)
    for key, value in want.items():
        if isinstance(value, float):
            assert got[key] == pytest.approx(value), key
        else:
            assert got[key] == value, key


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_full_record_matches_golden(name):
    got = record_of(FIXTURES / f"{name}.jsonl", full=True)
    for key, value in GOLDEN[name]["full"].items():
        assert got[key] == value, key
    for key, value in GOLDEN[name]["record"].items():  # the wide record extends the narrow one
        if isinstance(value, float):
            assert got[key] == pytest.approx(value), key
        else:
            assert got[key] == value, key
