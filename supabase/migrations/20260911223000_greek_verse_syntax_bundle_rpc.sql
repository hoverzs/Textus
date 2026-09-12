-- Greek Analysis v2 — Phase 2C read-path: one RPC per verse instead of
-- N sequential PostgREST requests, learning directly from the Hebrew
-- Phase 2D.2 lesson (migration 20260910120000) BEFORE any Greek Supabase
-- deployment ever ships a naive per-table read path (task §6/§3).
--
-- get_greek_verse_syntax_bundle(p_verse_ref) returns every deterministic
-- fact for one verse — tokens (with morphology + alignment status +
-- lexicon), phrases, clauses, membership, semantic roles, coreference —
-- as one jsonb object, in ONE HTTP round trip. Column selections match
-- the local SQLite store's own shape (bible_engine/greek_syntax_sqlite.py)
-- so SupabaseGreekAnalysisRepository's row-assembly logic can be written
-- once and reused against either backend's JSON shape.
--
-- Ordering is fully deterministic: tokens by word_index, membership by
-- member_order (preserves MACULA's own constituent/document order — see
-- the linguistic-layer migration's note on hyperbaton), everything else
-- by its own surrogate id (insertion order) — never by a text column that
-- could sort lexicographically wrong (the exact bug the Hebrew bundle RPC
-- was written to avoid, migration 20260910120000's own header note).
--
-- Access model: service_role-only, matching every other function/table in
-- this schema.

create or replace function get_greek_verse_syntax_bundle(p_verse_ref text)
returns jsonb
language sql
stable
set search_path = public
as $$
  select jsonb_build_object(
    'verse_ref', p_verse_ref,
    'tokens', coalesce((
      select jsonb_agg(jsonb_build_object(
        'token_id', t.token_id,
        'word_index', t.word_index,
        'surface', t.surface,
        'lemma', t.lemma,
        'strong_id', t.strong_id,
        'edition_flags', t.edition_flags,
        'part_of_speech', t.part_of_speech,
        'morphology_raw_code', t.morphology_raw_code,
        'morphology_confidence', t.morphology_confidence,
        'case', t.case_,
        'number', t.number_,
        'gender', t.gender,
        'person', t.person,
        'tense', t.tense,
        'voice', t.voice,
        'mood', t.mood,
        'verb_form', t.verb_form,
        'degree', t.degree,
        'pronoun_type', t.pronoun_type,
        'name_type', t.name_type,
        'alignment_status', a.alignment_status,
        'alignment_unresolved_category', a.unresolved_category,
        'lexicon', (
          select jsonb_build_object(
            'primary_gloss', l.primary_gloss, 'senses', l.senses, 'note', l.note,
            'review_status', l.review_status, 'translation_method', l.translation_method,
            'source_name', l.source_name, 'source_version', l.source_version
          )
          from greek_lexicon_hu l where l.strong_id = t.strong_id
          order by l.id desc limit 1
        )
      ) order by t.word_index)
      from greek_tokens t
      join greek_verses v on v.id = t.verse_id
      left join greek_token_alignments a on a.token_id = t.token_id
      where v.verse_ref = p_verse_ref
    ), '[]'::jsonb),
    'phrases', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', p.id, 'phrase_type', p.phrase_type, 'role', p.role,
        'head_token_id', p.head_token_id, 'parent_phrase_id', p.parent_phrase_id,
        'parent_clause_id', p.parent_clause_id
      ) order by p.id)
      from greek_phrases p where p.verse_ref = p_verse_ref
    ), '[]'::jsonb),
    'clauses', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', c.id, 'clause_type', c.clause_type, 'predicate_token_id', c.predicate_token_id,
        'parent_clause_id', c.parent_clause_id, 'parent_phrase_id', c.parent_phrase_id,
        'relation_to_parent', c.relation_to_parent
      ) order by c.id)
      from greek_clauses c where c.verse_ref = p_verse_ref
    ), '[]'::jsonb),
    'membership', coalesce((
      select jsonb_agg(jsonb_build_object(
        'token_id', m.token_id, 'phrase_id', m.phrase_id, 'clause_id', m.clause_id
      ) order by coalesce(m.phrase_id, m.clause_id), m.member_order)
      from greek_syntax_membership m
      where m.phrase_id in (select id from greek_phrases where verse_ref = p_verse_ref)
         or m.clause_id in (select id from greek_clauses where verse_ref = p_verse_ref)
    ), '[]'::jsonb),
    'semantic_roles', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', r.id, 'role_code', r.role_code,
        'predicate_token_id', r.predicate_token_id, 'argument_token_id', r.argument_token_id
      ) order by r.id)
      from greek_semantic_roles r where r.verse_ref = p_verse_ref
    ), '[]'::jsonb),
    'coreference', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', cr.id, 'link_type', cr.link_type,
        'source_token_id', cr.source_token_id, 'target_token_id', cr.target_token_id
      ) order by cr.id)
      from greek_coreference_links cr where cr.verse_ref = p_verse_ref
    ), '[]'::jsonb)
  );
$$;

revoke all on function get_greek_verse_syntax_bundle(text) from public, anon, authenticated;
grant execute on function get_greek_verse_syntax_bundle(text) to service_role;
