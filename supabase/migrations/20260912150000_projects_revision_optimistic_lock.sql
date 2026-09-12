-- 2026-09 audit fix — optimistic concurrency for the `projects` table.
--
-- Problem: project_storage.update_project() previously did a blind
-- `UPDATE ... WHERE id = ? AND owner_sub = ?` with no version/timestamp
-- precondition. Two browser tabs (or a stale autosave racing a manual
-- save) editing the same project both succeed, and whichever write lands
-- last silently overwrites the other's changes with no conflict signal
-- to either user — a real data-loss path confirmed by the 2026-09 system
-- audit.
--
-- Fix: every row carries a monotonically increasing `revision`. A client
-- must supply the revision it last observed (on load, or on its own
-- previous successful save); the UPDATE only matches a row if that
-- revision is STILL the one stored, and it bumps the revision by exactly
-- one on success. A write from a stale revision therefore matches zero
-- rows — the application layer (bible_engine's caller, project_storage.py)
-- turns that into an explicit CONFLICT result instead of a silent
-- overwrite. No merge logic here or in the application: conflict
-- resolution is left to the user (reload, or save as a new project).
--
-- NOTE: the base `projects` table itself (id, owner_sub, title, passage,
-- project_data, created_at, updated_at, and its RLS policies) is not
-- defined in this repository's migrations — it predates this migration
-- history and was created directly against the Supabase project. This
-- migration only adds the new column; it does not attempt to reconstruct
-- or restate the table's existing schema or policies.

ALTER TABLE public.projects
    ADD COLUMN IF NOT EXISTS revision integer NOT NULL DEFAULT 1;

COMMENT ON COLUMN public.projects.revision IS
    'Optimistic-concurrency token. Incremented by exactly 1 on every successful update_project() call; a write against a stale revision matches zero rows and is reported to the caller as a conflict, never silently overwritten. See project_storage.update_project / UpdateProjectResult.';
