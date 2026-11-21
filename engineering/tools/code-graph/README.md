# code-graph

Hooks that keep the codebase-memory-mcp code graph fresh and in use.

| Hook                                                   | Event                     | Effect                                                                    |
| ------------------------------------------------------ | ------------------------- | ------------------------------------------------------------------------- |
| `code-graph-index`                                     | session start             | Indexes the repo in the background and tells the agent to query the graph |
| `code-graph-reindex`                                   | stop                      | Re-indexes a dirty main checkout in the background                        |
| `code-graph-bash-reminder`, `code-graph-find-reminder` | before Bash, Grep/Glob    | Nudges toward `search_graph` before a grep or find sweep                  |
| `code-graph-subagent-reminder`                         | subagent start            | Gives subagents the graph directive                                       |
| `code-graph-index-rewrite`                             | before `index_repository` | Points a linked worktree at its main checkout                             |

`code-graph-index` and `code-graph-reindex` share `hooks/index-bg`: one lock per repo, a stale lock (dead pid or older than 6 hours) is taken over.

## code-graph-index-rewrite is unverified

The hook returns `updatedInput` with no permission decision, so the normal permission flow still decides. Whether the
runtime applies `updatedInput` in that case has not been verified on a live harness. The injected context therefore says
the path was rewritten "if your harness applies the update". Claude Code only: the matcher is the Claude name of the MCP
tool. Open item: confirm in a live `index_repository` call that `repo_path` was changed.
