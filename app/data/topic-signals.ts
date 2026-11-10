// A static, dated early read of which topics the collected conversation is about,
// by channel. It is NOT a ranking and NOT live. Every number below comes from one
// of two places, named next to it on the page:
//   - a random sample of 27 landed YouTube videos (taken 2026-11-04), whose topics
//     were labelled by a model from the titles (not reviewed by a person);
//   - the first GitHub collector run (2026-11-03): releases found per watchlist repo.
// Post text, authors and titles are deliberately not stored here.
// Slice 3 of platform/docs/LANDING_REDESIGN_PLAN.md replaces this file with a
// CI-exported snapshot.

export type TopicSignal = {
  id: string;
  name: string;
  why: string;
  youtubePosts: number;
  github?: string;
};

export const topicSignals = {
  asOf: "2026-11-04",
  youtubeSampleSize: 27,
  topics: [
    {
      id: "governance_security",
      name: "Governance and security",
      why: "Approvals, access control and audit for agents that act on company systems.",
      youtubePosts: 10,
    },
    {
      id: "reliability",
      name: "Reliability in production",
      why: "Keeping agents correct once live: state, retries, failure handling, observability.",
      youtubePosts: 4,
    },
    {
      id: "build_vs_buy",
      name: "Build vs buy",
      why: "Choosing a platform or framework, and what it costs to switch later.",
      youtubePosts: 4,
    },
    {
      id: "evals",
      name: "Evals",
      why: "Measuring whether an agent does the job, before and after each release.",
      youtubePosts: 3,
    },
    {
      id: "framework",
      name: "Agent frameworks",
      why: "LangGraph, CrewAI, the OpenAI Agents SDK, Google ADK, Pydantic AI, Microsoft Agent Framework.",
      youtubePosts: 2,
      github: "23 releases found across 6 framework repos in 30 days (capped at 5 per repo)",
    },
    {
      id: "mcp",
      name: "MCP",
      why: "Connecting agents to tools and data through the Model Context Protocol.",
      youtubePosts: 1,
      github: "4 releases found in the reference servers repo in 30 days",
    },
  ] satisfies TopicSignal[],
  channels: [
    { name: "YouTube", state: "Collecting", detail: "Hourly keyword and channel discovery." },
    { name: "X", state: "Collecting", detail: "Capped recent search and curated handles. Topic labels are pending." },
    { name: "GitHub", state: "Collecting", detail: "Daily snapshots and releases for 7 watched repos. An adoption signal, not posts." },
    { name: "Instagram", state: "Not collected", detail: "Out of scope for this pilot: access is gated." },
  ],
  startHere:
    "In this sample, 14 of 27 videos were about governance and security or about reliability.",
  next: [
    "Label about 200 posts so topic detection is reliable enough to compare channels.",
    "Have a named reviewer approve the first recommendation.",
    "Show X and GitHub topic signals here once ingestion resumes.",
  ],
  caveat:
    "Static snapshot from 4 Nov 2026. Topics were labelled by a model from video titles and have not been reviewed by a person. One channel, 27 videos: a prompt to check, not a ranking. Topic rules are still being validated (53% primary accuracy on held-out posts). No post text, author or score is shown.",
};
