# Extract claims

Turn the recorded sources into a list of claims.

1. One claim is one statement of fact that one source can confirm or refute.
2. Every claim cites at least one source from the search output, with its URL and access date. Do not cite
   a source that the search did not record.
3. Keep the source's quote with the claim, so a reviewer can check it without a new search.
4. When two sources disagree, write one claim per position and cite each position's source.

Return JSON: `{"claims": [{"id", "text", "sources": [{"url", "accessed", "quote"}]}]}`.
The next code step, `claims-cited`, fails when any claim has no source with both a URL and an access date.
