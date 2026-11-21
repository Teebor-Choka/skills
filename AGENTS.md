# AGENTS.md

Public marketplace of portable [Agent Skills](https://code.claude.com/docs/en/skills). Each skill
is a self-contained `SKILL.md` directory that runs unchanged on Claude Code, Codex, and OpenCode
(see [extension-author](./ai/model/skills/extension-author/SKILL.md)).

## Layout

`<domain>/[<group>/]<plugin>/skills/<skill>/SKILL.md`, with `<plugin root>/.claude-plugin/plugin.json`.
A plugin root has no wrapper directory (`ai/model`, `ai/harness`); a group directory holds several
plugins (`engineering/swe`, `engineering/tools`, `engineering/infra`).
`.claude-plugin/marketplace.json` lists every plugin (`source: ./<plugin root>`) and is the
source of truth. The host sees `plugin:skill`. Domains: `ai`, `communication`, `education`,
`engineering`, `knowledge`, `research`.

A skill never names a skill from another repo. Cross-repo binding goes through `.agents/policy`.

## Changing a skill

- `SKILL.md` frontmatter needs `name` (matches the directory, `^[a-z0-9][a-z0-9-]*$`) and
  `description` (what it does, when to use it, when not). Agent-specific parts go in an adapter.
  Validate: `python3 ai/model/skills/extension-author/scripts/validate_skill.py <skill-dir>`.
- Add a plugin: create the dir with `plugin.json`, add a `marketplace.json` entry, bump the top-level
  `metadata.version` (minor), and add a README row.
- Remove a plugin: `git rm -r` its dir, delete its `marketplace.json` entry, add `"<name>": null`
  under `renames` so installs clean up, bump the top-level `metadata.version` (major), delete its
  README rows, and drop the `flake.nix` wiring and tests only it needed (grep first). History stays:
  no force-push.
- Edit a skill: bump the plugin's version in `plugin.json` and `marketplace.json` (patch fix, minor
  addition, major breaking).
- Check: `python3 scripts/check-marketplace.py .` and `python3 scripts/validate-skills.py .`.
- Hooks: edit `hooks/manifest.json`, then `scripts/render-hooks.sh <plugin-dir>` writes `hooks/hooks.json`
  (the `hooks-manifest` check compares the two).

## Conventions

- Conventional commits scoped to the area: `feat(nix):`, `fix(swe):`, `docs(readme):`.
- Prose follows the [unslop](./communication/writing/skills/unslop/SKILL.md) skill.
- `direnv allow` once per worktree installs the pre-commit hooks (treefmt, skills validator,
  shellcheck, actionlint, zizmor). Run `pre-commit run --all-files` to check everything.
- Land changes through a pull request, never a direct push to `main`.
