---
name: sw-development
trigger:
  on: work-item-ready
policy:
  work.tracker: where work items and issues live
  vcs.remote: where branches are pushed
  vcs.default-branch: the branch changes merge into
  comms.channel: how agents reach each other and the owner
  report.sink: where run reports and iteration records go
entities:
  liaison:
    role: delegate
    escalates-to: owner
  pm:
    role: project-manager
    escalates-to: liaison
    may-spawn: [architect, lead]
  architect:
    role: architect
    escalates-to: pm
  lead:
    role: team-lead
    escalates-to: pm
    may-spawn: [worker, reviewer]
  worker:
    role: worker
    escalates-to: lead
    may-spawn: [worker]
  reviewer:
    role: reviewer
    escalates-to: lead
kpis:
  flow:
    owner: owner
    metrics: [rework, rounds]
  trouble:
    owner: owner
    metrics: [escalations]
loops:
  fix:
    stages: [build, review]
    exit:
      kind: verdict
    bound: 3
    on-exhausted: lead
    carries: verdict
stages:
  align:
    entity: pm
    skills: [ramble]
    consumes: [idea]
    produces: [brief]
    metrics: [escalations]
    uses: [comms.channel]
  spec:
    floor: true
    entity: lead
    skills: [triage]
    needs: [align]
    consumes: [brief]
    produces: [item]
    metrics: [rework]
    uses: [work.tracker]
  design:
    entity: architect
    skills: [architect]
    needs: [spec]
    consumes: [item]
    produces: [work-package]
    review: [adversarial]
    metrics: [rework]
  cut:
    entity: lead
    skills: [decompose]
    needs: [design]
    consumes: [work-package]
    produces: [units]
    metrics: [rework]
    uses: [work.tracker]
  build:
    entity: worker
    skills: [implement]
    needs: [cut]
    consumes: [units]
    produces: [change]
    metrics: [rounds]
    uses: [vcs.remote, work.tracker]
  review:
    floor: true
    entity: reviewer
    skills: [swe-workflows:by-angle]
    needs: [build]
    consumes: [change]
    produces: [verdict]
    review: [adversarial]
    metrics: [rounds]
  integrate:
    entity: pm
    skills: [git:workflow]
    needs: [review]
    consumes: [verdict]
    produces: [merged]
    metrics: [escalations]
    uses: [vcs.remote, vcs.default-branch]
  reflect:
    entity: pm
    skills: [models:reflect]
    needs: [integrate]
    consumes: [merged]
    produces: [lessons]
    metrics: [rework]
    uses: [report.sink]
---

The default software-delivery procedure. It says how work flows and who does each step; where the
tracker, the remote, the channel and the reports are is the policy's job (the keys under `policy`).

- `spec` and `review` are floor stages: nothing skips the spec check, and the reviewer is never the
  author. A delta cannot remove them or rewire what feeds them.
- `fix` is the build and review loop: up to three rounds, then the team lead decides.
- `integrate` ends at a merge that only the owner approves. `reflect` turns what the run taught into
  a change request on the process documents, with an iteration record.
