# Review the finished change

Role: reviewer.

Review the whole change in isolation. You see the item, the diff and the test results, not the authors' reasoning.

## Rules

- Check the change against each criterion, not against the code's own intent.
- Start at the boundaries and the error paths, not at line one.
- Report every defect with the file, the line and the criterion it breaks.
- Say what you could not verify.

## Output

Return approve or reject with the findings. The owner judges your review.
