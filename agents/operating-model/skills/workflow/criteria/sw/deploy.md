# Criteria: deploy report

The judge passes the work only if every rule holds. Each rule names what it is judged against.

## Pass conditions

1. The report names the deployed commit and it equals the merged head. Judged against: the output (the deploy report) and the merge result in the evidence.
2. Every step of the procedure appears with its result. Judged against: the output (the deploy report) and the project's deploy runbook.
3. A failed step is reported as failed, not omitted. Judged against: the output (the deploy report).
4. No step outside the runbook was run. Judged against: the output (the deploy report).

## On a fail

The judge reports fail and states the number of the first rule that failed and the step it concerns. The judge adds one sentence on what would make it pass. An unreadable or missing input is a fail.
