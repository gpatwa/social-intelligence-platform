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
    title: "Connector-ready",
    copy: "Add Instagram, X, Reddit, or approved providers behind one versioned, tenant-aware event contract.",
    metric: "v1",
    label: "canonical event contract",
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
            Live MVP · YouTube → Databricks
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
            Live YouTube discovery is running now. Databricks may require
            workspace access.
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
                <span>Source · YouTube Data API v3</span>
                <strong>Discovery live</strong>
              </div>
              <h2>Social events are landing.</h2>
              <p>
                GitHub Actions collects public YouTube results. Databricks
                validates, deduplicates, scores, and serves the analytics layer.
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
              YouTube source live
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
          <span>
            <b>37</b> automated tests
          </span>
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
          Titles, descriptions, channels, and publish times are flowing now.
          Engagement counters stay at zero when Google blocks statistics
          enrichment under the project&apos;s current quota.
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
              <li>Additional approved social connectors</li>
              <li>Service identity and managed secrets</li>
              <li>Provider deletion and retention workflows</li>
              <li>Production storage, reconciliation, and DR</li>
            </ul>
          </article>
        </div>
      </section>

      <section className="pilot-section" id="pilot">
        <div>
          <p className="section-kicker">The first source is live</p>
          <h2>Start with YouTube. Expand behind one contract.</h2>
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
          Live YouTube discovery on Databricks Free Edition. Engagement counts
          remain in degraded mode until Google enables generic query quota.
        </p>
        <a href="#top">Back to top ↑</a>
      </footer>
    </main>
  );
}
