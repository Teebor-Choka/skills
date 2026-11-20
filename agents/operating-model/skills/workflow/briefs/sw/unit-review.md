# Review one unit

Role: reviewer.

Review the unit's diff and tests in isolation.

## Rules

- Check that each test would catch a real regression.
- Check that no test was weakened or edited after the red.
- Check the diff stays inside the write-set.
- Report each defect with the file and line.

## Output

Return pass or fail with the findings.
