---
type: Attested Computation
title: Evidence rank computation
description: Deterministic decision-specific evidence ranking with canonical source links and platform diversity.
status: active
tags: [attested, evidence, ranking, deterministic]
generated: {by: "process:internal-pilot-workspace", at: "2026-08-20T00:00:00Z"}
verified:
  - {by: "process:unit-tests", at: "2026-08-20T00:00:00Z", status: passed}
runtime: "python>=3.10"
parameters:
  - {name: candidates, type: array}
  - {name: limit, type: integer, minimum: 1, maximum: 20, default: 5}
computation: "#computation"
executor:
  resource: ../../../src/social_intelligence/evidence_ranking.py
  receipt: [ranking_id, tenant_id, decision_id, items, score_version, causality_claim]
attester:
  resource: ../references/attesters/evidence_rank.py
sources:
  - resource: ../../../docs/INTERNAL_PILOT_WORKSPACE.md
---

# Evidence rank computation

Agents must supply normalized within-platform features and canonical source
URLs. The computation deduplicates URLs, applies explicit feature weights and a
small repeated-platform penalty, and returns ranked items with reasons.

## Computation

```python
from social_intelligence.evidence_ranking import EvidenceCandidate, rank_evidence

ranking = rank_evidence(
    [EvidenceCandidate(**candidate) for candidate in candidates],
    limit=limit,
)
```

The output makes no causal claim and performs no mutation. The executable
source is [`evidence_ranking.py`](../../../src/social_intelligence/evidence_ranking.py).
