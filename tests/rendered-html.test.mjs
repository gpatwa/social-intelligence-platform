import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

async function listDirectoryIfPresent(url) {
  try {
    return await readdir(url);
  } catch (error) {
    if (error && typeof error === "object" && error.code === "ENOENT") {
      return [];
    }
    throw error;
  }
}

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("https://social-intelligence.example/", {
      headers: {
        accept: "text/html",
        host: "social-intelligence.example",
        "x-forwarded-host": "social-intelligence.example",
        "x-forwarded-proto": "https",
      },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

async function loadWorker() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}-api`);
  return (await import(workerUrl.href)).default;
}

test("server-renders the Social Intelligence landing page", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(
    html,
    /<title>Social Intelligence — Enterprise AI Builder Intelligence<\/title>/i,
  );
  assert.match(html, /Find the signal\./);
  assert.match(html, /Shape what(?:’|&#x27;)s next\./);
  // The hero shows real, dated evidence and says what has not happened yet.
  assert.match(html, /Recent evidence, grouped by pilot topic\./);
  assert.match(html, /Static snapshot/);
  assert.match(html, /7 Nov 2026/);
  assert.match(html, /none approved yet/);
  assert.match(html, /first review pending/);
  assert.match(html, /53% primary accuracy on 60 held-out posts/);
  assert.match(html, /https:\/\/x\.com\/i\/web\/status\/2118559322745581582/);
  assert.match(html, /https:\/\/www\.youtube\.com\/watch\?v=_Pv_Y078vd8/);
  assert.match(html, /Staging pilot/);
  assert.match(html, /Pipeline status, without the guesswork/);
  assert.match(html, /Databricks · gold_connector_operations/);
  assert.match(html, /Google quota/);
  assert.match(html, /Control plane/);
  assert.match(html, /Data plane/);
  assert.match(html, /Experience plane/);
  assert.match(html, /From “what is trending\?” to “what should we fund next\?”/);
  assert.match(html, /Opportunity/);
  assert.match(html, /Recommendation/);
  assert.match(html, /Experiment/);
  assert.match(html, /Campaign intelligence/);
  assert.match(html, /Databricks governs the decision\. Snowflake makes it measurable\./);
  assert.match(html, /Open BA query pack/);
  assert.match(html, /Agent Stack Advisor/);
  assert.match(html, /Start with the outcome\. Earn the autonomy\./);
  assert.match(html, /Deterministic document workflow/);
  assert.match(html, /No provisioning\. No credentials\. No automatic spend\./);
  assert.match(html, /Internal Pilot Workspace/);
  assert.match(html, /From ranked evidence to a seven-day decision\./);
  assert.match(html, /Open source/);
  assert.match(html, /no sample post is fabricated/);
  assert.match(
    html,
    /https:\/\/social-intelligence\.example\/og-agent-stack\.png/,
  );
});

test("makes no typed claim about live state, fixed metrics or the internal workspace", async () => {
  const response = await render();
  const html = await response.text();
  // Status words come from the computed status panel, never from page copy.
  for (const claim of [
    /Operational/,
    /Discovery and serving are live/,
    /collection are live/,
    /Live YouTube/,
    /<b>22<\/b>/,
    /<b>111<\/b>/,
    /<b>100%<\/b>/,
    /Latest verified delivery/,
    /View the successful run/,
    /Open the analytics workspace/,
    /Open governed metrics/,
  ]) {
    assert.doesNotMatch(html, claim, String(claim));
  }
  assert.doesNotMatch(html, /Pilot-ready<\/div>/); // the hero eyebrow says "Staging pilot"
  // No internal Databricks workspace host, dashboard id or old CI run link on a public page.
  assert.doesNotMatch(html, /cloud\.databricks\.com/);
  assert.doesNotMatch(html, /dashboardsv3/);
  assert.doesNotMatch(html, /actions\/runs\/\d+/);
  // The status panel is not one big live region; only its summary is announced.
  assert.doesNotMatch(html, /<section[^>]*id="status"[^>]*aria-live/);
  assert.match(html, /role="status"/);
});

test("removes the disposable starter preview", async () => {
  const [page, layout, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.doesNotMatch(page, /SkeletonPreview|codex-preview/);
  assert.doesNotMatch(layout, /Starter Project|codex-preview|_sites-preview/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
  assert.deepEqual(
    await listDirectoryIfPresent(
      new URL("../app/_sites-preview", import.meta.url),
    ),
    [],
  );
});

test("fails closed when the public metrics store is unavailable", async () => {
  const worker = await loadWorker();
  const response = await worker.fetch(
    new Request("https://social-intelligence.example/api/pipeline-status"),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );

  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), {
    available: false,
    source: "Databricks · gold_connector_operations",
    status: "PENDING",
    operationalStatus: "AWAITING_TELEMETRY",
    message: "Metrics store is not configured",
  });
});

test("fails closed when the metrics table is not initialized", async () => {
  const worker = await loadWorker();
  const response = await worker.fetch(
    new Request("https://social-intelligence.example/api/pipeline-status"),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
      DB: {
        prepare() {
          return {
            async first() {
              throw new Error("no such table: pipeline_status");
            },
          };
        },
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );

  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), {
    available: false,
    source: "Databricks · gold_connector_operations",
    status: "PENDING",
    operationalStatus: "AWAITING_TELEMETRY",
    message: "Metrics store schema is not initialized",
  });
});
