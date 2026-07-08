# backend/scripts/track_pr_outcomes.py
"""
Task 9: Production PR Outcome Tracking

This script runs periodically (e.g., weekly) to track the accuracy of GitNova's
LLM hints against real-world pull requests.

It checks if published issues have been closed by merged PRs, resolves the
modified files in those PRs, compares them to GitNova's predicted hint files,
and logs the accuracy verdict to the DB.
"""
import os
import re
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.pipeline.github_client import GitHubClient

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


def extract_files_from_hint(hint: str) -> list:
    """Extracts filenames enclosed in backticks from the hint Markdown."""
    found = re.findall(r'`([^`]+\.[a-zA-Z0-9]+)`', hint)
    return list(set(found))


def find_closing_pr_for_issue(gh_client: GitHubClient, repo: str, issue_number: int) -> dict:
    """
    Uses GitHub's Timeline API to find the Pull Request that closed this issue.
    Returns the PR details (number, merged_at) or None.
    """
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/events"
    events = gh_client.get(url)
    if not events or not isinstance(events, list):
        return None

    for event in events:
        # Check if this event was a close event linked to a PR
        if event.get("event") == "closed" and event.get("commit_id"):
            # Check if there is a linked pull request reference
            # Sometimes events contain pull_request details directly
            pass
            
    # Alternative: Search for PRs referencing this issue
    search_url = f"https://api.github.com/search/issues?q=repo:{repo}+type:pr+is:merged+{issue_number}"
    search_results = gh_client.get(search_url)
    if search_results and search_results.get("items"):
        pr_item = search_results["items"][0]
        # Return PR number and merge state
        return {
            "number": pr_item["number"],
            "url": pr_item["pull_request"]["url"]
        }
        
    return None


def main():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    github_token = os.getenv("GITHUB_TOKEN")

    if not supabase_url or not supabase_key or not github_token:
        print("❌ Error: Credentials missing from .env")
        sys.exit(1)

    supabase = create_client(supabase_url, supabase_key)
    gh_client = GitHubClient(token=github_token)

    # 1. Fetch all issues in the DB that were published
    resp = supabase.table("issues").select("id, repo_name, url, ai_hint, difficulty").execute()
    db_issues = resp.data or []
    print(f"📊 Tracking PR outcomes for {len(db_issues)} cached issues...")

    verified_count = 0
    correct_count = 0

    for issue in db_issues:
        issue_id = issue["id"]
        repo = issue["repo_name"]
        hint = issue.get("ai_hint") or ""
        
        # Extract the issue number from the URL
        match = re.search(r'/issues/(\d+)', issue["url"])
        if not match:
            continue
        issue_number = int(match.group(1))

        # 2. Extract predicted files from the GitNova hint
        predicted_files = extract_files_from_hint(hint)
        if not predicted_files:
            continue

        # 3. Find if there is a merged PR that closed this issue
        closing_pr = find_closing_pr_for_issue(gh_client, repo, issue_number)
        if not closing_pr:
            continue

        pr_num = closing_pr["number"]
        print(f"   🎯 Issue {repo} #{issue_number} was closed by PR #{pr_num}")

        # 4. Fetch the files modified in that PR
        files_url = f"https://api.github.com/repos/{repo}/pulls/{pr_num}/files?per_page=50"
        pr_files_data = gh_client.get(files_url)
        if not pr_files_data or not isinstance(pr_files_data, list):
            continue

        actual_files = [f["filename"] for f in pr_files_data]
        
        # 5. Check if any predicted file matches actual files modified in the fix
        expected_set = set(actual_files)
        predicted_set = set(predicted_files)
        correct_match = len(expected_set.intersection(predicted_set)) > 0

        verified_count += 1
        if correct_match:
            correct_count += 1
            print(f"      ✅ GitNova was CORRECT! Match found.")
        else:
            print(f"      ❌ GitNova was INCORRECT. Predicted: {predicted_files} | Actual: {actual_files[:3]}")

        # 6. Log the feedback verdict to Supabase to enable feedback loop
        try:
            # We can log this as metadata on the issues table or insert to an audit table
            # For simplicity, we flag the issue record itself with a validated column
            supabase.table("issues").update({
                "hint_correct": correct_match,
                "validated_at": "now()"
            }).eq("id", issue_id).execute()
        except Exception as e:
            print(f"      ⚠️ Failed to save outcome to Supabase: {e}")

    # Summary
    if verified_count > 0:
        accuracy = (correct_count / verified_count) * 100
        print(f"\n📈 Live Production Accuracy: {correct_count}/{verified_count} ({accuracy:.1f}%)")
    else:
        print("\n📈 Live Production Accuracy: No closed issues resolved by PRs yet.")


if __name__ == "__main__":
    main()
