# Criteria: green step

The judge passes the work only if every rule holds. Each rule names what it is judged against.

## Pass conditions

1. The production code is the least that makes the failing test pass. Judged against: the green step's diff.
2. No test file was edited in this step. Judged against: the green-evidence output tests_edited.
3. The change stays inside the unit's write-set. Judged against: the diff and the unit's write_set in the cut output.

## On a fail

The judge reports fail and states the number of the first rule that failed and the file and line at fault. The judge adds one sentence on what would make it pass. An unreadable or missing input is a fail.
