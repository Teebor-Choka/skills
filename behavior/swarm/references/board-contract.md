# Board contract

A binding is valid if it can do every verb below. `beads.md` maps them to `bd`.

## Item fields

| Field      | Meaning                                                               |
| ---------- | --------------------------------------------------------------------- |
| id         | Stable unique id.                                                     |
| title      | One line.                                                             |
| body       | Context a fresh agent needs to act with no other source.              |
| acceptance | Tests that can fail. Required before the item leaves the first state. |
| state      | Charter-defined label.                                                |
| area       | Optional label for affinity.                                          |
| holder     | Agent id of the claimant, or none.                                    |
| heartbeat  | Time of the holder's last refresh.                                    |
| revision   | Version identifier of the work the last verdict judged.               |
| links      | `duplicate-of`, `caused-by`, `blocks`, `discovered-from`.             |
| log        | Append-only notes: results, verdicts, reaps, escalation answers.      |

## Verbs

| Verb                  | Rule                                                                                                                      |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| list(filter)          | Filter by state, area, holder. Must show holder and heartbeat age.                                                        |
| show(id)              | Full item with log.                                                                                                       |
| file(item)            | Create. Reject an item with no acceptance tests.                                                                          |
| claim(id)             | Atomic. Fails if held. Sets holder and starts the lease.                                                                  |
| heartbeat(id)         | Refreshes the lease. Holder only.                                                                                         |
| release(id)           | Clears holder. The holder may call it at any time. Any other agent may call it only on a stale item, after re-reading it. |
| note(id, text)        | Append to log. Never edit or delete an earlier note.                                                                      |
| transition(id, state) | Holder only. Logs revision.                                                                                               |
| link(a, b, type)      | Create a link.                                                                                                            |
| close(id, reason)     | Terminal. Reason required.                                                                                                |

## Invariants

- One holder per item. One item per holder.
- A log entry is never edited. Corrections are new entries.
- A verdict entry names the revision it judged.
- No state change happens without a log entry that says why.
