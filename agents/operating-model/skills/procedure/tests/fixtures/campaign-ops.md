---
name: campaign-ops
trigger:
  on: quarter-start
kpis:
  reach:
    owner: owner
    metrics: [briefs-per-week, creative-rework, launch-lead-time]
stages:
  brief:
    consumes: [goal]
    produces: [audience-brief]
    metrics: [briefs-per-week]
  create:
    needs: [brief]
    consumes: [audience-brief]
    produces: [creative]
    review: [brand]
    metrics: [creative-rework]
  launch:
    needs: [create]
    consumes: [creative]
    produces: [live-campaign]
    metrics: [launch-lead-time]
    on-fail:
      to: create
      bound: 2 rounds
---

Custom kinds show the format is not software-specific.
