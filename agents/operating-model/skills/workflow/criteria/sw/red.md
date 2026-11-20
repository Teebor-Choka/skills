# Criteria: red step

The judge passes the work only if every rule holds. Each rule names what it is judged against.

## Pass conditions

The judge runs when this step ends, before the next evidence step: the test facts (red, suite green, tests edited) are judged by the checks on that step, not here (P56).

1. The new test targets one behaviour of the unit. Judged against: `evidence.change.diff` (the new test).
2. The step wrote only tests: no production file of the write-set changed. Judged against: `evidence.change.diff` and `evidence.input.unit.write_set`.
3. The test asserts the behaviour, not an implementation detail. Judged against: `evidence.change.diff` (the new test).

## On a fail

The judge reports fail and states the number of the first rule that failed and the test id at fault. The judge adds one sentence on what would make it pass. An unreadable or missing input is a fail.
