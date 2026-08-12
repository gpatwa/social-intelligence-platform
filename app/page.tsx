import { PipelineStatusPanel } from "./pipeline-status";

const dashboardUrl =
  "https://dbc-b8672746-8e43.cloud.databricks.com/dashboardsv3/01f17ce244971d80b97f3c0aa6b033ef/published?o=7474657828954669";
const githubUrl = "https://github.com/gpatwa/social-intelligence-platform";
const pipelineRunUrl =
  "https://github.com/gpatwa/social-intelligence-platform/actions/runs/30737199706";

const capabilities = [
  {
    index: "01",
    title: "Emerging trends",
    copy: "Track topics and creators as they accelerate, with every signal linked back to replayable source evidence.",
    metric: "Hourly",
    label: "scheduled discovery",
  },
  {
    index: "02",
    title: "Challenge intelligence",
    copy: "Measure participation growth, creator diversity, geographic spread, and persistence—not just hashtag volume.",
    metric: "12",
    label: "live events validated",
  },
  {
    index: "03",
    title: "Operational trust",
    copy: "Monitor collection, checkpoints, quota use, rejected records, and enrichment health alongside the insight.",
    metric: "5 / 5",
    label: "pipeline stages passing",
  },
  {
    index: "04",
    title: "Multi-source by design",
    copy: "Each approved provider lands behind the same versioned, tenant-aware contract—without coupling analytics to a single social API.",
    metric: "4",
    label: "connector paths defined",
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
          <a href="#product">Product</a>
          <a href="#architecture">Architecture</a>
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
            Live MVP · Social signals → Databricks
          </div>
          <h1>
            See the signal
            <span>before it becomes the story.</span>
          </h1>
          <p className="hero-lede">
            A governed social intelligence platform that collects real social
            signals, preserves the evidence, and turns momentum into measurable
            trends, challenges, and brand intelligence.
          </p>
          <div className="hero-actions">
            <a
              className="button button-primary"
              href={dashboardUrl}
              target="_blank"
              rel="noreferrer"
            >
              Open the analytics workspace <span aria-hidden="true">↗</span>
            </a>
            <a
              className="button button-secondary"
              href={githubUrl}
              target="_blank"
              rel="noreferrer"
            >
              Inspect the platform
            </a>
          </div>
          <p className="access-note">
            YouTube and X collection are live. Databricks may require workspace
            access.
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
                <span>Sources · YouTube + X</span>
                <strong>Collection live</strong>
              </div>
              <h2>Social events are landing.</h2>
              <p>
                Approved provider APIs collect public signals. Databricks
                validates, deduplicates, scores, and serves one analytics layer.
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
                <span>Collect · :17</span>
                <span>Process · :47</span>
              </div>
            </div>
            <div className="score-stack">
              <article className="score-card accent-green">
                <span>Events landed</span>
                <strong>12</strong>
                <small>real source data</small>
              </article>
              <article className="score-card accent-coral">
                <span>Workflow health</span>
                <strong>5/5</strong>
                <small>stages passing</small>
              </article>
            </div>
          </div>
          <div className="console-footer">
            <div>
              <span className="health-dot" />
              Two source paths live
            </div>
            <div>Hourly schedule</div>
            <div>0 rejected</div>
          </div>
        </div>
      </section>

      <section className="proof-strip" aria-label="Validated MVP metrics">
        <p>Latest live validation</p>
        <div className="proof-metrics">
          <span>
            <b>12</b> real events landed
          </span>
          <span>
            <b>0</b> rejected events
          </span>
          <span><b>51</b> automated tests</span>
          <span>
            <b>5/5</b> Databricks stages passing
          </span>
        </div>
      </section>

      <aside className="operational-note" aria-label="Live data status">
        <div>
          <span className="health-dot" />
          <strong>Discovery data is live</strong>
        </div>
        <p>
          YouTube and X source records are flowing now. Google engagement
          enrichment remains degraded until its generic-query quota is enabled.
        </p>
        <a href="#readiness">See the production gates ↓</a>
      </aside>

      <PipelineStatusPanel dashboardUrl={dashboardUrl} />

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
            </ul>
          </article>
          <article className="readiness-card path">
            <div className="readiness-title">
              <span>Production path</span>
              <b>Next gates</b>
            </div>
            <ul>
              <li>Google quota for engagement enrichment</li>
          <li>Meta authorization and Reddit API approval</li>
              <li>Service identity and managed secrets</li>
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
            Databricks analytics. The next source can reuse the same controls,
            checkpoints, and event envelope.
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
          <a className="text-link" href={githubUrl} target="_blank" rel="noreferrer">
            Explore the public repository <span aria-hidden="true">↗</span>
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
          Live YouTube and X collection on Databricks Free Edition. Instagram is
          authorization-ready; Reddit remains approval-pending.
        </p>
        <a href="#top">Back to top ↑</a>
      </footer>
    </main>
  );
}
