---
type: Metric
title: Trend score
description: Bounded momentum score derived from volume, velocity, and engagement.
status: active
tags: [trend, momentum, score]
generated: {by: "process:knowledge-bootstrap", at: "2026-08-17T00:00:00Z"}
sources:
  - resource: ../../../src/social_intelligence/scoring.py
---

# Trend score

Trend score ranks observed topics within the monitored collection scope. It is
not a provider-certified global trend ranking. Query coverage and source
freshness must accompany the score in consumer experiences.
