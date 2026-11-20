# Rubric: recorded sources

The judge reads the search task's output. It passes only when every rule holds.

1. Every source has a URL, an access date (YYYY-MM-DD), the sub-question it answers, and a quote.
2. Every URL is on a host that the policy `research.source-allowlist` permits.
3. A source that reports what another source said is marked `secondary`.
4. Every sub-question has at least one source or is listed as `not-found`.
5. No sub-question is answered without a source.

## On a fail

Report the number of each rule that fails, the source URL or sub-question it concerns, and one sentence on
what is wrong.
