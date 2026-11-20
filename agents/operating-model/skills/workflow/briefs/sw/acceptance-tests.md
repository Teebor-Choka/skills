# Write the acceptance tests

Role: tester.

Write one or more tests for every criterion in the approved item. Derive them from the spec, not from any implementation.

## Rules

- Cover the boundaries where meaningful for the criterion: empty, zero, one, maximum, null, concurrent.
- Cover every failure path the spec names.
- Tag each test with the criterion ids it covers.
- Assert the bad behaviour too, not only the good one.

## Output

Write test files only. Do not write production code. Every test must fail on an assertion before the build starts.

## Write-set

You may write only the acceptance test files. The cut later forbids every unit from writing them.

## Test ids

List each test by its pytest node id, for example `tests/test_x.py::test_y`. The checks compare these ids with the real test run.
