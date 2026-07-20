"""Test RAG retrieval directly for a repo that SHOULD have chunks"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
from supabase import create_client

sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Pick grafana — 182 chunks, 7 issues, 0 RAG
repo = "grafana/grafana"

# 1. Get the ACTIVE snapshot SHA
snap = sb.table("repository_snapshots").select("commit_sha").eq("repo_name", repo).eq("status", "ACTIVE").limit(1).execute()
sha = snap.data[0]["commit_sha"] if snap.data else None
print(f"Snapshot SHA for {repo}: {sha}")

# 2. Check how many chunks exist in DB for this repo + SHA
chunks = sb.table("code_chunks").select("chunk_id", count="exact").eq("repo_name", repo).eq("commit_sha", sha).execute()
print(f"Chunks in DB matching repo={repo}, sha={sha}: {chunks.count}")

# 3. Check if chunks exist for this repo with ANY sha
all_chunks = sb.table("code_chunks").select("chunk_id, commit_sha", count="exact").eq("repo_name", repo).limit(5).execute()
print(f"Total chunks for {repo} (any SHA): {all_chunks.count}")
if all_chunks.data:
    chunk_shas = set(c["commit_sha"] for c in all_chunks.data)
    print(f"Chunk SHAs found: {chunk_shas}")
    print(f"Snapshot SHA: {sha}")
    print(f"Match: {sha in chunk_shas}")
