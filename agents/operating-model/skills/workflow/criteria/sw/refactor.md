# Criteria: refactor step

The judge passes the work only if every rule holds. Each rule names what it is judged against.

## Pass conditions

1. The refactor leaves behaviour unchanged. Judged against: the diff and the refactor-evidence output.
2. No test file was edited in this step. Judged against: the refactor-evidence output tests_edited.
3. The refactor removes duplication or unclear names the unit introduced, not other code. Judged against: the diff and the unit's write_set in the cut output.

## On a fail

The judge reports fail and states the number of the first rule that failed and the file and line at fault. The judge adds one sentence on what would make it pass. An unreadable or missing input is a fail.
