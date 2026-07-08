# backend/app/pipeline/code_indexer.py
import os
import re
import ast
import time
import hashlib
import requests
from typing import List, Dict, Any, Optional
from app.pipeline.github_client import GitHubClient

# ── Configurable budget ────────────────────────────────────────────────────────
# 50 files × ~10 chunks × ~2.5 KB/chunk ≈ 1.25 MB per repo — well within limits.
# Raised from original 25; safe upper bound for CPU-only embedding machines.
MAX_INDEX_FILES: int = 50
# ──────────────────────────────────────────────────────────────────────────────


# ── Jina Embeddings API ───────────────────────────────────────────────────────
# We call Jina's cloud API instead of running the model locally on CPU.
# Why: local CPU inference takes 8-10 hours for 65 repos.
#      Jina API (same model) takes ~15-20 minutes — 50x faster.
# Free tier: 10 million tokens — enough for full initial index + ~10 months.
JINA_API_URL = "https://api.jina.ai/v1/embeddings"
JINA_MODEL   = "jina-embeddings-v2-base-code"


def _embed_via_api(texts: List[str]) -> List[List[float]]:
    """
    Sends a batch of texts to the Jina Embeddings API and returns their vectors.

    Each text becomes a 768-dimensional float vector — the same format as the
    local model produced, so all existing Supabase vector search RPCs still work.

    Retries up to 3 times on transient errors (rate limits, network blips).
    """
    api_key = os.getenv("JINA_API_KEY")
    if not api_key:
        raise RuntimeError("JINA_API_KEY missing from .env — cannot embed chunks.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": JINA_MODEL,
        "input": texts,
    }

    for attempt in range(1, 4):  # 3 attempts
        try:
            resp = requests.post(JINA_API_URL, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                data = resp.json()["data"]
                # API returns embeddings in the same order as input texts
                return [item["embedding"] for item in data]
            elif resp.status_code == 429:  # Rate limit
                wait = 2 ** attempt  # 2s, 4s, 8s
                print(f"   ⚠️ Jina API rate limit hit. Waiting {wait}s... (attempt {attempt}/3)")
                time.sleep(wait)
            else:
                raise RuntimeError(f"Jina API error {resp.status_code}: {resp.text[:200]}")
        except requests.exceptions.RequestException as e:
            if attempt == 3:
                raise RuntimeError(f"Jina API unreachable after 3 attempts: {e}")
            time.sleep(2 ** attempt)

    raise RuntimeError("Jina API failed after 3 retries.")
# ──────────────────────────────────────────────────────────────────────────────



def split_identifiers(text: str) -> str:
    """
    Tokenizes compound names like validate_user_token or validateUser 
    into space-separated sub-words for text search index matching.
    """
    # 1. Replace underscores and dashes with spaces
    words = text.replace("_", " ").replace("-", " ")
    # 2. Insert spaces between camelCase transitions (lowercase to uppercase)
    words = re.sub(r'([a-z])([A-Z])', r'\1 \2', words)
    # 3. Normalize whitespace and lowercase
    return re.sub(r'\s+', ' ', words).lower().strip()


def _chunk_python_code(content: str, file_path: str) -> List[Dict[str, Any]]:
    """
    Uses Python's AST parser to extract classes and functions as complete code units.
    """
    chunks = []
    lines = content.splitlines()
    
    try:
        root = ast.parse(content)
    except SyntaxError as e:
        # Fallback to line-based chunking if syntax is invalid for Python parser
        print(f"⚠️ AST: Syntax error parsing {file_path}: {e}. Falling back to standard lines.")
        return _chunk_generic_code(content, file_path, "python")

    # Inspect top-level nodes (Classes and Functions)
    for node in ast.iter_child_nodes(root):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start_line = node.lineno
            # Determine end line by looking at final statements inside the node
            end_line = getattr(node, "end_lineno", len(lines))
            
            chunk_content = "\n".join(lines[start_line - 1 : end_line])
            words = len(chunk_content.split())
            token_count = int(words * 1.3) # 1 word ≈ 1.3 tokens average for code
            
            # Skip empty or trivially small symbols
            if token_count < 10:
                continue

            chunks.append({
                "symbol_name": node.name,
                "symbol_kind": "class" if isinstance(node, ast.ClassDef) else "function",
                "start_line": start_line,
                "end_line": end_line,
                "content": chunk_content,
                "token_count": token_count
            })

    # If the file has no classes or functions (e.g. flat script), index the entire file as one chunk
    if not chunks and content.strip():
        words = len(content.split())
        chunks.append({
            "symbol_name": "module",
            "symbol_kind": "module",
            "start_line": 1,
            "end_line": len(lines),
            "content": content,
            "token_count": int(words * 1.3)
        })

    return chunks


def _chunk_generic_code(content: str, file_path: str, language: str) -> List[Dict[str, Any]]:
    """
    Fallback regex-based chunker for non-Python languages.
    Splits by method declaration patterns or fixed line blocks (40 lines with 5 line overlaps).
    """
    chunks = []
    lines = content.splitlines()
    
    # Simple sliding line window fallback
    chunk_size = 40
    overlap = 5
    
    i = 0
    while i < len(lines):
        chunk_lines = lines[i : i + chunk_size]
        chunk_content = "\n".join(chunk_lines)
        words = len(chunk_content.split())
        
        chunks.append({
            "symbol_name": f"block_{i + 1}",
            "symbol_kind": "code_block",
            "start_line": i + 1,
            "end_line": min(i + chunk_size, len(lines)),
            "content": chunk_content,
            "token_count": int(words * 1.3)
        })
        i += (chunk_size - overlap)

    return chunks


# Directories that are definitively non-core: docs, tests, generated code, tooling.
# Listed as lowercase path-prefix fragments. Checked via substring on the lowercased path.
EXCLUDE_DIR_PREFIXES = [
    "test/", "tests/", "__tests__/", "spec/",
    "docs/", "docs_src/", "documentation/",
    "examples/", "example/", "samples/", "sample/",
    "benchmarks/", "benchmark/", "fixtures/", "fixture/",
    "node_modules/", "vendor/", "venv/", "env/",
    ".git/", ".github/",
    "dist/", "build/", "out/", "target/",
    "tools/", "scripts/", "playground/",
]

# Config/markup file extensions that are never executable source code.
NON_SOURCE_EXTENSIONS = [
    ".json", ".lock", ".yml", ".yaml", ".toml", ".md",
    ".txt", ".rst", ".csv", ".html", ".css", ".svg",
    ".png", ".jpg", ".gif", ".ico", ".woff", ".ttf",
]


def _path_segments(path: str) -> List[str]:
    """Returns lowercase path segments split by '/'."""
    return path.lower().replace("\\", "/").split("/")


def _has_exact_segment(path_lower: str, segment: str) -> bool:
    """
    True if any directory component of the path equals `segment` exactly.
    Example: 'packages/react/src/index.js' -> True for 'src'.
    Example: 'docs_src/tutorial.py' -> False for 'src'.
    This prevents the substring trap where 'src' matches inside 'docs_src'.
    """
    return segment in _path_segments(path_lower)


def filter_source_files(
    file_paths: List[str],
    valid_extensions: List[str],
    repo_name: str = ""
) -> tuple:
    """
    Filters out tests, docs, configs, lock files, and non-source directories.
    Returns (filtered_files, exclusion_reason_counts) for observability.
    """
    filtered = []
    reason_counts = {}

    for path in file_paths:
        path_lower = path.lower()

        # 1. Skip explicitly excluded directories
        excluded_by = None
        for prefix in EXCLUDE_DIR_PREFIXES:
            if prefix in path_lower:
                excluded_by = prefix.strip("/")
                break

        if excluded_by:
            reason_counts[excluded_by] = reason_counts.get(excluded_by, 0) + 1
            continue

        # 2. Skip non-source file extensions
        if any(path_lower.endswith(ext) for ext in NON_SOURCE_EXTENSIONS):
            reason_counts["non_source_ext"] = reason_counts.get("non_source_ext", 0) + 1
            continue

        # 3. Keep only valid language extensions for this repo
        if not any(path_lower.endswith(ext) for ext in valid_extensions):
            reason_counts["wrong_ext"] = reason_counts.get("wrong_ext", 0) + 1
            continue

        filtered.append(path)

    return filtered, reason_counts


def select_top_structural_files(
    file_paths: List[str],
    count: int = MAX_INDEX_FILES,
    repo_package_name: str = ""
) -> List[str]:
    """
    Ranks files by general importance signals and returns the top `count`.

    Scoring rationale (all signals are repo-general, not tuned to any test set):
      +15  File is inside a directory segment named exactly 'src', 'lib', 'core', or 'app'.
             These are the canonical source roots in virtually every language ecosystem.
      +12  File's top-level directory matches the repo's package name (e.g. 'fastapi/' for
             fastapi/fastapi). In Python and many JS repos, the package folder IS the library.
      +5   File name contains a known architectural keyword (router, model, handler, etc.).
             These are strong proxies for "this file does real work".
      -3   Per '/' depth penalty. Shallower files tend to be more central than deeply nested helpers.
      -8   File is inside a known peripheral sub-project: 'compiler/', 'devtools/', 'playground/',
             'tools/', 'scripts/'. These are legitimate source code but rarely the fix location
             for core bug reports.
    """
    ARCH_KEYWORDS = [
        "router", "routing", "model", "controller", "handler", "middleware",
        "auth", "client", "server", "service", "db", "database", "utils",
        "config", "application", "app", "main", "index", "core", "base",
        "resolver", "dispatcher", "scheduler", "worker", "pipeline",
    ]
    PERIPHERAL_DIRS = ["compiler/", "devtools/", "playground/", "tools/", "scripts/"]

    scored_paths = []
    for path in file_paths:
        score = 0
        path_lower = path.lower()
        segments = _path_segments(path_lower)

        # +15: exact 'src', 'lib', 'core', 'app' directory segment
        if any(_has_exact_segment(path_lower, seg) for seg in ["src", "lib", "core", "app"]):
            score += 15

        # +12: top-level folder matches the repo package name
        if repo_package_name and segments and segments[0] == repo_package_name.lower():
            score += 12

        # +5: architectural keyword in any path segment or filename
        filename = segments[-1] if segments else ""
        if any(kw in filename or kw in path_lower for kw in ARCH_KEYWORDS):
            score += 5

        # -3 per depth level (penalise deeply nested helpers)
        score -= path.count("/") * 3

        # -8: peripheral sub-projects
        if any(d in path_lower for d in PERIPHERAL_DIRS):
            score -= 8

        scored_paths.append((score, path))

    scored_paths.sort(key=lambda x: x[0], reverse=True)
    return [path for _, path in scored_paths[:count]]


def ensure_repo_indexed(supabase_client: Any, github_client: GitHubClient, repo_name: str, repo_context: dict, issues: List[Dict[str, Any]] = []) -> str:
    """
    Checks commit SHA freshness. If stale, crawls, chunks, embeds, and atomically swap indexes.
    Uses multi-signal file selection (structural, stack trace path extraction, and issue term-matching)
    to select the top 25 files.
    Returns the ACTIVE commit SHA on success, or empty string on failure.
    """
    staging_snapshot_id = None
    try:
        default_branch = repo_context.get("default_branch") or "main"
        valid_extensions = repo_context.get("valid_extensions", [".py"])

        # 1. Fetch current repository head commit SHA from GitHub API
        branch_url = f"https://api.github.com/repos/{repo_name}/branches/{default_branch}"
        branch_data = github_client.get(branch_url)
        commit_sha = branch_data["commit"]["sha"]
        
        if not commit_sha:
            print(f"⚠️ Indexer: Could not resolve commit SHA for {repo_name}. Skipping index.")
            return ""

        # 2. Check if an ACTIVE snapshot already exists for this exact commit SHA in Supabase
        active_resp = supabase_client.table("repository_snapshots") \
            .select("commit_sha") \
            .eq("repo_name", repo_name) \
            .eq("commit_sha", commit_sha) \
            .eq("status", "ACTIVE") \
            .execute()

        if active_resp.data:
            print(f"✅ Indexer: {repo_name} is already indexed and fresh at commit {commit_sha[:7]}.")
            return commit_sha

        print(f"🔄 Indexer: Snapshot missing/stale for {repo_name}. Re-indexing at {commit_sha[:7]}...")

        # 3. Create a STAGING snapshot record
        snapshot_record = {
            "repo_name": repo_name,
            "commit_sha": commit_sha,
            "default_branch": default_branch,
            "status": "STAGING",
            "embedding_model": "jinaai/jina-embeddings-v2-base-code",
            "embedding_dimensions": 768,
            "parser_version": "v3-ast"
        }
        
        snap_resp = supabase_client.table("repository_snapshots").insert(snapshot_record).execute()
        if not snap_resp.data:
            raise Exception("Failed to insert STAGING snapshot metadata into database.")
        
        staging_snapshot_id = snap_resp.data[0]["id"]

        # 4. Fetch recursive file tree from GitHub API
        tree_url = f"https://api.github.com/repos/{repo_name}/git/trees/{commit_sha}?recursive=1"
        tree_data = github_client.get(tree_url)
        all_paths = [node["path"] for node in tree_data.get("tree", []) if node.get("type") == "blob"]

        # 5. Filter & Rank files using multi-signal strategy
        # Derive the repo's own package folder name from the repo slug (e.g. 'fastapi' from 'fastapi/fastapi').
        # This is the heuristic that handles Python/JS repos where the library code lives in a
        # top-level folder sharing the repo's name — no hardcoding per repo.
        repo_package_name = repo_name.split("/")[-1] if "/" in repo_name else repo_name

        source_files, exclusion_counts = filter_source_files(all_paths, valid_extensions, repo_name)
        
        # Boost C: Extract paths from stack traces / bodies
        matched_stack_trace_files = set()
        extracted_paths = set()
        if issues:
            escaped_exts = [re.escape(ext) for ext in valid_extensions]
            ext_pattern = "|".join(escaped_exts)
            path_regex = re.compile(rf"[a-zA-Z0-9_\/.-]+(?:{ext_pattern})\b")
            for issue in issues:
                for text in [issue.get("title", ""), issue.get("body", "") or ""]:
                    for match in path_regex.findall(text):
                        clean_path = match.strip().replace("\\", "/").lstrip("/")
                        extracted_paths.add(clean_path)
            
            for path in extracted_paths:
                for src_file in source_files:
                    if src_file.endswith(path) or path.endswith(src_file):
                        matched_stack_trace_files.add(src_file)

        # Boost B: Term matching between issue vocabulary and file names
        file_keyword_scores = {}
        if issues:
            issue_keywords = set()
            for issue in issues:
                text = (issue.get("title", "") + " " + (issue.get("body", "") or "")).lower()
                words = re.findall(r'\b[a-z0-9_-]{3,20}\b', text)
                issue_keywords.update(words)
            
            for src_file in source_files:
                normalized_path = src_file.lower().replace("/", " ").replace("\\", " ").replace(".", " ").replace("_", " ").replace("-", " ")
                path_words = set(normalized_path.split())
                matching = path_words.intersection(issue_keywords)
                if matching:
                    file_keyword_scores[src_file] = len(matching)

        # Priority 1: Stack Trace Files
        selected_files = list(matched_stack_trace_files)
        
        # Priority 2: High keyword matching score files (excluding already selected)
        keyword_files = [f for f in file_keyword_scores.keys() if f not in selected_files]
        keyword_files.sort(key=lambda f: file_keyword_scores[f], reverse=True)
        selected_files.extend(keyword_files)
        
        # Priority 3: Structural Files (ranked by general importance signals)
        remaining_sources = [f for f in source_files if f not in selected_files]
        structural_files = select_top_structural_files(
            remaining_sources,
            count=MAX_INDEX_FILES,
            repo_package_name=repo_package_name
        )
        selected_files.extend(structural_files)
        
        # Cap total files to configurable budget
        target_files = selected_files[:MAX_INDEX_FILES]

        # ── Fix 3: Observability report ─────────────────────────────────────────
        print(f"\n📊 Indexer Selection Report for {repo_name}:")
        print(f"   Total blobs in git tree:      {len(all_paths)}")
        print(f"   After extension/dir filter:   {len(source_files)}")
        if exclusion_counts:
            top_exclusions = sorted(exclusion_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            for reason, cnt in top_exclusions:
                print(f"      Excluded [{reason}]:  {cnt} files")
        print(f"   Files selected for indexing:  {len(target_files)} (budget: {MAX_INDEX_FILES})")
        print(f"   Top 10 files to be indexed:")
        for fp in target_files[:10]:
            print(f"      ✔ {fp}")
        print()
        # ─────────────────────────────────────────────────────────────────────────

        if not target_files:
            print(f"⚠️ Indexer: No valid source code files found for {repo_name}. Retiring staging.")
            # Update status to failed
            supabase_client.table("repository_snapshots").update({"status": "FAILED"}).eq("id", staging_snapshot_id).execute()
            return ""

        # 6. Crawl contents of target files and parse them into chunks
        all_chunks = []
        for path in target_files:
            content_url = f"https://api.github.com/repos/{repo_name}/contents/{path}?ref={commit_sha}"
            try:
                file_metadata = github_client.get(content_url)
                # Decode base64 file content securely
                import base64
                content = base64.b64decode(file_metadata["content"]).decode("utf-8", errors="ignore")
                
                # Choose parser based on language
                if path.endswith(".py"):
                    file_chunks = _chunk_python_code(content, path)
                else:
                    file_chunks = _chunk_generic_code(content, path, repo_context.get("language_lower", "generic"))

                for chunk in file_chunks:
                    # Calculate SHA256 of text content to avoid re-embedding duplicates
                    content_hash = hashlib.sha256(chunk["content"].encode("utf-8")).hexdigest()
                    
                    # Tokenize camelCase/snake_case to split sub-words for lexical indexing
                    fts_text = f"{path} {chunk['symbol_name'] or ''} {chunk['content']}"
                    fts_tokenized = split_identifiers(fts_text)

                    all_chunks.append({
                        "file_path": path,
                        "symbol_name": chunk["symbol_name"],
                        "symbol_kind": chunk["symbol_kind"],
                        "start_line": chunk["start_line"],
                        "end_line": chunk["end_line"],
                        "content": chunk["content"],
                        "content_hash": content_hash,
                        "token_count": chunk["token_count"],
                        "fts_raw": fts_tokenized # Temporary container before SQL tsvector mapping
                    })
            except Exception as e:
                print(f"⚠️ Indexer: Failed to download/parse file {path} from GitHub: {e}")
                continue

        if not all_chunks:
            raise Exception("No code chunks generated successfully.")

        # 7. Generate embeddings via Jina Cloud API (replaces local CPU model).
        #
        # Why API instead of local:
        #   Local CPU inference on 254 chunks takes ~8 minutes.
        #   The Jina API processes the same 254 chunks in ~3-5 seconds.
        #   We still batch at 16 chunks per call to stay within API payload limits.
        #   Each chunk is truncated to 3000 chars — the meaningful semantic window.
        MAX_CHUNK_CHARS  = 3000
        EMBED_BATCH_SIZE = 16

        chunk_texts = [
            f"{c['file_path']} {c['symbol_name'] or ''}\n{c['content']}"[:MAX_CHUNK_CHARS]
            for c in all_chunks
        ]

        print(f"   🌐 Embedding {len(chunk_texts)} chunks via Jina API...")
        embeddings = []
        for batch_start in range(0, len(chunk_texts), EMBED_BATCH_SIZE):
            batch = chunk_texts[batch_start : batch_start + EMBED_BATCH_SIZE]
            batch_embeddings = _embed_via_api(batch)
            embeddings.extend(batch_embeddings)
            print(f"   🔢 Embedded chunks {batch_start + 1}–{min(batch_start + EMBED_BATCH_SIZE, len(chunk_texts))} / {len(chunk_texts)}")


        # 8. Prepare data and batch insert code chunks into Supabase
        db_chunks = []
        for idx, chunk in enumerate(all_chunks):
            # Generate unique primary key hash: repo + commit + path + lines + hash + parser_version
            unique_str = f"{repo_name}|{commit_sha}|{chunk['file_path']}|{chunk['start_line']}|{chunk['end_line']}|{chunk['content_hash']}|v3-ast"
            chunk_id = hashlib.sha256(unique_str.encode("utf-8")).hexdigest()
            
            db_chunks.append({
                "chunk_id": chunk_id,
                "snapshot_id": staging_snapshot_id,
                "repo_name": repo_name,
                "commit_sha": commit_sha,
                "file_path": chunk["file_path"],
                "language": repo_context.get("language", "generic"),
                "symbol_name": chunk["symbol_name"],
                "symbol_kind": chunk["symbol_kind"],
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
                "content": chunk["content"],
                "content_hash": chunk["content_hash"],
                "token_count": chunk["token_count"],
                "embedding": embeddings[idx]
            })

        # Batch insert chunks of 50 to avoid network payload limits
        batch_size = 50
        for i in range(0, len(db_chunks), batch_size):
            batch = db_chunks[i : i + batch_size]
            supabase_client.table("code_chunks").insert(batch).execute()

        # Update staging snapshot metadata values
        supabase_client.table("repository_snapshots").update({
            "file_count": len(target_files),
            "chunk_count": len(db_chunks),
            "content_bytes": sum(len(c["content"].encode("utf-8")) for c in db_chunks)
        }).eq("id", staging_snapshot_id).execute()

        # 9. Invoke server-side transaction function to atomically swap the ACTIVE snapshot
        supabase_client.rpc(
            "activate_snapshot",
            {
                "target_snapshot_id": staging_snapshot_id,
                "target_repo": repo_name
            }
        ).execute()

        print(f"✅ Indexer: Successfully indexed {repo_name} at commit {commit_sha[:7]} ({len(db_chunks)} chunks).")
        return commit_sha

    except Exception as e:
        print(f"❌ Indexer: Indexing failed for {repo_name}: {e}")
        # Clean up staging snapshot on error to avoid orphan rows
        if staging_snapshot_id:
            try:
                supabase_client.table("repository_snapshots").update({
                    "status": "FAILED",
                    "error_message": str(e)
                }).eq("id", staging_snapshot_id).execute()
            except Exception as clean_err:
                print(f"⚠️ Indexer: Cleanup database update failed: {clean_err}")
        return ""
