# Run the MVP in Databricks Free Edition

This project fits within Free Edition limits: it uses Python, serverless compute,
one sequential five-task job, Unity Catalog managed tables, and one managed
volume. The demo does not require external network access or model serving.

## Fastest path: import the notebook archive

1. Sign in to the Databricks workspace.
2. In **Workspace**, open your user folder.
3. Select **Create > Import**.
4. Upload `social-intelligence-free-edition.zip`.
5. Open and run these notebooks in order using serverless compute:
   - `00_initialize_platform`
   - `01_generate_demo_data`
   - `02_build_analytics`
   - `04_model_governance`
   - `03_validate_product`
6. Confirm that the validation notebook reports that every acceptance check passed.

The default destination in Databricks Free Edition is:

```text
dev.social_intelligence_dev
```

If that schema name is unavailable, change the `schema` widget at the top of
each notebook to a schema you can create. Use the same value in all three.

## Optional: deploy the Asset Bundle

Free Edition supports serverless jobs, and this bundle has only five sequential
tasks, below the Free Edition maximum of five concurrent job tasks.

Install the current Databricks CLI, then authenticate using browser-based OAuth:

```bash
databricks auth login \
  --host https://dbc-b8672746-8e43.cloud.databricks.com \
  --profile social-intelligence-free
```

Deploy from the project directory:

```bash
databricks bundle validate -t dev --profile social-intelligence-free
databricks bundle deploy -t dev --profile social-intelligence-free
databricks bundle run social_intelligence_mvp -t dev --profile social-intelligence-free
```

## Collect live YouTube data

Use the repository's GitHub Actions collector for live API access. It runs
outside Databricks, lands immutable files through the Files API, and keeps
checkpoints and quota accounting in the managed volume. Follow
[the external collector runbook](docs/EXTERNAL_COLLECTOR.md).

After the first collector batch lands, refresh the real-source tables with:

```bash
databricks bundle run social_intelligence_external_ingestion -t dev \
  --profile social-intelligence-free
```

Both the GitHub schedule and the external-ingestion job start disabled. This
prevents missing credentials or an unvalidated query from consuming API and
Free Edition quotas immediately after deployment.

## Create the dashboard

Start the workspace's serverless SQL warehouse and open the SQL editor. Copy
queries from `dashboard_queries.sql`, replacing:

```text
${catalog} -> dev
${schema}  -> social_intelligence_dev
```

Create an AI/BI dashboard from the query results. To conserve the Free Edition
quota, stop running additional notebook experiments after the workflow finishes
and avoid scheduling the demo more frequently than necessary.

## Free Edition suitability

This is suitable for learning and demonstrating the analytic product. Databricks
Free Edition is intended for non-commercial use, has daily/monthly fair-use
quotas, offers no SLA, and restricts outbound internet access. A commercial or
production deployment should use a paid workspace or a trial intended for
business evaluation.
