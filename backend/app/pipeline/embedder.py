# backend/app/pipeline/embedder.py
"""
Local embedding module using sentence-transformers.
Replaces the Jina API calls with the same model running locally.
Same model = same 768-dim vectors = existing indexed chunks still work.

Why local:
  - Zero API cost (Jina free credits ran out)
  - No rate limits
  - Same vector space as existing chunks (jinaai/jina-embeddings-v2-base-code)
  - ~1 second per query on CPU (acceptable for 60 issues/run)
"""
import os
from typing import List
from sentence_transformers import SentenceTransformer

# Lazy-loaded singleton — model downloads once, reused across all calls
_model = None
MODEL_NAME = "jinaai/jina-embeddings-v2-base-code"


def _get_model() -> SentenceTransformer:
    """Load the model once and cache it for the process lifetime."""
    global _model
    if _model is None:
        print(f"   📦 Loading embedding model: {MODEL_NAME}...")
        _model = SentenceTransformer(MODEL_NAME, trust_remote_code=True)
        print(f"   ✅ Embedding model loaded (768-dim)")
    return _model


def embed_query(text: str) -> List[float]:
    """
    Embed a single query string (issue title + body).
    Returns a 768-dimensional float vector for vector similarity search.
    Used by: code_retriever.py
    """
    model = _get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def embed_batch(texts: List[str]) -> List[List[float]]:
    """
    Embed a batch of texts (code chunks).
    Returns a list of 768-dimensional float vectors.
    Used by: code_indexer.py
    """
    model = _get_model()
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=16, show_progress_bar=True)
    return embeddings.tolist()
