# Frame the question

You receive one research question as `question`.

1. Restate the question in one sentence that a source can answer.
2. Split it into at most 5 sub-questions. Each sub-question must be answerable from a source on its own.
3. Choose the route:
   - `lookup` when one authoritative source (a specification, an official page, a standard) answers the
     whole question.
   - `survey` in every other case.
4. List what is out of scope, and why.

Return JSON: `{"route": "lookup" | "survey", "questions": [...], "out_of_scope": [...]}`.
Do not search yet. Do not answer the question.
