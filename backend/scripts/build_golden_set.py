import os
import sys
import csv
import json
import time
import requests
from dotenv import load_dotenv
from openai import OpenAI
from groq import Groq

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

load_dotenv()

# Setup API clients
github_token = os.getenv("GITHUB_TOKEN")
if not github_token:
    print("Error: GITHUB_TOKEN missing.")
    sys.exit(1)

headers = {
    "Authorization": f"token {github_token}",
    "Accept": "application/vnd.github.v3+json"
}

# LLM Gateway
nvidia_key = os.getenv("NVIDIA_API_KEY")
nvidia_client = None
if nvidia_key:
    nvidia_client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=nvidia_key)

groq_key = os.getenv("GROQ_API_KEY")
groq = Groq(api_key=groq_key) if groq_key else None

def get_linked_pr(repo: str, issue_number: int) -> tuple:
    """
    Find the PR that closed an issue by querying its timeline events.
    Returns (pr_number, pr_html_url) or (None, None).
    """
    # Use the mockinbird-preview header to get connected events
    timeline_headers = headers.copy()
    timeline_headers["Accept"] = "application/vnd.github.mockingbird-preview"
    
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/timeline"
    try:
        r = requests.get(url, headers=timeline_headers, timeout=10)
        if r.status_code != 200:
            return None, None
            
        events = r.json()
        for event in events:
            # Check for connected or cross-referenced events
            if event.get("event") in ["connected", "cross-referenced"]:
                source = event.get("source", {})
                if source.get("type") == "issue":
                    issue_info = source.get("issue", {})
                    if "pull_request" in issue_info:
                        pr_url = issue_info["pull_request"].get("url", "")
                        # Normalize repository comparison to handle redirects (e.g., facebook/react -> react/react)
                        url_parts = pr_url.split("/")
                        if len(url_parts) >= 5:
                            # url_parts format: ['https:', '', 'api.github.com', 'repos', 'owner', 'name', 'pulls', 'number']
                            pr_owner = url_parts[-4].lower()
                            pr_name = url_parts[-3].lower()
                            target_name = repo.split("/")[-1].lower()
                            if pr_name == target_name:
                                pr_num = issue_info.get("number")
                                pr_html = issue_info["pull_request"].get("html_url")
                                return pr_num, pr_html
                # If there's a commit, we could query the commit to see if it belongs to a PR,
                # but timeline connected events are the most direct.
                pass
    except Exception as e:
        print(f"Error fetching timeline for {repo}#{issue_number}: {e}")
    return None, None

def check_pr_merged(repo: str, pr_number: int) -> bool:
    """Checks the PR merge status directly from the GitHub API."""
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json().get("merged") == True
    except Exception as e:
        print(f"Error checking PR merge status: {e}")
    return False

def get_pr_changed_files(repo: str, pr_number: int) -> list:
    """Fetches the list of files changed in a PR."""
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files?per_page=100"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return [f.get("filename") for f in r.json()]
    except Exception as e:
        print(f"Error fetching changed files: {e}")
    return []

def select_core_files_with_llm(issue_title: str, file_paths: list) -> list:
    """
    Uses the LLM Gateway to select the 1-2 core fix files from a list of modified files.
    Filters out obvious test/configuration/docs files first.
    """
    # 1. Basic deterministic filtering
    filtered_paths = []
    for path in file_paths:
        path_lower = path.lower()
        if any(x in path_lower for x in ["test", "tests", "docs", "example", ".github", "package.json", "poetry.lock", "setup.py", "requirements.txt", ".md"]):
            continue
        filtered_paths.append(path)
        
    # If no files left or only 1-2, return them directly without LLM
    if not filtered_paths:
        return file_paths[:2]
    if len(filtered_paths) <= 2:
        return filtered_paths

    # 2. LLM Judgment Step
    prompt = f"""You are a senior code reviewer. An issue titled: "{issue_title}" was fixed by a Pull Request that changed the following files:
{json.dumps(filtered_paths, indent=2)}

Please analyze which 1 or 2 files contain the CORE implementation fix (not boilerplate, configuration, docstrings, or structural changes).
Return a JSON object in this format:
{{
  "core_files": ["path/to/file1.py"]
}}
"""

    models = []
    if nvidia_client:
        models.append({"client": nvidia_client, "name": "meta/llama-3.3-70b-instruct"})
    if groq:
        models.extend([
            {"client": groq, "name": "llama-3.3-70b-versatile"},
            {"client": groq, "name": "llama-3.1-8b-instant"}
        ])

    for model in models:
        try:
            r = model["client"].chat.completions.create(
                model=model["name"],
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            data = json.loads(r.choices[0].message.content)
            core = data.get("core_files", [])
            if core:
                return [c for c in core if c in filtered_paths]
        except Exception as e:
            print(f"LLM Error on {model['name']}: {e}")
            continue
            
    # Fallback if LLM fails
    return filtered_paths[:2]

def build_golden_set():
    print("🚀 Starting Golden Set Extractor...")
    repos = ["fastapi/fastapi", "facebook/react"]
    golden_rows = []
    target_count = 15
    
    for repo in repos:
        if len(golden_rows) >= target_count:
            break
            
        print(f"\nScanning closed issues for {repo}...")
        for page in range(6, 11):
            if len(golden_rows) >= target_count:
                break
                
            print(f"   Fetching page {page} of closed issues...")
            url = f"https://api.github.com/repos/{repo}/issues?state=closed&per_page=100&page={page}"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                print(f"Error fetching issues on page {page}: {r.status_code}")
                break
                
            issues = r.json()
            if not issues:
                break
                
            for issue in issues:
                if len(golden_rows) >= target_count:
                    break
                    
                # Skip PRs that are returned in the issues endpoint
                if "pull_request" in issue:
                    continue
                    
                issue_number = issue.get("number")
                issue_title = issue.get("title")
                issue_id = issue.get("id")
                
                # 1. Get linked PR
                pr_num, pr_url = get_linked_pr(repo, issue_number)
                if not pr_num:
                    continue
                    
                # 2. Check if merged
                if not check_pr_merged(repo, pr_num):
                    continue
                    
                print(f"      [#{issue_number}] Found merged PR #{pr_num}: {issue_title[:45]}...")
                
                # 3. Get changed files
                changed_files = get_pr_changed_files(repo, pr_num)
                if not changed_files:
                    continue
                    
                # 4. Extract core fix files (LLM + rules)
                core_files = select_core_files_with_llm(issue_title, changed_files)
                print(f"      Core fix files identified: {core_files}")
                
                golden_rows.append({
                    "issue_id": issue_id,
                    "issue_title": issue_title,
                    "repo": repo,
                    "ground_truth_files": ",".join(core_files)
                })
                
                # Rate limiting safety sleep
                time.sleep(1)

    # Append to CSV
    csv_path = "golden_set.csv"
    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["issue_id", "issue_title", "repo", "ground_truth_files"])
        if not file_exists:
            writer.writeheader()
        writer.writerows(golden_rows)
        
    print(f"\n🎉 Finished! Golden set appended to {csv_path} with {len(golden_rows)} new rows.")

if __name__ == "__main__":
    build_golden_set()
