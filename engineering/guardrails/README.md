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
