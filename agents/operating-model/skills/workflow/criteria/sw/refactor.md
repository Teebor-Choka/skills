# Criteria: refactor step

The judge passes the work only if every rule holds. Each rule names what it is judged against.

## Pass conditions

The judge runs when this step ends, before the next evidence step: the test facts (red, suite green, tests edited) are judged by the checks on that step, not here (P56).

1. The refactor leaves behaviour unchanged. Judged against: `evidence.change.diff`.
2. No existing test was changed. Judged against: `evidence.change.diff`.
3. The refactor removes duplication or unclear names the unit introduced, not other code. A refactor that changes nothing passes when the unit's code has nothing to clean up (P60). Judged against: `evidence.change.diff` and `evidence.input.unit.write_set`.

## On a fail

The judge reports fail and states the number of the first rule that failed and the file and line at fault. The judge adds one sentence on what would make it pass. An unreadable or missing input is a fail.
