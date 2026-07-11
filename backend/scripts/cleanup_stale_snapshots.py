from dotenv import load_dotenv
import os, sys
load_dotenv()
from supabase import create_client
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Find orphaned snapshots
stale = sb.table("repository_snapshots").select("id, repo_name, status").neq("status", "ACTIVE").execute()
print("Orphaned/stale snapshots:")
for s in stale.data:
    repo = s["repo_name"]
    status = s["status"]
    sid = s["id"]
    print(f"  {repo} | {status} | id={sid}")
print(f"Total: {len(stale.data)}")

# Clean them up
if stale.data:
    print("\nCleaning up...")
    sb.table("repository_snapshots").delete().neq("status", "ACTIVE").execute()
    print("Done. Orphaned snapshots removed.")
