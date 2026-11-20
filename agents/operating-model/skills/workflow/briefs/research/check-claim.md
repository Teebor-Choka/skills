# Check one claim

You see one claim and its cited sources. You did not write it.

1. Open each cited URL. Confirm that the quote is on the page and that it says what the claim says.
2. Give one verdict:
   - `verified`: a primary source states the claim.
   - `hearsay`: only a secondary source states it, or the primary source only implies it.
   - `refuted`: a cited source contradicts the claim.
   - `unreachable`: no cited URL could be opened.
3. Give one sentence of evidence for the verdict.

Return JSON: `{"id", "verdict", "evidence"}`. A `hearsay`, `refuted` or `unreachable` verdict is a valid
result: report it, do not try to fix the claim.
