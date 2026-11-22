## The deploy path fails but your probe passes

A probe that runs the same hops (sudo, launchctl, ssh) but not the real generated script proves
nothing. Do this first, before you test theories:

1. Build the target. Read line 1 and the sudo or launchctl hops of the generated activation
   script (for example `result/activate`). A shebang such as `#!/usr/bin/env -i <bash>` scrubs the
   environment.
2. List which env vars survive that environment (`SSH_AUTH_SOCK` does not under `env -i`). Hand
   such state over in a file, not in the environment.
3. Reproduce with the real script, not a lookalike.

Report a deploy-affecting change as `built: yes / activated: no (needs sudo)`, with the exact
rebuild command. An activation you did not run is never "works". A dirty-tree warning on the
build output means the build did not include your last edit state: say so.

Run ssh probes with `-o ControlPath=none -F <temp config>`. End every probe session with
`ssh -O exit` and one line that lists what you left running. A leftover ControlMaster gives the
user's later check a false result.
