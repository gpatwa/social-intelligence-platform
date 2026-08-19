# ADR 0001: Open standards for event, knowledge, and agent interoperability

- Status: Accepted
- Date: 2026-08-17
- Owners: Platform and data engineering

## Context

The platform must add providers, models, tools, and future agents without
coupling durable data to a single orchestration framework. It also needs
portable business definitions and verifiable computations that SQL users and
agents can discover without reverse-engineering notebooks.

OKF is intentionally not a schema registry, runtime, access-control system, or
agent protocol. Using it for those jobs would create a fragile abstraction.

## Decision

Adopt a layered standards profile:

1. JSON Schema and OpenAPI define durable data and service contracts.
2. CloudEvents 1.0 is the optional transport representation for social events.
3. OKF 0.2 packages definitions, lineage, policies, playbooks, and attested
   computation metadata in repository-native Markdown.
4. OpenTelemetry will carry traces and correlation identifiers.
5. MCP exposes governed read tools and non-persisting drafts to agents. Any
   future write tool requires separate authentication, idempotency, policy, and
   human approval controls.
6. A2A will be introduced only when independently deployed agents need to
   negotiate work across service boundaries.
7. AG-UI will be introduced only for interactive human review experiences.

The platform's internal workflow remains deterministic Python and Databricks
SQL. Agents may recommend actions, but cannot approve spend, publish content, or
change experiment state without policy and human gates.

## Consequences

- The connector envelope remains backward compatible; CloudEvents is an adapter.
- Business artifacts reference evidence IDs rather than provider chat history.
- OKF is pinned to 0.2 and treated as experimental until the specification is
  stable enough for a formal upgrade policy.
- The repository validates contracts and the OKF bundle in CI.
- Runtime frameworks can be evaluated later against these boundaries instead of
  defining the boundaries themselves.

## Rejected alternatives

- A single agent framework as the platform contract: too much vendor and runtime
  coupling.
- OKF as a replacement for JSON Schema or a semantic layer: outside its scope.
- A distributed agent mesh in the MVP: unnecessary operational and evaluation
  complexity before durable artifacts and policies exist.
