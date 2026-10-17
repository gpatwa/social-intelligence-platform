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
| Accounts and channels | Starter set approved 2026-10-17; see Trusted sources below |
| Language and geography | English, global (YouTube region code stays `US` for ranking) |
| Window | 14-day evidence window; collectors look back 6 hours per run |
| Exclude | crypto, giveaways, income claims without method, course promotions, reposts |

## Collector settings

These are GitHub repository variables. Changing them alters what the live
collectors fetch and spend, so they are applied only on explicit approval. `YOUTUBE_SEARCH_EXPRESSION`,
`X_SEARCH_EXPRESSION`, `X_MAX_REQUESTS_PER_RUN` and `ENABLE_X_COLLECTOR` were
applied on 2026-10-17; channel IDs and account handles await the product owner.

| Variable | Current | Proposed |
|---|---|---|
| `YOUTUBE_SEARCH_EXPRESSION` | **Applied 2026-10-17 (v2)** | `"agent framework"\|LangGraph\|CrewAI\|"Microsoft Agent Framework"\|"OpenAI Agents SDK"\|"agent evaluation"\|"AI agents in production"\|"enterprise MCP" -crypto -trading` |
| `YOUTUBE_CHANNEL_IDS` | **Applied 2026-10-17** | AI Engineer, LangChain (IDs below) |
| `X_SEARCH_EXPRESSION` | **Applied 2026-10-17 (v2)** | `("agent framework" OR LangGraph OR CrewAI OR "Microsoft Agent Framework" OR "OpenAI Agents SDK" OR "Google ADK" OR PydanticAI OR "agent evals" OR "agent evaluation" OR (MCP (enterprise OR production OR governance OR security))) lang:en -is:retweet -is:reply -has:cashtags -crypto -airdrop -giveaway -memecoin` |
| `X_ACCOUNT_HANDLES` | **Applied 2026-10-17** | 10 handles below |
| `X_MAX_REQUESTS_PER_RUN` | **Applied 2026-10-17** | `11` (1 keyword search + 10 account searches) |
| `ENABLE_X_COLLECTOR` | **Applied 2026-10-17** (budget accepted) | `true` |
| `X_TRENDS_WOEID` | **Applied 2026-10-17** | `none` (San Francisco trends off) |
| `X_DAILY_READ_BUDGET` / `X_MONTHLY_READ_BUDGET` | defaults since PR 21 | `2000` / `30000` |

Trends were disabled with `X_TRENDS_WOEID=none` once the read-budget change
(PR 21) made that possible, so both X requests per run go to search.

## Trusted sources (starter set, approved 2026-10-17)

Chosen for reach and practitioner credibility on agent stacks and evaluation.
YouTube IDs and subscriber counts were read from the channel pages on
2026-10-17. X handles come from public knowledge and were not checked against
the X API; a handle that does not exist simply returns no posts.

| YouTube channel | Channel ID | Subscribers |
|---|---|---|
| AI Engineer (conference talks) | `UCLKPca3kwwd-B59HNr-_lvA` | ~751K |
| LangChain (framework maintainer) | `UCC-lyoTfSrcJzA1ab3APAgw` | ~208K |

Held back for quota: DeepLearning.AI `UCcIXc5mJsHVYTZR1maL5l9w` (~734K),
Latent Space `UCxBcwypKK-W3GHd_RZ9FZrQ` (~322K), Dave Ebbelaar
`UCn8ujwUInbJkBhffxqAPBVQ` (~301K), Cole Medin `UCMwVTLZIRRUyyVrkjDpn4pA`
(~229K), Sam Witteveen `UC55ODQSvARtgSyc8ThfiepQ` (~136K). Each channel costs
one search call per run against roughly 95 usable search calls per day, so
1 keyword + 2 channels at an hourly schedule (72/day) is the safe maximum.
Adding more needs channel collection through uploads playlists (1 unit per
call) instead of search.

| X handle | Why |
|---|---|
| `hwchase17` | Harrison Chase, LangChain / LangGraph |
| `joaomdmoura` | João Moura, CrewAI |
| `samuel_colvin` | Samuel Colvin, Pydantic / PydanticAI |
| `jerryjliu0` | Jerry Liu, LlamaIndex |
| `simonw` | Simon Willison, hands-on LLM tooling and security |
| `HamelHusain` | Hamel Husain, LLM evaluation practice |
| `sh_reya` | Shreya Shankar, evaluation research |
| `eugeneyan` | Eugene Yan, applied LLM systems |
| `swyx` | swyx, AI Engineer / Latent Space |
| `chipro` | Chip Huyen, AI engineering |

Each handle is one search request per run, so `X_MAX_REQUESTS_PER_RUN` is 11.
Spend stays bounded by the read budget (2,000 reads per day).

## Cost and quota

- **X:** $0.005 per post read (docs.x.com, checked 2026-10-16). Since PR 21 the
  collector enforces 2,000 reads per UTC day and 30,000 per UTC month, about
  $10/day and $150/month at most, and reports reads used and remaining in each
  run metric. Prepaid X credits remain the hard ceiling. The first pilot run
  read 93 resources (73 posts, 20 trends), about $0.47.
- **YouTube:** the collector used 5 search calls per run on 2026-10-17 with
  90 search calls remaining in its budget; one page per rule. Recheck quota
  after adding rules.

## Verified on 2026-10-17

- YouTube collector: last run `SUCCESS`, `HEALTHY`, 13 videos, on the old demo
  terms; data collected before the 2026-10-17 change is not pilot evidence.
- X collector: enabled 2026-10-17 with the query above and a 2-request cap;
  first scheduled run (at :29) not yet checked.
- Tenant: collectors write to tenant `demo`. Decide whether the pilot uses a
  separate tenant before storing reviewed records.

## First evidence review (2026-10-17, v1 queries)

Manual runs at 03:45 UTC, read from the landed event files. Judgments below are
from keyword counts and reading samples, not a full hand-labelled set.

**X** (2 requests, 93 billed reads):
- 73 posts from 70 distinct authors, all English, no near-duplicates: good
  diversity.
- 39 of 73 posts matched only "MCP server", mostly generic tool chatter rather
  than stack decisions. Named frameworks were rare (LangGraph 4, CrewAI 2,
  Microsoft Agent Framework 1).
- Noise: 4 crypto posts (including a token contract launch), engagement-bait
  listicles; 32 of 73 posts had zero engagement.
- 20 San Francisco trends (sports, wildfires, local news): irrelevant, about a
  fifth of the reads.

**YouTube** (6 search calls, 13 videos):
- 13 distinct small channels, on-topic titles (MCP servers, CrewAI, Microsoft
  Agent Framework, sandboxing), but low authority and a heavy MCP skew.
- Statistics are empty for every video, so views and likes are recorded as 0
  and ranking cannot use momentum. Needs investigation in the YouTube
  connector's statistics call.
- At least 3 titles are Portuguese or Vietnamese while the payload says `en`:
  the language field is taken from configuration, not detected.

**Changes made (v2 queries above):** dropped bare "MCP server" in favour of MCP
with enterprise, production, governance or security terms; added OpenAI Agents
SDK, Google ADK, PydanticAI and agent evaluation; excluded cashtags, crypto,
airdrops, giveaways and memecoins on X, and crypto and trading on YouTube.

**Follow-up (2026-10-17):** trends disabled; PR 22 now reports YouTube stats
failures (`stats_enrichment_failures`, `videos_missing_stats`) and labels
undeclared video language `und`. The root cause of the empty statistics will
show in the first run that finds videos. Still open: trusted account handles and
channel IDs from the product owner; re-review evidence after 2-3 days of v2
queries.
