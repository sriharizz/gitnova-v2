# LATER.md — Deferred Issues Found During Sustainability Hardening

These are real problems found during the 5-task hardening session.
None of these were fixed now to avoid scope creep. Revisit in a future session.

---

## 1. Initial 65-Repo Indexing Exceeds GitHub Actions Time Limit

**Problem:**
Indexing all 65 repos from scratch takes ~8-10 hours on a CPU runner.
GitHub Actions free tier kills jobs after 6 hours.
The daily cron is fine (~40-60 min, since most repos are unchanged).
But the FIRST-TIME full setup will fail silently mid-job.

**Impact:** High — first-run indexing is incomplete, some repos never get indexed.

**Fix Options (pick one):**
- Split into 7 GitHub Actions jobs (10 repos each), triggered in parallel
- Use Jina's hosted embedding API (free: 1M tokens/month) — reduces indexing
  time from hours to minutes by offloading embedding to their servers
- Index repos in rolling batches: 10 repos per day for the first week

---

## 2. Janitor Does Not Check for Assigned Issues

**Problem:**
`clean_closed_issues()` only deletes issues where GitHub `state == 'closed'`.
It does NOT remove issues that are still open but now assigned to someone.
An issue being actively worked on by another developer should not appear in GitNova.

**Impact:** Medium — assigned issues pollute the feed for users.

**Fix:**
In `clean_closed_issues()`, also check `gh_data.get('assignee')` or
`gh_data.get('assignees')` — if either is non-empty, delete the issue from DB.

---

## 3. ETag Cache Stores Full Issue List JSON (Storage Risk at Scale)

**Problem:**
`_save_etag_to_db()` stores the full GitHub API response (list of 30 issues)
as JSONB in the `etag_cache` table. For 65 repos × 30 issues × ~2KB each,
that's ~3.9 MB of JSON stored in the cache table.
Currently small, but will grow if FETCH_PER_REPO is increased.

**Impact:** Low right now — 64 kB observed. Monitor if FETCH_PER_REPO > 50.

**Fix:** Store only issue IDs and updated_at timestamps instead of full payloads,
and refetch from GitHub on cache hit if needed.

---

## 4. React Repo Still Has Old 120-File Index (1,315 chunks)

**Problem:**
`facebook/react` was indexed with the old `MAX_INDEX_FILES = 120` budget,
giving 1,315 chunks. With the new budget of 50 files, it should have ~300.
The extra ~1,000 chunks are wasting ~8 MB of storage unnecessarily.

**Impact:** Low — 8 MB waste. Storage is still well within limits (34% of 500 MB).

**Fix:** Run `reindex_repos.py` targeting `facebook/react` to replace with
a fresh 50-file index. The CASCADE delete will clean up the old 1,315 chunks.

---

## 5. No Alerting When GitHub Actions Cron Fails

**Problem:**
If the daily cron fails silently (rate limit, timeout, exception), no one
is notified. The issues table just stops getting fresh data and goes stale.

**Impact:** Medium — you won't notice until the feed visibly ages.

**Fix:** Add a GitHub Actions step that posts to a Slack/Discord webhook or
sends an email on job failure using `if: failure()` condition in the workflow YAML.

---

## Summary

| # | Issue | Impact | Effort |
|---|-------|--------|--------|
| 1 | Initial indexing > 6hr limit | High | Medium |
| 2 | Janitor misses assigned issues | Medium | Low |
| 3 | ETag cache stores full JSON | Low | Low |
| 4 | React old 120-file index | Low | Trivial |
| 5 | No failure alerting on cron | Medium | Low |
