# Search the web

Search for sources that answer the sub-questions in `questions`.

1. Prefer primary sources: the official documentation, the specification, the vendor's own page, the
   author's own post.
2. Use only hosts that the policy `research.source-allowlist` permits.
3. For each source, record the URL, the access date (YYYY-MM-DD), the sub-question it answers, and a short
   quote that carries the answer.
4. Mark a source as `secondary` when it reports what another source said.
5. Record a sub-question with no source found as `not-found`. Do not guess an answer.

Return JSON: `{"sources": [{"url", "accessed", "question", "quote", "kind": "primary" | "secondary"}],
"not_found": [...]}`.
