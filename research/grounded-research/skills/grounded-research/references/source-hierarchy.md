# Source hierarchy

Rank by closeness to the origin of the claim. Prefer the higher rung; cite lower rungs only as
pointers or when nothing higher exists, and say so.

| Domain                    | Primary (cite these)                                                                                                              | Secondary (pointers only)                 |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| Science, ML               | The paper on its archive page (arXiv, journal, conference proceedings), the dataset card, the authors' repository                 | Blog posts, news, summaries, social posts |
| Software and tools        | Official documentation at a pinned version, the release notes, the source repository, the licence file, the package registry page | Tutorials, Q&A answers, aggregator sites  |
| Standards and protocols   | The standards body's published text (IETF RFC, W3C, ISO catalogue entry)                                                          | Explainers                                |
| Law and regulation        | The statute or official journal text, the regulator's published guidance                                                          | Law-firm notes, news                      |
| Markets and companies     | Filings, the company's own announcements, audited reports, exchange data                                                          | Analyst commentary, press                 |
| Government and statistics | The statistics office or agency dataset and its methodology note                                                                  | Press coverage                            |

## Judging a source

- **Owner:** is the source the party that makes or controls the thing? A vendor is authoritative for
  its product's behaviour and not for how it compares with competitors.
- **Date:** published and last-updated; stale pages go in `Conflicts` or `Hearsay` when a newer
  primary source disagrees.
- **Version:** docs for the version in question, not "latest" by accident.
- **Independence:** count copies once.
- **Access:** if you could only see a snippet, an abstract, or a cached copy, say so in the
  `Why unverified` column.
