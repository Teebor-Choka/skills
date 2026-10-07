# GLOSSARY.md format

Write a term the moment it settles in the interview. A glossary only — devoid of implementation
detail; it defines what a term _is_, never what it does.

## Structure

```md
# {Context name}

{One or two sentences: what this context is and why it exists.}

## Language

**Order**:
A customer's request to buy, once submitted.
_Avoid_: Purchase, transaction

**Invoice**:
A request for payment sent to a customer after delivery.
_Avoid_: Bill, payment request
```

## Rules

- **Be opinionated.** When several words mean the same thing, pick the best and list the rest under
  `_Avoid_`.
- **Keep definitions tight** — one or two sentences, defining what it IS.
- **Only project-specific terms.** General programming concepts (timeout, retry, error type) don't
  belong, however much the project uses them. Ask: is this unique to this context, or general? Only
  the former.
- **Group under subheadings** when natural clusters emerge; a flat list is fine otherwise.
- **Create lazily** — the file appears on the first resolved term, not before.

## Multiple contexts

If a `GLOSSARY-MAP.md` exists at the repo root, the repo has several contexts; read it to find where
each lives and infer which the current topic belongs to (ask if unclear). Otherwise a single root
`GLOSSARY.md` is the whole model.

<!-- Adapted closely from mattpocock/skills domain-modeling GLOSSARY-FORMAT.md — not copied verbatim. -->
