# Criteria: red step

The judge passes the work only if every rule holds. Each rule names what it is judged against.

## Pass conditions

1. The new test targets one behaviour of the unit. Judged against: output and evidence of the red-evidence step.
2. The test was written before any production code for it. Judged against: the red step's diff and the red-evidence output.
3. The test asserts the behaviour, not an implementation detail. Judged against: output (the new test file).

## On a fail

The judge reports fail and states the number of the first rule that failed and the test id at fault. The judge adds one sentence on what would make it pass. An unreadable or missing input is a fail.
