# backend/scripts/reindex_repos.py
"""
Clears and re-indexes fastapi/fastapi only (budget: 50 files).
Run this directly — it handles the Supabase cleanup automatically.
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

def main():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    github_token = os.getenv("GITHUB_TOKEN")

    if not supabase_url or not supabase_key:
        print("❌ Error: SUPABASE_URL or SUPABASE_KEY missing from .env")
        sys.exit(1)

    supabase = create_client(supabase_url, supabase_key)
    github_client = GitHubClient(token=github_token)

    # Auto-clear stale fastapi snapshots so we always do a clean re-index
    print(f"🗑️  Clearing old snapshots for {REPO}...")
    try:
        supabase.table("code_chunks").delete().eq("repo_name", REPO).execute()
        supabase.table("repository_snapshots").delete().eq("repo_name", REPO).execute()
        print(f"   ✅ Old data cleared.")
    except Exception as e:
        print(f"   ⚠️  Cleanup warning (non-fatal): {e}")

    print(f"\n{'=' * 60}")
    print(f"🔄 Re-indexing: {REPO} (budget: 50 files)")
    print(f"{'=' * 60}")

    repo_ctx = get_repo_context(REPO)
    print(f"   Language: {repo_ctx.get('language')} | Extensions: {repo_ctx.get('valid_extensions')}")

    commit_sha = ensure_repo_indexed(supabase, github_client, REPO, repo_ctx, issues=[])

    if commit_sha:
        print(f"\n✅ {REPO} indexed at commit {commit_sha[:7]}")
        print("   Next step: run evaluate_pipeline.py to get recall metrics.")
    else:
        print(f"\n❌ Indexing FAILED for {REPO}")

if __name__ == "__main__":
    main()
