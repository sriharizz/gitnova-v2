import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
from supabase import create_client

sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Top 5 issues by quality
issues = sb.table("issues").select(
    "title, repo_name, quality_score, quality_grade, model_provider, retrieval_method, ai_hint"
).eq("quality_grade", "High").order("quality_score", desc=True).limit(5).execute()

print("=== TOP 5 HIGHEST QUALITY ISSUES ===\n")
for i, iss in enumerate(issues.data):
    title = iss["title"][:85]
    hint = (iss.get("ai_hint") or "")[:350].encode("ascii", "replace").decode()
    print(f"{i+1}. [{iss['quality_score']}] {iss['repo_name']}")
    print(f"   Title: {title}")
    print(f"   Provider: {iss['model_provider']} | RAG: {iss['retrieval_method']}")
    print(f"   Hint: {hint}...")
    print()

# Stats summary
all_issues = sb.table("issues").select("quality_grade, category, retrieval_method", count="exact").eq("status", "PUBLISHED").execute()
total = all_issues.count
rag_count = sum(1 for i in all_issues.data if i.get("retrieval_method") == "RRF")
no_rag = total - rag_count
print(f"=== SUMMARY ===")
print(f"Total issues: {total}")
print(f"With RAG (code-grounded): {rag_count}")
print(f"Without RAG (LLM only): {no_rag}")
print(f"RAG coverage: {rag_count/total*100:.0f}%" if total else "N/A")
