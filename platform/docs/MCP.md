# MCP operations

The repository now includes a thin MCP adapter for agent hosts. It is a
protocol boundary over governed read models, not a second data plane or a place
for model-specific business logic.

## Start it

Install the optional MCP extra and run the stdio server:

```bash
python3 -m pip install -e './platform[mcp,standards]'
social-intelligence-mcp
```

Desktop hosts launch the command as a child process over stdio. The server reads
the optional `SOCIAL_INTELLIGENCE_MCP_SNAPSHOT_DIR` directory. Each projection
is a JSON array or an object with an `items` array:

```text
opportunities.json
evidence.json
metrics.json
pipeline_status.json
```

The serving/export task is responsible for writing these projections from
Databricks or Snowflake. The MCP layer does not accept arbitrary SQL, provider
tokens, table names, or model prompts.

For a live read-only connector, set `SOCIAL_INTELLIGENCE_MCP_PROVIDER` to
`databricks` or `snowflake` and install the matching optional extra. Provider
credentials remain environment/secret-manager inputs. For Free Edition, run a
scheduled export with `write_projection_snapshots()` and use `snapshot` mode.

## Tools

| Tool | Access | Behavior |
| --- | --- | --- |
| `list_opportunities` | Read | Tenant-scoped ranking with status, score, and limit filters |
| `get_evidence` | Read | Tenant-scoped lookup by durable evidence ID |
| `get_metrics` | Read | Tenant-scoped metric observations with source filters |
| `get_pipeline_status` | Read | Tenant-scoped source freshness and health projection |
| `draft_recommendation` | Draft | Returns deterministic `PROPOSED` output; never persists or approves |

Every tool requires `tenant_id`. The service rejects malformed tenant IDs and
filters rows before returning them. An empty or missing snapshot directory
returns an empty projection; it does not fall back to another tenant.

Approval, spend, publishing, lifecycle mutation, and arbitrary SQL are not MCP
tools. A future write path must use a separate authenticated service, an
idempotency key, policy checks, and an explicit human approval record.

## Provider boundary

`McpService` depends on the `SocialIntelligenceDataProvider` protocol. The
current `SnapshotDataProvider` is intentionally portable for Databricks Free
Edition and local testing. A production adapter can read a governed SQL view or
an API projection without changing the MCP tools or their contracts.

## Service mode and agent governance

Set `SOCIAL_INTELLIGENCE_MCP_TRANSPORT=streamable-http` to expose the MCP v2
Streamable HTTP transport. `SOCIAL_INTELLIGENCE_MCP_BEARER_TOKEN` is required;
`SOCIAL_INTELLIGENCE_MCP_ALLOWED_TENANTS` can restrict the process to a comma
separated tenant allow-list. Tool metadata is emitted as structured audit
records and can be connected to an OpenTelemetry tracer.

`social_intelligence.agents.Supervisor` composes research, evidence, critic,
and strategist stages over the same tool gateway. It produces replayable agent
artifacts and always stops at `PROPOSED`. `ApprovalGate` and `ExperimentGate`
are separate deterministic policy boundaries; no agent can approve spend or
launch an experiment implicitly.
