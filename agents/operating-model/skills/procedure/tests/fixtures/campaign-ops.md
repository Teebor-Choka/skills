---
name: campaign-ops
trigger:
  on: quarter-start
stages:
  brief:
    consumes: [goal]
    produces: [audience-brief]
  create:
    needs: [brief]
    consumes: [audience-brief]
    produces: [creative]
    review: [brand]
  launch:
    needs: [create]
    consumes: [creative]
    produces: [live-campaign]
    on-fail:
      to: create
      bound: 2 rounds
---

Custom kinds show the format is not software-specific.
