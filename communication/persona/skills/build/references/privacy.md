# Privacy and consent

Samples of how someone writes are personal data. So are the profile, which describes their habits
and temperament, and every report, which holds their messages.

## Where the data lives

- Default: `~/.config/agents/state/persona/<persona>/`. Override with `PERSONA_STATE_HOME` (the
  persona dir goes under it; the old `MIMIC_STATE_HOME` is a fallback for one release) or `--state-dir`.
- Directories are created 0700 and files 0600.
- Never in a repository. Before any write, the scripts look for a git work tree above the target.
  Inside one, `git check-ignore` must confirm git ignores the path, else they exit 3 and write
  nothing. `~/.config/agents` is a git work tree whose allowlist `.gitignore` ignores `/state/`,
  so the default passes. `--allow-git-worktree` overrides; use it only for a path you know is
  never pushed.
- The `claude` runner passes `--no-session-persistence`, so prompts with samples are not written
  to session history.
- Nothing is sent anywhere except to the model runner you choose.

## Consent

- Your own voice: fine.
- Another person: only with their consent, or for study of their public material. Do not build a
  profile of a private person from messages they sent you without asking them.
- Never present generated text as the person's own words to a reader who does not know it was
  generated. Drafting a message the person reviews and sends themselves is fine.
- Never use a profile to get past a check that relies on someone's writing (support, banking,
  identity), or to deceive their contacts.

## Sharing results

Report aggregates: identification rate, rubric means, band and channel rows, counts, rounds. Do
not paste samples, worked examples or generated messages into issues, PRs or chats. Describe a
trait in your own words instead of quoting the person.

## Deleting

`rm -r <state dir>` removes everything. There is no other copy.
