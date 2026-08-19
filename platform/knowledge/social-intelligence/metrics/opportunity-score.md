---
type: Metric
title: Opportunity score
description: Bounded commercial priority combining signal, evidence, product fit, commercial fit, and risk.
status: active
tags: [decisioning, priority, commercial]
generated: {by: "process:knowledge-bootstrap", at: "2026-08-17T00:00:00Z"}
sources:
  - resource: ../computations/opportunity-score.md
---

# Opportunity score

Opportunity score is a 0–100 priority, not a probability. Signal momentum has
the largest weight; explicit risk is subtracted and remains visible. Confidence
is reported separately. See the [attested computation](../computations/opportunity-score.md).
