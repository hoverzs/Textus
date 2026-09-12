-- Greek Analysis v2 — Phase 2C: normalized linguistic data layer.
--
-- Adds the Phase 2A/2B/2B.1 deterministic Greek foundation (TAGNT tokens,
-- TEGMC-verified morphology, TBESG/Hungarian lexicon, MACULA Greek syntax)
-- to Supabase, additive-only, alongside the existing Hebrew schema
-- (20260908190000_hebrew_linguistic_layer.sql). Nothing Hebrew is touched.
--
-- AUTHORITY RULE (enforced by design, mirrors the Hebrew schema's own
-- rule): this schema never stores a "winning" morphology value derived
-- from MACULA. MACULA's own morphology is recorded ONLY inside
-- greek_source_nodes (raw import, provenance/comparison only) — nothing
-- in greek_tokens is ever overwritten from a MACULA fact. TAGNT/TEGMC
-- remain authoritative for morphology and token identity; MACULA is
-- authoritative only for phrase/clause/semantic-role/coreference
-- structure (see docs/greek_analysis_v2_phase2b_syntax.md §1).
--
-- DELIBERATE STRUCTURAL DIFFERENCES FROM THE HEBREW SCHEMA (not oversights
-- — see docs/greek_analysis_v2_phase2b1_full_corpus.md §1 for the local-
-- store precedent this mirrors exactly):
--   * No greek_token_morphology table — Hebrew inlines its morphology
--     fields directly onto hebrew_tokens rather than a separate table;
--     this schema does the same for greek_tokens (fewer joins for the
--     read-path RPC, and Greek morphology is already flat/single-valued
--     per token, unlike Hebrew's per-component breakdown).
--   * No greek_token_lexical_ids table — TAGNT already carries exactly
--     ONE disambiguated Strong id per token (never a Hebrew-style array),
--     so it is a plain column on greek_tokens, not a join table.
--   * No greek_participants / greek_syntax_edges tables — MACULA Greek's
--     flat TSV supplies semantic roles and coreference directly (frame/
--     referent/subjref columns), and the local store (Phase 2B/2B.1)
--     established that a separate "edges" or "participants" table would
--     duplicate greek_semantic_roles/greek_coreference_links under a
--     different name. Not forcing tables for data the source does not
--     structurally separate (task instruction).
--   * No greek_detected_pattern tables — Phase 2B's construction
--     detectors (bible_engine/greek_construction_detection.py) run
--     on-the-fly from the deterministic bundle, exactly like Hebrew's
--     Phase 2C detectors did before Hebrew's own Phase 2D added
--     persistence; add persistence here in a later phase if profiling
--     ever shows it is needed, not preemptively.
--
-- Dataset versioning: REUSES the existing, already-generic
-- original_language_dataset_versions table (added by the Hebrew
-- migration) rather than a new greek_dataset_versions table — it was
-- already dataset-id-keyed and language-agnostic; the importer registers
-- 'tagnt' | 'tegmc' | 'tbesg' | 'greek_hu_lexicon' | 'macula_greek_sblgnt'
-- rows in it, mirroring 'tahot' | 'tehmc' | 'tbesh' | ... exactly.
--
-- Access model: identical convention to the Hebrew migration —
-- service_role-only, RLS enabled with no policies, anon/authenticated
-- explicitly revoked.
--
-- This file has been validated locally (parsed/dry-run against a local
-- Postgres-compatible check where practical) but has NOT been applied to
-- any real Supabase project from this environment — no production
-- Supabase credentials were available this phase (see
-- docs/greek_analysis_v2_phase2c_contextual.md §22 for exact manual-apply
-- steps once credentials exist).

-- ===========================================================================
-- 1. Canonical verse + token identity (TAGNT-authoritative)
-- ===========================================================================

create table if not exists greek_verses (
    id bigint generated always as identity primary key,
    book_id text not null,                 -- TAGNT 3-letter code, e.g. 'Jhn', 'Mat'
    chapter integer not null,
    verse integer not null,
    verse_ref text not null,               -- canonical string form, e.g. 'Jhn.3.16'
    greek_text text not null default '',   -- rendered surface text (tagnt_parser.render_greek_text)
    dataset_version_id bigint not null references original_language_dataset_versions(id),
    created_at timestamptz not null default now(),
    unique (book_id, chapter, verse),
    unique (verse_ref)
);

create index if not exists idx_greek_verses_book_chapter
    on greek_verses (book_id, chapter, verse);

create table if not exists greek_tokens (
    -- token_id is the Phase 2A stable Textus id
    -- ({book}.{chapter}.{verse}:{word_index}) — see
    -- bible_engine.greek_analysis_service.greek_token_id.
    token_id text primary key,
    verse_id bigint not null references greek_verses(id),
    word_index integer not null,

    surface text not null,                 -- pilcrow-stripped TAGNT greek_form
    lemma text not null default '',
    strong_id text not null default '',    -- TAGNT's own disambiguated id, e.g. 'G0007G' — already unique per sense, never an array
    edition_flags text not null default '',

    part_of_speech text not null default '',
    morphology_raw_code text not null default '',
    morphology_confidence text not null default 'unresolved',
    case_ text not null default '',        -- 'case' is reserved in some SQL contexts; matches GreekMorphologyFacts.case
    number_ text not null default '',
    gender text not null default '',
    person text not null default '',
    tense text not null default '',
    voice text not null default '',
    mood text not null default '',
    verb_form text not null default '',    -- 'participle' | 'infinitive' | ''
    degree text not null default '',
    pronoun_type text not null default '',
    name_type text not null default '',
    -- aspect is deliberately NOT a column — see
    -- bible_engine.greek_analysis_bundle.GreekMorphologyFacts.aspect: no
    -- source this schema imports encodes it separately from tense-form; a
    -- column that is always NULL would invite a future writer to start
    -- guessing at it. Re-introduce only with a real source and its own
    -- authority rule, exactly like Hebrew's root-column precedent above.

    dataset_version_id bigint not null references original_language_dataset_versions(id),
    created_at timestamptz not null default now()
);

create index if not exists idx_greek_tokens_verse
    on greek_tokens (verse_id, word_index);
create index if not exists idx_greek_tokens_lemma
    on greek_tokens (lemma);
create index if not exists idx_greek_tokens_strong_id
    on greek_tokens (strong_id);

-- ===========================================================================
-- 2. MACULA raw import — kept for provenance/comparison, never morphology
--    authority (see header AUTHORITY RULE).
-- ===========================================================================

create table if not exists greek_source_nodes (
    id bigint generated always as identity primary key,
    dataset_version_id bigint not null references original_language_dataset_versions(id),
    macula_xml_id text not null,           -- MACULA's own xml:id, e.g. 'n43003016001'
    verse_ref text not null,
    word_index integer not null,           -- MACULA's OWN per-verse index — NOT assumed equal to TAGNT's (Phase 2B §2)
    role text not null default '',
    word_class text not null default '',
    word_type text not null default '',
    text_ text not null default '',
    lemma text not null default '',
    normalized text not null default '',
    strong text not null default '',       -- MACULA's own bare (undisambiguated) Strong number — comparison only
    morph text not null default '',        -- MACULA's own morph code — comparison only, never copied to greek_tokens
    macula_case text not null default '',
    macula_number text not null default '',
    frame text not null default '',        -- raw semantic-frame string, source of greek_semantic_roles below
    subjref text not null default '',
    referent text not null default '',     -- raw source of greek_coreference_links below
    created_at timestamptz not null default now(),
    unique (dataset_version_id, macula_xml_id)
);

create index if not exists idx_greek_source_nodes_verse
    on greek_source_nodes (dataset_version_id, verse_ref);

-- ===========================================================================
-- 3. TAGNT ↔ MACULA token alignment (bible_engine.greek_token_alignment —
--    see docs/greek_analysis_v2_phase2b_syntax.md §2 for the algorithm,
--    docs/greek_analysis_v2_phase2b1_full_corpus.md §2 for the full
--    unresolved-category taxonomy)
-- ===========================================================================

create table if not exists greek_token_alignments (
    id bigint generated always as identity primary key,
    token_id text not null references greek_tokens(token_id) on delete cascade,
    source_node_id bigint references greek_source_nodes(id),  -- NULL only for UNRESOLVED_*
    alignment_status text not null,        -- 'EXACT' | 'COMPOSITE' | 'VALIDATED_FALLBACK' | 'UNRESOLVED_TEXTUAL_VARIANT' | 'UNRESOLVED_OTHER'
    unresolved_category text not null default '',  -- Phase 2B.1 §2 taxonomy, empty when resolved
    evidence text not null default '',     -- human-readable reason
    dataset_version_id_tagnt bigint not null references original_language_dataset_versions(id),
    dataset_version_id_macula bigint not null references original_language_dataset_versions(id),
    created_at timestamptz not null default now(),
    unique (token_id),
    check (alignment_status in (
        'EXACT', 'COMPOSITE', 'VALIDATED_FALLBACK', 'UNRESOLVED_TEXTUAL_VARIANT', 'UNRESOLVED_OTHER'
    )),
    check (
        (alignment_status in ('UNRESOLVED_TEXTUAL_VARIANT', 'UNRESOLVED_OTHER')) = (source_node_id is null)
    )
);

create index if not exists idx_greek_alignments_source_node
    on greek_token_alignments (source_node_id);
create index if not exists idx_greek_alignments_status
    on greek_token_alignments (alignment_status);

-- ===========================================================================
-- 4. Normalized phrase / clause structure
-- ===========================================================================

-- ``macula_group_id`` is the local store's own synthesized, globally-unique
-- group identity (see bible_engine.macula_greek_parser.MaculaGreekGroup's
-- docstring: "{first_leaf_xml_id}.g{depth}.{sibling_index}" — NOT the same
-- thing as a source node's own xml_id). It, not source_node_id, is this
-- table's natural key: 13,090 of 91,448 groups corpus-wide (measured
-- against data/generated/greek_syntax_dev.sqlite3) share their FIRST LEAF
-- TOKEN with at least one other, nested group (e.g. an "np" phrase and the
-- "cl" clause it opens both starting at the same word) — a
-- ``unique(dataset_version_id, source_node_id)`` constraint would silently
-- collapse those distinct nested groups on upsert. source_node_id is kept
-- as a plain (non-unique) reference to that first leaf token's source node,
-- useful for joins/provenance, never as the identity column.
create table if not exists greek_phrases (
    id bigint generated always as identity primary key,
    macula_group_id text not null,
    source_node_id bigint not null references greek_source_nodes(id),
    dataset_version_id bigint not null references original_language_dataset_versions(id),
    verse_ref text not null,
    phrase_type text not null,             -- MACULA class verbatim: 'np' | 'pp' | 'vp' | 'adjp' | 'advp'
    parent_phrase_id bigint references greek_phrases(id),
    parent_clause_id bigint,               -- FK added after greek_clauses exists, below
    head_token_id text references greek_tokens(token_id),
    role text not null default '',         -- MACULA's own group role attribute, verbatim (e.g. 's', 'o')
    child_order integer not null default 0,
    created_at timestamptz not null default now(),
    unique (dataset_version_id, macula_group_id)
);

-- parent_phrase_id: a clause's own parent constituent is not always
-- another clause — measured 2,565 of 83,198 parented groups corpus-wide
-- where a "cl" group's immediate parent is a phrase (e.g. a relative
-- clause nested inside its head noun phrase), so a clause needs the same
-- dual parent-column shape greek_phrases already has, not just
-- parent_clause_id.
create table if not exists greek_clauses (
    id bigint generated always as identity primary key,
    macula_group_id text not null,
    source_node_id bigint not null references greek_source_nodes(id),
    dataset_version_id bigint not null references original_language_dataset_versions(id),
    verse_ref text not null,
    clause_type text not null default '',  -- MACULA rule verbatim, e.g. 'O-S-V-IO'
    parent_clause_id bigint references greek_clauses(id),
    parent_phrase_id bigint,               -- FK added after greek_phrases exists, below
    predicate_token_id text references greek_tokens(token_id),
    relation_to_parent text not null default '',  -- MACULA's own predication attribute, e.g. 'elided'
    child_order integer not null default 0,
    created_at timestamptz not null default now(),
    unique (dataset_version_id, macula_group_id)
);

alter table greek_phrases
    add constraint greek_phrases_parent_clause_fkey
    foreign key (parent_clause_id) references greek_clauses(id);

alter table greek_clauses
    add constraint greek_clauses_parent_phrase_fkey
    foreign key (parent_phrase_id) references greek_phrases(id);

create index if not exists idx_greek_phrases_verse on greek_phrases (verse_ref);
create index if not exists idx_greek_phrases_parent on greek_phrases (parent_phrase_id);
create index if not exists idx_greek_clauses_verse on greek_clauses (verse_ref);
create index if not exists idx_greek_clauses_parent on greek_clauses (parent_clause_id);

-- Token membership in a phrase or clause. Unlike Hebrew's join table, a
-- Greek group's member token set is stored ordered (MACULA's own
-- constituent/document order, which can differ from linear word order —
-- see docs/greek_analysis_v2_phase2b_syntax.md's note on hyperbaton) via
-- an explicit member_order column, since Phase 2B/2B.1's local store
-- proved that order carries real linguistic information (§6 of the local
-- greek_syntax_sqlite.py schema stores it as a JSON array for the same
-- reason).
create table if not exists greek_syntax_membership (
    id bigint generated always as identity primary key,
    token_id text not null references greek_tokens(token_id) on delete cascade,
    phrase_id bigint references greek_phrases(id) on delete cascade,
    clause_id bigint references greek_clauses(id) on delete cascade,
    member_order integer not null default 0,
    check (
        (phrase_id is not null and clause_id is null)
        or (phrase_id is null and clause_id is not null)
    )
);

create index if not exists idx_greek_syntax_membership_token on greek_syntax_membership (token_id);
create index if not exists idx_greek_syntax_membership_phrase on greek_syntax_membership (phrase_id, member_order);
create index if not exists idx_greek_syntax_membership_clause on greek_syntax_membership (clause_id, member_order);

-- ===========================================================================
-- 5. Semantic roles (MACULA's `frame` column, PropBank-style Arg0/Arg1/...
--    codes — imported verbatim; this IS the "syntax edges" data for Greek,
--    see header note)
-- ===========================================================================

create table if not exists greek_semantic_roles (
    id bigint generated always as identity primary key,
    dataset_version_id bigint not null references original_language_dataset_versions(id),
    verse_ref text not null,
    predicate_token_id text not null references greek_tokens(token_id),
    role_code text not null,               -- source verbatim, e.g. 'A0', 'A1'
    argument_token_id text not null references greek_tokens(token_id),
    created_at timestamptz not null default now()
);

create index if not exists idx_greek_semantic_roles_verse on greek_semantic_roles (verse_ref);
create index if not exists idx_greek_semantic_roles_predicate on greek_semantic_roles (predicate_token_id);
create index if not exists idx_greek_semantic_roles_argument on greek_semantic_roles (argument_token_id);

-- ===========================================================================
-- 6. Coreference (MACULA's `referent`/`subjref` columns — see
--    bible_engine.greek_syntax_sqlite module docstring for the two
--    distinct link types this deliberately never conflates)
-- ===========================================================================

create table if not exists greek_coreference_links (
    id bigint generated always as identity primary key,
    dataset_version_id bigint not null references original_language_dataset_versions(id),
    verse_ref text not null,
    source_token_id text not null references greek_tokens(token_id),
    link_type text not null,               -- 'referent' (pronoun -> antecedent) | 'subjref' (participle/infinitive -> implicit subject)
    target_token_id text not null references greek_tokens(token_id),
    created_at timestamptz not null default now(),
    check (link_type in ('referent', 'subjref'))
);

create index if not exists idx_greek_coreference_verse on greek_coreference_links (verse_ref);
create index if not exists idx_greek_coreference_source on greek_coreference_links (source_token_id);

-- ===========================================================================
-- 7. Hungarian lexical layer (TBESG-derived; provenance/review-status
--    columns are load-bearing — see docs/greek_analysis_v2_phase2a_
--    foundation.md §3 and §11 of the Phase 2C brief's lexical authority
--    model)
-- ===========================================================================

create table if not exists greek_lexicon_hu (
    id bigint generated always as identity primary key,
    strong_id text not null,               -- canonical disambiguated id, matches greek_tokens.strong_id
    lemma text not null,
    primary_gloss text not null default '',
    senses jsonb not null default '[]'::jsonb,
    note text not null default '',
    review_status text not null default 'draft',        -- 'draft' | 'reviewed'
    translation_method text not null default 'ai_assisted',  -- 'ai_assisted' | 'human'
    source_name text not null default '',
    source_version text not null default '',
    dataset_version_id bigint not null references original_language_dataset_versions(id),
    created_at timestamptz not null default now(),
    unique (dataset_version_id, strong_id),
    check (review_status in ('draft', 'reviewed')),
    check (translation_method in ('ai_assisted', 'human'))
);

create index if not exists idx_greek_lexicon_hu_strong on greek_lexicon_hu (strong_id);

-- ===========================================================================
-- 8. Row Level Security — default-deny, service_role-only (see header note)
-- ===========================================================================

do $$
declare
    tbl text;
begin
    for tbl in
        select unnest(array[
            'greek_verses',
            'greek_tokens',
            'greek_source_nodes',
            'greek_token_alignments',
            'greek_phrases',
            'greek_clauses',
            'greek_syntax_membership',
            'greek_semantic_roles',
            'greek_coreference_links',
            'greek_lexicon_hu'
        ])
    loop
        execute format('alter table %I enable row level security;', tbl);
        execute format('revoke all on %I from anon, authenticated;', tbl);
        execute format('grant select, insert, update, delete on %I to service_role;', tbl);
    end loop;
end $$;
