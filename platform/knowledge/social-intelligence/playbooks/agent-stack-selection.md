---
type: Playbook
title: Enterprise agent stack selection
description: Automation-first sequence for selecting a governed AI agent implementation stack.
status: active
tags: [agents, architecture, human-in-the-loop, stack-advisor]
generated: {by: "process:agent-stack-advisor", at: "2026-08-20T00:00:00Z"}
sources:
  - resource: ../../../docs/AGENT_STACK_ADVISOR.md
---

# Enterprise agent stack selection

1. Define one business outcome, process owner, baseline, and decision rights.
2. Separate deterministic steps from tasks that genuinely require model
   reasoning.
3. Prefer typed APIs and MCP; isolate computer use as an exception path.
4. Choose the orchestration runtime using cloud alignment, team capability, and
   operational risk—not popularity.
5. Add explicit identity, authorization, approval, audit, retry, and
   compensation controls.
6. Create evaluation cases before allowing external side effects.
7. Run in shadow mode, then increase autonomy only after measured outcomes meet
   the release threshold.
