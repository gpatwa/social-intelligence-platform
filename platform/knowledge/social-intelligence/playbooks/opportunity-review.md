---
type: Playbook
title: Opportunity review
description: Evidence-first sequence for turning an opportunity into a measurable proposal.
status: active
tags: [workflow, decisioning, human-in-the-loop]
generated: {by: "process:knowledge-bootstrap", at: "2026-08-17T00:00:00Z"}
sources:
  - resource: ../../../docs/DECISION_ENGINE.md
---

# Opportunity review

1. Confirm source freshness and monitored-query coverage.
2. Inspect the evidence IDs behind the signal.
3. Verify explicit product and commercial fit mappings.
4. Execute the [opportunity score computation](../computations/opportunity-score.md).
5. Draft a recommendation with claim-level evidence and risks.
6. Require critic validation before presenting it for human approval.
7. Create an experiment only after approval; close the loop with measured lift
   and contribution margin.
