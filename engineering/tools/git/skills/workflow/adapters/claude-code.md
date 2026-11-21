# Claude Code adapter — ambient triggering in a git repo

The portable `description` triggers this skill on git/PR _operations_ (commit, branch, worktree,
PR, review threads, force-push), which is the primary mechanism and works on every agent. This
adapter adds the "whenever inside a git repository" firing on Claude Code specifically — there is
no portable, cross-agent way to auto-load a skill from the mere presence of `.git`, so it lives
here, not in the core.

Claude Code can't force a skill to load from a hook, but a `PreToolUse` hook on Bash can inject a
reminder when a `git`/`gh` command runs, which reliably surfaces the skill at the moment it
matters. Wire it in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/git-workflow-nudge.sh"
          }
        ]
      }
    ]
  }
}
```

`~/.claude/hooks/git-workflow-nudge.sh` — emit a one-line nudge only for git/gh commands, stay
silent otherwise:

```bash
#!/usr/bin/env bash
cmd=$(jq -r '.tool_input.command // empty')
case "$cmd" in
  git\ *|*/git\ *|gh\ *|*/gh\ *)
    jq -n '{hookSpecificOutput: {hookEventName: "PreToolUse",
      additionalContext: "Working with git/gh — apply the git:workflow skill: worktree off latest origin, never push to main, never git add -A, never merge/tag without approval."}}'
    ;;
  *) exit 0 ;;
esac
```

Keep the nudge short — it is a pointer to the skill and its non-negotiables, not a second copy of
them. On Codex and OpenCode, rely on the description's operation triggers; neither needs this file.

## Babysitting with `Monitor`

Run `babysit` under the `Monitor` tool: each stdout line arrives as a notification, so the
session reacts to PR events without polling.

```
Monitor({
  command: "~/.claude/skills/workflow/scripts/babysit -C <worktree> --heartbeat 900",
  description: "PR #<n> babysitter",
  timeout_ms: 1800000,
})
```

A monitor dies at `timeout_ms` (30 minutes at most). On that expiry notice, arm it again with the
same command until a `merged`, `closed` or `error` line arrives; the script's state file stops the
re-armed run from repeating old events. Send a `PushNotification` for `merge` `CLEAN` with an
approval, and for `error`.

To make babysitting start without anyone asking, extend the nudge hook above so a `gh pr create`
command adds "PR opened: start babysit under Monitor (git:workflow skill)" to its context.
