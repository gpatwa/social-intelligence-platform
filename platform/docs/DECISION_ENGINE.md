# Creative Investment Decision Engine

## Product contract

The decision engine answers one operational question:

> What should the brand promote or address next, why now, and what controlled
> experiment will determine whether the recommendation creates commercial value?

It extends the existing signal pipeline with four governed records:

1. **Opportunity** — a reproducible projection of a social signal, explicit
   product fit, commercial fit, priority, confidence, expiry, and evidence.
2. **Recommendation** — a durable proposal containing the audience, channel,
   hypothesis, creative brief, primary metric, approval state, and decision
   rationale.
3. **Experiment** — a controlled test created only after approval, with a fixed
   control, treatment, metric, guardrail, target lift, budget, and outcome inputs.
4. **Learning** — an immutable commercial result that can calibrate later
   recommendations for comparable products, audiences, channels, and offers.

## Lifecycle and safety gates

```text
social signal
  -> mapped opportunity
  -> PROPOSED recommendation
  -> APPROVED or REJECTED
  -> EXPERIMENT_PLANNED
  -> RUNNING
  -> COMPLETED or CANCELLED
  -> WIN / LOSS / INCONCLUSIVE learning
```

- Scheduled jobs may refresh reproducible opportunities and untouched
  proposals. They cannot overwrite approved, rejected, running, or completed
  decisions.
- No experiment is created before explicit recommendation approval.
- Creating a `PLANNED` experiment does not launch ads or authorize spend.
- The first outcome calculation is `DIRECTIONAL`. Statistical confidence must
  be supplied by the execution adapter before a result can be treated as causal.
- Every opportunity and recommendation stores an evidence reference to its
  source signal, timestamp, Gold table, and evidence count.

## Tables

| Layer | Table | Ownership |
|---|---|---|
| Control | `control_product_catalog` | Commerce/catalog sync |
| Control | `control_signal_product_map` | Product and marketing owners |
| Gold | `gold_opportunities` | Rebuilt from governed signals |
| Decision | `decision_recommendations` | Durable workflow state |
| Decision | `decision_experiments` | Durable execution state |
| Decision | `decision_learnings` | Immutable outcome memory |
| Gold | `gold_experiment_performance` | Read model for analysis |
| Gold | `gold_pilot_scorecard` | Pilot success metrics |

The Snowflake publisher exposes these tables to the read-only BA role. It does
not expose Bronze payloads or allow analysts to mutate lifecycle state.

## Pilot acceptance criteria

The first paid design-partner pilot should target:

- at least five reviewed recommendations per week;
- at least three controlled experiments in eight weeks;
- recommendation adoption rate reported without hiding rejections;
- experiment win rate and measured lift reported with confidence level;
- incremental revenue and contribution margin captured separately;
- every recommendation traceable to provider evidence and an explicit product
  mapping.

The product has not demonstrated product-market fit until a customer repeatedly
acts on recommendations and pays for the workflow—not merely the dashboard.
