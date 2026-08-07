/** Cloudflare Worker entry point for the vinext-starter template. */
import { handleImageOptimization, DEFAULT_DEVICE_SIZES, DEFAULT_IMAGE_SIZES } from "vinext/server/image-optimization";
import handler from "vinext/server/app-router-entry";

interface Env {
  ASSETS: Fetcher;
  DB?: D1Database;
  PIPELINE_STATUS_INGEST_KEY?: string;
  IMAGES: {
    input(stream: ReadableStream): {
      transform(options: Record<string, unknown>): {
        output(options: { format: string; quality: number }): Promise<{ response(): Response }>;
      };
    };
  };
}

interface ExecutionContext {
  waitUntil(promise: Promise<unknown>): void;
  passThroughOnException(): void;
}

// Image security config. SVG sources with .svg extension auto-skip the
// optimization endpoint on the client side (served directly, no proxy).
// To route SVGs through the optimizer (with security headers), set
// dangerouslyAllowSVG: true in next.config.js and uncomment below:
// const imageConfig: ImageConfig = { dangerouslyAllowSVG: true };

const worker = {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/api/pipeline-status") {
      if (request.method === "GET") return getPipelineStatus(env);
      if (request.method === "POST") return updatePipelineStatus(request, env);
      return new Response("Method not allowed", { status: 405 });
    }

    if (url.pathname === "/_vinext/image") {
      const allowedWidths = [...DEFAULT_DEVICE_SIZES, ...DEFAULT_IMAGE_SIZES];
      return handleImageOptimization(request, {
        fetchAsset: (path) => env.ASSETS.fetch(new Request(new URL(path, request.url))),
        transformImage: async (body, { width, format, quality }) => {
          const result = await env.IMAGES.input(body).transform(width > 0 ? { width } : {}).output({ format, quality });
          return result.response();
        },
      }, allowedWidths);
    }

    return handler.fetch(request, env, ctx);
  },
};

export default worker;

type StatusPayload = {
  run_id: string;
  source_id: string;
  platform: string;
  runtime: string;
  started_at: string;
  completed_at: string;
  status: "SUCCESS" | "FAILED";
  active_rules: number;
  videos_discovered: number;
  events_emitted: number;
  search_calls_remaining: number;
  core_units_remaining: number;
  error_type?: string;
};

const jsonHeaders = {
  "Cache-Control": "no-store, max-age=0",
  "Content-Type": "application/json; charset=utf-8",
};

async function getPipelineStatus(env: Env) {
  if (!env.DB) {
    return Response.json(emptyStatus("Metrics store is not configured"), {
      headers: jsonHeaders,
      status: 503,
    });
  }

  const row = await env.DB.prepare(
    `SELECT run_id, source_id, platform, runtime, status, operational_status,
            started_at, completed_at, received_at, active_rules,
            videos_discovered, events_emitted, search_calls_remaining,
            core_units_remaining, error_type
       FROM pipeline_status
      WHERE id = 1`,
  ).first<Record<string, string | number>>();

  if (!row) {
    return Response.json(emptyStatus("Awaiting the next Databricks metric heartbeat"), {
      headers: jsonHeaders,
    });
  }

  const ageMinutes = Math.max(
    0,
    Math.floor((Date.now() - Date.parse(String(row.completed_at))) / 60_000),
  );
  const reportedStatus = String(row.operational_status);
  const operationalStatus =
    reportedStatus === "HEALTHY" && ageMinutes > 180 ? "STALE" : reportedStatus;

  return Response.json(
    {
      available: true,
      source: "Databricks · gold_connector_operations",
      runId: row.run_id,
      sourceId: row.source_id,
      platform: row.platform,
      runtime: row.runtime,
      status: row.status,
      operationalStatus,
      startedAt: row.started_at,
      completedAt: row.completed_at,
      receivedAt: row.received_at,
      activeRules: Number(row.active_rules),
      videosDiscovered: Number(row.videos_discovered),
      eventsEmitted: Number(row.events_emitted),
      searchCallsRemaining: Number(row.search_calls_remaining),
      coreUnitsRemaining: Number(row.core_units_remaining),
      errorType: row.error_type,
      runAgeMinutes: ageMinutes,
    },
    { headers: jsonHeaders },
  );
}

async function updatePipelineStatus(request: Request, env: Env) {
  if (!env.DB || !env.PIPELINE_STATUS_INGEST_KEY) {
    return Response.json({ error: "Status ingestion is not configured" }, { status: 503 });
  }

  const authorization = request.headers.get("authorization");
  if (authorization !== `Bearer ${env.PIPELINE_STATUS_INGEST_KEY}`) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "Invalid JSON" }, { status: 400 });
  }
  if (!isStatusPayload(payload)) {
    return Response.json({ error: "Invalid pipeline status payload" }, { status: 422 });
  }

  const receivedAt = new Date().toISOString();
  const operationalStatus = deriveOperationalStatus(payload);
  await env.DB.prepare(
    `INSERT INTO pipeline_status (
       id, run_id, source_id, platform, runtime, status, operational_status,
       started_at, completed_at, received_at, active_rules, videos_discovered,
       events_emitted, search_calls_remaining, core_units_remaining, error_type
     ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(id) DO UPDATE SET
       run_id = excluded.run_id,
       source_id = excluded.source_id,
       platform = excluded.platform,
       runtime = excluded.runtime,
       status = excluded.status,
       operational_status = excluded.operational_status,
       started_at = excluded.started_at,
       completed_at = excluded.completed_at,
       received_at = excluded.received_at,
       active_rules = excluded.active_rules,
       videos_discovered = excluded.videos_discovered,
       events_emitted = excluded.events_emitted,
       search_calls_remaining = excluded.search_calls_remaining,
       core_units_remaining = excluded.core_units_remaining,
       error_type = excluded.error_type`,
  )
    .bind(
      payload.run_id,
      payload.source_id,
      payload.platform,
      payload.runtime,
      payload.status,
      operationalStatus,
      payload.started_at,
      payload.completed_at,
      receivedAt,
      payload.active_rules,
      payload.videos_discovered,
      payload.events_emitted,
      payload.search_calls_remaining,
      payload.core_units_remaining,
      payload.error_type ?? "",
    )
    .run();

  return Response.json({ accepted: true, operationalStatus }, { status: 202 });
}

function emptyStatus(message: string) {
  return {
    available: false,
    source: "Databricks · gold_connector_operations",
    status: "PENDING",
    operationalStatus: "AWAITING_TELEMETRY",
    message,
  };
}

function deriveOperationalStatus(payload: StatusPayload) {
  if (payload.status === "FAILED") return "DEGRADED";
  if (payload.search_calls_remaining <= 5 || payload.core_units_remaining <= 500) {
    return "QUOTA_GUARD";
  }
  return "HEALTHY";
}

function isStatusPayload(value: unknown): value is StatusPayload {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  const strings = [
    "run_id",
    "source_id",
    "platform",
    "runtime",
    "started_at",
    "completed_at",
  ];
  const numbers = [
    "active_rules",
    "videos_discovered",
    "events_emitted",
    "search_calls_remaining",
    "core_units_remaining",
  ];
  return (
    strings.every((key) => typeof item[key] === "string" && item[key] !== "") &&
    numbers.every(
      (key) =>
        typeof item[key] === "number" &&
        Number.isInteger(item[key]) &&
        Number(item[key]) >= 0,
    ) &&
    (item.status === "SUCCESS" || item.status === "FAILED") &&
    Number.isFinite(Date.parse(String(item.started_at))) &&
    Number.isFinite(Date.parse(String(item.completed_at))) &&
    (item.error_type === undefined || typeof item.error_type === "string")
  );
}
