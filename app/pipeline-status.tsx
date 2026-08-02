"use client";

import { useEffect, useMemo, useState } from "react";

type PipelineStatus = {
  available: boolean;
  source: string;
  runId?: string;
  status: string;
  operationalStatus: string;
  completedAt?: string;
  activeRules?: number;
  videosDiscovered?: number;
  eventsEmitted?: number;
  searchCallsRemaining?: number;
  coreUnitsRemaining?: number;
  runAgeMinutes?: number;
  message?: string;
};

const initialStatus: PipelineStatus = {
  available: false,
  source: "Databricks · gold_connector_operations",
  status: "PENDING",
  operationalStatus: "LOADING",
  message: "Connecting to the latest governed metric…",
};

export function PipelineStatusPanel({ dashboardUrl }: { dashboardUrl: string }) {
  const [snapshot, setSnapshot] = useState<PipelineStatus>(initialStatus);
  const [refreshing, setRefreshing] = useState(true);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const response = await fetch("/api/pipeline-status", { cache: "no-store" });
        const value = (await response.json()) as PipelineStatus;
        if (active) setSnapshot(value);
      } catch {
        if (active) {
          setSnapshot({
            ...initialStatus,
            operationalStatus: "UNAVAILABLE",
            message: "The public status projection is temporarily unavailable.",
          });
        }
      } finally {
        if (active) setRefreshing(false);
      }
    };
    void load();
    const interval = window.setInterval(load, 60_000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  const tone = useMemo(() => {
    if (snapshot.operationalStatus === "HEALTHY") return "healthy";
    if (snapshot.operationalStatus === "LOADING") return "loading";
    if (snapshot.operationalStatus === "STALE") return "stale";
    return "degraded";
  }, [snapshot.operationalStatus]);

  const completedLabel = snapshot.completedAt
    ? new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZoneName: "short",
      }).format(new Date(snapshot.completedAt))
    : "Waiting for first heartbeat";

  const statusLabel = snapshot.operationalStatus.replaceAll("_", " ");

  return (
    <section className="pipeline-status-section" id="status" aria-live="polite">
      <div className="pipeline-status-heading">
        <div>
          <p className="section-kicker">Live operations</p>
          <h2>Pipeline status, without the guesswork.</h2>
        </div>
        <div className={`status-badge ${tone}`}>
          <span aria-hidden="true" />
          {refreshing ? "Refreshing" : statusLabel}
        </div>
      </div>

      <div className="status-command-center">
        <div className="status-summary">
          <span className="status-source">{snapshot.source}</span>
          <strong>{snapshot.available ? "Latest run received" : "Telemetry connection pending"}</strong>
          <p>
            {snapshot.available
              ? `Completed ${completedLabel}. The public projection refreshes every minute.`
              : snapshot.message}
          </p>
          <a href={dashboardUrl} target="_blank" rel="noreferrer">
            Open governed metrics <span aria-hidden="true">↗</span>
          </a>
        </div>

        <div className="status-metric-grid">
          <article>
            <span>Events emitted</span>
            <strong>{formatMetric(snapshot.eventsEmitted)}</strong>
            <small>latest collection run</small>
          </article>
          <article>
            <span>Videos discovered</span>
            <strong>{formatMetric(snapshot.videosDiscovered)}</strong>
            <small>public source objects</small>
          </article>
          <article>
            <span>Search headroom</span>
            <strong>{formatMetric(snapshot.searchCallsRemaining)}</strong>
            <small>calls remaining today</small>
          </article>
          <article>
            <span>Core headroom</span>
            <strong>{formatMetric(snapshot.coreUnitsRemaining)}</strong>
            <small>quota units remaining</small>
          </article>
        </div>
      </div>

      <div className="status-flow" aria-label="Pipeline stage health">
        <StatusStage label="Collect" detail="YouTube API" state={snapshot.status} />
        <i aria-hidden="true">→</i>
        <StatusStage label="Land" detail="Databricks volume" state={snapshot.available ? "SUCCESS" : "PENDING"} />
        <i aria-hidden="true">→</i>
        <StatusStage label="Measure" detail="Gold operations" state={snapshot.operationalStatus} />
        <i aria-hidden="true">→</i>
        <StatusStage label="Publish" detail="Safe status view" state={snapshot.available ? "SUCCESS" : "PENDING"} />
      </div>
    </section>
  );
}

function StatusStage({ label, detail, state }: { label: string; detail: string; state: string }) {
  const isGood = state === "SUCCESS" || state === "HEALTHY";
  return (
    <div className="status-stage">
      <span className={isGood ? "stage-dot good" : "stage-dot"} aria-hidden="true" />
      <div>
        <strong>{label}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function formatMetric(value?: number) {
  return typeof value === "number" ? value.toLocaleString("en-US") : "—";
}
