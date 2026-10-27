# Accepted tradeoffs

Owner decisions that validators use to reject findings that are not defects. Every entry cites the
decision that created it (escalation item id). Validators read this file before every verdict.

An entry that is wrong is deleted, not edited: add a new entry that supersedes it.

```
## T-<n>: <short name>
decision: <what was accepted, one sentence>
scope: <areas or items it covers>
reason: <why the owner accepted it>
source: <escalation item id and date>
reopen-if: <condition that voids it>
```

Example:

```
## T-1: stale cache on reload
decision: A viewer may see data up to 30 s old after reload.
scope: area:viewer
reason: Fresh reads cost a round trip per frame; the owner values frame rate.
source: ESC-12, 2026-10-27
reopen-if: A user reports a wrong value that lasts longer than 30 s.
```
