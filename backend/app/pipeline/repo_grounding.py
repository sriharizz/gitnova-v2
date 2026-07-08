"""
GitNova Repository Grounding
=============================
Fetches repo metadata from GitHub API and caches it per pipeline run.
Provides language, description, topics, and top-level directory names
to ground the LLM prompt in reality.
"""

import os
import requests

# In-memory cache: repo_name -> context dict
_repo_cache = {}

# Language -> common file extensions mapping
LANGUAGE_EXTENSIONS = {
    "python": [".py"],
    "javascript": [".js", ".jsx", ".mjs"],
    "typescript": [".ts", ".tsx"],
    "java": [".java"],
    "kotlin": [".kt", ".kts"],
    "go": [".go"],
    "rust": [".rs"],
    "ruby": [".rb"],
    "swift": [".swift"],
    "c": [".c", ".h"],
    "c++": [".cpp", ".cc", ".cxx", ".h", ".hpp"],
    "c#": [".cs"],
    "php": [".php"],
    "dart": [".dart"],
    "scala": [".scala"],
    "shell": [".sh", ".bash"],
    "objective-c": [".m", ".h"],
    "hcl": [".tf", ".hcl"],
    "html": [".html", ".htm"],
    "css": [".css", ".scss", ".less"],
}


def get_repo_context(repo_name: str) -> dict:
    """
    Fetch and cache repo metadata from GitHub API.
    
    Returns:
        {
            "language": "Python",
            "language_lower": "python",
            "valid_extensions": [".py"],
            "description": "...",
            "topics": ["ml", "deep-learning"],
            "top_dirs": ["src/", "tests/", "docs/"],
            "grounding_block": "Repository: ...\nLanguage: ...\n..."
        }
    """
    if repo_name in _repo_cache:
        return _repo_cache[repo_name]
    
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"} if token else {}
    
    context = {
        "language": "Unknown",
        "language_lower": "unknown",
        "valid_extensions": [],
        "description": "",
        "topics": [],
        "top_dirs": [],
        "grounding_block": "",
        "default_branch": "main",
    }
    
    try:
        # Fetch repo metadata
        resp = requests.get(f"https://api.github.com/repos/{repo_name}", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            lang = data.get("language") or "Unknown"
            context["language"] = lang
            context["language_lower"] = lang.lower()
            context["description"] = data.get("description") or ""
            context["topics"] = data.get("topics") or []
            context["valid_extensions"] = LANGUAGE_EXTENSIONS.get(lang.lower(), [])
            context["default_branch"] = data.get("default_branch") or "main"
        
        # Fetch top-level directory listing
        tree_resp = requests.get(
            f"https://api.github.com/repos/{repo_name}/contents/",
            headers=headers, timeout=10
        )
        if tree_resp.status_code == 200:
            items = tree_resp.json()
            if isinstance(items, list):
                dirs = [item["name"] + "/" for item in items if item.get("type") == "dir"]
                context["top_dirs"] = dirs[:7]  # Top 7 directories
    
    except Exception as e:
        print(f"      ⚠️ Repo grounding failed for {repo_name}: {e}")
    
    # Build the grounding block
    context["grounding_block"] = _build_grounding_block(repo_name, context)
    
    _repo_cache[repo_name] = context
    return context


def get_repo_context_from_name(repo_name: str) -> dict:
    """
    Quick context lookup for retroactive CSV filtering.
    Only fetches the language (lightweight).
    """
    if repo_name in _repo_cache:
        return _repo_cache[repo_name]
    
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Authorization": f"token {token}"} if token else {}
    
    context = {
        "language": "Unknown",
        "language_lower": "unknown",
        "valid_extensions": [],
    }
    
    try:
        resp = requests.get(f"https://api.github.com/repos/{repo_name}", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            lang = data.get("language") or "Unknown"
            context["language"] = lang
            context["language_lower"] = lang.lower()
            context["valid_extensions"] = LANGUAGE_EXTENSIONS.get(lang.lower(), [])
    except Exception:
        pass
    
    _repo_cache[repo_name] = context
    return context


def clear_cache():
    """Clear the repo context cache (call between pipeline runs)."""
    _repo_cache.clear()


def _build_grounding_block(repo_name: str, ctx: dict) -> str:
    lines = [
        f"Repository: {repo_name}",
        f"Language: {ctx['language']}",
    ]
    if ctx["description"]:
        lines.append(f"Description: {ctx['description']}")
    if ctx["topics"]:
        lines.append(f"Topics: {', '.join(ctx['topics'])}")
    if ctx["top_dirs"]:
        lines.append(f"Top Directories: {', '.join(ctx['top_dirs'])}")
    
    # Add strict language grounding instruction
    if ctx["language"] and ctx["language"].lower() != "unknown":
        lines.append(f"\nCRITICAL: This repository is primarily written in {ctx['language']}.")
        lines.append(f"You MUST ONLY suggest files and logic that match this language ecosystem.")
        lines.append(f"Do not suggest web-dev files (.ts, .tsx) for a Python/C++ codebase.")
    
    return "\n".join(lines)
