# Reproduce the bug

Role: tester.

Read the bug report. Write one acceptance test that fails because of the bug, and commit it.

## Rules

- Write one test for the reported behaviour, at the level where the user sees it.
- Run the test and read the failure. It must fail on an assertion about the reported behaviour. A compile error, an import error or a timeout is not a reproduction.
- Commit the test on the change branch. A test that exists only in the working tree does not count.
- Do not change production code in this step.
- Record the test id, the failing output and the commit.

## Output

Stop once the committed test fails for the right reason.

## Write-set

You may write only test files. Touch nothing else.
