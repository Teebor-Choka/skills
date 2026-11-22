## Silencing direnv shell-enter noise

Every command run in a direnv-managed directory re-enters the shell and prints a
`direnv: loading …` / `direnv: export +AR …` banner, which buries real command output and
eats context. Silence it by exporting an empty log format _before_ the direnv hook runs — put
it in `~/.zshenv` (or wherever the parent shell sources its profile):

```sh
export DIRENV_LOG_FORMAT=""
```

Verify by running any command and confirming the output starts with the command's own stdout,
not `direnv: loading …`. A repo-specific banner (a project `shellHook` that `echo`s a header)
is separate — it comes from the nix shell, not direnv, and is gated in the repo's `flake.nix`.
