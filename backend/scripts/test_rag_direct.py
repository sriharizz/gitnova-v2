"""Test the ACTUAL retrieval pipeline for a repo with known chunks"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
from supabase import create_client
from app.pipeline.code_retriever import retrieve_code_for_issue

sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# grafana has 182 chunks at SHA 606b1bc5...
repo = "grafana/grafana"
sha = "606b1bc59a3b3d49c92cf4b3c376ced28a68ebb4"

# Use a real issue title
title = "Dashboard panel not rendering after refresh"
body = "When I reload the page, the dashboard panel shows a blank white screen."

print(f"Testing retrieval for {repo} at {sha[:7]}...")
result = retrieve_code_for_issue(sb, repo, sha, title, body)
code, chunk_ids = result
print(f"Retrieved {len(chunk_ids)} chunks")
if code:
    print(f"Code length: {len(code)} chars")
    print(f"First 200 chars: {code[:200]}")
else:
    print("NO CODE RETURNED")
