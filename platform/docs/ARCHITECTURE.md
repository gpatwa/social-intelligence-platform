# Architecture Decision: Logical Planes on an Event-Driven Lakehouse

## Decision

The product uses an event-driven lakehouse with three logical planes:

- **Control plane** describes tenants, sources, collection rules, compatible
  event contracts, ownership, and operational policy.
- **Data plane** receives immutable source events, validates contracts,
  quarantines invalid deliveries, deduplicates logical events, and creates
  tenant-scoped Bronze, Silver, and Gold data products.
- **Experience plane** exposes stable, tenant-scoped read models for dashboards,
  alerts, human review, search, and future APIs.

These are logical boundaries in the MVP, not three separately operated service
stacks. Physical separation becomes appropriate when security boundaries,
independent scaling, regional residency, or team ownership require it.

## Runtime topology

```text
Approved social API / licensed provider
    -> webhook, stream, or polling adapter
    -> queue and immutable cloud-object landing
    -> bronze_social_events
       -> rejected: bronze_dead_letter_events
       -> accepted post observations: bronze_social_posts -> silver_social_posts
       -> accepted trend observations: bronze_social_trends -> gold_trending_topics
    -> tenant-scoped Gold metrics
    -> gold_signal_feed / gold_source_health
    -> dashboard, alerts, review queue, and APIs
```

The demo generator acts as a source adapter and emits the same event envelope a
production connector must emit.

## Event contract

Every delivery has:

```text
event_id, schema_version, tenant_id, source_id, platform, event_type,
source_object_id, occurred_at, collected_at, idempotency_key,
correlation_id, payload, attributes
```

`payload` is immutable source-shaped JSON. Mapping into canonical posts occurs
after raw ingestion, so changes to schemas or business logic can be replayed
without recollecting data.

Delivery is **at least once**. `event_id` identifies a physical delivery;
`idempotency_key` identifies the logical event. Raw deliveries remain
immutable, while downstream post tables deterministically retain one event per
tenant and idempotency key.

## Tenancy and security

- Every source, rule, raw event, canonical post, metric, review record, and
  serving signal is tenant-scoped.
- Connector configuration stores secret references only. Credentials belong in
  a secret manager and are resolved by the connector runtime.
- Production serving must enforce tenant filters with Unity Catalog grants,
  row filters, separate catalogs/schemas, or isolated workspaces according to
  the required trust boundary.
- Source deletion and retention requirements must propagate from raw storage to
  derived data products.

## Operational contract

`gold_source_health` reports delivered events, unique logical events,
duplicates, rejected events, p95 collection latency, freshness, and health
status for every registered source.

Initial production SLOs should be negotiated per source because provider
capabilities differ. Recommended starting points:

| Measure | Starting objective |
|---|---:|
| Valid-event acceptance | >= 99.5% |
| Duplicate deliveries after canonicalization | 0 |
| Unexplained data loss | 0 |
| Webhook/stream freshness | 95% within 5 minutes |
| Polling-source freshness | 95% within 3 polling intervals |
| Replay recovery point | Full retained raw-event history |

## Evolution triggers

Move the control plane into an independently deployed service when customers
must self-manage connections or collection policies. Move connector workers
into independent regional data planes when one tenant/source can affect another,
when throughput needs independent scaling, or when data-residency rules require
regional processing. Until then, preserve the interfaces and operate the
smallest reliable deployment.
