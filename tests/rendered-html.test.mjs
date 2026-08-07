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
    /<title>Social Intelligence — YouTube signals to Databricks decisions<\/title>/i,
  );
  assert.match(html, /See the signal/);
  assert.match(html, /before it becomes the story\./);
  assert.match(html, /<b>12<\/b> real events landed/);
  assert.match(html, /<b>0<\/b> rejected events/);
  assert.match(html, /<b>37<\/b> automated tests/);
  assert.match(html, /Discovery data is live/);
  assert.match(html, /Pipeline status, without the guesswork/);
  assert.match(html, /Databricks · gold_connector_operations/);
  assert.match(html, /Google quota/);
  assert.match(html, /Control plane/);
  assert.match(html, /Data plane/);
  assert.match(html, /Experience plane/);
  assert.match(
    html,
    /https:\/\/social-intelligence\.example\/og-live\.png/,
  );
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
