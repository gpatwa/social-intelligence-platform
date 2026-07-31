const dashboardUrl =
  "https://dbc-b8672746-8e43.cloud.databricks.com/dashboardsv3/01f17ce244971d80b97f3c0aa6b033ef/published?o=7474657828954669";

const capabilities = [
  {
    index: "01",
    title: "Emerging trends",
    copy: "Spot topics accelerating beyond their normal baseline—with velocity, breadth, and supporting evidence.",
    metric: "52.54",
    label: "top trend score",
  },
  {
    index: "02",
    title: "Challenge intelligence",
    copy: "Measure participation growth, creator diversity, geographic spread, and persistence—not just hashtag volume.",
    metric: "56.64",
    label: "challenge score",
  },
  {
    index: "03",
    title: "Brand risk",
    copy: "Surface negative conversation and high-risk mentions early enough for communications and support teams to act.",
    metric: "89.41",
    label: "risk signal",
  },
  {
    index: "04",
    title: "Source health",
    copy: "Know whether the signal can be trusted with freshness, rejection, duplication, and delivery health built in.",
    metric: "3 / 3",
    label: "sources healthy",
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
          <a href="#readiness">Readiness</a>
        </nav>
        <a className="nav-cta" href="#pilot">
          Explore the pilot <span aria-hidden="true">↗</span>
        </a>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <div className="eyebrow">
            <span className="live-dot" />
            Working MVP · Databricks-powered
          </div>
          <h1>
            See the signal
            <span>before it becomes the story.</span>
          </h1>
          <p className="hero-lede">
            A governed social intelligence platform for detecting emerging
            trends, participation challenges, and brand risk—before raw
            conversation turns into business impact.
          </p>
          <div className="hero-actions">
            <a
              className="button button-primary"
              href={dashboardUrl}
              target="_blank"
              rel="noreferrer"
            >
              Open the live dashboard <span aria-hidden="true">↗</span>
            </a>
            <a className="button button-secondary" href="#architecture">
              See how it works
            </a>
          </div>
          <p className="access-note">
            The working demo opens in Databricks and may require workspace
            access.
          </p>
        </div>

        <div className="signal-console" aria-label="Product signal preview">
          <div className="console-topbar">
            <span>Signal feed / current window</span>
            <span className="console-live">Live model</span>
          </div>
          <div className="console-main">
            <div className="console-feature">
              <div className="feature-label">
                <span>Emerging signal</span>
                <strong>High confidence</strong>
              </div>
              <h2>Glow up challenge</h2>
              <p>
                Creator participation is accelerating across three monitored
                sources.
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
                <span>−24h</span>
                <span>Now</span>
              </div>
            </div>
            <div className="score-stack">
              <article className="score-card accent-green">
                <span>Trend score</span>
                <strong>52.54</strong>
                <small>↑ accelerating</small>
              </article>
              <article className="score-card accent-coral">
                <span>Brand risk</span>
                <strong>89.41</strong>
                <small>critical signal</small>
              </article>
            </div>
          </div>
          <div className="console-footer">
            <div>
              <span className="health-dot" />
              3 sources healthy
            </div>
            <div>943 canonical events</div>
            <div>0 rejected</div>
          </div>
        </div>
      </section>

      <section className="proof-strip" aria-label="Validated MVP metrics">
        <p>Validated in the working MVP</p>
        <div className="proof-metrics">
          <span>
            <b>943</b> replayable events
          </span>
          <span>
            <b>0</b> rejected events
          </span>
          <span>
            <b>7</b> unified signals
          </span>
          <span>
            <b>5/5</b> workflow stages passing
          </span>
        </div>
      </section>

      <section className="section product-section" id="product">
        <div className="section-heading">
          <p className="section-kicker">Product intelligence</p>
          <h2>From noisy conversation to an explainable signal.</h2>
          <p>
            The product scores what is changing, why it matters, and whether the
            underlying data is healthy enough to trust.
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
              <li>Brand-risk monitoring</li>
              <li>Explainable scoring and evidence</li>
              <li>Source-health and quality metrics</li>
              <li>Tenant-scoped dashboards and alerts</li>
            </ul>
          </article>
          <article className="readiness-card path">
            <div className="readiness-title">
              <span>Production path</span>
              <b>Next gates</b>
            </div>
            <ul>
              <li>Approved real-source connector</li>
              <li>Paid cloud workspace and object storage</li>
              <li>Application identity and secured API</li>
              <li>Provider deletion and retention workflows</li>
              <li>Reconciliation, incident response, and DR</li>
            </ul>
          </article>
        </div>
      </section>

      <section className="pilot-section" id="pilot">
        <div>
          <p className="section-kicker">Start with one signal</p>
          <h2>Prove value with one approved source and one real decision.</h2>
          <p>
            A focused pilot connects a defined source, calibrates signal quality,
            and measures whether the insight changed an outcome.
          </p>
        </div>
        <div className="pilot-actions">
          <a
            className="button button-light"
            href={dashboardUrl}
            target="_blank"
            rel="noreferrer"
          >
            Explore the working demo <span aria-hidden="true">↗</span>
          </a>
          <a className="text-link" href="#readiness">
            Review rollout gates <span aria-hidden="true">↓</span>
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
          Working MVP on Databricks. Current metrics use deterministic
          demonstration data.
        </p>
        <a href="#top">Back to top ↑</a>
      </footer>
    </main>
  );
}
