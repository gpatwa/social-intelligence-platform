# Deploying the product site to your own Cloudflare account

The site is a vinext (Next-compatible) app built as a Cloudflare Worker with a
D1 database. Today it is hosted by OpenAI Sites. This folder lets you host it on
a Cloudflare account you own instead. Nothing here runs automatically.

| File | Purpose |
| --- | --- |
| `wrangler.jsonc` | Deploy config: Worker, static assets, Images, D1 `DB`, migrations |
| `../../.github/workflows/site-deploy-cloudflare.yml` | Manual build, validate and deploy |

## One-time setup (you do these; they change your Cloudflare account)

1. **Create or choose a Cloudflare account** and note its Account ID
   (dashboard, right sidebar of Workers & Pages).
2. **Create the D1 database** and note the `database_id` it prints:
   ```bash
   npx wrangler login
   npx wrangler d1 create social-intelligence-landing
   ```
3. **Create an API token** (My Profile, API Tokens, custom token) with only:
   Account / Workers Scripts / Edit, Account / D1 / Edit. Add
   Account / Workers Routes / Edit only if you use a custom domain.
   Set an expiry.
4. **Create a GitHub environment** named `cloudflare-production` (add required
   reviewers if you want a manual gate) and set:

   | Kind | Name | Value |
   | --- | --- | --- |
   | Secret | `CLOUDFLARE_API_TOKEN` | the token from step 3 |
   | Secret | `PIPELINE_STATUS_INGEST_KEY` | the same value the collectors already use |
   | Variable | `CLOUDFLARE_ACCOUNT_ID` | from step 1 |
   | Variable | `CLOUDFLARE_D1_DATABASE_ID` | from step 2 (not secret) |
   | Variable | `SITE_URL` | optional; enables the post-deploy smoke test |

   Never put the token in the repo, a workflow file, or chat.

## Deploy

1. Run the **Site deploy (Cloudflare)** workflow with `dry_run` left on. It
   lints, builds, runs the rendered-HTML tests and validates the Worker bundle
   without credentials.
2. Run it again with `dry_run` off. It applies D1 migrations, deploys, syncs the
   ingest key secret, and, if `SITE_URL` is set, checks the live page.
3. First deploy gives you `https://social-intelligence-landing.<subdomain>.workers.dev`.
   Set `SITE_URL` to it for later runs.

## After the move

- **Collectors:** update the repo variable `PIPELINE_STATUS_URL` to
  `<site>/api/pipeline-status`. Until then, status heartbeats keep going to the
  OpenAI Sites copy.
- **Old site:** the `chatgpt.site` URL stops matching `main` once you stop
  publishing there. Update any links you have shared.
- **D1 data:** the new database starts empty. `pipeline_status` refills on the
  next collector run; nothing else is stored in it.

## Local checks (no account needed)

```bash
npm run build
npx wrangler deploy --dry-run --outdir /tmp/wrangler-out --config deploy/cloudflare/wrangler.jsonc
```

## Known caveats

- The `IMAGES` binding powers `/_vinext/image`. Images transformations have a
  free monthly allowance; check current Cloudflare limits for your plan.
- The deploy config is hand-written. If a `vinext` upgrade changes the build
  output shape (`dist/server`, `dist/client`), re-run the dry run and compare with
  the generated `dist/server/wrangler.json`.
- Deploy has not been run end to end against a real account. Only the offline
  dry run and the workflow's YAML structure were checked.
