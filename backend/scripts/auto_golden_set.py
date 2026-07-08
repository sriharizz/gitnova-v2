# backend/scripts/auto_golden_set.py
"""
Task 4: Auto-Expanding Golden Set

This script harvests recently merged Pull Requests from our target repos,
links them to closed issues, resolves the files changed in the PR, and
appends them as new rows to golden_set.csv.

This creates a continuously growing, self-improving evaluation dataset
based on real-world ground truth, completely eliminating manual labeling.
"""
import os
import re
import csv
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.pipeline.github_client import GitHubClient

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

CSV_PATH = "golden_set.csv"

# Target repos to harvest PRs from
HARVEST_REPOS = [
    "fastapi/fastapi",
    "pallets/flask",
    "django/django"
]


def parse_linked_issue_ids(pr_body: str) -> list:
    """
    Parses GitHub keyword linking syntax (e.g. 'fixes #123', 'closes #456')
    to find associated closed issue IDs.
    """
    if not pr_body:
        return []
    
    # Matches: fixes #123, fixed #123, close #123, closed #123, resolves #123, resolved #123
    pattern = r'(?:close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)\s+#(\d+)'
    matches = re.findall(pattern, pr_body, re.IGNORECASE)
    return [int(m) for m in matches]


def filter_fix_files(files: list, repo_lang: str = "python") -> list:
    """
    Filters out documentation, tests, scripts, and configuration files.
    We only want actual source code files that represent the code fix.
    """
    valid_exts = {
        "python": [".py"],
        "javascript": [".js", ".jsx", ".ts", ".tsx"]
    }
    
    exts = valid_exts.get(repo_lang.lower(), [".py"])
    filtered = []
    
    for f in files:
        path = f.lower()
        # Exclude common non-source directories
        if any(x in path for x in ["docs/", "tests/", "test/", "scripts/", ".github/", "docs_src/"]):
            continue
        # Check extensions
        if any(path.endswith(ext) for ext in exts):
            filtered.append(f)
            
    return filtered


def main():
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("❌ Error: GITHUB_TOKEN is missing from .env")
        sys.exit(1)

    # Initialize GitHub client without DB (read-only harvest operations)
    gh_client = GitHubClient(token=token)
    
    # Load existing issues to avoid duplicates
    existing_ids = set()
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_ids.add(row["issue_id"])

    new_entries = []
    
    # Lookback window: pull PRs merged in the last 14 days
    since_date = (datetime.now() - timedelta(days=14)).isoformat() + "Z"
    
    print(f"🌾 Harvesting merged PRs since {since_date[:10]}...")

    for repo in HARVEST_REPOS:
        print(f"\nScanning repository: {repo}")
        try:
            # Fetch closed PRs
            url = f"https://api.github.com/repos/{repo}/pulls?state=closed&per_page=30&sort=updated&direction=desc"
            prs = gh_client.get(url)
            if not prs or not isinstance(prs, list):
                print(f"   ⚠️ No PRs returned for {repo}")
                continue
                
            print(f"   Fetched {len(prs)} closed PRs. Filtering merged ones...")
            
            for pr in prs:
                # Check if it was actually merged (closed != merged)
                if not pr.get("merged_at"):
                    continue
                    
                pr_number = pr["number"]
                body = pr.get("body") or ""
                linked_issues = parse_linked_issue_ids(body)
                
                if not linked_issues:
                    continue
                
                print(f"   🔍 PR #{pr_number} merged. Links to issue(s): {linked_issues}")
                
                # Fetch changed files
                files_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files?per_page=50"
                pr_files_data = gh_client.get(files_url)
                
                if not pr_files_data or not isinstance(pr_files_data, list):
                    continue
                    
                raw_paths = [f["filename"] for f in pr_files_data]
                fix_files = filter_fix_files(raw_paths)
                
                if not fix_files:
                    print(f"      ⏭️  No source code changes found (only docs/tests). Skipping.")
                    continue
                    
                # Map linked issues to golden set records
                for issue_id in linked_issues:
                    issue_str_id = f"{repo}#{issue_id}"
                    if issue_str_id in existing_ids:
                        continue
                        
                    # Fetch issue details for the title
                    try:
                        issue_url = f"https://api.github.com/repos/{repo}/issues/{issue_id}"
                        issue_data = gh_client.get(issue_url)
                        title = issue_data.get("title", f"Issue #{issue_id}")
                    except Exception:
                        title = f"Issue #{issue_id}"
                        
                    new_entries.append({
                        "issue_id": issue_str_id,
                        "issue_title": title,
                        "repo": repo,
                        "ground_truth_files": ",".join(fix_files)
                    })
                    existing_ids.add(issue_str_id)
                    print(f"      ✨ Added new golden scenario: {issue_str_id} -> {fix_files}")
                    
        except Exception as e:
            print(f"   ❌ Error harvesting {repo}: {e}")

    # Append new entries to golden_set.csv
    if new_entries:
        write_header = not os.path.exists(CSV_PATH)
        with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["issue_id", "issue_title", "repo", "ground_truth_files"])
            if write_header:
                writer.writeheader()
            for entry in new_entries:
                writer.writerow(entry)
        print(f"\n💾 Saved {len(new_entries)} new golden scenarios to {CSV_PATH}.")
    else:
        print("\n🌾 Harvesting finished. No new scenarios discovered.")


if __name__ == "__main__":
    main()
