---
type: Metric
title: Engagement rate
description: Public interactions divided by public exposure for an observed post.
status: active
tags: [engagement, normalized]
generated: {by: "process:knowledge-bootstrap", at: "2026-08-17T00:00:00Z"}
sources:
  - resource: ../../../src/social_intelligence/scoring.py
---

# Engagement rate

Engagement rate normalizes public interactions by exposure. It is a comparative
signal, not a causal business outcome, and must preserve missing provider values
instead of coercing them to zero.
