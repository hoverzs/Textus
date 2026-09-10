-- Phase 2D.2 performance fix — bulk parent-link RPCs for the Hebrew
-- linguistic-layer importer (scripts/import_macula_to_supabase.py).
--
-- Problem: hebrew_source_nodes.id / hebrew_clauses.id / hebrew_phrases.id
-- are all `generated always as identity` (see
-- supabase/migrations/20260908190000_hebrew_linguistic_layer.sql). Both a
-- plain per-row `UPDATE ... SET id = ...` and a PostgREST upsert with
-- on_conflict=id fail identically ("column \"id\" can only be updated to
-- DEFAULT") because either path puts the identity column into the
-- generated UPDATE's SET list. The two-pass self-referencing-FK import
-- (insert with parent = NULL, then link parents once remote ids are
-- known) therefore cannot use upsert for its second pass — it needs a
-- real multi-row UPDATE that touches ONLY the parent-link column(s),
-- never `id` and never any other column.
--
-- These three functions do exactly that, one per linking call site, each
-- driven by parallel arrays (one bigint[] per touched column) unnested
-- into a values-table and joined back to the target table on `id`. This
-- replaces a one-HTTP-request-per-row .update() (observed ~8 rows/sec
-- against the real project — 30+ hours for the full corpus) with one
-- request per batch. Not a general arbitrary-SQL endpoint: each function
-- is hard-coded to one table and one/two named columns.
--
-- Cardinality guard: every caller in this codebase derives all of a
-- call's arrays from the same Python list via one-to-one comprehension,
-- so a length mismatch cannot currently happen from
-- scripts/import_macula_to_supabase.py — but the RPC is a real network
-- boundary any future caller (or a bug in a later edit of that script)
-- could call directly with hand-built arrays. Each function therefore
-- validates that every input array has the same cardinality *before*
-- touching the table, and RAISEs (aborting the function, and with it the
-- single implicit transaction PostgREST wraps one RPC call in) rather
-- than running a partial or misaligned UPDATE. `coalesce(array_length(x,
-- 1), 0)` treats both NULL and `'{}'` as length 0, so all-empty/all-NULL
-- calls are a harmless no-op rather than a false-positive mismatch.
--
-- Access model: same as the base migration (service_role-only; see its
-- header note) — anon/authenticated explicitly revoked, service_role
-- explicitly granted EXECUTE.

create or replace function bulk_link_source_node_parents(p_ids bigint[], p_parent_ids bigint[])
returns void
language plpgsql
set search_path = public
as $$
declare
  n_ids int := coalesce(array_length(p_ids, 1), 0);
  n_parent_ids int := coalesce(array_length(p_parent_ids, 1), 0);
begin
  if n_ids <> n_parent_ids then
    raise exception 'bulk_link_source_node_parents: array length mismatch (p_ids=%, p_parent_ids=%)',
      n_ids, n_parent_ids;
  end if;

  update hebrew_source_nodes t
  set parent_node_id = v.parent_id
  from (select unnest(p_ids) as id, unnest(p_parent_ids) as parent_id) v
  where t.id = v.id;
end;
$$;

create or replace function bulk_link_clause_parents(p_ids bigint[], p_parent_ids bigint[])
returns void
language plpgsql
set search_path = public
as $$
declare
  n_ids int := coalesce(array_length(p_ids, 1), 0);
  n_parent_ids int := coalesce(array_length(p_parent_ids, 1), 0);
begin
  if n_ids <> n_parent_ids then
    raise exception 'bulk_link_clause_parents: array length mismatch (p_ids=%, p_parent_ids=%)',
      n_ids, n_parent_ids;
  end if;

  update hebrew_clauses t
  set parent_clause_id = v.parent_id
  from (select unnest(p_ids) as id, unnest(p_parent_ids) as parent_id) v
  where t.id = v.id;
end;
$$;

-- A given phrase row may carry only parent_phrase_id, only
-- parent_clause_id, or both (see link_phrase_parents in the importer) —
-- a NULL array slot means "leave this column alone for this row", not
-- "set it to NULL", hence COALESCE against the row's current value.
create or replace function bulk_link_phrase_parents(
    p_ids bigint[], p_parent_phrase_ids bigint[], p_parent_clause_ids bigint[]
)
returns void
language plpgsql
set search_path = public
as $$
declare
  n_ids int := coalesce(array_length(p_ids, 1), 0);
  n_parent_phrase_ids int := coalesce(array_length(p_parent_phrase_ids, 1), 0);
  n_parent_clause_ids int := coalesce(array_length(p_parent_clause_ids, 1), 0);
begin
  if n_ids <> n_parent_phrase_ids or n_ids <> n_parent_clause_ids then
    raise exception 'bulk_link_phrase_parents: array length mismatch (p_ids=%, p_parent_phrase_ids=%, p_parent_clause_ids=%)',
      n_ids, n_parent_phrase_ids, n_parent_clause_ids;
  end if;

  update hebrew_phrases t
  set
    parent_phrase_id = coalesce(v.parent_phrase_id, t.parent_phrase_id),
    parent_clause_id = coalesce(v.parent_clause_id, t.parent_clause_id)
  from (
    select
      unnest(p_ids) as id,
      unnest(p_parent_phrase_ids) as parent_phrase_id,
      unnest(p_parent_clause_ids) as parent_clause_id
  ) v
  where t.id = v.id;
end;
$$;

revoke all on function bulk_link_source_node_parents(bigint[], bigint[]) from public, anon, authenticated;
revoke all on function bulk_link_clause_parents(bigint[], bigint[]) from public, anon, authenticated;
revoke all on function bulk_link_phrase_parents(bigint[], bigint[], bigint[]) from public, anon, authenticated;

grant execute on function bulk_link_source_node_parents(bigint[], bigint[]) to service_role;
grant execute on function bulk_link_clause_parents(bigint[], bigint[]) to service_role;
grant execute on function bulk_link_phrase_parents(bigint[], bigint[], bigint[]) to service_role;
