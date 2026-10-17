# Internal pilot: audience and monitoring set

Decided 2026-10-17 by the product owner. Builds on
[Market gap analysis](MARKET_GAP_ANALYSIS.md) and the
[Internal Pilot Workspace](INTERNAL_PILOT_WORKSPACE.md).

## Decision

- **Audience:** engineering and platform leads choosing a stack for
  enterprise AI-agent workflows.
- **Offer:** an evidence-backed stack shortlist from the Agent Stack Advisor,
  fitted to the team's cloud, compliance needs and skills.
- **Evidence sources:** practitioner and maintainer accounts, plus creators who
  build and sell agent services. Creators are a signal source, not the audience.
- **Primary metric:** share of landing-page visitors who request a shortlist.
  Guardrails as in the pilot workspace scorecard.
- **Exit test:** one traceable chain from cited evidence to an approved
  hypothesis to a logged aggregate result, ending in GO, ITERATE or STOP. With
  this audience the v1 quality gate (1,000 impressions and 25 conversions per
  arm) will probably not be met in a week; an `INSUFFICIENT_DATA` result is an
  acceptable pilot outcome, not a failure of the loop.
- **Out of scope:** Reddit (commercial access gated), Instagram, LinkedIn.

## Monitoring set

| Field | Value |
|---|---|
| Topics | agent framework selection; production agent reliability; agent evaluation and observability; MCP in the enterprise; agent governance and security |
| Named frameworks | LangGraph, CrewAI, Microsoft Agent Framework, OpenAI Agents SDK, Google ADK, PydanticAI |
| Accounts and channels | **To be supplied by the product owner** (5-10 trusted practitioners and channels). Not guessed. |
| Language and geography | English, global (YouTube region code stays `US` for ranking) |
| Window | 14-day evidence window; collectors look back 6 hours per run |
| Exclude | crypto, giveaways, income claims without method, course promotions, reposts |

## Proposed collector settings (not applied)

These are GitHub repository variables. Changing them alters what the live
collectors fetch and spend, so they are applied only on explicit approval.

| Variable | Current | Proposed |
|---|---|---|
| `YOUTUBE_SEARCH_EXPRESSION` | `Acme\|GlowUpChallenge` (demo terms) | `"agent framework"\|LangGraph\|CrewAI\|"Microsoft Agent Framework"\|"AI agents in production"\|"MCP server"\|"agent evaluation"` |
| `YOUTUBE_CHANNEL_IDS` | unset | the supplied channel IDs |
| `X_SEARCH_EXPRESSION` | unset | `("agent framework" OR LangGraph OR CrewAI OR "Microsoft Agent Framework" OR "agent evals" OR "MCP server") lang:en -is:retweet -is:reply` |
| `X_ACCOUNT_HANDLES` | unset | the supplied handles |
| `X_MAX_REQUESTS_PER_RUN` | unset (default 10) | `2` |
| `ENABLE_X_COLLECTOR` | unset (collector skipped) | `true`, only after the budget below is accepted |

The proposed `X_SEARCH_EXPRESSION` drops X's default San Francisco trends. Set
`X_TRENDS_WOEID` to empty only if the connector accepts an empty value;
otherwise keep the default and accept a few unrelated trend events.

## Cost and quota

- **X:** $0.005 per post read (docs.x.com, checked 2026-10-16). The collector runs
  hourly with up to 100 posts per page. At the default of 10 requests per run
  the worst case is 24,000 reads/day, about $120/day. At 2 requests per run the
  worst case is 4,800 reads/day, about $24/day or $168/week. Narrow queries
  return fewer posts, so real cost should be lower. Pay-per-use is capped at
  3 million reads per month.
- **YouTube:** the collector used 5 search calls per run on 2026-10-17 with
  90 search calls remaining in its budget; one page per rule. Recheck quota
  after adding rules.

## Verified on 2026-10-17

- YouTube collector: last run `SUCCESS`, `HEALTHY`, 13 videos, but it is
  searching the demo terms above, so its data is not pilot evidence.
- X collector: skipped on schedule because `ENABLE_X_COLLECTOR` is not set,
  and no query, hashtag or account variables are configured.
- Tenant: collectors write to tenant `demo`. Decide whether the pilot uses a
  separate tenant before storing reviewed records.
