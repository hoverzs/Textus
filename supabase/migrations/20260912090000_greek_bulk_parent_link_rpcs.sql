-- Phase 2C performance fix — bulk parent-link RPCs for the Greek
-- linguistic-layer importer (scripts/import_greek_syntax_to_supabase.py).
--
-- Mirrors supabase/migrations/20260909210000_hebrew_bulk_parent_link_rpcs.sql
-- exactly, for the same reason: greek_phrases.id / greek_clauses.id are
-- `generated always as identity` (see 20260911220000_greek_linguistic_
-- layer.sql), so neither a plain per-row UPDATE nor a PostgREST upsert with
-- on_conflict=id can link parent_phrase_id/parent_clause_id after the
-- two-pass insert (parent = NULL, then linked once every group's remote id
-- is known) — both put the identity column in the generated SET list.
-- Greek has no equivalent of hebrew_source_nodes' self-referencing
-- parent_node_id (greek_source_nodes is flat, never nested), so only the
-- clause- and phrase-parent functions are needed here.
--
-- Cardinality guard and access model: identical rationale to the Hebrew
-- migration's own header note — every array comes from one Python list via
-- one-to-one comprehension, but the RPC itself still validates length
-- equality before touching any row, and is granted to service_role only.
--
-- Unlike Hebrew's clause-parent function, a Greek clause's own parent is
-- not always another clause — measured 2,565 of 83,198 parented MACULA
-- groups corpus-wide where a "cl" group's immediate parent is a phrase
-- (e.g. a relative clause nested inside its head noun phrase; see
-- 20260911220000_greek_linguistic_layer.sql's note on greek_clauses.
-- parent_phrase_id) — so this function takes the same dual-parent-array,
-- COALESCE-based shape as bulk_link_greek_phrase_parents below, not the
-- single-array shape Hebrew's bulk_link_clause_parents uses.
create or replace function bulk_link_greek_clause_parents(
    p_ids bigint[], p_parent_clause_ids bigint[], p_parent_phrase_ids bigint[]
)
returns void
language plpgsql
set search_path = public
as $$
declare
  n_ids int := coalesce(array_length(p_ids, 1), 0);
  n_parent_clause_ids int := coalesce(array_length(p_parent_clause_ids, 1), 0);
  n_parent_phrase_ids int := coalesce(array_length(p_parent_phrase_ids, 1), 0);
begin
  if n_ids <> n_parent_clause_ids or n_ids <> n_parent_phrase_ids then
    raise exception 'bulk_link_greek_clause_parents: array length mismatch (p_ids=%, p_parent_clause_ids=%, p_parent_phrase_ids=%)',
      n_ids, n_parent_clause_ids, n_parent_phrase_ids;
  end if;

  update greek_clauses t
  set
    parent_clause_id = coalesce(v.parent_clause_id, t.parent_clause_id),
    parent_phrase_id = coalesce(v.parent_phrase_id, t.parent_phrase_id)
  from (
    select
      unnest(p_ids) as id,
      unnest(p_parent_clause_ids) as parent_clause_id,
      unnest(p_parent_phrase_ids) as parent_phrase_id
  ) v
  where t.id = v.id;
end;
$$;

-- A given phrase row may carry only parent_phrase_id, only
-- parent_clause_id, or both — a NULL array slot means "leave this column
-- alone for this row", not "set it to NULL", hence COALESCE against the
-- row's current value (identical semantics to the Hebrew function).
create or replace function bulk_link_greek_phrase_parents(
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
    raise exception 'bulk_link_greek_phrase_parents: array length mismatch (p_ids=%, p_parent_phrase_ids=%, p_parent_clause_ids=%)',
      n_ids, n_parent_phrase_ids, n_parent_clause_ids;
  end if;

  update greek_phrases t
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

revoke all on function bulk_link_greek_clause_parents(bigint[], bigint[], bigint[]) from public, anon, authenticated;
revoke all on function bulk_link_greek_phrase_parents(bigint[], bigint[], bigint[]) from public, anon, authenticated;

grant execute on function bulk_link_greek_clause_parents(bigint[], bigint[], bigint[]) to service_role;
grant execute on function bulk_link_greek_phrase_parents(bigint[], bigint[], bigint[]) to service_role;
