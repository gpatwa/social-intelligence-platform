// A static, dated sample of real evidence, taken from the pipeline by hand on the
// snapshot date. It is deliberately NOT live: the page says so next to the data.
// Slice 3 of the redesign plan (platform/docs/LANDING_REDESIGN_PLAN.md) replaces it
// with a CI-exported snapshot.
//
// What is shown on purpose: platform, pilot topic, publication date and a link to
// the source. What is not: post text, author, and any ranking score. The ranked-
// evidence scores are still computed under the legacy `topic:lifestyle` decision
// key, so showing them here would over-claim.

export type EvidenceItem = {
  platform: "X" | "YouTube";
  topic: string;
  published: string; // ISO date
  url: string;
};

export const evidenceSnapshot = {
  asOf: "2026-11-07",
  source: "Databricks silver_social_posts, pilot-topics-v1 rules",
  items: [
    { platform: "X", topic: "Reliability", published: "2026-11-06", url: "https://x.com/i/web/status/2118559322745581582" },
    { platform: "X", topic: "MCP", published: "2026-11-06", url: "https://x.com/i/web/status/2118831175967900000" },
    { platform: "YouTube", topic: "Evals", published: "2026-11-06", url: "https://www.youtube.com/watch?v=_Pv_Y078vd8" },
  ] satisfies EvidenceItem[],
  measurement:
    "Topics come from keyword rules that scored 53% primary accuracy on 60 held-out posts (2026-11-06); no topic passed the quality gate.",
};

export function formatSnapshotDate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}
