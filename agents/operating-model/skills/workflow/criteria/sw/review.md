# Criteria: final review

The judge passes the work only if every rule holds. Each rule names what it is judged against.

## Pass conditions

1. The reviewer's verdict is approve and no upheld defect is open. Judged against: output (the review verdict and findings list).
2. Every criterion of the item is checked against the change. Judged against: the review's per-criterion notes and item.criteria.
3. Each reported defect cites a file, a line and a criterion. Judged against: output (the review findings).
4. The review names what was not verified. Judged against: output (the review's not-verified list).
5. No defect was waved through because the tests pass. Judged against: the diff and the test results.

## On a fail

The judge reports fail and states the number of the first rule that failed and a sample of the missed defects. The judge adds one sentence on what would make it pass. An unreadable or missing input is a fail.

A reject verdict fails the item. A reject verdict fails the item even when every other rule holds.
