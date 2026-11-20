# Write the run report

Role: pm.

Write the report of the finished run for the owner. Use the ledger, the review, the test results and the metrics. Claim nothing that these sources do not show.

## Rules

- Give each of the six sections a body with content: Summary, Acceptance, Tests, Defects, Metrics, Not verified.
- Under Acceptance, list each criterion of the item and whether the evidence shows it met.
- Under Defects, list every defect found in review or after deploy, with its status.
- Under Not verified, name what no check or reviewer covered. Write "nothing" only when you can say why.
- Do not write n/a or a placeholder as a body.

## Output

One JSON object: `{"report": <the report as Markdown with the six sections as level-two headings>}`.

## Write-set

You may write nothing in the repository. Read only.
