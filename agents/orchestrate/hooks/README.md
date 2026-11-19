# orchestrate hooks

| Hook                    | Tool             | Effect                                                                                                 |
| ----------------------- | ---------------- | ------------------------------------------------------------------------------------------------------ |
| `schedule-wakeup-guard` | `ScheduleWakeup` | Denies a wake that polls `gh pr                                                                        | issue | run`, sleeps or waits on a subagent. A repeated non-polling prompt passes: a dynamic loop re-issues one prompt each tick. No state. |
| `send-message-guard`    | `SendMessage`    | Denies a long free-text message that carries no `#N` or URL.                                           |
| `review-dedup-guard`    | `Agent`          | Per PR and session: the first two review spawns pass, the third asks, the fourth and later are denied. |

`review-dedup-guard` counts a spawn only when it asks for a review or audit as the task (not "address review comments"),
names a PR, and comes from the top-level session (a payload with an `agent_id` is a subagent and is not counted). A
fan-out role word (`verify`, `verifier`, `finder`) counts once per PR per role, so one review fanned out to many agents
is one review. State is an append-only file, one line per counted spawn.
