---
type: Attested Computation
title: Opportunity score computation
description: Deterministic priority and confidence scoring for a governed opportunity.
status: active
tags: [attested, decisioning, deterministic]
generated: {by: "process:knowledge-bootstrap", at: "2026-08-17T00:00:00Z"}
verified:
  - {by: "process:unit-tests", at: "2026-08-17T00:00:00Z", status: passed}
runtime: "python>=3.10"
parameters:
  - {name: signal_score, type: number, minimum: 0, maximum: 100}
  - {name: evidence_count, type: integer, minimum: 0}
  - {name: product_fit, type: number, minimum: 0, maximum: 1}
  - {name: commercial_fit, type: number, minimum: 0, maximum: 1}
  - {name: risk_penalty, type: number, minimum: 0, maximum: 100, default: 0}
computation: "#computation"
executor:
  resource: ../../../src/social_intelligence/decisioning.py
  receipt: [inputs, priority_score, confidence_score, implementation_sha256]
attester:
  resource: ../references/attesters/opportunity_score.py
sources:
  - resource: ../../../docs/DECISION_ENGINE.md
---

# Opportunity score computation

Agents must not estimate this result. They provide bounded inputs and invoke the
canonical deterministic implementation. The returned receipt is independently
checked by the attester.

## Computation

```python
from social_intelligence.decisioning import opportunity_score

priority_score, confidence_score = opportunity_score(
    signal_score,
    evidence_count,
    product_fit,
    commercial_fit,
    risk_penalty,
)
```

The executable source is [`decisioning.py`](../../../src/social_intelligence/decisioning.py).
