-- Migration: 02_hybrid_search.sql
-- Description: Creates remote procedure call (RPC) functions for vector similarity matching and lexical keyword matching.

-- 1. Vector similarity search function
create or replace function match_chunks_vector(
  query_embedding vector(768),
  target_repo text,
  target_commit text,
  match_count int default 20
)
returns table (
  chunk_id text,
  file_path text,
  symbol_name text,
  start_line integer,
  end_line integer,
  content text,
  similarity float
)
language plpgsql security definer as $$
begin
  return query
  select
    cc.chunk_id,
    cc.file_path,
    cc.symbol_name,
    cc.start_line,
    cc.end_line,
    cc.content,
    (1 - (cc.embedding <=> query_embedding))::float as similarity
  from code_chunks cc
  where cc.repo_name = target_repo
    and cc.commit_sha = target_commit
  order by cc.embedding <=> query_embedding
  limit match_count;
end;
$$;

-- 2. Lexical (keyword) search function
create or replace function match_chunks_lexical(
  query_text text,
  target_repo text,
  target_commit text,
  match_count int default 20
)
returns table (
  chunk_id text,
  file_path text,
  symbol_name text,
  start_line integer,
  end_line integer,
  content text,
  lexical_rank float
)
language plpgsql security definer as $$
begin
  return query
  select
    cc.chunk_id,
    cc.file_path,
    cc.symbol_name,
    cc.start_line,
    cc.end_line,
    cc.content,
    ts_rank_cd(cc.fts, plainto_tsquery('simple', query_text))::float as lexical_rank
  from code_chunks cc
  where cc.repo_name = target_repo
    and cc.commit_sha = target_commit
    and cc.fts @@ plainto_tsquery('simple', query_text)
  order by lexical_rank desc
  limit match_count;
end;
$$;
