# Criteria: acceptance tests

The judge passes the work only if every rule holds. Each rule names what it is judged against.

## Pass conditions

1. Each test asserts a spec criterion, not an implementation detail. Judged against: the test files and the tests list of the spec-coverage evidence.
2. Where meaningful for the criterion, the boundaries are covered: empty, zero, one, maximum, null, concurrent. Judged against: output (the test files, per criterion).
3. Every failure path in item.failure_definition has a test. Judged against: item.failure_definition and the test files.
4. Each test asserts the bad behaviour, so it cannot pass without the feature. Judged against: output (the test files).
5. Each test also asserts the good behaviour it guards. Judged against: output (the test files).
6. Every listed test id is a pytest node id such as `tests/test_x.py::test_y`. Judged against: output (the tests list).

## On a fail

The judge reports fail and states the number of the first rule that failed and the test id at fault. The judge adds one sentence on what would make it pass. An unreadable or missing input is a fail.
