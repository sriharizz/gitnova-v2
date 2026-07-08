# backend/scripts/expand_fastapi_golden.py
"""
Expands the golden_set.csv with more fastapi/fastapi issues.
Scans pages 11-25 of closed fastapi issues to find ~7 more merged PRs,
bringing us to ~10 total fastapi rows.
Does NOT look at facebook/react to keep eval focused.
"""
import os
import sys
import csv
import time
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
load_dotenv()

github_token = os.getenv("GITHUB_TOKEN")
headers = {
    "Authorization": f"token {github_token}",
    "Accept": "application/vnd.github.v3+json"
}

REPO = "fastapi/fastapi"
TARGET_NEW_ROWS = 8    # We already have 3 fastapi rows — want ~8 more = 11 total
SCAN_PAGES = range(11, 26)  # Pages 11-25 of closed issues

# Rules: only index real source code files, not docs
EXCLUDE_PREFIXES = ("docs/", "docs_src/", ".github/", "scripts/", "requirements")
CORE_EXTENSIONS = (".py",)


def get_linked_pr(repo, issue_number):
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/timeline"
    r = requests.get(url, headers={**headers, "Accept": "application/vnd.github.mockingbird-preview+json"}, timeout=10)
    if r.status_code != 200:
        return None, None
    for event in r.json():
        if event.get("event") in ("cross-referenced", "connected"):
            src = event.get("source", {})
            pr_info = src.get("issue", {})
            if pr_info.get("pull_request"):
                pr_url = pr_info["pull_request"].get("url", "")
                pr_num = int(pr_url.split("/")[-1]) if pr_url else None
                return pr_num, pr_url
    return None, None


def check_pr_merged(repo, pr_num):
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_num}"
    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code != 200:
        return False
    return r.json().get("merged", False)


def get_pr_changed_files(repo, pr_num):
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_num}/files"
    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code != 200:
        return []
    return [f["filename"] for f in r.json()]


def select_core_files(changed_files):
    """
    Pick implementation files only — skip docs_src, tests, config.
    General rule: keep .py files not in excluded prefixes.
    """
    core = []
    for f in changed_files:
        f_lower = f.lower()
        if any(f_lower.startswith(p) for p in EXCLUDE_PREFIXES):
            continue
        if any(f_lower.endswith(e) for e in CORE_EXTENSIONS):
            if "test" not in f_lower:
                core.append(f)
    return core if core else changed_files[:1]   # fallback: first changed file


def main():
    print(f"🔍 Scanning fastapi/fastapi for more golden issues (pages 11-25)...")

    new_rows = []

    for page in SCAN_PAGES:
        if len(new_rows) >= TARGET_NEW_ROWS:
            break

        print(f"   Page {page}...")
        url = f"https://api.github.com/repos/{REPO}/issues?state=closed&per_page=100&page={page}"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200 or not r.json():
            break

        for issue in r.json():
            if len(new_rows) >= TARGET_NEW_ROWS:
                break
            if "pull_request" in issue:
                continue

            issue_number = issue["number"]
            issue_title = issue["title"]
            issue_id = issue["id"]

            pr_num, _ = get_linked_pr(REPO, issue_number)
            if not pr_num:
                continue
            if not check_pr_merged(REPO, pr_num):
                continue

            changed = get_pr_changed_files(REPO, pr_num)
            if not changed:
                continue

            core = select_core_files(changed)
            print(f"      [#{issue_number}] {issue_title[:55]}...")
            print(f"         Fix files: {core}")

            new_rows.append({
                "issue_id": issue_id,
                "issue_title": issue_title,
                "repo": REPO,
                "ground_truth_files": ",".join(core)
            })

            time.sleep(0.5)

    # Append to CSV
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'golden_set.csv')
    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["issue_id", "issue_title", "repo", "ground_truth_files"])
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_rows)

    print(f"\n✅ Added {len(new_rows)} new fastapi rows to golden_set.csv.")

if __name__ == "__main__":
    main()
