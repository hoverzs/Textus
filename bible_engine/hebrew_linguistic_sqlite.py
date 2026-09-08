"""Phase 2D — local SQLite mirror of the normalized Hebrew linguistic
schema (``supabase/migrations/20260908190000_hebrew_linguistic_layer.sql``).

Used for: offline MACULA import + corpus-wide alignment verification,
small committed test fixtures, and ``LocalHebrewAnalysisRepository`` (dev/
test default, no network). Column set mirrors the Postgres migration as
closely as SQLite's type system allows (INTEGER PK instead of
``bigint generated always as identity``, TEXT instead of ``jsonb``/
``timestamptz``) — see that file for the authoritative column comments and
authority-rule rationale; this module does not repeat them.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "2d.0.0"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS store_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS original_language_dataset_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    revision TEXT NOT NULL,
    source_repository TEXT NOT NULL DEFAULT '',
    source_commit TEXT NOT NULL DEFAULT '',
    license TEXT NOT NULL DEFAULT '',
    attribution TEXT NOT NULL DEFAULT '',
    retrieved_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (dataset_id, revision)
);

CREATE TABLE IF NOT EXISTS hebrew_verses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id TEXT NOT NULL,
    chapter INTEGER NOT NULL,
    verse INTEGER NOT NULL,
    verse_ref TEXT NOT NULL UNIQUE,
    language TEXT NOT NULL,
    dataset_version_id INTEGER NOT NULL REFERENCES original_language_dataset_versions(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (book_id, chapter, verse)
);
CREATE INDEX IF NOT EXISTS idx_hebrew_verses_book_chapter ON hebrew_verses (book_id, chapter, verse);

CREATE TABLE IF NOT EXISTS hebrew_tokens (
    token_id TEXT PRIMARY KEY,
    verse_id INTEGER NOT NULL REFERENCES hebrew_verses(id),
    legacy_stable_key TEXT NOT NULL UNIQUE,
    source_token_id TEXT NOT NULL,
    word_index INTEGER NOT NULL,
    surface TEXT NOT NULL,
    surface_plain TEXT NOT NULL,
    lemma TEXT NOT NULL DEFAULT '',
    transliteration TEXT NOT NULL DEFAULT '',
    part_of_speech TEXT NOT NULL DEFAULT '',
    morphology_raw_code TEXT NOT NULL DEFAULT '',
    morphology_confidence TEXT NOT NULL DEFAULT 'unresolved',
    verb_stem TEXT NOT NULL DEFAULT '',
    verb_form TEXT NOT NULL DEFAULT '',
    person TEXT NOT NULL DEFAULT '',
    gender TEXT NOT NULL DEFAULT '',
    number TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT '',
    ketiv TEXT NOT NULL DEFAULT '',
    qere TEXT NOT NULL DEFAULT '',
    source_edition TEXT NOT NULL DEFAULT '',
    maqaf INTEGER NOT NULL DEFAULT 0,
    punctuation TEXT NOT NULL DEFAULT '',
    dataset_version_id INTEGER NOT NULL REFERENCES original_language_dataset_versions(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_hebrew_tokens_verse ON hebrew_tokens (verse_id, word_index);
CREATE INDEX IF NOT EXISTS idx_hebrew_tokens_source_token_id ON hebrew_tokens (source_token_id);
CREATE INDEX IF NOT EXISTS idx_hebrew_tokens_lemma ON hebrew_tokens (lemma);

CREATE TABLE IF NOT EXISTS hebrew_token_strong_ids (
    token_id TEXT NOT NULL REFERENCES hebrew_tokens(token_id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    strong_id TEXT NOT NULL,
    PRIMARY KEY (token_id, seq)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS hebrew_token_components (
    token_id TEXT NOT NULL REFERENCES hebrew_tokens(token_id) ON DELETE CASCADE,
    component_index INTEGER NOT NULL,
    role TEXT NOT NULL,
    surface TEXT NOT NULL DEFAULT '',
    gloss_en TEXT NOT NULL DEFAULT '',
    strong_id TEXT NOT NULL DEFAULT '',
    is_grammar_marker INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (token_id, component_index)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS hebrew_source_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_version_id INTEGER NOT NULL REFERENCES original_language_dataset_versions(id),
    macula_node_id TEXT NOT NULL,
    node_kind TEXT NOT NULL,
    macula_class TEXT NOT NULL DEFAULT '',
    macula_role TEXT NOT NULL DEFAULT '',
    macula_rule TEXT NOT NULL DEFAULT '',
    clause_type TEXT NOT NULL DEFAULT '',
    parent_node_id INTEGER REFERENCES hebrew_source_nodes(id),
    child_order INTEGER NOT NULL DEFAULT 0,
    verse_ref TEXT NOT NULL,
    surface TEXT NOT NULL DEFAULT '',
    lemma TEXT NOT NULL DEFAULT '',
    transliteration TEXT NOT NULL DEFAULT '',
    gloss_en TEXT NOT NULL DEFAULT '',
    macula_strong_number TEXT NOT NULL DEFAULT '',
    macula_morph_code TEXT NOT NULL DEFAULT '',
    macula_part_of_speech TEXT NOT NULL DEFAULT '',
    macula_stem TEXT NOT NULL DEFAULT '',
    macula_person TEXT NOT NULL DEFAULT '',
    macula_gender TEXT NOT NULL DEFAULT '',
    macula_number TEXT NOT NULL DEFAULT '',
    raw_attributes TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (dataset_version_id, macula_node_id)
);
CREATE INDEX IF NOT EXISTS idx_source_nodes_parent ON hebrew_source_nodes (parent_node_id, child_order);
CREATE INDEX IF NOT EXISTS idx_source_nodes_verse ON hebrew_source_nodes (dataset_version_id, verse_ref);
CREATE INDEX IF NOT EXISTS idx_source_nodes_kind_class ON hebrew_source_nodes (node_kind, macula_class);

CREATE TABLE IF NOT EXISTS hebrew_token_alignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id TEXT NOT NULL REFERENCES hebrew_tokens(token_id) ON DELETE CASCADE,
    component_index INTEGER,
    source_node_id INTEGER REFERENCES hebrew_source_nodes(id),
    alignment_type TEXT NOT NULL,
    confidence TEXT NOT NULL,
    evidence TEXT NOT NULL,
    dataset_version_id_textus INTEGER NOT NULL REFERENCES original_language_dataset_versions(id),
    dataset_version_id_macula INTEGER NOT NULL REFERENCES original_language_dataset_versions(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (alignment_type IN ('EXACT', 'COMPOSITE', 'VALIDATED_FALLBACK', 'UNRESOLVED')),
    CHECK ((alignment_type = 'UNRESOLVED') = (source_node_id IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_alignments_token ON hebrew_token_alignments (token_id);
CREATE INDEX IF NOT EXISTS idx_alignments_source_node ON hebrew_token_alignments (source_node_id);
CREATE INDEX IF NOT EXISTS idx_alignments_type ON hebrew_token_alignments (alignment_type);

CREATE TABLE IF NOT EXISTS hebrew_phrases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_node_id INTEGER NOT NULL REFERENCES hebrew_source_nodes(id),
    dataset_version_id INTEGER NOT NULL REFERENCES original_language_dataset_versions(id),
    verse_ref TEXT NOT NULL,
    phrase_type TEXT NOT NULL,
    parent_phrase_id INTEGER REFERENCES hebrew_phrases(id),
    parent_clause_id INTEGER REFERENCES hebrew_clauses(id),
    head_token_id TEXT REFERENCES hebrew_tokens(token_id),
    child_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (dataset_version_id, source_node_id)
);

CREATE TABLE IF NOT EXISTS hebrew_clauses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_node_id INTEGER NOT NULL REFERENCES hebrew_source_nodes(id),
    dataset_version_id INTEGER NOT NULL REFERENCES original_language_dataset_versions(id),
    verse_ref TEXT NOT NULL,
    clause_type TEXT NOT NULL DEFAULT '',
    parent_clause_id INTEGER REFERENCES hebrew_clauses(id),
    predicate_token_id TEXT REFERENCES hebrew_tokens(token_id),
    subject_token_id TEXT REFERENCES hebrew_tokens(token_id),
    child_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (dataset_version_id, source_node_id)
);
CREATE INDEX IF NOT EXISTS idx_phrases_verse ON hebrew_phrases (verse_ref);
CREATE INDEX IF NOT EXISTS idx_phrases_parent ON hebrew_phrases (parent_phrase_id);
CREATE INDEX IF NOT EXISTS idx_clauses_verse ON hebrew_clauses (verse_ref);
CREATE INDEX IF NOT EXISTS idx_clauses_parent ON hebrew_clauses (parent_clause_id);

CREATE TABLE IF NOT EXISTS hebrew_syntax_membership (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id TEXT NOT NULL REFERENCES hebrew_tokens(token_id) ON DELETE CASCADE,
    phrase_id INTEGER REFERENCES hebrew_phrases(id) ON DELETE CASCADE,
    clause_id INTEGER REFERENCES hebrew_clauses(id) ON DELETE CASCADE,
    CHECK (
        (phrase_id IS NOT NULL AND clause_id IS NULL)
        OR (phrase_id IS NULL AND clause_id IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS idx_syntax_membership_token ON hebrew_syntax_membership (token_id);
CREATE INDEX IF NOT EXISTS idx_syntax_membership_phrase ON hebrew_syntax_membership (phrase_id);
CREATE INDEX IF NOT EXISTS idx_syntax_membership_clause ON hebrew_syntax_membership (clause_id);

CREATE TABLE IF NOT EXISTS hebrew_syntax_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_version_id INTEGER NOT NULL REFERENCES original_language_dataset_versions(id),
    verse_ref TEXT NOT NULL,
    parent_source_node_id INTEGER NOT NULL REFERENCES hebrew_source_nodes(id),
    child_source_node_id INTEGER NOT NULL REFERENCES hebrew_source_nodes(id),
    relation_type TEXT NOT NULL,
    source_role_code TEXT NOT NULL DEFAULT '',
    parent_token_id TEXT REFERENCES hebrew_tokens(token_id),
    child_token_id TEXT REFERENCES hebrew_tokens(token_id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (dataset_version_id, parent_source_node_id, child_source_node_id)
);
CREATE INDEX IF NOT EXISTS idx_syntax_edges_verse ON hebrew_syntax_edges (verse_ref);
CREATE INDEX IF NOT EXISTS idx_syntax_edges_parent ON hebrew_syntax_edges (parent_source_node_id);
CREATE INDEX IF NOT EXISTS idx_syntax_edges_relation ON hebrew_syntax_edges (relation_type);

CREATE TABLE IF NOT EXISTS hebrew_semantic_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_version_id INTEGER NOT NULL REFERENCES original_language_dataset_versions(id),
    verse_ref TEXT NOT NULL,
    predicate_source_node_id INTEGER NOT NULL REFERENCES hebrew_source_nodes(id),
    predicate_token_id TEXT REFERENCES hebrew_tokens(token_id),
    role_code TEXT NOT NULL,
    role_label TEXT NOT NULL DEFAULT '',
    participant_source_node_id INTEGER REFERENCES hebrew_source_nodes(id),
    participant_token_id TEXT REFERENCES hebrew_tokens(token_id),
    confidence TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_semantic_roles_verse ON hebrew_semantic_roles (verse_ref);
CREATE INDEX IF NOT EXISTS idx_semantic_roles_predicate ON hebrew_semantic_roles (predicate_source_node_id);

CREATE TABLE IF NOT EXISTS hebrew_participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_version_id INTEGER NOT NULL REFERENCES original_language_dataset_versions(id),
    source_node_id INTEGER NOT NULL REFERENCES hebrew_source_nodes(id),
    token_id TEXT REFERENCES hebrew_tokens(token_id),
    verse_ref TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (dataset_version_id, source_node_id)
);

CREATE TABLE IF NOT EXISTS hebrew_coreference (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_version_id INTEGER NOT NULL REFERENCES original_language_dataset_versions(id),
    verse_ref TEXT NOT NULL,
    referring_source_node_id INTEGER NOT NULL REFERENCES hebrew_source_nodes(id),
    referring_token_id TEXT REFERENCES hebrew_tokens(token_id),
    participant_id INTEGER NOT NULL REFERENCES hebrew_participants(id),
    relation_type TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_participants_verse ON hebrew_participants (verse_ref);
CREATE INDEX IF NOT EXISTS idx_coreference_verse ON hebrew_coreference (verse_ref);
CREATE INDEX IF NOT EXISTS idx_coreference_participant ON hebrew_coreference (participant_id);

CREATE TABLE IF NOT EXISTS hebrew_detected_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_id TEXT NOT NULL UNIQUE,
    verse_ref TEXT NOT NULL,
    pattern_type TEXT NOT NULL,
    detector_version TEXT NOT NULL,
    confidence TEXT NOT NULL,
    explanation_hu TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS hebrew_detected_pattern_tokens (
    pattern_id TEXT NOT NULL REFERENCES hebrew_detected_patterns(pattern_id) ON DELETE CASCADE,
    token_id TEXT NOT NULL REFERENCES hebrew_tokens(token_id) ON DELETE CASCADE,
    is_evidence INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (pattern_id, token_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_detected_patterns_verse ON hebrew_detected_patterns (verse_ref);
"""


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(_SCHEMA_SQL)
    connection.execute(
        "INSERT OR REPLACE INTO store_metadata(key, value) VALUES ('schema_version', ?)",
        (SCHEMA_VERSION,),
    )
    connection.commit()


def open_store(path: str | Path, *, create: bool = True) -> sqlite3.Connection:
    path = Path(path)
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if create:
        create_schema(connection)
    return connection


__all__ = ["SCHEMA_VERSION", "create_schema", "open_store"]
