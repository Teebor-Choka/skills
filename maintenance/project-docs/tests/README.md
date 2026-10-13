# validate_docs tests

Run with `python3 -m pytest tests/` from the skill directory (needs only pytest; the validator
itself is standard-library-only).

`fixtures/conformant/` is a sample project doc tree that passes clean. Each broken-variant test copies
it into a tmp dir and mutates exactly one thing, so a failure points at a single rule.
