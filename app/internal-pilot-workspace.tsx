"use client";

import { useMemo, useState } from "react";

type Workflow =
  | "lead_response"
  | "document_processing"
  | "follow_up"
  | "crm_reactivation"
  | "internal_reporting";
type View = "evidence" | "workflow" | "plan" | "scorecard";

const workflowLabels: Record<Workflow, string> = {
  lead_response: "Lead response and qualification",
  document_processing: "Document processing",
  follow_up: "Context-aware follow-up",
  crm_reactivation: "CRM reactivation",
  internal_reporting: "Internal reporting",
};

const workflows: Record<Workflow, Array<{ name: string; mode: string; gate: string }>> = {
  lead_response: [
    { name: "Receive and deduplicate lead", mode: "Code", gate: "Read only" },
    { name: "Enrich approved account fields", mode: "Workflow", gate: "Scoped API" },
    { name: "Classify intent and urgency", mode: "AI judgment", gate: "Evaluated" },
    { name: "Draft a compliant response", mode: "AI generation", gate: "Draft only" },
    { name: "Approve sensitive language", mode: "Human", gate: "Required" },
    { name: "Record outcome and learning", mode: "Workflow", gate: "Internal write" },
  ],
  document_processing: [
    { name: "Receive and fingerprint document", mode: "Code", gate: "Internal write" },
    { name: "Extract structured fields", mode: "AI extraction", gate: "Evaluated" },
    { name: "Validate types and rules", mode: "Code", gate: "Deterministic" },
    { name: "Route ambiguous exceptions", mode: "AI judgment", gate: "Recommend" },
    { name: "Approve material exceptions", mode: "Human", gate: "Required" },
    { name: "Write record and lineage", mode: "Workflow", gate: "Internal write" },
  ],
  follow_up: [
    { name: "Read approved contact context", mode: "Workflow", gate: "Read only" },
    { name: "Select an approved next action", mode: "AI judgment", gate: "Recommend" },
    { name: "Draft the channel message", mode: "AI generation", gate: "Draft only" },
    { name: "Check consent and cadence", mode: "Code", gate: "Deterministic" },
    { name: "Approve communication", mode: "Human", gate: "Required" },
    { name: "Record response", mode: "Workflow", gate: "Internal write" },
  ],
  crm_reactivation: [
    { name: "Select eligible dormant records", mode: "Code", gate: "Read only" },
    { name: "Score reactivation potential", mode: "AI judgment", gate: "Recommend" },
    { name: "Assign control and treatment", mode: "Code", gate: "Deterministic" },
    { name: "Draft message variants", mode: "AI generation", gate: "Draft only" },
    { name: "Approve campaign batch", mode: "Human", gate: "Required" },
    { name: "Measure incremental pipeline", mode: "Workflow", gate: "Read only" },
  ],
  internal_reporting: [
    { name: "Read governed metric tables", mode: "Workflow", gate: "Read only" },
    { name: "Compute deterministic measures", mode: "Code", gate: "Deterministic" },
    { name: "Detect material exceptions", mode: "Code", gate: "Recommend" },
    { name: "Draft grounded explanation", mode: "AI generation", gate: "Draft only" },
    { name: "Verify citations and claims", mode: "Human", gate: "Required" },
    { name: "Publish internal report", mode: "Workflow", gate: "Internal write" },
  ],
};

const evidence = [
  {
    rank: 1,
    score: 91,
    platform: "YouTube",
    title: "Build, sell, deploy, and retain AI agent clients",
    source: "Andrew Warner with Nick Vasilescu",
    reason: "Strong decision relevance · concrete delivery model · outcome review",
    href: "https://www.youtube.com/watch?v=FIhj0yb9KPI",
  },
  {
    rank: 2,
    score: 86,
    platform: "YouTube",
    title: "The five most valuable AI automations to sell in 2026",
    source: "Reference supplied for the pilot",
    reason: "High workflow relevance · commercial use-case evidence · recent",
    href: "https://www.youtube.com/watch?v=tgjYMym_0-c",
  },
  {
    rank: 3,
    score: 82,
    platform: "Build evidence",
    title: "Managed authentication and tool execution for agents",
    source: "Composio documentation",
    reason: "Official technical evidence · integration fit · scoped authentication",
    href: "https://docs.composio.dev/docs/how-composio-works",
  },
];

const sevenDays = [
  ["01", "Baseline", "Confirm owner, workflow, evidence, baseline, and exclusions."],
  ["02", "Contracts", "Type inputs, outputs, identities, and action policy."],
  ["03", "Golden path", "Run one deterministic path on synthetic fixtures."],
  ["04", "AI boundary", "Pass grounding, quality, and refusal tests."],
  ["05", "Exceptions", "Verify retries, deduplication, approvals, and kill switch."],
  ["06", "Shadow run", "Operate without external side effects; collect scorecard data."],
  ["07", "Outcome review", "Choose GO, ITERATE, or STOP from agreed thresholds."],
];

function Field({
  label,
  value,
  onChange,
  suffix,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  suffix?: string;
}) {
  return (
    <label>
      <span>{label}</span>
      <div className="pilot-number-field">
        <input
          type="number"
          min="0"
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
        />
        {suffix ? <i>{suffix}</i> : null}
      </div>
    </label>
  );
}

export function InternalPilotWorkspace() {
  const [workflow, setWorkflow] = useState<Workflow>("lead_response");
  const [weeklyVolume, setWeeklyVolume] = useState(100);
  const [minutes, setMinutes] = useState(20);
  const [hourlyCost, setHourlyCost] = useState(60);
  const [baseline, setBaseline] = useState(12);
  const [target, setTarget] = useState(18);
  const [view, setView] = useState<View>("evidence");
  const [generated, setGenerated] = useState(false);

  const economics = useMemo(() => {
    const monthlyCases = Math.max(0, weeklyVolume) * 4.33;
    const monthlyHours = (monthlyCases * Math.max(0, minutes)) / 60;
    const monthlyCost = monthlyHours * Math.max(0, hourlyCost);
    return {
      monthlyCases: Math.round(monthlyCases),
      monthlyHours: Math.round(monthlyHours),
      hoursSaved: Math.round(monthlyHours * 0.35),
      capacityValue: Math.round(monthlyCost * 0.35),
      gain: Math.max(0, target - baseline),
    };
  }, [weeklyVolume, minutes, hourlyCost, baseline, target]);

  return (
    <section className="section pilot-workspace-section" id="workspace">
      <div className="pilot-workspace-heading">
        <p className="section-kicker">Internal Pilot Workspace</p>
        <h2>From ranked evidence to a seven-day decision.</h2>
        <p>
          Scope one workflow, inspect the source evidence, draw the automation
          boundary, and agree on the outcome before anything can act.
        </p>
      </div>

      <div className="pilot-workspace">
        <form className="pilot-discovery" onSubmit={(event) => { event.preventDefault(); setGenerated(true); }}>
          <div className="pilot-panel-title">
            <span>01 · Discovery lite</span>
            <strong>One owner. One outcome. One measurable workflow.</strong>
          </div>
          <label>
            <span>Workflow</span>
            <select value={workflow} onChange={(event) => setWorkflow(event.target.value as Workflow)}>
              {Object.entries(workflowLabels).map(([value, label]) => (
                <option value={value} key={value}>{label}</option>
              ))}
            </select>
          </label>
          <Field label="Cases per week" value={weeklyVolume} onChange={setWeeklyVolume} />
          <Field label="Minutes per case" value={minutes} onChange={setMinutes} suffix="min" />
          <Field label="Loaded hourly cost" value={hourlyCost} onChange={setHourlyCost} suffix="USD" />
          <div className="pilot-split-fields">
            <Field label="Baseline success" value={baseline} onChange={setBaseline} suffix="%" />
            <Field label="Target success" value={target} onChange={setTarget} suffix="%" />
          </div>
          <button className="button pilot-generate" type="submit">
            Create seven-day staging plan <span aria-hidden="true">→</span>
          </button>
          <p>Synthetic or non-sensitive data · Draft and recommend only</p>
        </form>

        <div className="pilot-output">
          <div className="pilot-output-top">
            <div>
              <span>02 · Pilot artifact</span>
              <strong>{generated ? "Plan generated" : "Live working model"}</strong>
            </div>
            <div className="pilot-mode"><i /> Internal staging</div>
          </div>

          <div className="pilot-economics" aria-label="Pilot baseline estimate">
            <div><span>Monthly cases</span><strong>{economics.monthlyCases.toLocaleString()}</strong></div>
            <div><span>Baseline hours</span><strong>{economics.monthlyHours.toLocaleString()}</strong></div>
            <div><span>Capacity available</span><strong>{economics.hoursSaved.toLocaleString()}h</strong></div>
            <div><span>Estimated value</span><strong>${economics.capacityValue.toLocaleString()}</strong></div>
          </div>
          <p className="pilot-assumption">Capacity value is an estimate, not booked revenue. Social evidence supports prioritization, not causation.</p>

          <div className="pilot-tabs" role="tablist" aria-label="Pilot artifact views">
            {(["evidence", "workflow", "plan", "scorecard"] as View[]).map((item) => (
              <button
                type="button"
                role="tab"
                aria-selected={view === item}
                className={view === item ? "active" : ""}
                onClick={() => setView(item)}
                key={item}
              >
                {item === "plan" ? "7-day plan" : item}
              </button>
            ))}
          </div>

          <div className="pilot-tab-panel" role="tabpanel" aria-live="polite">
            {view === "evidence" ? (
              <div className="ranked-evidence-list">
                {evidence.map((item) => (
                  <article key={item.rank}>
                    <div className="evidence-rank"><b>{item.rank}</b><span>{item.score}</span></div>
                    <div>
                      <span>{item.platform} · {item.source}</span>
                      <h3>{item.title}</h3>
                      <p>{item.reason}</p>
                    </div>
                    <a href={item.href} target="_blank" rel="noreferrer" aria-label={`Open source: ${item.title}`}>
                      Open source ↗
                    </a>
                  </article>
                ))}
                <p className="evidence-live-note"><i /> X posts populate from the next governed connector snapshot; no sample post is fabricated.</p>
              </div>
            ) : null}

            {view === "workflow" ? (
              <div className="pilot-workflow-list">
                {workflows[workflow].map((step, index) => (
                  <article key={step.name}>
                    <b>{String(index + 1).padStart(2, "0")}</b>
                    <div><strong>{step.name}</strong><span>{step.mode}</span></div>
                    <em>{step.gate}</em>
                  </article>
                ))}
              </div>
            ) : null}

            {view === "plan" ? (
              <div className="seven-day-list">
                {sevenDays.map(([day, focus, exit]) => (
                  <article key={day}><b>{day}</b><strong>{focus}</strong><p>{exit}</p></article>
                ))}
              </div>
            ) : null}

            {view === "scorecard" ? (
              <div className="pilot-scorecard">
                <div className="scorecard-primary">
                  <span>Primary outcome</span>
                  <strong>{baseline}% → {target}%</strong>
                  <p>{economics.gain} point target improvement in success rate.</p>
                </div>
                <ul>
                  <li><span>Cycle time</span><strong>−35%</strong></li>
                  <li><span>Evidence coverage</span><strong>100%</strong></li>
                  <li><span>Unauthorized actions</span><strong>0</strong></li>
                  <li><span>Decision</span><strong>GO · ITERATE · STOP</strong></li>
                </ul>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="pilot-guardrails">
        <span>Staging boundary</span>
        <strong>Read only by default</strong>
        <strong>Human approval before external action</strong>
        <strong>Quota + spend caps</strong>
        <strong>Kill switch + immutable log</strong>
      </div>
    </section>
  );
}
