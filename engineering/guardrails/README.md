# guardrails

Hooks that keep secrets and bulk file content out of an agent transcript.

| Hook                | Event                | Effect                                                                                 |
| ------------------- | -------------------- | -------------------------------------------------------------------------------------- |
| `secret-read-guard` | before Bash and Read | Asks before a call prints a secret: key files, `.env*`, env dumps, keychain passwords  |
| `read-size-nudge`   | before Read          | Nudges on a whole-file read over 40 KB; denies it for a source file in an indexed repo |

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
