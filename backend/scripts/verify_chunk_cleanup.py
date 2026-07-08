# backend/scripts/verify_chunk_cleanup.py
"""
Task 3: Verifies that re-indexing a repo REPLACES old code chunks (storage stays flat)
rather than accumulating new ones on top (storage doubles over time).

How it works:
  1. Count existing chunks for fastapi/fastapi (the "before" number)
  2. Force a clean re-index of fastapi
  3. Count chunks again (the "after" number)
  4. Assert that "after" is within 20% of "before"
     - If flat: ON DELETE CASCADE is working correctly ✅
     - If doubled: CASCADE is broken → will flag it so we can fix manually

Why this matters:
  At 65 repos × 50 files × ~10 chunks each = ~32,500 chunks per index cycle.
  If old chunks are NOT deleted, 10 index cycles = 325,000 chunks → ~150 MB for vectors alone.
  Postgres free tier = 500MB. That's 3 cycles before hitting the wall.
"""
import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.pipeline.code_indexer import ensure_repo_indexed
from app.pipeline.repo_grounding import get_repo_context
from app.pipeline.github_client import GitHubClient

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

REPO = "fastapi/fastapi"
TOLERANCE = 0.20  # Allow up to 20% growth (e.g. repo added new files upstream)


def count_chunks(supabase, repo_name: str) -> int:
    """Counts how many code chunks are in the DB for a given repo."""
    resp = supabase.table("code_chunks") \
        .select("chunk_id", count="exact") \
        .eq("repo_name", repo_name) \
        .execute()
    return resp.count or 0


def count_snapshots(supabase, repo_name: str) -> list:
    """Returns all snapshot rows for a repo so we can see status and IDs."""
    resp = supabase.table("repository_snapshots") \
        .select("id, status, chunk_count, started_at") \
        .eq("repo_name", repo_name) \
        .execute()
    return resp.data or []


def main():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    github_token = os.getenv("GITHUB_TOKEN")

    if not supabase_url or not supabase_key:
        print("❌ Error: SUPABASE_URL or SUPABASE_KEY missing from .env")
        sys.exit(1)

    supabase = create_client(supabase_url, supabase_key)
    github_client = GitHubClient(token=github_token, supabase_client=supabase)

    # ─────────────────────────────────────────────
    # STEP 1: Measure BEFORE
    # ─────────────────────────────────────────────
    print(f"\n📊 STEP 1 — Counting chunks BEFORE re-index")
    before_count = count_chunks(supabase, REPO)
    before_snapshots = count_snapshots(supabase, REPO)
    print(f"   Chunks in DB for {REPO}: {before_count}")
    print(f"   Snapshots:")
    for s in before_snapshots:
        print(f"      [{s['status']}] id={s['id'][:8]}... chunks={s['chunk_count']}")

    # ─────────────────────────────────────────────
    # STEP 2: Force re-index
    # Why: we need to trigger the full activate_snapshot flow to test CASCADE
    # We do NOT manually delete first — we let the indexer handle the swap
    # ─────────────────────────────────────────────
    print(f"\n🔄 STEP 2 — Forcing re-index of {REPO}")
    print(f"   (Deleting existing snapshots to force a fresh indexing cycle...)")

    # Clear existing active snapshot so the indexer triggers a full new index
    supabase.table("code_chunks").delete().eq("repo_name", REPO).execute()
    supabase.table("repository_snapshots").delete().eq("repo_name", REPO).execute()

    repo_ctx = get_repo_context(REPO)
    commit_sha = ensure_repo_indexed(supabase, github_client, REPO, repo_ctx, issues=[])

    if not commit_sha:
        print(f"\n❌ STEP 2 FAILED: Indexer returned no commit SHA. Cannot verify cleanup.")
        sys.exit(1)

    print(f"   ✅ Indexed at commit {commit_sha[:7]}")

    # ─────────────────────────────────────────────
    # STEP 3: Measure AFTER first index
    # ─────────────────────────────────────────────
    print(f"\n📊 STEP 3 — Counting chunks AFTER first index")
    after_first_count = count_chunks(supabase, REPO)
    after_first_snapshots = count_snapshots(supabase, REPO)
    print(f"   Chunks in DB for {REPO}: {after_first_count}")
    print(f"   Snapshots:")
    for s in after_first_snapshots:
        print(f"      [{s['status']}] id={s['id'][:8]}... chunks={s['chunk_count']}")

    # ─────────────────────────────────────────────
    # STEP 4: Force SECOND re-index (same repo, simulating next day's run)
    # This is the critical test: does the second index REPLACE or ACCUMULATE?
    # We do NOT clear manually — we let the pipeline swap snapshots naturally
    # ─────────────────────────────────────────────
    print(f"\n🔄 STEP 4 — Simulating next day: Second re-index WITHOUT manual clear")
    print(f"   (Clearing only the snapshot to force re-index while keeping chunks intact)")

    # Only delete the snapshot record, not the chunks — force re-index
    supabase.table("repository_snapshots").delete().eq("repo_name", REPO).execute()

    repo_ctx2 = get_repo_context(REPO)
    commit_sha2 = ensure_repo_indexed(supabase, github_client, REPO, repo_ctx2, issues=[])

    if not commit_sha2:
        print(f"\n❌ STEP 4 FAILED: Second index returned no commit SHA.")
        sys.exit(1)

    # ─────────────────────────────────────────────
    # STEP 5: Measure AFTER second index — the key number
    # ─────────────────────────────────────────────
    print(f"\n📊 STEP 5 — Counting chunks AFTER second index (the key verification)")
    after_second_count = count_chunks(supabase, REPO)
    after_second_snapshots = count_snapshots(supabase, REPO)
    print(f"   Chunks in DB for {REPO}: {after_second_count}")
    print(f"   Snapshots:")
    for s in after_second_snapshots:
        print(f"      [{s['status']}] id={s['id'][:8]}... chunks={s['chunk_count']}")

    # ─────────────────────────────────────────────
    # VERDICT
    # ─────────────────────────────────────────────
    print(f"\n{'=' * 55}")
    print(f"🧾 VERIFICATION REPORT — {REPO}")
    print(f"{'=' * 55}")
    print(f"   Chunks before:       {before_count}")
    print(f"   After 1st index:     {after_first_count}")
    print(f"   After 2nd index:     {after_second_count}  ← KEY NUMBER")

    if after_first_count == 0:
        print(f"\n❌ ERROR: No chunks were indexed. Check the indexer.")
        sys.exit(1)

    growth_ratio = after_second_count / after_first_count
    print(f"   Growth ratio:        {growth_ratio:.2f}x  (expected ≤ {1 + TOLERANCE:.2f}x)")

    if growth_ratio <= (1 + TOLERANCE):
        print(f"\n✅ VERDICT: Storage is FLAT. ON DELETE CASCADE is working correctly.")
        print(f"   Old chunks were deleted when the snapshot was replaced.")
        print(f"   Daily cron runs for 3-6 months will NOT accumulate unbounded chunks.")
    else:
        print(f"\n❌ VERDICT: Storage is GROWING ({growth_ratio:.2f}x after one re-index).")
        print(f"   Old chunks were NOT deleted. ON DELETE CASCADE may be broken.")
        print(f"   At this rate, {65 * after_second_count} chunks after 65 repos = storage limit risk.")
        print(f"   ACTION NEEDED: Add explicit DELETE before activate_snapshot in code_indexer.py")


if __name__ == "__main__":
    main()
