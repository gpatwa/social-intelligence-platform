# GitHub repository connector

**Status: draft, not live.** The code and workflow exist on a branch. Nothing
has been deployed, no repository variable is set, and no run has happened.

## Why

Posts show what people talk about. Repository activity shows what teams adopt.
Release cadence and star growth on a curated set of agent frameworks is a
second, harder-to-fake signal for the evidence layer. It costs nothing: the
GitHub REST API is free for public data.

## What it collects

Only the operator's watchlist, set in `GITHUB_REPOSITORIES` as comma-separated
`owner/repo` names. Two requests per repository per run:

| Request | Used for |
|---|---|
| `GET /repos/{owner}/{repo}` | Daily snapshot: description, topics, stars, forks, open issues, last push |
| `GET /repos/{owner}/{repo}/releases?per_page=5` | New, non-draft releases since the cursor |

It does not read contributors, issues, commits, pull requests, or user
profiles. The only person-like field is the public owner login, kept as the
author. Topic search is a later step; `keyword` rules are rejected.

## Event mapping

Both kinds are `social.post.observed` with `platform = github`, so the existing
landing and Bronze path accepts them without a contract change.

| Field | Repo snapshot | Release |
|---|---|---|
| `post_id` | `owner/repo@YYYY-MM-DD` | `owner/repo#release-<id>` |
| `created_at` | start of the UTC day | release `published_at` |
| `content_text` | name and description | name, tag and notes (first 2,000 characters) |
| `saves` | stars | 0 |
| `shares` | forks | 0 |
| `likes`, `comments`, `views` | 0 | 0 |
| `hashtags` | repository topics | repository topics |
| `attributes.resource_type` | `repo_snapshot` | `release` |
| `attributes.rule_id` | per-repository rule | per-repository rule |

Stars are the closest analogue of a save and forks of a share. Open issues are
not comments, so raw counts (including open issues) stay in `source_payload`.
A snapshot per day with a dated `post_id` makes growth a difference between
days, and the fixed day-start time keeps the idempotency key stable if a run is
retried.

## Controls

- **Request cap:** `GITHUB_MAX_REQUESTS_PER_RUN` (default 40). The run fails
  closed before exceeding it, and the config requires at least two per repo.
- **Rate limits:** 403 and 429 are not retried; the run fails and the next
  scheduled run tries again. Only 5xx and transport errors use bounded backoff.
- **Checkpoint:** per-repository `snapshot_date` and `release_published_at`
  cursors in the same remote checkpoint pattern as YouTube. A failed run
  commits nothing.
- **Missing repo (404):** counted as `repos_not_found` and skipped.
- **Credential:** the workflow passes the built-in `GITHUB_TOKEN` as
  `GITHUB_API_TOKEN`. No new secret is needed. Unauthenticated access also
  works for a small list, at a lower rate limit.

## Variables (none set yet)

| Variable | Proposed |
|---|---|
| `ENABLE_GITHUB_COLLECTOR` | `true` only after approval |
| `GITHUB_REPOSITORIES` | See the starter watchlist below |
| `GITHUB_MAX_REQUESTS_PER_RUN` | `40` |
| `GITHUB_RELEASES_PER_REPO` | `5` |
| `GITHUB_RELEASE_LOOKBACK_DAYS` | `30` on the first run |

Starter watchlist, chosen from general knowledge and not verified against the
API: `langchain-ai/langgraph`, `crewAIInc/crewAI`, `pydantic/pydantic-ai`,
`openai/openai-agents-python`, `google/adk-python`,
`microsoft/agent-framework`, `modelcontextprotocol/servers`. Confirm each name
exists before enabling; a wrong name is skipped as `repos_not_found`.

## Known limits and open decisions

- **Stars lag and can be inflated.** Prefer growth over time and release
  cadence to raw counts.
- **Silver treats these as posts.** Cross-platform scoring will rank repo
  snapshots against social posts unless Gold filters on `platform`. Decide
  whether GitHub rows feed the post score or only an adoption view before
  enabling the collector.
- **Topic classification** will label most rows `other` until the pilot topic
  taxonomy lands.
- **Shared runner:** this worker repeats the YouTube worker's structure.
  Extracting one runner is a follow-up.
- **Not verified:** no live API call was made. The tests use a fake transport.
