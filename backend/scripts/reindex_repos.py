# backend/scripts/reindex_repos.py
"""
One-time indexing script for ALL tracked repositories.

This runs SEPARATELY from the daily pipeline. The daily cron (daily_pipeline.yml)
only reads existing snapshots — it never indexes.

Usage:
    cd backend
    python scripts/reindex_repos.py          # Index all repos
    python scripts/reindex_repos.py --repo fastapi/fastapi  # Index one repo

What it does:
  1. For each repo, checks if an ACTIVE snapshot exists at the current HEAD SHA
  2. If yes → skips (already indexed)
  3. If no → downloads top 50 files, chunks, embeds via Jina, saves to Supabase

Run this locally the first time (takes 4-6 hours for 65 repos).
After that, only new repos or stale ones need re-indexing.
"""
import os
import sys
import argparse
from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.pipeline.code_indexer import ensure_repo_indexed
from app.pipeline.repo_grounding import get_repo_context
from app.pipeline.github_client import GitHubClient

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Same repo list as main.py — kept in sync
ALL_REPOS = [
    # Frontend
    "facebook/react", "shadcn-ui/ui", "vercel/next.js",
    "tailwindlabs/tailwindcss", "mui/material-ui", "sveltejs/svelte",
    "vuejs/core", "remix-run/remix", "solidjs/solid", "withastro/astro",
    "freeCodeCamp/freeCodeCamp", "storybookjs/storybook", "appsmithorg/appsmith",
    # Machine Learning
    "pytorch/pytorch", "huggingface/transformers", "langchain-ai/langchain",
    "tensorflow/tensorflow", "karpathy/nanoGPT", "openai/whisper",
    "microsoft/DeepSpeed", "ray-project/ray", "huggingface/diffusers",
    "scikit-learn/scikit-learn", "keras-team/keras", "streamlit/streamlit",
    # Backend
    "fastapi/fastapi", "django/django", "nestjs/nest", "expressjs/express",
    "tiangolo/sqlmodel", "pallets/flask", "rails/rails", "laravel/laravel",
    "strapi/strapi", "go-gorm/gorm", "RocketChat/Rocket.Chat",
    "supabase/supabase", "redis/redis",
    # DevOps
    "microsoft/vscode", "docker/cli", "kubernetes/kubernetes",
    "ansible/ansible", "prometheus/prometheus", "grafana/grafana",
    "hashicorp/terraform", "jenkinsci/jenkins", "gitlabhq/gitlabhq",
    "elastic/elasticsearch", "moby/moby",
    # Data Science
    "pandas-dev/pandas", "apache/spark", "apache/arrow",
    "plotly/plotly.py", "matplotlib/matplotlib", "ydataai/ydata-profiling",
    "seleniumhq/selenium", "scrapy/scrapy",
    # Mobile
    "flutter/flutter", "facebook/react-native", "ionic-team/ionic-framework",
    "expo/expo", "airbnb/lottie-android", "square/retrofit",
    "realm/realm-swift", "skylot/jadx"
]


def main():
    parser = argparse.ArgumentParser(description="Index repositories for GitNova RAG")
    parser.add_argument("--repo", type=str, help="Index a specific repo (e.g. fastapi/fastapi)")
    args = parser.parse_args()

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    github_token = os.getenv("GITHUB_TOKEN")

    if not supabase_url or not supabase_key:
        print("❌ Error: SUPABASE_URL or SUPABASE_KEY missing from .env")
        sys.exit(1)

    supabase = create_client(supabase_url, supabase_key)
    github_client = GitHubClient(token=github_token, supabase_client=supabase)

    repos_to_index = [args.repo] if args.repo else ALL_REPOS

    print(f"🔄 Indexing {len(repos_to_index)} repositories...")
    print(f"   Already-indexed repos will be skipped automatically.\n")

    indexed = 0
    skipped = 0
    failed = 0

    for i, repo in enumerate(repos_to_index):
        print(f"\n[{i+1}/{len(repos_to_index)}] {repo}")
        try:
            repo_ctx = get_repo_context(repo)
            commit_sha = ensure_repo_indexed(supabase, github_client, repo, repo_ctx, issues=[])
            if commit_sha:
                indexed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"   ❌ Error: {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"📊 INDEXING COMPLETE")
    print(f"   ✅ Indexed/Fresh: {indexed}")
    print(f"   ❌ Failed: {failed}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
