-- Phase 2D.2 read-path performance fix — one RPC per verse instead of up
-- to 9 sequential PostgREST requests.
--
-- Problem: SupabaseHebrewAnalysisRepository.get_verse_syntax() issued one
-- REST request each for hebrew_phrases, hebrew_clauses,
-- hebrew_syntax_membership (up to twice — once for phrase ids, once for
-- clause ids), hebrew_syntax_edges, hebrew_semantic_roles,
-- hebrew_participants, hebrew_coreference, and the grounding view — up to
-- 9 sequential round trips. Measured live: ~1.0-1.15s per verse, ~31s for
-- a 31-verse chapter (Genesis 1). Each individual query was already fast;
-- the round-trip *count*, not any single query, was the bottleneck.
--
-- get_verse_syntax_bundle(p_verse_ref) does the same 7 reads server-side
-- in one statement and returns them as one jsonb object — one HTTP
-- request per verse. No linguistic/alignment data is touched or
-- recomputed; this is purely a read-shape optimization over the existing
-- tables and the existing hebrew_verse_syntax_grounding view (migration
-- 20260908223000). Column selections match
-- bible_engine/hebrew_analysis_repository.py's existing REST .select()
-- lists exactly, so the repository's row-assembly logic
-- (_assemble_from_rows) is unchanged.
--
-- Access model: service_role-only, matching every other function/table in
-- this schema (see 20260908190000's header note and
-- 20260909210000_hebrew_bulk_parent_link_rpcs.sql's grants).

create or replace function get_verse_syntax_bundle(p_verse_ref text)
returns jsonb
language sql
stable
set search_path = public
as $$
  select jsonb_build_object(
    'phrases', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', p.id, 'phrase_type', p.phrase_type,
        'head_token_id', p.head_token_id, 'parent_phrase_id', p.parent_phrase_id
      ) order by p.id)
      from hebrew_phrases p where p.verse_ref = p_verse_ref
    ), '[]'::jsonb),
    'clauses', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', c.id, 'clause_type', c.clause_type, 'predicate_token_id', c.predicate_token_id,
        'subject_token_id', c.subject_token_id, 'parent_clause_id', c.parent_clause_id
      ) order by c.id)
      from hebrew_clauses c where c.verse_ref = p_verse_ref
    ), '[]'::jsonb),
    'membership', coalesce((
      -- Ordered by m.id (its own insertion-order surrogate key), NOT
      -- token_id: token_id is a TEXT column like "Ezra.4.8:10" whose
      -- numeric tail sorts lexicographically ("Ezra.4.8:10" < "...:9"),
      -- which reverses within-phrase/clause word order versus the local
      -- SQLite path's natural (insertion-order) fetch. Caught live by
      -- tests/test_hebrew_analysis_repository_parity.py before this
      -- migration was ever applied — id preserves the same insertion
      -- order the local repository already relies on, without the
      -- lexicographic-string-sort bug.
      select jsonb_agg(jsonb_build_object('token_id', m.token_id, 'phrase_id', m.phrase_id, 'clause_id', m.clause_id)
        order by m.id)
      from hebrew_syntax_membership m
      where m.phrase_id in (select id from hebrew_phrases where verse_ref = p_verse_ref)
         or m.clause_id in (select id from hebrew_clauses where verse_ref = p_verse_ref)
    ), '[]'::jsonb),
    'edges', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', e.id, 'relation_type', e.relation_type, 'source_role_code', e.source_role_code,
        'parent_token_id', e.parent_token_id, 'child_token_id', e.child_token_id
      ) order by e.id)
      from hebrew_syntax_edges e where e.verse_ref = p_verse_ref
    ), '[]'::jsonb),
    'roles', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', r.id, 'role_code', r.role_code, 'role_label', r.role_label,
        'predicate_token_id', r.predicate_token_id, 'participant_token_id', r.participant_token_id
      ) order by r.id)
      from hebrew_semantic_roles r where r.verse_ref = p_verse_ref
    ), '[]'::jsonb),
    'participants', coalesce((
      select jsonb_agg(jsonb_build_object('id', pt.id, 'token_id', pt.token_id) order by pt.id)
      from hebrew_participants pt where pt.verse_ref = p_verse_ref
    ), '[]'::jsonb),
    'coreference', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', cr.id, 'referring_token_id', cr.referring_token_id,
        'participant_id', cr.participant_id, 'relation_type', cr.relation_type
      ) order by cr.id)
      from hebrew_coreference cr where cr.verse_ref = p_verse_ref
    ), '[]'::jsonb),
    'grounding_status', (
      select g.grounding_status from hebrew_verse_syntax_grounding g where g.verse_ref = p_verse_ref limit 1
    )
  );
$$;

revoke all on function get_verse_syntax_bundle(text) from public, anon, authenticated;
grant execute on function get_verse_syntax_bundle(text) to service_role;
