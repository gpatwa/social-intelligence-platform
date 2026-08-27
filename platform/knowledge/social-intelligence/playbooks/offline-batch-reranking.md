---
type: Playbook
title: Offline batch reranking
description: Evaluate a bounded candidate reranker with citation and candidate-set gates before using a model in an internal pilot.
status: active
tags: [recommendation, reranking, evaluation, grounding, staging]
generated: {by: "process:batch-reranker-v1", at: "2026-08-27T00:00:00Z"}
sources:
  - resource: ../../../docs/BATCH_RERANKER.md
---

# Offline batch reranking

1. Compile a `recommendation-context-v1` from governed evidence and eligible candidates.
2. Run the deterministic baseline to establish repeatable fixture expectations.
3. Introduce one provider adapter at a time behind the structured adapter protocol.
4. Reject any output that omits a candidate, cites unknown evidence, or exceeds the supplied candidate set.
5. Evaluate grounding, candidate-boundary compliance, expected selection, cost, and latency offline.
6. Compare a candidate model with the baseline and retain a reproducible result artifact.
7. Keep outputs `PROPOSED`; route only a human-approved recommendation to experiment planning.

No reranker, model, or agent is allowed to activate a campaign, publish content,
or claim observational evidence proves causality.
