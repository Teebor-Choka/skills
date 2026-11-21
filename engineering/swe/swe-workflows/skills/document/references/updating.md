# Updating a page

A change obliges a page update when it does one of these inside a component's `path`:

| Change                                                                  | Page section |
| ----------------------------------------------------------------------- | ------------ |
| Adds, removes or renames an exported item                               | Public API   |
| Adds or removes an internal dependency in the manifest                  | `depends-on` |
| Changes who calls whom, or the order of the top-level flow              | Flow         |
| Moves, adds or removes an internal module                               | Structure    |
| Reverses a decision, or makes its reason untrue                         | Decisions    |
| Adds or removes a file, socket, process or environment variable it uses | Interactions |

Formatting, renames of private items, test changes and internal refactors that leave the
table above untouched need no update.

How to update:

1. Edit the section the change touches. Do not rewrite the page.
2. Re-check the Public API table against the code. Delete rows for removed items.
3. Delete any Decisions bullet that is no longer true.
4. Set `updated` to today's date, and run the validator.

How to skip: add one trailer line to a commit in the change, naming the component and the reason.

```
Docs-Unchanged: sandy-fsutil: only reordered private helpers
```

Give a reason that a reviewer can check. A bare "no change" is not one.
