-- 06_etag_cache.sql
-- Create table to store GitHub API ETags for persistent HTTP cache across cron runs

create table if not exists etag_cache (
  resource_key text primary key,
  etag text not null,
  updated_at timestamptz not null default now()
);
