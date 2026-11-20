# Criteria: acceptance tests

The judge passes the work only if every rule holds.

## Pass conditions

1. Each test asserts a spec criterion, not an implementation detail.
2. The boundaries are covered: empty, zero, one, maximum, null, concurrent.
3. Every failure path in the spec has a test.
4. No test passes without the feature: each asserts the bad behaviour too.

## On a fail

The judge reports fail and states the number of the first rule that failed and the test id at fault. The judge adds one sentence on what would make it pass.
