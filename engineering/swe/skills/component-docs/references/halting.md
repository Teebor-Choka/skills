# Halting

`scripts/resolve.py` never prompts. It stops with one JSON object on stdout and exit 3:

```json
{
  "status": "needs-input",
  "missing": [{ "field": "...", "reason": "...", "supply": ["..."] }]
}
```

| `field`        | Cause                                                                  | What the caller supplies                        |
| -------------- | ---------------------------------------------------------------------- | ----------------------------------------------- |
| `components`   | the workspace format cannot be read (pnpm, Bazel, Gradle, and similar) | `--components 'glob'` or the policy include key |
| `project-docs` | the docs tooling was not found                                         | `--project-docs <dir>` or `PROJECT_DOCS_DIR`    |
| `project`      | `docs/overview.md` has no `project:` key to copy into the pages        | add the key (write the overview first)          |

On exit 3:

1. Return the JSON unchanged to your caller. Do not paraphrase it.
2. Write no page, and do not scaffold by hand.
3. Do not invent a component list from directory names.

A caller with a person present may pass `--interactive`; the resolver then asks on stderr. It is
never a required step. Exit 2 means an unreadable manifest or policy file: report the message.
