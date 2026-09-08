-- Hebrew Analysis v2 — Phase 2D: normalized linguistic data layer.
--
-- Adds MACULA-sourced syntax/phrase/clause/semantic-role/coreference data
-- ON TOP OF the Phase 2A/2B/2C deterministic Hebrew foundation (TAHOT
-- tokens, TEHMC morphology, TBESH lexicon), without replacing it. See
-- docs/hebrew_analysis_v2_phase2d.md for the full design rationale.
--
-- AUTHORITY RULE (enforced by design, not just convention): this schema
-- never stores a "winning" morphology value derived from MACULA. Where
-- MACULA's own morphology disagrees with the token's TAHOT/TEHMC-decoded
-- value, the MACULA value is recorded ONLY inside hebrew_source_nodes
-- (raw import, provenance/comparison only) — nothing in hebrew_tokens or
-- hebrew_token_components is ever overwritten from a MACULA fact.
--
-- Access model: mirrors the existing service_role-only convention
-- established in scripts/setup_commentary_translation_table.py — RLS
-- enabled with no policies (default-deny for every non-service_role
-- role), anon/authenticated explicitly revoked, service_role explicitly
-- granted exactly the operations the importer/repository actually need.
-- This data is public-domain/CC-BY linguistic reference data (not
-- per-user content), so read access for `anon`/`authenticated` MAY be
-- granted later via an explicit SELECT-only grant once a read-facing
-- Supabase repository is actually deployed — deliberately NOT done here,
-- to keep this migration's blast radius limited to what Phase 2D itself
-- needs (service_role-only import + local/service-role reads).
--
-- This file has been validated locally (parsed/dry-run against a local
-- Postgres-compatible check where practical) but has NOT been applied to
-- any real Supabase project from this environment — see
-- docs/hebrew_analysis_v2_phase2d.md §6 for exact manual-apply steps.

-- ===========================================================================
-- 1. Dataset version / provenance registry
-- ===========================================================================

create table if not exists original_language_dataset_versions (
    id bigint generated always as identity primary key,
    dataset_id text not null,              -- 'tahot' | 'tehmc' | 'tbesh' | 'macula_hebrew_lowfat' | 'hebrew_component_fidelity' | 'textus_hu_lexicon'
    display_name text not null,
    revision text not null,                -- upstream tag/version or commit SHA
    source_repository text not null default '',
    source_commit text not null default '',
    license text not null default '',
    attribution text not null default '',
    retrieved_at timestamptz,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    unique (dataset_id, revision)
);

-- Only one active revision per dataset at a time — lookups for "the
-- current TAHOT version" or "the current MACULA version" never need to
-- resolve ambiguity between multiple concurrently-active revisions.
create unique index if not exists idx_dataset_versions_one_active
    on original_language_dataset_versions (dataset_id)
    where is_active;

-- ===========================================================================
-- 2. Canonical verse + token identity (TAHOT-authoritative, Phase 2C carried
--    forward — see bible_engine.hebrew_token_identity for the id scheme)
-- ===========================================================================

create table if not exists hebrew_verses (
    id bigint generated always as identity primary key,
    book_id text not null,                 -- OSIS-like canonical book id, e.g. 'Ruth', '1Sam'
    chapter integer not null,
    verse integer not null,
    verse_ref text not null,               -- canonical string form, e.g. 'Ruth.1.1'
    language text not null,                -- 'hebrew' | 'aramaic' | 'mixed'
    dataset_version_id bigint not null references original_language_dataset_versions(id),
    created_at timestamptz not null default now(),
    unique (book_id, chapter, verse),
    unique (verse_ref)
);

create index if not exists idx_hebrew_verses_book_chapter
    on hebrew_verses (book_id, chapter, verse);

create table if not exists hebrew_tokens (
    -- token_id is the Phase 2C stable Textus id
    -- ({OSIS_book}.{chapter}.{verse}:{word_index}) — the natural key every
    -- other table in this schema references. See
    -- bible_engine.hebrew_token_identity.build_token_id.
    token_id text primary key,
    verse_id bigint not null references hebrew_verses(id),
    legacy_stable_key text not null,       -- pre-2C 'book:chapter:verse:word_index' (TAHOT book code) form
    source_token_id text not null,         -- verbatim TAHOT record id, e.g. 'Rut.1.1#01=L'
    word_index integer not null,

    surface text not null,
    surface_plain text not null,
    lemma text not null default '',
    transliteration text not null default '',

    part_of_speech text not null default '',
    morphology_raw_code text not null default '',
    morphology_confidence text not null default 'unresolved',
    verb_stem text not null default '',
    verb_form text not null default '',
    person text not null default '',
    gender text not null default '',
    number text not null default '',
    state text not null default '',

    ketiv text not null default '',
    qere text not null default '',
    source_edition text not null default '',
    maqaf boolean not null default false,
    punctuation text not null default '',

    -- root is intentionally NOT a column here — Phase 2C established that
    -- no deterministic Hebrew root source exists yet; adding a nullable
    -- column that is always NULL would invite a future writer to silently
    -- start populating it from a non-authoritative source. Re-introduce
    -- explicitly (with its own authority rule) only once a real
    -- deterministic root source is integrated.

    dataset_version_id bigint not null references original_language_dataset_versions(id),
    created_at timestamptz not null default now(),
    unique (legacy_stable_key)
);

create index if not exists idx_hebrew_tokens_verse
    on hebrew_tokens (verse_id, word_index);
create index if not exists idx_hebrew_tokens_source_token_id
    on hebrew_tokens (source_token_id);
create index if not exists idx_hebrew_tokens_lemma
    on hebrew_tokens (lemma);

create table if not exists hebrew_token_strong_ids (
    token_id text not null references hebrew_tokens(token_id) on delete cascade,
    seq integer not null,
    strong_id text not null,
    primary key (token_id, seq)
);

create table if not exists hebrew_token_components (
    token_id text not null references hebrew_tokens(token_id) on delete cascade,
    component_index integer not null,
    role text not null,                    -- 'prefix' | 'core' | 'suffix'
    surface text not null default '',
    gloss_en text not null default '',
    strong_id text not null default '',
    is_grammar_marker boolean not null default false,
    primary key (token_id, component_index)
);

-- ===========================================================================
-- 3. MACULA raw import — the full source tree, kept for provenance,
--    comparison, and as the basis the normalized phrase/clause/role tables
--    below are built from. Never itself treated as morphology authority.
-- ===========================================================================

create table if not exists hebrew_source_nodes (
    id bigint generated always as identity primary key,
    dataset_version_id bigint not null references original_language_dataset_versions(id),
    macula_node_id text not null,          -- MACULA's own xml:id, e.g. 'o080010010011'
    node_kind text not null,               -- 'word' | 'group'
    macula_class text not null default '', -- 'cj' | 'cl' | 'pp' | 'np' | 'vp' | ... (source vocabulary, verbatim)
    macula_role text not null default '',  -- 'v' | 's' | 'o' | 'p' | 'pp' | 'adv' | '' (source vocabulary, verbatim)
    macula_rule text not null default '',
    clause_type text not null default '',
    parent_node_id bigint references hebrew_source_nodes(id),
    child_order integer not null default 0,
    verse_ref text not null,
    surface text not null default '',
    lemma text not null default '',
    transliteration text not null default '',
    gloss_en text not null default '',
    -- MACULA's own morphology values, kept ONLY for comparison against the
    -- TAHOT/TEHMC-authoritative hebrew_tokens row — never copied there.
    macula_strong_number text not null default '',
    macula_morph_code text not null default '',
    macula_part_of_speech text not null default '',
    macula_stem text not null default '',
    macula_person text not null default '',
    macula_gender text not null default '',
    macula_number text not null default '',
    -- Every other source-specific attribute MACULA carries (mandarin gloss,
    -- Greek equivalent, semantic-domain codes, sense numbers, ...) that is
    -- not promoted to a first-class column above — genuinely optional,
    -- source-varying metadata, the one legitimate JSONB use in this schema.
    raw_attributes jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (dataset_version_id, macula_node_id)
);

create index if not exists idx_source_nodes_parent
    on hebrew_source_nodes (parent_node_id, child_order);
create index if not exists idx_source_nodes_verse
    on hebrew_source_nodes (dataset_version_id, verse_ref);
create index if not exists idx_source_nodes_kind_class
    on hebrew_source_nodes (node_kind, macula_class);

-- ===========================================================================
-- 4. Textus ↔ MACULA token alignment (see docs/hebrew_analysis_v2_phase2d.md
--    §3 for the deterministic evidence-priority algorithm)
-- ===========================================================================

create table if not exists hebrew_token_alignments (
    id bigint generated always as identity primary key,
    token_id text not null references hebrew_tokens(token_id) on delete cascade,
    component_index integer,               -- NULL = token-level alignment; set = component-level
    source_node_id bigint references hebrew_source_nodes(id),  -- NULL only for UNRESOLVED
    alignment_type text not null,          -- 'EXACT' | 'COMPOSITE' | 'VALIDATED_FALLBACK' | 'UNRESOLVED'
    confidence text not null,              -- 'certain' | 'probable' | 'low' | 'none'
    evidence text not null,                -- human-readable reason, e.g. 'verse_ref+word_index+surface exact match'
    dataset_version_id_textus bigint not null references original_language_dataset_versions(id),
    dataset_version_id_macula bigint not null references original_language_dataset_versions(id),
    created_at timestamptz not null default now(),
    check (alignment_type in ('EXACT', 'COMPOSITE', 'VALIDATED_FALLBACK', 'UNRESOLVED')),
    check ((alignment_type = 'UNRESOLVED') = (source_node_id is null))
);

create index if not exists idx_alignments_token
    on hebrew_token_alignments (token_id);
create index if not exists idx_alignments_source_node
    on hebrew_token_alignments (source_node_id);
create index if not exists idx_alignments_type
    on hebrew_token_alignments (alignment_type);

-- ===========================================================================
-- 5. Normalized phrase / clause structure (derived from hebrew_source_nodes
--    once alignment is validated — never generated, only imported)
-- ===========================================================================

create table if not exists hebrew_phrases (
    id bigint generated always as identity primary key,
    source_node_id bigint not null references hebrew_source_nodes(id),
    dataset_version_id bigint not null references original_language_dataset_versions(id),
    verse_ref text not null,
    phrase_type text not null,             -- MACULA class verbatim: 'pp' | 'np' | 'advp' | ...
    parent_phrase_id bigint references hebrew_phrases(id),
    parent_clause_id bigint,               -- set below once hebrew_clauses exists (nullable FK added after)
    head_token_id text references hebrew_tokens(token_id),
    child_order integer not null default 0,
    created_at timestamptz not null default now(),
    unique (dataset_version_id, source_node_id)
);

create table if not exists hebrew_clauses (
    id bigint generated always as identity primary key,
    source_node_id bigint not null references hebrew_source_nodes(id),
    dataset_version_id bigint not null references original_language_dataset_versions(id),
    verse_ref text not null,
    clause_type text not null default '',  -- MACULA clausetype verbatim, e.g. 'nominalized-clause'
    parent_clause_id bigint references hebrew_clauses(id),
    predicate_token_id text references hebrew_tokens(token_id),
    subject_token_id text references hebrew_tokens(token_id),
    child_order integer not null default 0,
    created_at timestamptz not null default now(),
    unique (dataset_version_id, source_node_id)
);

alter table hebrew_phrases
    add constraint hebrew_phrases_parent_clause_fkey
    foreign key (parent_clause_id) references hebrew_clauses(id);

create index if not exists idx_phrases_verse on hebrew_phrases (verse_ref);
create index if not exists idx_phrases_parent on hebrew_phrases (parent_phrase_id);
create index if not exists idx_clauses_verse on hebrew_clauses (verse_ref);
create index if not exists idx_clauses_parent on hebrew_clauses (parent_clause_id);

-- Token/component membership in a phrase or clause (many-to-many via
-- explicit join table — a token can be a leaf of exactly one immediate
-- group in the source tree, but this stays a join table rather than a
-- foreign key on hebrew_tokens so a token never needs to "belong" to
-- syntax data at all when none was imported for it).
create table if not exists hebrew_syntax_membership (
    id bigint generated always as identity primary key,
    token_id text not null references hebrew_tokens(token_id) on delete cascade,
    phrase_id bigint references hebrew_phrases(id) on delete cascade,
    clause_id bigint references hebrew_clauses(id) on delete cascade,
    check (
        (phrase_id is not null and clause_id is null)
        or (phrase_id is null and clause_id is not null)
    )
);

create index if not exists idx_syntax_membership_token on hebrew_syntax_membership (token_id);
create index if not exists idx_syntax_membership_phrase on hebrew_syntax_membership (phrase_id);
create index if not exists idx_syntax_membership_clause on hebrew_syntax_membership (clause_id);

-- ===========================================================================
-- 6. Syntax relations (subject/predicate/object/modifier/... where MACULA
--    explicitly encodes them via its `role` attribute)
-- ===========================================================================

create table if not exists hebrew_syntax_edges (
    id bigint generated always as identity primary key,
    dataset_version_id bigint not null references original_language_dataset_versions(id),
    verse_ref text not null,
    parent_source_node_id bigint not null references hebrew_source_nodes(id),
    child_source_node_id bigint not null references hebrew_source_nodes(id),
    relation_type text not null,           -- normalized: 'subject' | 'predicate' | 'object' | 'modifier' | 'complement' | 'phrase_member' | 'clause_member' | 'other'
    source_role_code text not null default '',  -- MACULA's own role attribute, verbatim (e.g. 's', 'v', 'o', 'p', 'adv')
    parent_token_id text references hebrew_tokens(token_id),
    child_token_id text references hebrew_tokens(token_id),
    created_at timestamptz not null default now(),
    unique (dataset_version_id, parent_source_node_id, child_source_node_id)
);

create index if not exists idx_syntax_edges_verse on hebrew_syntax_edges (verse_ref);
create index if not exists idx_syntax_edges_parent on hebrew_syntax_edges (parent_source_node_id);
create index if not exists idx_syntax_edges_relation on hebrew_syntax_edges (relation_type);

-- ===========================================================================
-- 7. Semantic roles (from MACULA's `frame` attribute, PropBank-style
--    Arg0/Arg1/... codes — imported verbatim, only lightly labeled)
-- ===========================================================================

create table if not exists hebrew_semantic_roles (
    id bigint generated always as identity primary key,
    dataset_version_id bigint not null references original_language_dataset_versions(id),
    verse_ref text not null,
    predicate_source_node_id bigint not null references hebrew_source_nodes(id),
    predicate_token_id text references hebrew_tokens(token_id),
    role_code text not null,               -- source verbatim, e.g. 'A0', 'A1', 'A2'
    role_label text not null default '',   -- normalized label where a stable convention is known, e.g. 'agent', 'patient' — empty if not confidently mappable
    participant_source_node_id bigint references hebrew_source_nodes(id),
    participant_token_id text references hebrew_tokens(token_id),
    confidence text not null default '',   -- only set if MACULA itself encodes a confidence signal; empty otherwise
    created_at timestamptz not null default now()
);

create index if not exists idx_semantic_roles_verse on hebrew_semantic_roles (verse_ref);
create index if not exists idx_semantic_roles_predicate on hebrew_semantic_roles (predicate_source_node_id);

-- ===========================================================================
-- 8. Participants and coreference (from MACULA's `subjref`/`participantref`)
-- ===========================================================================

create table if not exists hebrew_participants (
    id bigint generated always as identity primary key,
    dataset_version_id bigint not null references original_language_dataset_versions(id),
    source_node_id bigint not null references hebrew_source_nodes(id),
    token_id text references hebrew_tokens(token_id),
    verse_ref text not null,
    created_at timestamptz not null default now(),
    unique (dataset_version_id, source_node_id)
);

create table if not exists hebrew_coreference (
    id bigint generated always as identity primary key,
    dataset_version_id bigint not null references original_language_dataset_versions(id),
    verse_ref text not null,
    referring_source_node_id bigint not null references hebrew_source_nodes(id),
    referring_token_id text references hebrew_tokens(token_id),
    participant_id bigint not null references hebrew_participants(id),
    relation_type text not null,           -- 'subjref' | 'participantref' (MACULA attribute name, verbatim)
    created_at timestamptz not null default now()
);

create index if not exists idx_participants_verse on hebrew_participants (verse_ref);
create index if not exists idx_coreference_verse on hebrew_coreference (verse_ref);
create index if not exists idx_coreference_participant on hebrew_coreference (participant_id);

-- ===========================================================================
-- 9. Detected patterns (Phase 2C deterministic structural-fact detectors —
--    Textus-generated, not MACULA-sourced, included here so the whole
--    linguistic layer can live in one place once Supabase is the runtime
--    store)
-- ===========================================================================

create table if not exists hebrew_detected_patterns (
    id bigint generated always as identity primary key,
    pattern_id text not null unique,       -- e.g. 'Gen.1.2.negation'
    verse_ref text not null,
    pattern_type text not null,
    detector_version text not null,
    confidence text not null,
    explanation_hu text not null,
    created_at timestamptz not null default now()
);

create table if not exists hebrew_detected_pattern_tokens (
    pattern_id text not null references hebrew_detected_patterns(pattern_id) on delete cascade,
    token_id text not null references hebrew_tokens(token_id) on delete cascade,
    is_evidence boolean not null default true,
    primary key (pattern_id, token_id)
);

create index if not exists idx_detected_patterns_verse on hebrew_detected_patterns (verse_ref);

-- ===========================================================================
-- 10. Row Level Security — default-deny, service_role-only (see header note)
-- ===========================================================================

do $$
declare
    tbl text;
begin
    for tbl in
        select unnest(array[
            'original_language_dataset_versions',
            'hebrew_verses',
            'hebrew_tokens',
            'hebrew_token_strong_ids',
            'hebrew_token_components',
            'hebrew_source_nodes',
            'hebrew_token_alignments',
            'hebrew_phrases',
            'hebrew_clauses',
            'hebrew_syntax_membership',
            'hebrew_syntax_edges',
            'hebrew_semantic_roles',
            'hebrew_participants',
            'hebrew_coreference',
            'hebrew_detected_patterns',
            'hebrew_detected_pattern_tokens'
        ])
    loop
        execute format('alter table %I enable row level security;', tbl);
        execute format('revoke all on %I from anon, authenticated;', tbl);
        execute format('grant select, insert, update, delete on %I to service_role;', tbl);
    end loop;
end $$;
