# AGENTS.md

Public marketplace of portable [Agent Skills](https://code.claude.com/docs/en/skills). Each skill
is a self-contained `SKILL.md` directory that runs unchanged on Claude Code, Codex, and OpenCode
(see [extension-author](./models/models/skills/extension-author/SKILL.md)).

## Layout

`<domain>/<plugin>/skills/<skill>/SKILL.md`, with `<domain>/<plugin>/.claude-plugin/plugin.json`.
`.claude-plugin/marketplace.json` lists every plugin (`source: ./<domain>/<plugin>`) and is the
source of truth. The host sees `plugin:skill`. Domains: `agents`, `education`, `engineering`,
`knowledge`, `models`, `research`, `technology`, `writing`.

A skill never names a skill from another repo. Cross-repo binding goes through `.agents/policy`.

## Changing a skill

- `SKILL.md` frontmatter needs `name` (matches the directory, `^[a-z0-9][a-z0-9-]*$`) and
  `description` (what it does, when to use it, when not). Agent-specific parts go in an adapter.
  Validate: `python3 models/models/skills/extension-author/scripts/validate_skill.py <skill-dir>`.
- Add a plugin: create the dir with `plugin.json`, add a `marketplace.json` entry, bump the top-level
  `metadata.version` (minor), and add a README row.
- Edit a skill: bump the plugin's version in `plugin.json` and `marketplace.json` (patch fix, minor
  addition, major breaking).
- Check: `python3 scripts/check-marketplace.py .` and `python3 scripts/validate-skills.py .`.

## Conventions

- Conventional commits scoped to the area: `feat(nix):`, `fix(swe):`, `docs(readme):`.
- Prose follows the [unslop](./writing/writing/skills/unslop/SKILL.md) skill.
- `direnv allow` once per worktree installs the pre-commit hooks (treefmt, skills validator,
  shellcheck, actionlint, zizmor). Run `pre-commit run --all-files` to check everything.
- Land changes through a pull request, never a direct push to `main`.
