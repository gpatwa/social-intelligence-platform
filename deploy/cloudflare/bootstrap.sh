#!/usr/bin/env bash
# One-time Cloudflare setup for a GitHub repo that deploys a Worker with D1.
#
# Creates (or reuses) the D1 database, creates the GitHub environment, and sets
# CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_D1_DATABASE_ID and CLOUDFLARE_API_TOKEN on
# it. The token is read from your shell and passed straight to `gh`; it is never
# printed, written to a file or put on a command line.
#
# Needs in your shell: CLOUDFLARE_API_TOKEN (Workers Scripts: Edit, D1: Edit)
# and CLOUDFLARE_ACCOUNT_ID (not secret). Reusable for any repo:
#
#   deploy/cloudflare/bootstrap.sh --dry-run
#   deploy/cloudflare/bootstrap.sh --repo owner/name --db my-db --env cloudflare-production
set -euo pipefail

repo=""
db="social-intelligence-landing"
environment="cloudflare-production"
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) repo="$2"; shift 2 ;;
    --db) db="$2"; shift 2 ;;
    --env) environment="$2"; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

: "${CLOUDFLARE_API_TOKEN:?Set CLOUDFLARE_API_TOKEN in your shell first}"
: "${CLOUDFLARE_ACCOUNT_ID:?Set CLOUDFLARE_ACCOUNT_ID in your shell first}"
if [[ ! "$CLOUDFLARE_ACCOUNT_ID" =~ ^[0-9a-f]{32}$ ]]; then
  echo "CLOUDFLARE_ACCOUNT_ID must be 32 hex characters" >&2; exit 2
fi
if [[ -z "$repo" ]]; then
  repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
fi
export WRANGLER_SEND_METRICS=false

say() { printf '%s\n' "$*"; }
run() { if [[ "$dry_run" == 1 ]]; then say "[dry-run] $*"; else "$@"; fi; }

say "Repo: $repo   Environment: $environment   D1: $db   Account: $CLOUDFLARE_ACCOUNT_ID"

# 1. D1 database: reuse if it exists, otherwise create.
d1_id() {
  npx --yes wrangler d1 list --json 2>/dev/null |
    python3 -c 'import sys,json
name=sys.argv[1]
for d in json.load(sys.stdin):
    if d.get("name")==name: print(d.get("uuid") or d.get("id")); break' "$db"
}

if [[ "$dry_run" == 1 ]]; then
  say "[dry-run] wrangler d1 list/create $db (not contacted)"
  database_id="<D1-database-id>"
else
  database_id="$(d1_id || true)"
  if [[ -z "$database_id" ]]; then
    say "Creating D1 database $db"
    npx --yes wrangler d1 create "$db" >/dev/null
    database_id="$(d1_id)"
  else
    say "D1 database $db already exists; reusing it"
  fi
  [[ -n "$database_id" ]] || { echo "Could not read the D1 database id" >&2; exit 1; }
fi

# 2. GitHub environment, variables and secret.
run gh api -X PUT "repos/$repo/environments/$environment" --silent
run gh variable set CLOUDFLARE_ACCOUNT_ID --env "$environment" -R "$repo" --body "$CLOUDFLARE_ACCOUNT_ID"
run gh variable set CLOUDFLARE_D1_DATABASE_ID --env "$environment" -R "$repo" --body "$database_id"
if [[ "$dry_run" == 1 ]]; then
  say "[dry-run] gh secret set CLOUDFLARE_API_TOKEN --env $environment -R $repo (value read from your shell, not shown)"
else
  gh secret set CLOUDFLARE_API_TOKEN --env "$environment" -R "$repo" --body "$CLOUDFLARE_API_TOKEN"
fi

say "Done. Names only (values are not shown):"
if [[ "$dry_run" != 1 ]]; then
  gh variable list --env "$environment" -R "$repo" | cut -f1
  gh secret list --env "$environment" -R "$repo" | cut -f1
fi
