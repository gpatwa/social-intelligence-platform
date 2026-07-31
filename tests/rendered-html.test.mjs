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

test("server-renders the Social Intelligence landing page", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(
    html,
    /<title>Social Intelligence — See the signal before the story<\/title>/i,
  );
  assert.match(html, /See the signal/);
  assert.match(html, /before it becomes the story\./);
  assert.match(html, /<b>943<\/b> replayable events/);
  assert.match(html, /<b>0<\/b> rejected events/);
  assert.match(html, /<b>7<\/b> unified signals/);
  assert.match(html, /Control plane/);
  assert.match(html, /Data plane/);
  assert.match(html, /Experience plane/);
  assert.match(
    html,
    /https:\/\/social-intelligence\.example\/og\.png/,
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
