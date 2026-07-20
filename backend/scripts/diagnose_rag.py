"""Diagnose why RAG coverage is only 6%"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
from supabase import create_client

sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# 1. Which repos have ACTIVE snapshots?
snaps = sb.table("repository_snapshots").select("repo_name, commit_sha, chunk_count").eq("status", "ACTIVE").execute()
indexed_repos = {s["repo_name"]: s for s in snaps.data}
print(f"Repos with ACTIVE snapshots: {len(indexed_repos)}")

# 2. Which repos have published issues?
issues = sb.table("issues").select("repo_name, retrieval_method").eq("status", "PUBLISHED").execute()
issue_repos = set(i["repo_name"] for i in issues.data)
print(f"Repos with published issues: {len(issue_repos)}")

# 3. Overlap: repos that have BOTH snapshots AND issues
overlap = issue_repos & set(indexed_repos.keys())
print(f"Repos with BOTH snapshot + issues: {len(overlap)}")

# 4. For each overlapping repo, how many issues have RAG vs not?
print("\n=== REPOS WITH SNAPSHOTS + ISSUES ===")
for repo in sorted(overlap):
    repo_issues = [i for i in issues.data if i["repo_name"] == repo]
    rag_count = sum(1 for i in repo_issues if i.get("retrieval_method") == "RRF")
    no_rag = len(repo_issues) - rag_count
    chunks = indexed_repos[repo]["chunk_count"]
    sha = indexed_repos[repo]["commit_sha"][:7]
    print(f"  {repo:45} | {chunks:4} chunks | SHA={sha} | RAG={rag_count}, NoRAG={no_rag}")

# 5. Repos with issues but NO snapshot
no_snap = issue_repos - set(indexed_repos.keys())
print(f"\n=== REPOS WITH ISSUES BUT NO SNAPSHOT ({len(no_snap)}) ===")
for repo in sorted(no_snap):
    count = sum(1 for i in issues.data if i["repo_name"] == repo)
    print(f"  {repo:45} | {count} issues, NO index")
