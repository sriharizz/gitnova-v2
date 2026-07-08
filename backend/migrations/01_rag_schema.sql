-- Migration: 01_rag_schema.sql
-- Description: Creates the repository_snapshots and code_chunks tables, with vector similarity (pgvector) and GIN FTS indexes.

-- 1. Enable Vector Extension (768-dimensions for Jina embeddings v2 base code)
create extension if not exists vector;

-- 2. Repository Snapshots table (Tracks versioned snapshots of indexed repositories)
create table if not exists repository_snapshots (
  id uuid primary key default gen_random_uuid(),
  repo_name text not null,
  commit_sha text not null,
  default_branch text not null,
  status text not null check (status in ('STAGING', 'ACTIVE', 'FAILED', 'RETIRED')),
  file_count integer not null default 0,
  chunk_count integer not null default 0,
  content_bytes bigint not null default 0,
  embedding_model text not null,
  embedding_dimensions integer not null,
  parser_version text not null,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  error_message text,
  unique (repo_name, commit_sha, embedding_model, parser_version)
);

-- Index to enforce a single ACTIVE snapshot per repository at any point in time
create unique index if not exists one_active_snapshot_per_repo
  on repository_snapshots (repo_name)
  where status = 'ACTIVE';

-- 3. Code Chunks table (Stores syntax-aware, versioned code snippets)
create table if not exists code_chunks (
  chunk_id text primary key, -- SHA256(repo + commit + path + start + end + hash + parser_version)
  snapshot_id uuid not null references repository_snapshots(id) on delete cascade,
  repo_name text not null,
  commit_sha text not null,
  file_path text not null,
  language text not null,
  symbol_name text,
  symbol_kind text,
  start_line integer not null,
  end_line integer not null,
  content text not null,
  content_hash text not null,
  token_count integer not null,
  embedding vector(768) not null,
  fts tsvector generated always as (
    to_tsvector(
      'simple', -- 'simple' parser avoids English stemming that breaks code identifiers
      coalesce(file_path, '') || ' ' ||
      coalesce(symbol_name, '') || ' ' ||
      coalesce(content, '')
    )
  ) stored,
  created_at timestamptz not null default now(),
  check (start_line > 0),
  check (end_line >= start_line)
);

-- Indexes for retrieval optimization
create index if not exists code_chunks_snapshot_idx on code_chunks(snapshot_id);
create index if not exists code_chunks_repo_sha_idx on code_chunks(repo_name, commit_sha);
create index if not exists code_chunks_fts_idx on code_chunks using gin(fts);
