-- 07_validate_outcomes.sql
-- Add feedback validation columns to issues table to track live accuracy rates

alter table issues
  add column if not exists hint_correct boolean,
  add column if not exists validated_at timestamptz;
