"""Builders shared by the component tests: manifests, policy files and conformant pages."""

from __future__ import annotations

import json
from pathlib import Path

PAGE = """---
title: {name}
kind: component
project: {project}
updated: 2026-11-19
component: {name}
path: {path}
depends-on: [{depends}]
---

# {name}

## Purpose

Does one thing.

## Structure

| Module | Role |
| ------ | ---- |
| `lib`  | all  |

## Public API

| Item | What it does |
| ---- | ------------ |
{api}

## Interactions

Calls nothing.

## Flow

```mermaid
flowchart LR
  A --> B
```

## Decisions

- **Keep it small.** Less to maintain.
"""


def page_text(name: str, path: str, depends=(), project: str = "widgetd",
              api: tuple[str, ...] = ("`Thing` | does it",)) -> str:
    rows = "\n".join(f"| {r.split(' | ')[0]} | {r.split(' | ')[1]} |" for r in api)
    return PAGE.format(name=name, path=path, project=project, depends=", ".join(depends), api=rows)


def write_page(repo: Path, name: str, path: str, depends=(), **kw) -> Path:
    target = repo / "docs" / "components" / f"{name}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page_text(name, path, depends, **kw))
    return target


def write(repo: Path, rel: str, text: str) -> Path:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    return target


def cargo_member(repo: Path, name: str, dir: str | None = None, deps=(), dev=(), build=(),
                 source: str = "pub fn Thing() {}\n") -> str:
    """A crate under crates/<dir>; deps/dev/build name sibling crates. Returns its repo-relative dir."""
    rel = f"crates/{dir or name}"
    lines = [f'[package]\nname = "{name}"\nversion = "0.1.0"\n']
    for table, names in (("dependencies", deps), ("dev-dependencies", dev), ("build-dependencies", build)):
        if names:
            lines.append(f"[{table}]\n" + "".join(f'{n} = {{ path = "../{n}" }}\n' for n in names))
    write(repo, f"{rel}/Cargo.toml", "\n".join(lines))
    write(repo, f"{rel}/src/lib.rs", source)
    return rel


def cargo_workspace(repo: Path, members: str = '"crates/*"', exclude: str = "") -> None:
    extra = f"exclude = [{exclude}]\n" if exclude else ""
    write(repo, "Cargo.toml", f"[workspace]\nmembers = [{members}]\n{extra}")


def policy(repo: Path, body: str) -> None:
    write(repo, ".agents/policy.md", f"---\n{body}\n---\n\n# Policy\n")


def package_json(repo: Path, rel: str, name: str, **fields) -> None:
    write(repo, f"{rel}/package.json" if rel else "package.json", json.dumps({"name": name, **fields}))
