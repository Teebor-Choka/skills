# AGENTS.md

Public marketplace of portable [Agent Skills](https://code.claude.com/docs/en/skills). Every
skill is a self-contained `SKILL.md` directory that runs unchanged on Claude Code, Codex, and
OpenCode; the [skill-creator](./model/tools/skill-creator/SKILL.md) skill documents that
cross-agent model. Consumers install the whole set or a single skill via `claude plugin
marketplace add` (see [README](./README.md)).

## The manifest is the dispatch table

`.claude-plugin/marketplace.json` is the single source of truth for what this repo ships. To
learn which skills exist, where each one lives, and its version, read that file — its `plugins`
array maps every skill `name` to its `skills` path and `metadata.version`. Do not rely on a
hardcoded list anywhere else: the READMEs are hand-written mirrors for humans and can lag the
manifest, so when they disagree, the manifest wins. A host discovers each skill by the `name`
in its `SKILL.md`; the directory grouping below is for source organization only and is invisible
to the host.

## Layout

Skills are grouped into thematic category directories, each with its own README:

- `tools/` — general-purpose skills for ideas and knowledge.
- `model/tools/` — skills about working with the model and prose itself.
- `engineering/` — system design; `engineering/swe/` code-level skills; `engineering/ci/` CI and
  pipeline skills.
- `environment/` — skills for a development environment (Nix/direnv, etc.).

## Changing a skill

- **Portability.** Keep `SKILL.md` agent-neutral: only `name` and `description` are required
  frontmatter (`name` matches the directory, `^[a-z0-9][a-z0-9-]*$`), and the `description`
  carries the whole triggering signal — say what it does and when to use it, plus when not to.
  Anything agent-specific belongs in an adapter, not the core. Validate with
  `python3 model/tools/skill-creator/scripts/validate_skill.py <skill-dir>`.
- **Adding a skill.** Create the directory, then register it in `marketplace.json` (a `plugins`
  entry: `name`, `description`, `source: "./"`, `skills: ["./path"]`, `metadata.version:
  "1.0.0"`), bump the top-level `metadata.version` (minor), and add a row to the category README
  and the top-level README.
- **Editing a skill.** Bump that plugin's `metadata.version` in `marketplace.json` — patch for
  fixes, minor for additive guidance, major for a breaking change to how the skill is used.

## Conventions

- Conventional commits scoped to the skill or area: `feat(nix):`, `fix(rust-engineer):`,
  `docs(readme):`, `chore(marketplace):`.
- Prose follows a plain, de-slopped voice — see the [unslop](./model/tools/unslop/SKILL.md) skill.
- This is a public repo: land changes through a pull request, never a direct push to `main`.
