import { PipelineStatusPanel } from "./pipeline-status";
import { AgentStackAdvisor } from "./agent-stack-advisor";
import { InternalPilotWorkspace } from "./internal-pilot-workspace";
import { evidenceSnapshot, formatSnapshotDate } from "./data/evidence-snapshot";
import { topicSignals } from "./data/topic-signals";

const githubUrl = "https://github.com/gpatwa/social-intelligence-platform";
const baQueryPackUrl =
  "https://github.com/gpatwa/social-intelligence-platform/blob/main/platform/sql/snowflake_ba_starter_queries.sql";
const topicDesignUrl =
  "https://github.com/gpatwa/social-intelligence-platform/blob/main/platform/docs/PILOT_TOPICS.md";

const capabilities = [
  {
    index: "01",
    title: "Market opportunities",
    copy: "Translate accelerating conversations into product-level opportunities with explicit fit, confidence, expiry, and evidence.",
    metric: "0–100",
    label: "explainable priority",
  },
  {
    index: "02",
    title: "Creative recommendations",
    copy: "Generate a testable audience, channel, hypothesis, and creative brief without hiding the source signal or product mapping.",
    metric: "Gated",
    label: "human approval",
  },
  {
    index: "03",
    title: "Campaign intelligence",
    copy: "Turn only approved recommendations into aggregate control-versus-treatment test briefs with a human-owned handoff.",
    metric: "No PII",
    label: "aggregate measurement",
  },
  {
    index: "04",
    title: "Conservative learning",
    copy: "Calculate observed lift, retain the measurement boundary, and feed only quality-gated results into offline ranking.",
    metric: "Gated",
    label: "offline feedback",
  },
];

const decisionLoop = [
  {
    step: "01",
    title: "Opportunity",
    copy: "Social momentum + evidence strength + explicit product and commercial fit.",
    detail: "Reproducible",
  },
  {
    step: "02",
    title: "Recommendation",
    copy: "Audience, channel, hypothesis, creative brief, metric, and approval rationale.",
    detail: "Governed",
  },
  {
    step: "03",
    title: "Experiment",
    copy: "A fixed control and treatment with target lift, budget, and margin guardrails.",
    detail: "Controlled",
  },
  {
    step: "04",
    title: "Learning",
    copy: "Measured lift, incremental revenue, contribution margin, and reusable context.",
    detail: "Compounding",
  },
];

const connectorRoadmap = [
  {
    name: "YouTube",
    status: "Implemented",
    tone: "ready",
    detail: "Hourly discovery collection lands governed, replayable events for the Databricks pipeline. Current state is in the live status panel.",
  },
  {
    name: "X",
    status: "Implemented",
    tone: "ready",
    detail: "Budget-capped recent search and curated account monitoring land governed events; trend snapshots are switched off.",
  },
  {
    name: "GitHub",
    status: "Implemented",
    tone: "ready",
    detail: "Daily repository snapshots and releases for a curated agent-framework watchlist, kept as an adoption signal separate from post scoring.",
  },
  {
    name: "Instagram",
    status: "Needs authorization",
    tone: "ready",
    detail: "Graph API collector, checkpoints, and governed source registration exist but are switched off until a Meta account is linked and authorized.",
  },
  {
    name: "Reddit",
    status: "Approval pending",
    tone: "pending",
    detail: "Held behind Reddit Data API access approval; no scraping or credential workarounds.",
  },
  {
    name: "Bluesky",
    status: "Next",
    tone: "next",
    detail: "The next candidate for open public-conversation trend signals.",
  },
];

const architecture = [
  {
    number: "01",
    name: "Control plane",
    detail: "Sources, collection rules, event contracts, ownership, and policy.",
  },
  {
    number: "02",
    name: "Data plane",
    detail: "Replayable events, validation, deduplication, enrichment, and tenant-scoped metrics.",
  },
  {
    number: "03",
    name: "Experience plane",
    detail: "Unified signals, dashboards, alerts, review queues, and future product APIs.",
  },
];

export default function Home() {
  return (
    <main>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="Social Intelligence home">
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span>
            <b>Social Intelligence</b>
            <small>Signal operating system</small>
          </span>
        </a>
        <nav aria-label="Primary navigation">
          <a href="#topics">Topics</a>
          <a href="#decision">Decision engine</a>
          <a href="#workspace">Pilot workspace</a>
          <a href="#advisor">Stack advisor</a>
          <a href="#architecture">Architecture</a>
          <a href="#serving">Serving</a>
          <a href="#status">Live status</a>
          <a href="#readiness">Readiness</a>
        </nav>
        <a className="nav-cta" href={githubUrl} target="_blank" rel="noreferrer">
          View the source <span aria-hidden="true">↗</span>
        </a>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <div className="eyebrow">
            Enterprise AI Builder Intelligence · Staging pilot
          </div>
          <h1>
            Find the signal.
            <span>Shape what’s next.</span>
          </h1>
          <p className="hero-lede">
            Turn market signals into product decisions—and business workflows
            into governed AI architectures that prove their value.
          </p>
          <div className="hero-actions">
            <a
              className="button button-primary"
              href="#workspace"
            >
              Build an internal pilot <span aria-hidden="true">↓</span>
            </a>
            <a
              className="button button-secondary"
              href={topicDesignUrl}
              target="_blank"
              rel="noreferrer"
            >
              How results are measured <span aria-hidden="true">↗</span>
            </a>
          </div>
          <p className="access-note">
            Collectors for YouTube, X and GitHub are implemented; their current
            state is in the live status panel below. The curated serving layer is
            available in Snowflake for authorized analysts.
          </p>
        </div>

        <div className="signal-console evidence-card" aria-labelledby="evidence-card-title">
          <div className="console-topbar">
            <span>Evidence record</span>
            <span className="snapshot-badge">
              Static snapshot · {formatSnapshotDate(evidenceSnapshot.asOf)}
            </span>
          </div>
          <div className="evidence-card-body">
            <h2 id="evidence-card-title">Recent evidence, grouped by pilot topic.</h2>
            <p>
              Real items from the collectors, shown by platform, topic and date with a
              direct link to the source. No post text, author or ranking score is
              shown.
            </p>
            <ul className="evidence-list">
              {evidenceSnapshot.items.map((item) => (
                <li key={item.url}>
                  <span className="evidence-platform">{item.platform}</span>
                  <span className="evidence-topic">{item.topic}</span>
                  <time dateTime={item.published}>{formatSnapshotDate(item.published)}</time>
                  <a href={item.url} target="_blank" rel="noreferrer">
                    Open source <span aria-hidden="true">↗</span>
                    <span className="visually-hidden">
                      ({item.platform} post from {formatSnapshotDate(item.published)}, opens in a new tab)
                    </span>
                  </a>
                </li>
              ))}
            </ul>
            <ol className="evidence-path" aria-label="Where this evidence goes next">
              <li>
                <b>Evidence</b>
                <span>collected</span>
              </li>
              <li>
                <b>Recommendation</b>
                <span>none approved yet</span>
              </li>
              <li>
                <b>Named reviewer</b>
                <span>first review pending</span>
              </li>
              <li>
                <b>Measured result</b>
                <span>not started</span>
              </li>
            </ol>
          </div>
          <div className="console-footer evidence-footer">
            <p>{evidenceSnapshot.measurement}</p>
            <p>
              Taken by hand from {evidenceSnapshot.source}. It does not update; the
              live status panel below does.
            </p>
          </div>
        </div>
      </section>

      <section className="section topics-section" id="topics" aria-labelledby="topics-title">
        <div className="section-heading">
          <p className="section-kicker">Signals by topic and channel</p>
          <h2 id="topics-title">Which topics to listen to first.</h2>
          <p>
            An early read of what the collected conversation is about, where it
            is happening, and what to do next. It is a starting point, not a
            ranking.
          </p>
        </div>

        <ul className="topic-channels" aria-label="Channels">
          {topicSignals.channels.map((channel) => (
            <li key={channel.name} data-state={channel.state === "Collecting" ? "on" : "off"}>
              <b>{channel.name}</b>
              <span>{channel.state}</span>
              <small>{channel.detail}</small>
            </li>
          ))}
        </ul>

        <p className="topic-start">
          <b>Early read.</b> {topicSignals.startHere}
        </p>

        <ol className="topic-grid" aria-label="Topics, in order of videos in the sample">
          {topicSignals.topics.map((topic) => (
            <li className="topic-card" key={topic.id}>
              <h3>{topic.name}</h3>
              <p>{topic.why}</p>
              <dl>
                <div>
                  <dt>YouTube sample</dt>
                  <dd>{`${topic.youtubePosts} of ${topicSignals.youtubeSampleSize} videos`}</dd>
                </div>
                {topic.github ? (
                  <div>
                    <dt>GitHub</dt>
                    <dd>{topic.github}</dd>
                  </div>
                ) : null}
                <div>
                  <dt>X</dt>
                  <dd>Topic labels pending</dd>
                </div>
              </dl>
            </li>
          ))}
        </ol>

        <div className="topic-next">
          <h3>What happens next</h3>
          <ol>
            {topicSignals.next.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ol>
        </div>

        <p className="topic-caveat">{topicSignals.caveat}</p>
      </section>

      <PipelineStatusPanel />

      <section className="section decision-section" id="decision">
        <div className="section-heading decision-heading">
          <p className="section-kicker">Creative investment decision engine</p>
          <h2>From “what is trending?” to “what should we fund next?”</h2>
          <p>
            Every recommendation carries its source evidence, product mapping,
            confidence, approval state, experiment design, and commercial
            outcome. Production gets cheaper; decision quality compounds.
          </p>
        </div>
        <div className="decision-loop" aria-label="Decision engine workflow">
          {decisionLoop.map((stage, index) => (
            <article className="decision-card" key={stage.title}>
              <div className="decision-card-top">
                <span>{stage.step}</span>
                <small>{stage.detail}</small>
              </div>
              <h3>{stage.title}</h3>
              <p>{stage.copy}</p>
              {index < decisionLoop.length - 1 ? (
                <i aria-hidden="true">→</i>
              ) : null}
            </article>
          ))}
        </div>
        <div className="decision-proof">
          <span>Human approval before activation</span>
          <span>No automatic ad spend</span>
          <span>Incremental revenue + margin</span>
          <span>Snowflake-ready decision records</span>
        </div>
      </section>

      <InternalPilotWorkspace />

      <AgentStackAdvisor />

      <section className="section serving-section" id="serving">
        <div className="serving-intro">
          <p className="section-kicker">Analyst serving layer</p>
          <h2>Databricks governs the decision. Snowflake makes it measurable.</h2>
          <p>
            The pipeline publishes only validated Gold marts into a dedicated
            read-only analytics schema. Analysts can inspect opportunities,
            approvals, experiments, wins, revenue, and margin without raw
            payloads, provider credentials, or unverified events.
          </p>
          <div className="serving-actions">
            <a className="button button-primary" href={baQueryPackUrl} target="_blank" rel="noreferrer">
              Open BA query pack <span aria-hidden="true">↗</span>
            </a>
          </div>
        </div>
        <div className="serving-stack" aria-label="Snowflake serving flow">
          <article>
            <span>01</span>
            <strong>Validate</strong>
            <p>Gold quality gates must pass before any external publish.</p>
          </article>
          <article>
            <span>02</span>
            <strong>Publish</strong>
            <p>Dedicated key-pair publisher uses an auto-resuming load warehouse.</p>
          </article>
          <article>
            <span>03</span>
            <strong>Analyze</strong>
            <p>BA users query curated signal, evidence, decision, and aggregate campaign marts with a read-only role.</p>
          </article>
        </div>
      </section>

      <section className="section product-section" id="product">
        <div className="section-heading">
          <p className="section-kicker">Product intelligence</p>
          <h2>From public conversation to an explainable signal.</h2>
          <p>
            The platform separates collection from analytics, so teams can see
            what is changing, why it matters, and whether the data is healthy
            enough to trust.
          </p>
        </div>
        <div className="capability-grid">
          {capabilities.map((capability) => (
            <article className="capability-card" key={capability.title}>
              <div className="card-index">{capability.index}</div>
              <h3>{capability.title}</h3>
              <p>{capability.copy}</p>
              <div className="card-metric">
                <strong>{capability.metric}</strong>
                <span>{capability.label}</span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="section connector-section" id="connectors">
        <div className="section-heading">
          <p className="section-kicker">Connector roadmap</p>
          <h2>One governed path for every approved source.</h2>
          <p>
            New sources must use approved APIs, durable checkpoints, request
            controls, and the same replayable event contract before they reach
            product metrics.
          </p>
        </div>
        <div className="connector-grid">
          {connectorRoadmap.map((connector) => (
            <article className="connector-card" key={connector.name}>
              <div>
                <h3>{connector.name}</h3>
                <span className={`connector-status ${connector.tone}`}>
                  <i aria-hidden="true" />
                  {connector.status}
                </span>
              </div>
              <p>{connector.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section architecture-section" id="architecture">
        <div className="architecture-intro">
          <p className="section-kicker">Built for evolution</p>
          <h2>Clear planes. Small operational footprint.</h2>
          <p>
            Logical separation gives the platform strong security and ownership
            boundaries today—without prematurely splitting the MVP into a fleet
            of services.
          </p>
          <div className="architecture-note">
            <span>Design principle</span>
            <p>
              Raw events remain immutable. Every downstream decision can be
              replayed, audited, and improved.
            </p>
          </div>
        </div>
        <div className="plane-stack">
          {architecture.map((plane) => (
            <article className="plane-card" key={plane.name}>
              <span>{plane.number}</span>
              <div>
                <h3>{plane.name}</h3>
                <p>{plane.detail}</p>
              </div>
              <i aria-hidden="true">→</i>
            </article>
          ))}
          <div className="plane-foundation">
            <span>Shared foundation</span>
            <strong>Identity · Governance · Audit · Observability</strong>
          </div>
        </div>
      </section>

      <section className="section readiness-section" id="readiness">
        <div className="section-heading readiness-heading">
          <p className="section-kicker">Honest by design</p>
          <h2>Ready for a focused pilot. Clear about the production path.</h2>
        </div>
        <div className="readiness-grid">
          <article className="readiness-card ready">
            <div className="readiness-title">
              <span>Available now</span>
              <b>Pilot-ready</b>
            </div>
            <ul>
              <li>Trend and challenge detection</li>
              <li>YouTube, X and GitHub collectors (their current state is in the live status panel)</li>
              <li>Durable checkpoints and replayable events</li>
              <li>Quota controls, retries, and source health</li>
              <li>Scheduled Databricks analytics workflow</li>
              <li>Guarded Snowflake serving for BA SQL</li>
              <li>Direct-link, explainable ranked evidence</li>
              <li>Seven-day internal pilot planner and scorecard</li>
              <li>CLI + MCP enterprise Agent Stack Advisor</li>
            </ul>
          </article>
          <article className="readiness-card path">
            <div className="readiness-title">
              <span>Deferred production controls</span>
              <b>After pilot proof</b>
            </div>
            <ul>
              <li>Google quota for engagement enrichment</li>
          <li>Meta authorization and Reddit API approval</li>
              <li>Production workload identity and managed secrets</li>
              <li>Provider deletion and retention workflows</li>
              <li>Production storage, reconciliation, and DR</li>
            </ul>
          </article>
        </div>
      </section>

      <section className="pilot-section" id="pilot">
        <div>
          <p className="section-kicker">One operating path</p>
          <h2>Start with approved sources. Expand behind one contract.</h2>
          <p>
            The path runs from external collection through Databricks analytics
            to Snowflake serving. The next source can
            reuse the same controls, checkpoints, event envelope, and delivery
            path.
          </p>
        </div>
        <div className="pilot-actions">
          <a
            className="button button-light"
            href={githubUrl}
            target="_blank"
            rel="noreferrer"
          >
            Read the source <span aria-hidden="true">↗</span>
          </a>
          <a className="text-link" href={baQueryPackUrl} target="_blank" rel="noreferrer">
            Use the BA query pack <span aria-hidden="true">↗</span>
          </a>
        </div>
      </section>

      <footer>
        <div className="footer-brand">
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <b>Social Intelligence</b>
        </div>
        <p>
          Collectors for YouTube, X and GitHub, governed Databricks analytics, and
          Snowflake BA serving—with an evidence-linked advisor for enterprise AI
          automation and agent architecture.
        </p>
        <a href="#top">Back to top ↑</a>
      </footer>
    </main>
  );
}
