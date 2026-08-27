---
type: Playbook
title: Recommendation context preparation
description: Build a bounded, reviewable decision packet before any model-assisted recommendation ranking.
status: active
tags: [recommendation, evidence, llm, staging, human-in-the-loop]
generated: {by: "process:recommendation-context-v1", at: "2026-08-27T00:00:00Z"}
sources:
  - resource: ../../../docs/RECOMMENDATION_CONTEXT.md
---

# Recommendation context preparation

1. Select one tenant-scoped decision, market, objective, and primary metric.
2. Use `evidence-rank-v1` to create a canonical, source-linked evidence set.
3. Supply a finite candidate set and apply eligibility, channel, and exclusion rules.
4. Attach only governed outcome aggregates; never raw social content or PII.
5. Compile `recommendation-context-v1` deterministically and review exclusions.
6. Let a future batch reranker rank only the supplied candidates and cite the supplied evidence.
7. Require human approval and measure the approved action with an experiment.

The compiler itself makes no recommendation, calls no model, and performs no
external action. It exists to make later LLM use grounded, testable, and
replaceable.
