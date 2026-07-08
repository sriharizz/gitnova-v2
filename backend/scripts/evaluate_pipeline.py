# backend/scripts/evaluate_pipeline.py
import os
import sys
import csv
import json
import re
from typing import List, Dict, Any
from dotenv import load_dotenv
from supabase import create_client

# Adjust path to import from backend root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.pipeline.code_retriever import retrieve_code_for_issue
from app.pipeline.bot import evaluate_and_enrich
from app.pipeline.repo_grounding import get_repo_context

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

def extract_files_from_hint(hint: str) -> List[str]:
    """Helper to extract files referenced in the LLM hint text using simple regex matching."""
    # Look for patterns like packages/... or fastapi/... or custom paths
    # Match backticks containing filenames
    found = re.findall(r'`([^`]+\.[a-zA-Z0-9]+)`', hint)
    return list(set(found))

def load_golden_dataset(csv_path: str) -> List[Dict[str, Any]]:
    """Loads issue and ground truth files from golden_set.csv."""
    dataset = []
    if not os.path.exists(csv_path):
        print(f"❌ Error: {csv_path} not found. Please run scripts/build_golden_set.py first.")
        sys.exit(1)
        
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dataset.append({
                "issue_id": row["issue_id"],
                "issue_title": row["issue_title"],
                "repo_name": row["repo"],
                "expected_files": [f.strip() for f in row["ground_truth_files"].split(",") if f.strip()]
            })
    return dataset

def evaluate_rag():
    print("🧪 Starting GitNova V3 — FastAPI Retrieval Recall Evaluation...")
    
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        print("❌ Error: SUPABASE_URL or SUPABASE_KEY missing from .env")
        sys.exit(1)
        
    supabase = create_client(supabase_url, supabase_key)
    
    all_rows = load_golden_dataset("golden_set.csv")

    # Filter to only fastapi rows — this is our targeted eval
    golden_dataset = [r for r in all_rows if r["repo_name"] == "fastapi/fastapi"]
    total_issues = len(golden_dataset)
    print(f"Loaded {total_issues} fastapi/fastapi issues from golden_set.csv.")

    # Metrics tracking
    retrieval_success_count = 0
    hint_success_count = 0
    llm_eval_limit = 3          # LLM generation eval on first 3 issues only (rate limit safety)
    llm_evaluated_count = 0

    for idx, item in enumerate(golden_dataset):
        print(f"\n--- Scenario {idx + 1}/{total_issues}: {item['repo_name']}#{item['issue_title'][:40]}... ---")
        
        # 1. Fetch repo context
        repo_ctx = get_repo_context(item['repo_name'])
        
        # 2. Get active commit SHA
        commit_sha = ""
        try:
            active_resp = supabase.table("repository_snapshots") \
                .select("commit_sha") \
                .eq("repo_name", item['repo_name']) \
                .eq("status", "ACTIVE") \
                .execute()
            if active_resp.data:
                commit_sha = active_resp.data[0]["commit_sha"]
        except Exception as e:
            print(f"⚠️ Failed to fetch active snapshot: {e}")
            
        if not commit_sha:
            print(f"⚠️ Skipping scenario: No active snapshot for {item['repo_name']}.")
            continue
            
        # 3. Retrieve chunks
        print(f"🔍 Running RRF retrieval for {item['repo_name']} at commit {commit_sha[:7]}...")
        retrieved_code, retrieved_chunk_ids = retrieve_code_for_issue(
            supabase, item['repo_name'], commit_sha, item['issue_title'], ""
        )
        
        # Parse retrieved files
        retrieved_files = []
        if retrieved_code:
            # Header format: "--- SOURCE FILE: {file_path} ... ---"
            retrieved_files = re.findall(r'--- SOURCE FILE: ([^\s\)]+)', retrieved_code)
            
        retrieved_files_unique = list(set(retrieved_files))
        
        # Check if RAG successfully found any of the expected fix files
        expected_set = set(item['expected_files'])
        retrieved_set = set(retrieved_files_unique)
        
        intersection = expected_set.intersection(retrieved_set)
        retrieved_success = len(intersection) > 0
        if retrieved_success:
            retrieval_success_count += 1
            print(f"   ✅ RAG Retrieval Success! Found: {list(intersection)}")
        else:
            print(f"   ❌ RAG Retrieval Failed. Expected: {item['expected_files']} | Got: {retrieved_files_unique[:3]}")
            
        # 4. LLM Generation evaluation (limited to first 5 issues)
        if idx < llm_eval_limit:
            llm_evaluated_count += 1
            print(f"⚡ Invoking LLM Judge fallback gateway (with 7s cooldown)...")
            ai_response, provider_name, model_name = evaluate_and_enrich(
                item['issue_title'],
                "",  # empty body
                item['repo_name'],
                "Apprentice",
                repo_ctx,
                retrieved_code=retrieved_code
            )
            
            hint_success = False
            if ai_response:
                try:
                    judgement = json.loads(ai_response)
                    hint = judgement.get('hint', '')
                    
                    # Check if the LLM's hint output references any of our correct fix files
                    referenced_files = extract_files_from_hint(hint)
                    hint_intersection = expected_set.intersection(set(referenced_files))
                    
                    # fallback check: plain text substring search for file names inside the hint text
                    if not hint_intersection:
                        for exp_file in item['expected_files']:
                            basename = os.path.basename(exp_file)
                            if basename in hint:
                                hint_intersection.add(exp_file)
                                
                    if hint_intersection:
                        hint_success = True
                        hint_success_count += 1
                        print(f"   ✅ LLM Hint Success! Hint references correct fix file: {list(hint_intersection)}")
                    else:
                        print(f"   ❌ LLM Hint Failed. Hint referenced: {referenced_files} | Expected: {item['expected_files']}")
                except Exception as parse_err:
                    print(f"   ⚠️ Failed to parse LLM JSON output: {parse_err}")
            else:
                print("   ⚠️ LLM Judge call failed.")
                
    # Calculate percentages
    final_retrieval_recall = (retrieval_success_count / total_issues) if total_issues > 0 else 0
    final_hint_precision = (hint_success_count / llm_evaluated_count) if llm_evaluated_count > 0 else 0
    
    print("\n" + "=" * 60)
    print("📈 AUTOMATED EVALUATION SUMMARY")
    print("=" * 60)
    print(f"   📊 Total Issues Analyzed:      {total_issues}")
    print(f"   🎯 RAG Retrieval Recall:       {retrieval_success_count}/{total_issues} ({final_retrieval_recall:.1%})")
    print(f"   🧠 LLM Hint Precision:         {hint_success_count}/{llm_evaluated_count} ({final_hint_precision:.1%})")
    print("=" * 60)
    
    # Store results in Supabase
    print("\n💾 Saving metrics to Supabase 'eval_results' table...")
    try:
        supabase.table("eval_results").insert({
            "total_issues_evaluated": total_issues,
            "retrieval_recall": final_retrieval_recall,
            "hint_precision": final_hint_precision,
            "retrieval_success_count": retrieval_success_count,
            "hint_success_count": hint_success_count
        }).execute()
        print("✅ Successfully logged evaluation metrics to database.")
    except Exception as db_err:
        print(f"❌ Failed to store eval results in Supabase: {db_err}")

if __name__ == "__main__":
    evaluate_rag()
