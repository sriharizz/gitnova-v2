-- Migration: 04_activate_snapshot.sql
-- Description: Creates a server-side transaction function to atomically activate a staging snapshot and retire old snapshots for a repo.

create or replace function activate_snapshot(
  target_snapshot_id uuid,
  target_repo text
)
returns void
language plpgsql security definer as $$
begin
  -- 1. Demote the current active snapshot to RETIRED
  update repository_snapshots
  set status = 'RETIRED', completed_at = now()
  where repo_name = target_repo and status = 'ACTIVE';

  -- 2. Promote the staging snapshot to ACTIVE
  update repository_snapshots
  set status = 'ACTIVE', completed_at = now()
  where id = target_snapshot_id;

  -- 3. Delete retired and failed snapshots to reclaim storage space automatically
  delete from repository_snapshots
  where repo_name = target_repo 
    and status in ('RETIRED', 'FAILED');
end;
$$;
