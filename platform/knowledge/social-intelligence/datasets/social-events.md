---
type: Dataset
title: Social events
description: Immutable, replayable connector events in the Bronze data plane.
status: active
tags: [bronze, events, lineage]
generated: {by: "process:knowledge-bootstrap", at: "2026-08-17T00:00:00Z"}
sources:
  - resource: ../../../schemas/social-event-envelope-v1.json
---

# Social events

The dataset stores one connector landing envelope per observed source event.
`idempotency_key` identifies the logical event across delivery retries, while
`event_id` identifies a delivery record. Raw payloads remain replayable.
