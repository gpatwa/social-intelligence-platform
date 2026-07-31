# Production Readiness Checklist

## Before production

- Move from Databricks Free Edition to a paid workspace appropriate for commercial data and workload requirements.
- Create separate `dev`, `test`, and `prod` catalogs/schemas with least-privilege access.
- Replace demo ingestion with approved API or licensed-provider ingestion.
- Use secret scopes or governed connections for credentials.
- Configure data-retention, deletion, and privacy workflows for every social provider.
- Set up alert notifications and incident escalation paths.
- Add pipeline scheduling, retry policy, freshness SLAs, and cost budgets.
- Enable Unity Catalog data-quality monitoring on production schemas.
- Establish labeled evaluation data for sentiment, topic, entity, and safety classification.
- Version models/prompts, publish acceptance thresholds, and maintain a rollback procedure.

## Go-live gates

1. Ingestion completeness meets the provider-reconciled target for 14 consecutive days.
2. Data freshness meets the agreed SLA for 14 consecutive days.
3. Model quality meets the agreed precision/recall thresholds on labeled data.
4. Every alert has an owner, response target, and tested notification route.
5. Dashboard metrics have approved definitions and a named business owner.

