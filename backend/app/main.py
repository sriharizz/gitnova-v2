import os
import requests
import json
import sys
from supabase import create_client
from dotenv import load_dotenv

# --- IMPORTS ---
from app.ml.transformer_brain import predict_difficulty_with_transformer
from app.pipeline.bot import evaluate_and_enrich
from app.pipeline.pre_filter import pre_filter_issue
from app.pipeline.repo_grounding import get_repo_context, clear_cache
from app.pipeline.post_validator import validate_llama_output
from app.pipeline.quality_scorer import compute_quality_score
from app.pipeline.code_indexer import ensure_repo_indexed
from app.pipeline.code_retriever import retrieve_code_for_issue
from app.pipeline.github_client import GitHubClient

load_dotenv()

# --- ⚙️ CONFIGURATION ---
INTERESTS = {
    "Frontend": [
        "facebook/react", "shadcn-ui/ui", "vercel/next.js", 
        "tailwindlabs/tailwindcss", "mui/material-ui", "sveltejs/svelte",
        "vuejs/core", "remix-run/remix", "solidjs/solid", "withastro/astro",
        "freeCodeCamp/freeCodeCamp", "storybookjs/storybook", "appsmithorg/appsmith"
    ],
    "Machine Learning": [
        "pytorch/pytorch", "huggingface/transformers", "langchain-ai/langchain", 
        "tensorflow/tensorflow", "karpathy/nanoGPT", "openai/whisper",
        "microsoft/DeepSpeed", "ray-project/ray", "huggingface/diffusers",
        "scikit-learn/scikit-learn", "keras-team/keras", "streamlit/streamlit"
    ],
    "Backend": [
        "fastapi/fastapi", "django/django", "nestjs/nest", "expressjs/express",
        "tiangolo/sqlmodel", "pallets/flask", "rails/rails", "laravel/laravel",
        "strapi/strapi", "go-gorm/gorm", "RocketChat/Rocket.Chat", 
        "supabase/supabase", "redis/redis"
    ],
    "DevOps": [
        "microsoft/vscode", "docker/cli", "kubernetes/kubernetes", 
        "ansible/ansible", "prometheus/prometheus", "grafana/grafana",
        "hashicorp/terraform", "jenkinsci/jenkins", "gitlabhq/gitlabhq",
        "elastic/elasticsearch", "moby/moby"
    ],
    "Data Science": [
        "pandas-dev/pandas", "apache/spark", "apache/arrow", 
        "plotly/plotly.py", "matplotlib/matplotlib", "ydataai/ydata-profiling",
        "seleniumhq/selenium", "scrapy/scrapy"
    ],
    "Mobile": [
        "flutter/flutter", "facebook/react-native", "ionic-team/ionic-framework", 
        "expo/expo", "airbnb/lottie-android", "square/retrofit", 
        "realm/realm-swift", "skylot/jadx"
    ]
}

# 🚦 SAFE MODE SETTINGS
DRY_RUN = False              # Set True to test without DB writes
FETCH_PER_REPO = 30          # GitHub fetching depth
LOCAL_MIN_CONFIDENCE = 0.30  # DeBERTa Pass/Fail Threshold
CLOUD_SELECTION_LIMIT = 15   # Max issues to send to Groq per batch
MAX_RETRIES = 2              # Post-validation retry attempts

# Init Supabase
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("❌ CRITICAL: Supabase credentials missing from .env")

supabase = create_client(supabase_url, supabase_key)


# --- PIPELINE STATS ---
class PipelineStats:
    """Track statistics across the entire pipeline run."""
    def __init__(self):
        self.fetched: int = 0
        self.pre_filtered: int = 0
        self.skipped_unchanged: int = 0  # Issues already in DB with no changes — skipped before LLM+RAG
        self.deberta_passed: int = 0
        self.judged: int = 0
        self.validated: int = 0
        self.retried: int = 0
        self.retry_saved: int = 0
        self.published: int = 0
        self.rejected: int = 0
        self.quality_high: int = 0
        self.quality_medium: int = 0
        self.quality_low: int = 0
    
    def print_summary(self):
        print("\n" + "=" * 60)
        print("📊 PIPELINE SUMMARY")
        print("=" * 60)
        print(f"   📥 Fetched:              {self.fetched}")
        print(f"   ⏭️  Skipped (unchanged):  {self.skipped_unchanged}")
        print(f"   🚫 Pre-filtered out:     {self.pre_filtered}")
        print(f"   🧠 DeBERTa passed:       {self.deberta_passed}")
        print(f"   ⚡ Judged by LLM:     {self.judged}")
        print(f"   ✅ Validated:          {self.validated}")
        print(f"   🔄 Retried:           {self.retried} (saved {self.retry_saved})")
        print(f"   📤 Published:         {self.published}")
        print(f"   🚫 Rejected by LLM:   {self.rejected}")
        print(f"   ---")
        print(f"   🟢 High Quality:      {self.quality_high}")
        print(f"   🟡 Medium Quality:    {self.quality_medium}")
        print(f"   🔴 Low Quality:       {self.quality_low}")
        
        total_graded = self.quality_high + self.quality_medium + self.quality_low
        if total_graded > 0:
            pct_high = (self.quality_high / total_graded) * 100
            print(f"\n   📈 High-Quality Rate: {pct_high:.1f}%")
        print("=" * 60 + "\n")


# --- JANITOR ---
def clean_closed_issues():
    """Removes issues from Supabase if they are now closed on GitHub or malformed."""
    if DRY_RUN: return
    print("\n🧹 JANITOR: Checking for closed issues and malformed data...")
    try:
        # Sweep malformed data first
        del_resp = supabase.table("issues").delete().in_("difficulty", ["REJECT", "Reject", "Master"]).execute()
        if hasattr(del_resp, 'data') and len(del_resp.data) > 0:
            print(f"   🗑️ Swept {len(del_resp.data)} 'REJECT'/'Master' ghost issues from DB.")

        response = supabase.table("issues").select("id, repo_name, url").eq("status", "PUBLISHED").execute()
        db_issues = response.data
        
        token = os.getenv("GITHUB_TOKEN")
        headers = {"Authorization": f"token {token}"} if token else {}
        
        closed_count = 0
        for issue in db_issues:
            api_url = issue['url'].replace("github.com", "api.github.com/repos")
            try:
                r = requests.get(api_url, headers=headers, timeout=5)
                if r.status_code == 200:
                    gh_data = r.json()
                    is_closed = gh_data.get('state') == 'closed'
                    has_assignee = bool(gh_data.get('assignee') or gh_data.get('assignees'))
                    if is_closed or has_assignee:
                        supabase.table("issues").delete().eq("id", issue['id']).execute()
                        reason = "closed" if is_closed else "assigned"
                        print(f"   🗑️ Removed {reason} issue: {issue['repo_name']} #{issue['id']}")
                        closed_count += 1
            except Exception:
                continue
                
        print(f"   ✨ Janitor finished. Removed {closed_count} closed issues.\n")
    except Exception as e:
        print(f"   ⚠️ Janitor Error: {e}")


# --- PIPELINE ---
def run_pipeline():
    print(f"🚀 STARTING GITNOVA ENGINE v2.0")
    print(f"📝 MODE: {'DRY RUN' if DRY_RUN else 'PRODUCTION'}")
    print(f"🔒 SAFE MODE ACTIVE: Limiting Judge to top {CLOUD_SELECTION_LIMIT} candidates.")
    print(f"🛡️ NEW: Pre-filter + Post-validation + Quality Scoring ACTIVE\n")

    stats = PipelineStats()
    clean_closed_issues()
    clear_cache()  # Fresh repo context cache each run

    # ═══════════════════════════════════════════
    # STARTUP: Load all existing issue IDs + timestamps from DB (one query)
    # Purpose: lets us skip issues that are already stored AND unchanged,
    # before running any expensive DeBERTa / RAG / LLM steps.
    # Maps: github_issue_id (int) -> github_issue_updated_at (str)
    # ═══════════════════════════════════════════
    existing_issues: dict = {}
    try:
        existing_resp = supabase.table("issues") \
            .select("id, github_issue_updated_at") \
            .execute()
        existing_issues = {
            row["id"]: row.get("github_issue_updated_at", "")
            for row in (existing_resp.data or [])
        }
        print(f"📋 Loaded {len(existing_issues)} existing issue IDs from DB for dedup skip.")
    except Exception as e:
        print(f"⚠️ Could not load existing issues from DB (will reprocess all): {e}")

    for category, repos in INTERESTS.items():
        print(f"\n🌍 CATEGORY: {category}")
        candidates = []
        
        # ═══════════════════════════════════════════
        # STAGE A: HUNT (GitHub API)
        # ═══════════════════════════════════════════
        for repo in repos:
            try:
                url = f"https://api.github.com/repos/{repo}/issues?state=open&sort=created&per_page={FETCH_PER_REPO}"
                
                token = os.getenv("GITHUB_TOKEN")
                headers = {
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github.v3+json"
                } if token else {}

                resp = requests.get(url, headers=headers, timeout=10)
                
                if resp.status_code == 200:
                    issues = resp.json()
                    if not isinstance(issues, list): continue
                    print(f"   ✅ {repo}: Scanned {len(issues)} issues")
                elif resp.status_code == 403:
                    print(f"   🛑 {repo}: RATE LIMIT HIT (403).")
                    continue
                else:
                    print(f"   ⚠️ {repo}: Status {resp.status_code}")
                    continue
                
                for issue in issues:
                    if 'pull_request' in issue: continue
                    stats.fetched += 1

                    # ═══════════════════════════════════════════
                    # STAGE 0: SKIP UNCHANGED (Task 2 — Gap 1 fix)
                    # ═══════════════════════════════════════════
                    # If the issue is already in the DB AND its updated_at timestamp
                    # hasn't changed since we last stored it → nothing new to process.
                    # Skip BEFORE DeBERTa, RAG, and LLM to save the entire compute budget.
                    issue_id = issue.get('id')
                    issue_updated_at = issue.get('updated_at', '')
                    if issue_id in existing_issues and existing_issues[issue_id] == issue_updated_at:
                        stats.skipped_unchanged += 1
                        continue

                    # ═══════════════════════════════════════════
                    # STAGE 1: PRE-FILTER (NEW)
                    # ═══════════════════════════════════════════
                    issue_labels = issue.get('labels', [])
                    safe_body = issue.get('body') or ""
                    
                    filter_result = pre_filter_issue(
                        issue['title'], safe_body, issue_labels
                    )
                    
                    if not filter_result['pass']:
                        stats.pre_filtered += 1
                        continue
                    
                    # ═══════════════════════════════════════════
                    # STAGE 2: DeBERTa FILTER (existing)
                    # ═══════════════════════════════════════════
                    text = f"{issue['title']} {safe_body}"
                    analysis = predict_difficulty_with_transformer(text)
                    
                    if analysis['score'] < LOCAL_MIN_CONFIDENCE: 
                        continue
                    
                    stats.deberta_passed += 1
                    candidates.append({"data": issue, "analysis": analysis, "repo": repo})

            except Exception as e:
                print(f"   ❌ Error scanning {repo}: {e}")

        # ═══════════════════════════════════════════
        # STAGE C: SORT & PRIORITIZE
        # ═══════════════════════════════════════════
        if not candidates:
            print("   💤 No suitable candidates found.")
            continue

        candidates.sort(key=lambda x: x['analysis']['score'], reverse=True)
        top_picks = candidates[:CLOUD_SELECTION_LIMIT] 
        
        print(f"   💎 Sending {len(top_picks)} Best Candidates to The Judge...")

        # ═══════════════════════════════════════════
        # STAGE 3: REPO GROUNDING & RAG INDEXING
        # ═══════════════════════════════════════════
        # Pre-fetch repo contexts and index repository code (RAG)
        repo_contexts = {}
        repo_commits = {}
        gh_client = GitHubClient(supabase_client=supabase)
        
        for item in top_picks:
            r_name = item['repo']
            if r_name not in repo_contexts:
                # 1. Fetch repo metadata context
                repo_contexts[r_name] = get_repo_context(r_name)
                lang = repo_contexts[r_name].get('language', '?')
                print(f"   🌐 Grounded {r_name}: {lang}")
                
                # 2. Collect top-picks issues for this specific repo to guide indexing (Boosts B & C)
                repo_issues = [x['data'] for x in top_picks if x['repo'] == r_name]
                
                # 3. Trigger index update
                try:
                    active_sha = ensure_repo_indexed(supabase, gh_client, r_name, repo_contexts[r_name], repo_issues)
                    repo_commits[r_name] = active_sha
                except Exception as index_err:
                    print(f"   ⚠️ RAG Indexing error for {r_name}: {index_err}")
                    repo_commits[r_name] = ""

        # ═══════════════════════════════════════════
        # STAGE 4+5+6: JUDGE → RAG RETRIEVAL → VALIDATE → SCORE
        # ═══════════════════════════════════════════
        for item in top_picks:
            issue = item['data']
            safe_body = issue.get('body') or ""
            repo_ctx = repo_contexts.get(item['repo'], {})
            commit_sha = repo_commits.get(item['repo'], "")
            
            stats.judged += 1
            
            # --- STAGE 3.5: RAG Retrieve Code Evidence ---
            retrieved_code = ""
            retrieved_chunk_ids = []
            retrieval_method = "NONE"
            
            if commit_sha:
                try:
                    retrieved_code, retrieved_chunk_ids = retrieve_code_for_issue(
                        supabase, item['repo'], commit_sha, issue['title'], safe_body
                    )
                    if retrieved_chunk_ids:
                        retrieval_method = "RRF"
                except Exception as retrieve_err:
                    print(f"      ⚠️ RAG retrieval failed: {retrieve_err}")
            
            # --- STAGE 4: LLM Tactical Plan ---
            ai_response, provider_name, model_name = evaluate_and_enrich(
                issue['title'], 
                safe_body, 
                item['repo'], 
                item['analysis']['difficulty'],
                repo_ctx,
                retrieved_code=retrieved_code
            )
            
            if not ai_response:
                continue
            
            try:
                judgement = json.loads(ai_response)
                
                if judgement.get('verified_difficulty') == "Reject": 
                    print(f"      🚫 Rejected: {issue['title'][:40]}...")
                    stats.rejected += 1
                    continue
                
                hint_text = judgement.get('hint', '')
                
                # --- STAGE 6: POST-VALIDATION & RETRY LOOP ---
                repo_language = repo_ctx.get('language', 'Unknown')
                valid, failures = validate_llama_output(hint_text, repo_language)
                
                retries = 0
                while not valid and retries < MAX_RETRIES:
                    retries += 1
                    stats.retried += 1
                    print(f"      🔄 Retrying {retries}/{MAX_RETRIES} (failures: {', '.join(failures[:2])})")
                    
                    ai_response_retry, retry_provider, retry_model = evaluate_and_enrich(
                        issue['title'], safe_body, item['repo'],
                        item['analysis']['difficulty'], repo_ctx,
                        retrieved_code=retrieved_code,
                        retry_feedback=failures
                    )
                    
                    if ai_response_retry:
                        try:
                            judgement_retry = json.loads(ai_response_retry)
                            hint_retry = judgement_retry.get('hint', '')
                            # Re-validate the retry output
                            valid_retry, failures_retry = validate_llama_output(hint_retry, repo_language)
                            
                            if valid_retry:
                                judgement = judgement_retry
                                hint_text = hint_retry
                                valid = True
                                stats.retry_saved += 1
                                provider_name = retry_provider
                                model_name = retry_model
                                print(f"      ✅ Retry {retries} succeeded!")
                                break
                            else:
                                failures = failures_retry
                                print(f"      ❌ Retry {retries} failed validation.")
                        except Exception:
                            print(f"      ❌ Retry parse error.")
                            break
                    else:
                        break
                        
                if not valid:
                    print(f"      🛑 All {MAX_RETRIES} retries exhausted. Rejecting issue.")
                    stats.rejected += 1
                    continue
                
                stats.validated += 1
                
                # --- STAGE 6: QUALITY SCORING (NEW) ---
                quality = compute_quality_score(hint_text, repo_ctx)
                
                if quality['grade'] == "High":
                    stats.quality_high += 1
                elif quality['grade'] == "Medium":
                    stats.quality_medium += 1
                else:
                    stats.quality_low += 1
                
                final_record = {
                    "id": issue['id'],
                    "title": issue['title'],
                    "repo_name": item['repo'],
                    "difficulty": judgement.get('verified_difficulty', item['analysis']['difficulty']),
                    "ai_score": item['analysis']['score'],
                    "ai_hint": hint_text,
                    "category": category,
                    "url": issue['html_url'],
                    "status": "PUBLISHED",
                    "created_at": issue['created_at'],
                    
                    # RAG Metadata Columns:
                    "github_issue_number": issue.get('number'),
                    "github_issue_updated_at": issue.get('updated_at'),
                    "repo_commit_sha": commit_sha,
                    "retrieved_chunk_ids": retrieved_chunk_ids,
                    "retrieval_method": retrieval_method,
                    "model_provider": provider_name,
                    "model_name": model_name,
                    "prompt_version": "v3-grounded",
                    "quality_score": quality.get('overall', 0.0),
                    "quality_grade": quality.get('grade', 'Low')
                }
                
                if DRY_RUN:
                    print(f"      📝 [Dry Run] {quality['grade']}({quality['overall']}) | {issue['title'][:35]}...")
                else:
                    supabase.table("issues").upsert(final_record).execute()
                    print(f"      ✅ Published: {quality['grade']}({quality['overall']}) | {issue['title'][:35]}...")
                    stats.published += 1
                    
            except Exception as e:
                print(f"      ⚠️ Integration Error: {e}")

    stats.print_summary()


if __name__ == "__main__":
    run_pipeline()