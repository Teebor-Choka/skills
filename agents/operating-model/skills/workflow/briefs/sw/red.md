# Write the failing test

Role: worker.

Write the test for the next slice of the unit. Run it. It must fail on an assertion.

## Rules

- Write one behaviour per test.
- Run the test and read the failure. A compile error, an import error or a timeout is not a red.
- Do not write production code in this step. In a rework round the production files of the write-set may still
  hold the last round's code: restore each one to the base first (`git checkout -- <file>` for a tracked file,
  delete a file the last round created). The red check fails while a production file of the write-set differs
  from the base.
- A test for a function that does not exist yet fails with an import error. That counts as red only when the unit
  lists the function in `new_symbols`; do not write a stub.
- Record the test id and the failing output.

## Output

Stop once the test fails for the right reason.

## Write-set

You may write only test files inside the unit's write-set. Touch nothing else.
