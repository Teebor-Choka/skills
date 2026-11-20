# Criteria: bug reproduction

The judge passes the work only if every rule holds. Each rule names what it is judged against.

## Pass conditions

1. The test targets the behaviour in the bug report, not a nearby behaviour. Judged against: the bug report and the test source.
2. The test asserts the reported wrong result or the missing result. Judged against: the test source and the recorded failing output.
3. The failing output shows an assertion failure. Judged against: the recorded failing output.
4. No production code changed in this step. Judged against: the diff of the reproduction commit.

## On a fail

The judge reports fail and states the number of the first rule that failed and the line of the test or output that breaks it. The judge adds one sentence on what would make it pass. An unreadable or missing input is a fail.
