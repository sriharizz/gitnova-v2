# backend/app/pipeline/code_retriever.py
import re
import os
import time
from typing import List, Dict, Any, Optional

# ── Local Embeddings (sentence-transformers) ─────────────────────────────────
# Uses the same model as the indexer (jinaai/jina-embeddings-v2-base-code)
# but runs locally instead of calling the Jina API. Zero cost, same vectors.
from app.pipeline.embedder import embed_query as _embed_query
# ─────────────────────────────────────────────────────────────────────────────



def rrf_score(ranks: List[int], k: int = 60) -> float:
    """Computes Reciprocal Rank Fusion score for a list of rank positions."""
    return sum(1.0 / (k + rank) for rank in ranks)


def combine_rrf(vector_results: List[Dict[str, Any]], lexical_results: List[Dict[str, Any]], k: int = 60) -> List[Dict[str, Any]]:
    """
    Fuses Vector (dense) and Lexical (sparse) retrieval lists using RRF.
    Items present in both lists are boosted.
    """
    candidates: Dict[str, Dict[str, Any]] = {}
    
    # Process vector matches
    for rank_idx, item in enumerate(vector_results):
        chunk_id = item["chunk_id"]
        candidates[chunk_id] = {
            "chunk_id": chunk_id,
            "file_path": item["file_path"],
            "symbol_name": item.get("symbol_name"),
            "start_line": item["start_line"],
            "end_line": item["end_line"],
            "content": item["content"],
            "ranks": [rank_idx + 1] # 1-indexed rank
        }
        
    # Process lexical matches
    for rank_idx, item in enumerate(lexical_results):
        chunk_id = item["chunk_id"]
        if chunk_id in candidates:
            candidates[chunk_id]["ranks"].append(rank_idx + 1)
        else:
            candidates[chunk_id] = {
                "chunk_id": chunk_id,
                "file_path": item["file_path"],
                "symbol_name": item.get("symbol_name"),
                "start_line": item["start_line"],
                "end_line": item["end_line"],
                "content": item["content"],
                "ranks": [rank_idx + 1]
            }

    # Calculate final RRF score for each unique candidate chunk
    fused_list = []
    for candidate in candidates.values():
        score = rrf_score(candidate["ranks"], k)
        fused_list.append({
            "chunk_id": candidate["chunk_id"],
            "file_path": candidate["file_path"],
            "symbol_name": candidate["symbol_name"],
            "start_line": candidate["start_line"],
            "end_line": candidate["end_line"],
            "content": candidate["content"],
            "rrf_score": score
        })

    # Sort descending by fused RRF score
    fused_list.sort(key=lambda x: x["rrf_score"], reverse=True)
    return fused_list


def retrieve_code_for_issue(
    supabase_client: Any,
    repo_name: str,
    commit_sha: str,
    issue_title: str,
    issue_body: str,
    max_tokens: int = 2500,
    k_candidates: int = 20
) -> str:
    """
    Main retrieval entry point.
    Runs Vector + FTS search, merges via RRF, filters, and formats for prompt.
    Returns empty string "" on any failure (Graceful Fallback).
    """
    try:
        # 1. Check if we have a valid snapshot SHA. If none, fail fast.
        if not commit_sha:
            print(f"⚠️ RAG: No active commit SHA resolved for {repo_name}. Skipping retrieval.")
            return "", []

        # 2. Embed the query text via Jina API
        # Why: the query must be in the same vector space as the indexed chunks.
        # The indexer used jina-embeddings-v2-base-code via API; we use the same here.
        query_text = f"{issue_title} {issue_body or ''}".strip()
        query_vector = _embed_query(query_text)

        # 3. Call Supabase Vector matching function (RPC)
        vec_response = supabase_client.rpc(
            "match_chunks_vector",
            {
                "query_embedding": query_vector,
                "target_repo": repo_name,
                "target_commit": commit_sha,
                "match_count": k_candidates
            }
        ).execute()

        # 4. Call Supabase Lexical matching function (RPC)
        lex_response = supabase_client.rpc(
            "match_chunks_lexical",
            {
                "query_text": query_text[:500], # Limit search term text to avoid DB search limits
                "target_repo": repo_name,
                "target_commit": commit_sha,
                "match_count": k_candidates
            }
        ).execute()

        vector_results = vec_response.data or []
        lexical_results = lex_response.data or []

        # 5. Check if we retrieved absolutely nothing (Graceful Fallback case)
        if not vector_results and not lexical_results:
            print(f"⚠️ RAG: Zero matching chunks found for {repo_name} at {commit_sha[:7]}.")
            return "", []

        # 6. Fuse results using Reciprocal Rank Fusion (RRF)
        fused_results = combine_rrf(vector_results, lexical_results)

        # 7. Deduplicate duplicates and apply token/budget limit
        formatted_chunks = []
        retrieved_chunk_ids = []
        token_count = 0
        seen_content_hashes = set()
        file_chunk_counts: Dict[str, int] = {}

        for chunk in fused_results:
            # Simple content deduplication
            content = chunk["content"]
            content_hash = hash(content)
            if content_hash in seen_content_hashes:
                continue
            
            # Limit repeated chunks from the same file to prevent one file dominating
            file_path = chunk["file_path"]
            file_chunk_counts[file_path] = file_chunk_counts.get(file_path, 0) + 1
            if file_chunk_counts[file_path] > 3:
                continue

            # Estimate token count (1 word ≈ 1.3 tokens average for code)
            words = len(content.split())
            estimated_tokens = int(words * 1.3)
            
            if token_count + estimated_tokens > max_tokens:
                break # Token budget exceeded, stop adding

            token_count += estimated_tokens
            seen_content_hashes.add(content_hash)
            retrieved_chunk_ids.append(chunk["chunk_id"])

            # Format the output block
            symbol_str = f" in {chunk['symbol_name']}" if chunk.get("symbol_name") else ""
            formatted_chunks.append(
                f"--- SOURCE FILE: {file_path} (Lines {chunk['start_line']}-{chunk['end_line']}){symbol_str} ---\n"
                f"{content}\n"
            )

        print(f"✅ RAG: Successfully retrieved {len(formatted_chunks)} code chunks ({token_count} tokens) for {repo_name}")
        return "\n".join(formatted_chunks), retrieved_chunk_ids

    except Exception as e:
        # Graceful Fallback: print error logs but do not crash pipeline
        print(f"⚠️ RAG Exception: Retrieval failed for {repo_name}: {e}")
        return "", []
