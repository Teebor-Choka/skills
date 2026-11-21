# harness

How agent sessions run: the shared work board (`assign`, `pull`), the build `tracker`, the `.agents/policy`
settings (`policy`), and hooks that every session of a user with the plugin enabled runs.

## Hooks

| Hook                    | Event                                 | Effect                                                                                                                                                                      |
| ----------------------- | ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `schedule-wakeup-guard` | before `ScheduleWakeup`, `CronCreate` | Denies a wake that polls `gh pr\|issue\|run`, sleeps or waits on a subagent. A repeated non-polling prompt passes: a dynamic loop re-issues one prompt each tick. No state. |
| `send-message-guard`    | before `SendMessage`                  | Denies a long free-text message that carries no `#N` or URL.                                                                                                                |
| `review-dedup-guard`    | before `Agent`                        | Per PR and session: the first two review spawns pass, the third asks, the fourth and later are denied.                                                                      |
| `secret-read-guard`     | before Bash, Read, Grep               | Asks before a call prints a secret: key files, `.env*`, env dumps, keychain passwords                                                                                       |
| `read-size-nudge`       | before Read                           | Nudges on a whole-file read over 40 KB; denies it for a source file in an indexed repo                                                                                      |

## Review spawns

`review-dedup-guard` counts a spawn only when it asks for a review or audit as the task (not "address review comments"),
names a PR, and comes from the top-level session (a payload with an `agent_id` is a subagent and is not counted). A
fan-out role word (`verify`, `verifier`, `finder`) counts once per PR per role, so one review fanned out to many agents
is one review. State is an append-only file, one line per counted spawn.

## Protect more paths

`secret-read-guard` knows the common secret files (`.env*`, `*.pem`, `~/.ssh/id_*`, `~/.kube/config`, and others).
List site-specific ones in `AGENT_GUARDRAILS_SECRET_PATHS`: `os.pathsep`-separated globs, where `*` also matches `/`.
A path is matched after `~user` expansion, resolution against the working directory (and an earlier `cd` in the
same command), and `..` and symlink resolution. Case is folded on macOS and Windows.
A file named exactly `ssh_config` is exempt from these globs, because it holds hostnames and no credentials. The
exemption checks the resolved name too, so a symlink called `ssh_config` that points at a secret stays guarded.

```sh
export AGENT_GUARDRAILS_SECRET_PATHS="$HOME/.config/example-org/*:/srv/secrets/*"
```

An earlier version of this hook also protected credential files under a per-organisation config directory. That
rule is no longer built in. A machine that relied on it must list those directories in this variable, for
example `~/.config/<your-org-dir>/*` (leave out any file that holds no credential).

## What `ask` means

`secret-read-guard` never denies: it answers `ask`, so a person can approve a deliberate read. A harness that
cannot ask a person treats `ask` as a deny (the runtime maps it). The manifest marks the hook `warn` for that
reason.

## Grep, compound commands and heredocs

`secret-read-guard` also asks before a `Grep` in `content` mode over a secret path, or with a `glob` that names secret
files (`.env*`, `*.pem`, `credentials*`). Listing modes only name files and pass. `Glob` lists names only and is not
guarded.

The built-in rules resolve a path against the working directory and any earlier `cd`, so `cd ~/.ssh && cat id_rsa`
asks. Compound keywords and braces (`if`, `do`, `{`) and wrappers with arguments (`nice -n 5`, `env -u X`,
`timeout 60`, `sudo -u user`) are looked through to the real command. A `<<` inside quotes is not a heredoc, and a
heredoc body fed to a shell (`bash <<EOF`, `cat <<EOF | sh`) is scanned as commands.

The `Grep` registration uses a raw matcher, so it works on Claude Code only; other harnesses need their own matcher for
their search tool.
