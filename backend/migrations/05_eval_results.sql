-- 05_eval_results.sql
-- Create table to store pipeline evaluation run metrics

create table if not exists eval_results (
  id uuid primary key default gen_random_uuid(),
  run_at timestamptz not null default now(),
  total_issues_evaluated integer not null,
  retrieval_recall float not null,
  hint_precision float not null,
  retrieval_success_count integer not null,
  hint_success_count integer not null
);
