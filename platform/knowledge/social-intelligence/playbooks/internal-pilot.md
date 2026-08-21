---
type: Playbook
title: Seven-day internal pilot
description: A staging-only sequence for turning one workflow and ranked evidence into a measurable go, iterate, or stop decision.
status: active
tags: [pilot, staging, evidence, scorecard, human-in-the-loop]
generated: {by: "process:internal-pilot-workspace", at: "2026-08-20T00:00:00Z"}
sources:
  - resource: ../../../docs/INTERNAL_PILOT_WORKSPACE.md
---

# Seven-day internal pilot

1. Confirm one workflow owner, one outcome, the baseline, and exclusions.
2. Type the inputs, outputs, identities, action policy, and evidence contract.
3. Run one deterministic golden path using synthetic or non-sensitive fixtures.
4. Test the model boundary for grounding, quality, and refusal behavior.
5. Verify retries, deduplication, approvals, the audit log, and the kill switch.
6. Run in shadow mode without external side effects and collect scorecard data.
7. Decide **GO**, **ITERATE**, or **STOP** from the agreed thresholds.

During this internal stage the system may draft and recommend. A human must
approve every external action; production identity and compliance controls are
deferred until the pilot demonstrates value.
