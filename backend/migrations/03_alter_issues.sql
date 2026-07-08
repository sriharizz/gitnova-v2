-- Migration: 03_alter_issues.sql
-- Description: Alters the existing 'issues' table to add quality scores, repository commit SHAs, models tracked, and issue numbers.

alter table issues 
  add column if not exists github_issue_number integer,
  add column if not exists github_issue_updated_at timestamptz,
  add column if not exists repo_commit_sha text,
  add column if not exists retrieved_chunk_ids text[], -- Array of chunk IDs used as RAG evidence
  add column if not exists retrieval_method text,       -- E.g. 'RRF', 'LEXICAL', 'DENSE', 'NONE'
  add column if not exists quality_score float,
  add column if not exists quality_grade text,         -- 'High', 'Medium', 'Low'
  add column if not exists model_provider text,        -- E.g. 'groq', 'nvidia'
  add column if not exists model_name text,            -- E.g. 'llama-3.3-70b-versatile'
  add column if not exists prompt_version text,        -- E.g. 'v3-grounded'
  add column if not exists generated_at timestamptz default now();

-- Add index on quality_grade and score to optimize frontend sorting/filtering
create index if not exists idx_issues_quality on issues(quality_grade, quality_score desc);
