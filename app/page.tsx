import { PipelineStatusPanel } from "./pipeline-status";
import { AgentStackAdvisor } from "./agent-stack-advisor";
import { InternalPilotWorkspace } from "./internal-pilot-workspace";

const dashboardUrl =
  "https://dbc-b8672746-8e43.cloud.databricks.com/dashboardsv3/01f17ce244971d80b97f3c0aa6b033ef/published?o=7474657828954669";
const githubUrl = "https://github.com/gpatwa/social-intelligence-platform";
const baQueryPackUrl =
  "https://github.com/gpatwa/social-intelligence-platform/blob/main/platform/sql/snowflake_ba_starter_queries.sql";
const pipelineRunUrl =
  "https://github.com/gpatwa/social-intelligence-platform/actions/runs/30737199706";

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
    title: "Controlled experiments",
    copy: "Turn only approved recommendations into planned control-versus-treatment tests with budget and margin guardrails.",
    metric: "10%",
    label: "default target lift",
  },
  {
    index: "04",
    title: "Commercial learning",
    copy: "Measure adoption, win rate, incremental revenue, and contribution margin to improve the next recommendation.",
    metric: "Closed",
    label: "decision loop",
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
    status: "Live",
    tone: "live",
    detail: "Discovery events are flowing into the governed Databricks pipeline.",
  },
  {
    name: "X",
    status: "Live",
    tone: "live",
    detail: "San Francisco trend snapshots and targeted recent-search monitoring are operational.",
  },
  {
    name: "Instagram",
    status: "Ready to authorize",
    tone: "ready",
    detail: "Graph API collector, checkpoints, and governed source registration are ready pending Meta account linkage.",
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
            <span className="live-dot" />
            Enterprise AI Builder Intelligence · Pilot-ready
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
              href={dashboardUrl}
              target="_blank"
              rel="noreferrer"
            >
              Open the analytics workspace <span aria-hidden="true">↗</span>
            </a>
          </div>
          <p className="access-note">
            YouTube and X collection are live. The curated serving layer is
            available in Snowflake for authorized analysts.
          </p>
        </div>

        <div className="signal-console" aria-label="Product signal preview">
          <div className="console-topbar">
            <span>Pipeline / latest validated run</span>
            <span className="console-live">Operational</span>
          </div>
          <div className="console-main">
            <div className="console-feature">
              <div className="feature-label">
                <span>Opportunity → recommendation</span>
                <strong>Evidence retained</strong>
              </div>
              <h2>Turn momentum into a testable commercial decision.</h2>
              <p>
                Product fit, creative hypothesis, target audience, approval,
                experiment design, and outcome stay connected from end to end.
              </p>
              <div className="trend-chart" aria-hidden="true">
                {[24, 31, 28, 42, 49, 61, 73, 91].map((height, index) => (
                  <span
                    key={index}
                    style={{ "--bar-height": `${height}%` } as React.CSSProperties}
                  />
                ))}
              </div>
              <div className="chart-axis">
                <span>Discover</span>
                <span>Learn</span>
              </div>
            </div>
            <div className="score-stack">
              <article className="score-card accent-green">
                <span>Decision stages</span>
                <strong>4</strong>
                <small>one governed loop</small>
              </article>
              <article className="score-card accent-coral">
                <span>Serving marts</span>
                <strong>16</strong>
                <small>published to ANALYTICS</small>
              </article>
            </div>
          </div>
          <div className="console-footer">
            <div>
              <span className="health-dot" />
              Two sources · one evidence-to-outcome path
            </div>
            <div>Hourly publish</div>
            <div>Gold-only access</div>
          </div>
        </div>
      </section>

      <section className="proof-strip" aria-label="Validated MVP metrics">
        <p>Latest verified delivery</p>
        <div className="proof-metrics">
          <span>
            <b>16</b> BA-facing marts
          </span>
          <span>
            <b>1</b> guarded hourly path
          </span>
          <span><b>86</b> automated checks</span>
          <span>
            <b>100%</b> verified end-to-end run
          </span>
        </div>
      </section>

      <aside className="operational-note" aria-label="Live data status">
        <div>
          <span className="health-dot" />
          <strong>Discovery and serving are live</strong>
        </div>
        <p>
          Approved provider events are validated in Databricks before curated
          Gold marts refresh Snowflake ANALYTICS on the hourly schedule.
        </p>
        <a href="#serving">See the analyst serving layer ↓</a>
      </aside>

      <PipelineStatusPanel dashboardUrl={dashboardUrl} />

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
            <a className="text-link" href={dashboardUrl} target="_blank" rel="noreferrer">
              Open governed metrics <span aria-hidden="true">↗</span>
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
            <p>BA users query 16 curated signal, evidence, and decision marts with a read-only role.</p>
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
              <li>Live YouTube discovery ingestion</li>
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
          <p className="section-kicker">The operating path is proven</p>
          <h2>Start with approved sources. Expand behind one contract.</h2>
          <p>
            The operating path is proven from external collection through
            Databricks analytics through Snowflake serving. The next source can
            reuse the same controls, checkpoints, event envelope, and delivery
            path.
          </p>
        </div>
        <div className="pilot-actions">
          <a
            className="button button-light"
            href={pipelineRunUrl}
            target="_blank"
            rel="noreferrer"
          >
            View the successful run <span aria-hidden="true">↗</span>
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
          Live YouTube and X collection, governed Databricks analytics, and
          Snowflake BA serving—with an evidence-linked advisor for enterprise AI
          automation and agent architecture.
        </p>
        <a href="#top">Back to top ↑</a>
      </footer>
    </main>
  );
}
