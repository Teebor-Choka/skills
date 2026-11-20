# Criteria: improvement scan

The judge passes the work only if every rule holds. Each rule names what it is judged against.

## Pass conditions

1. The report proposes exactly one improvement. Judged against: the output (the scan report).
2. The improvement cites evidence a reader can open: a metric, a ledger entry, or a file and line. Judged against: the output (the scan report) and the cited sources.
3. The report states a criterion that shows the improvement worked. Judged against: the output (the scan report).
4. The report lists what the scan did not examine. Judged against: the output (the scan report).
5. No file was changed by the scan. Judged against: the diff of the working tree.

## On a fail

The judge reports fail and states the number of the first rule that failed and the claim that lacks evidence. The judge adds one sentence on what would make it pass. An unreadable or missing input is a fail.
