#!/usr/bin/env bash
# Store a copied OpenAI project key in GitHub's staging environment without
# printing it or putting it in shell history. Run only on a trusted machine.
set -euo pipefail

repository="${1:-gpatwa/social-intelligence-platform}"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required." >&2
  exit 1
fi
if ! command -v pbpaste >/dev/null 2>&1; then
  echo "This helper requires macOS pbpaste. Use: gh secret set OPENAI_API_KEY --env staging --repo $repository" >&2
  exit 1
fi

secret_value="$(pbpaste)"
if [[ -z "$secret_value" ]]; then
  echo "Clipboard is empty. Copy the OpenAI key, then rerun this command." >&2
  exit 1
fi
if [[ "$secret_value" != sk-* ]]; then
  echo "Clipboard does not look like an OpenAI API key; nothing was changed." >&2
  exit 1
fi

# Create/update the scoped environment before creating its secret. The key is
# streamed to gh and is never echoed, logged, or written to disk.
gh api --method PUT "repos/$repository/environments/staging" >/dev/null
printf '%s' "$secret_value" | gh secret set OPENAI_API_KEY --repo "$repository" --env staging
echo "Stored OPENAI_API_KEY in the GitHub Actions staging environment for $repository."
