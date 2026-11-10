#!/usr/bin/env bash
# One-time Cloudflare setup for a GitHub repo that deploys a Worker with D1.
#
# Creates (or reuses) the D1 database, creates the GitHub environment, and sets
# CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_D1_DATABASE_ID and CLOUDFLARE_API_TOKEN on
# it. The token is read from your shell and passed straight to `gh`; it is never
# printed, written to a file or put on a command line.
#
# Needs in your shell: CLOUDFLARE_ACCOUNT_ID (not secret) and one of:
#   - CLOUDFLARE_API_TOKEN (Workers Scripts: Edit, D1: Edit, Account Settings:
#     Read), or
#   - with --mint-token, CLOUDFLARE_BOOTSTRAP_TOKEN, a token whose only
#     permission is Account API Tokens: Edit. The script uses it once to mint a
#     narrow, expiring deploy token for this repo, so you create that one
#     bootstrap token per account instead of one token per repo.
# Reusable for any repo:
#
#   deploy/cloudflare/bootstrap.sh --dry-run
#   deploy/cloudflare/bootstrap.sh --mint-token --repo owner/name --db my-db --env cloudflare-production
set -euo pipefail

repo=""
db="social-intelligence-landing"
environment="cloudflare-production"
dry_run=0
mint=0
expires_days=90

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) repo="$2"; shift 2 ;;
    --db) db="$2"; shift 2 ;;
    --env) environment="$2"; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    --mint-token) mint=1; shift ;;
    --expires-days) expires_days="$2"; shift 2 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

: "${CLOUDFLARE_ACCOUNT_ID:?Set CLOUDFLARE_ACCOUNT_ID in your shell first}"
if [[ "$mint" == 1 ]]; then
  : "${CLOUDFLARE_BOOTSTRAP_TOKEN:?Set CLOUDFLARE_BOOTSTRAP_TOKEN (Account API Tokens: Edit) for --mint-token}"
else
  : "${CLOUDFLARE_API_TOKEN:?Set CLOUDFLARE_API_TOKEN in your shell first}"
fi
if [[ ! "$expires_days" =~ ^[0-9]+$ ]] || (( expires_days < 1 || expires_days > 365 )); then
  echo "--expires-days must be 1 to 365" >&2; exit 2
fi
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

# 0. Optionally mint a narrow deploy token with the bootstrap token. The value
# is held in a shell variable only: never printed, logged or put on a command
# line (curl reads the header from a process-substitution file).
cf_api() { # method path [json-body-on-stdin]
  local method="$1" path="$2"
  curl -sS -X "$method" "https://api.cloudflare.com/client/v4$path" \
    -K <(printf 'header = "Authorization: Bearer %s"\nheader = "Content-Type: application/json"\n' "$CLOUDFLARE_BOOTSTRAP_TOKEN") \
    ${3:+--data-binary @-}
}

if [[ "$mint" == 1 ]]; then
  if [[ "$dry_run" == 1 ]]; then
    say "[dry-run] mint a deploy token on account $CLOUDFLARE_ACCOUNT_ID: Workers Scripts Write, D1 Write, Account Settings Read; expires in ${expires_days} days (not contacted)"
    CLOUDFLARE_API_TOKEN="<minted-token>"
  else
    groups="$(cf_api GET "/accounts/$CLOUDFLARE_ACCOUNT_ID/tokens/permission_groups")"
    body="$(printf '%s' "$groups" | python3 -c '
import sys, json, datetime
acct, repo, days = sys.argv[1], sys.argv[2], int(sys.argv[3])
data = json.load(sys.stdin)
if not data.get("success"):
    sys.exit("permission group lookup failed: %s" % [e.get("message") for e in data.get("errors", [])])
wanted = ["Workers Scripts Write", "D1 Write", "Account Settings Read"]
ids = {g["name"]: g["id"] for g in data["result"]}
missing = [w for w in wanted if w not in ids]
if missing:
    sys.exit("permission groups not found: %s" % missing)
expires = (datetime.datetime.utcnow() + datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
print(json.dumps({
    "name": "%s-deploy" % repo.replace("/", "-"),
    "expires_on": expires,
    "policies": [{
        "effect": "allow",
        "resources": {"com.cloudflare.api.account.%s" % acct: "*"},
        "permission_groups": [{"id": ids[w]} for w in wanted],
    }],
}))' "$CLOUDFLARE_ACCOUNT_ID" "$repo" "$expires_days")"
    created="$(printf '%s' "$body" | cf_api POST "/accounts/$CLOUDFLARE_ACCOUNT_ID/tokens" body)"
    CLOUDFLARE_API_TOKEN="$(printf '%s' "$created" | python3 -c '
import sys, json
data = json.load(sys.stdin)
if not data.get("success"):
    sys.exit("token creation failed: %s" % [e.get("message") for e in data.get("errors", [])])
print(data["result"]["value"])')"
    export CLOUDFLARE_API_TOKEN
    say "Minted a deploy token expiring in ${expires_days} days (value not shown)"
  fi
fi

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
