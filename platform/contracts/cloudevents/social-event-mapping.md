# Social event CloudEvents 1.0 mapping

`SocialEventEnvelope.to_cloudevent()` maps the existing connector contract to a
CloudEvents structured JSON object. It does not change Databricks storage.

| CloudEvents attribute | Connector source |
| --- | --- |
| `id` | `event_id` |
| `source` | Stable URN from tenant, platform, and source ID |
| `type` | Existing `social.*` event type |
| `subject` | Platform and source object ID |
| `time` | `occurred_at` in UTC |
| `correlationid` | `correlation_id` |
| `idempotencykey` | `idempotency_key` |
| `collectedat` | `collected_at` in UTC |
| `data` | Schema version, native source payload, and attributes |

CloudEvents extension names are lowercase to satisfy the 1.0 attribute naming
rules. The `dataschema` attribute identifies only the `data` value—not the
outer CloudEvent or the Databricks landing record.
