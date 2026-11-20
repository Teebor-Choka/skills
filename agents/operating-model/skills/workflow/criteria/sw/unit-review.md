# Criteria: unit review

The judge passes the work only if every rule holds. Each rule names what it is judged against.

## Pass conditions

1. The reviewer's verdict is pass and no upheld defect is open. Judged against: output (the unit review verdict and findings list).
2. Each new test would fail if the behaviour regressed. Judged against: output (the unit's test files).
3. No test was edited or weakened after the red run. Judged against: the unit's diff and the green-evidence tests_edited field.
4. The diff stays inside the unit's write-set. Judged against: `evidence.change.diff` and `evidence.input.unit.write_set`.
5. Each reported defect cites a file and a line. Judged against: output (the review findings).

## On a fail

The judge reports fail and states the number of the first rule that failed and the file and line at fault. The judge adds one sentence on what would make it pass. An unreadable or missing input is a fail.

A fail verdict fails the item, so the rework loop cannot end accepted on a rejected unit.
