# Iterating — running a second round and beyond

Read this before re-forging. It covers what changes once the first round is done: what to
re-test, how to read triangulation, when to fork, and the periodic step-back.

## Iterate

Loop steps 4–6 until the premise stabilizes (a full round changes nothing) or the user stops.
The idea file body is the living report. Each round:

- **Re-test only what changed.** Carry forward branches that already came back VIABLE; re-test
  only the materially-changed or newly-introduced ones.
- **Reconfirm the target on redirect.** If the smith redirected to a variant, re-confirm the fit
  target before re-testing — a redirect can change who the idea is _for_ (and how success is even
  measured), so a fit score against the old target measures against the wrong bar.
- **Watch for triangulation.** A parked variant that independently reappears from a different
  attack angle is the strongest signal there is — elevate it over freshly-generated options (the
  cross-round convergence principle lives in `forge-tactics.md`).
- **Stabilizing vs drifting — and fork on drift.** Distinguish **converging** (reshapes get
  smaller each round → keep looping) from **drifting** (each round crosses a different
  target / customer / domain and spawns a fresh premise). When a reshape crosses
  target/customer/domain, **recommend forking** at the checkpoint (step 6) — spin out a new
  stage-prefixed file carrying the `**Lineage:**` pointer from `references/forge-report.md`,
  rather than mutating the parent into something it no longer is. The fork is the smith's call,
  like every transition.
- **Step back periodically** (every few rounds, or whenever the premise keeps drifting):
  synthesize across the `## Dead ends` and `## Viable variants` ledgers — _what do all the
  survivors share? what do all the prunes share?_ The through-line is often the real idea; this is how the
  strongest thesis in a long run tends to surface.
