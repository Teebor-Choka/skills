# Criteria: unit review

The judge passes the work only if every rule holds.

## Pass conditions

1. Each new test would fail if the behaviour regressed.
2. No test was edited or weakened after the red run.
3. The diff stays inside the unit's write-set.
4. Each reported defect cites a file and a line.

## On a fail

The judge reports fail and states the number of the first rule that failed and the file and line at fault. The judge adds one sentence on what would make it pass.
