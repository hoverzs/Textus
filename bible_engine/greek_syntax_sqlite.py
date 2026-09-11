"""Phase 2B §5 — normalized local SQLite store for Greek syntax data.

Schema mirrors the entity list the phase brief requested, restricted to
what MACULA Greek (SBLGNT variant) actually supplies (never synthesized):

- ``macula_source_nodes``      — one row per MACULA token (full corpus)
- ``token_alignments``         — one row per TAGNT token (full corpus;
                                  ``macula_xml_id`` NULL when unresolved)
- ``macula_groups``            — phrase/clause constituents (bounded book
                                  scope — see the phase doc §1 for why)
- ``semantic_role_assignments`` — parsed from the flat TSV's own ``frame``
                                  column (full corpus, no XML needed)
- ``coreference_links``        — parsed from the flat TSV's ``referent``
                                  (pronoun → antecedent xml_id(s)) and
                                  ``subjref`` (participle/infinitive →
                                  implicit-subject xml_id) columns — both
                                  genuinely present (14,542 and 16,625
                                  non-empty rows respectively out of
                                  137,741 — see the phase doc §1.3), kept
                                  as two distinct ``link_type`` values,
                                  never conflated into one claim.

TAGNT remains authoritative for every morphology/lemma/token-identity fact;
this store only ever ADDS alignment/syntax facts keyed by the TAGNT token
id, never overrides one.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from bible_engine.greek_token_alignment import TokenAlignment
from bible_engine.macula_greek_parser import MaculaGreekGroup, MaculaGreekToken


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS macula_source_nodes (
            xml_id TEXT PRIMARY KEY,
            book TEXT NOT NULL,
            chapter INTEGER NOT NULL,
            verse INTEGER NOT NULL,
            word_index INTEGER NOT NULL,
            role TEXT, word_class TEXT, word_type TEXT,
            text TEXT, after TEXT, lemma TEXT, normalized TEXT, strong TEXT,
            morph TEXT, person TEXT, number TEXT, gender TEXT, case_ TEXT,
            tense TEXT, voice TEXT, mood TEXT, degree TEXT,
            domain TEXT, ln TEXT, frame TEXT, subjref TEXT, referent TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_macula_nodes_verse
            ON macula_source_nodes(book, chapter, verse);

        CREATE TABLE IF NOT EXISTS token_alignments (
            tagnt_token_id TEXT PRIMARY KEY,
            macula_xml_id TEXT,
            status TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            FOREIGN KEY (macula_xml_id) REFERENCES macula_source_nodes(xml_id)
        );
        CREATE INDEX IF NOT EXISTS idx_alignments_macula
            ON token_alignments(macula_xml_id);

        CREATE TABLE IF NOT EXISTS macula_groups (
            group_id TEXT PRIMARY KEY,
            book TEXT NOT NULL,
            chapter INTEGER NOT NULL,
            verse INTEGER NOT NULL,
            group_class TEXT NOT NULL,
            rule TEXT, role TEXT, predication TEXT,
            token_ids_json TEXT NOT NULL,
            parent_group_id TEXT,
            depth INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_groups_verse
            ON macula_groups(book, chapter, verse);
        CREATE INDEX IF NOT EXISTS idx_groups_parent
            ON macula_groups(parent_group_id);

        CREATE TABLE IF NOT EXISTS semantic_role_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            predicate_xml_id TEXT NOT NULL,
            role_code TEXT NOT NULL,
            argument_xml_id TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_roles_predicate
            ON semantic_role_assignments(predicate_xml_id);
        CREATE INDEX IF NOT EXISTS idx_roles_argument
            ON semantic_role_assignments(argument_xml_id);

        CREATE TABLE IF NOT EXISTS coreference_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_xml_id TEXT NOT NULL,
            link_type TEXT NOT NULL,
            target_xml_id TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_coref_source
            ON coreference_links(source_xml_id);
        CREATE INDEX IF NOT EXISTS idx_coref_target
            ON coreference_links(target_xml_id);
        """
    )


def insert_source_nodes(connection: sqlite3.Connection, tokens: list[MaculaGreekToken]) -> None:
    connection.executemany(
        """
        INSERT OR IGNORE INTO macula_source_nodes (
            xml_id, book, chapter, verse, word_index, role, word_class, word_type,
            text, after, lemma, normalized, strong, morph, person, number, gender,
            case_, tense, voice, mood, degree, domain, ln, frame, subjref, referent
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        [
            (
                t.xml_id, t.book, t.chapter, t.verse, t.word_index, t.role, t.word_class,
                t.word_type, t.text, t.after, t.lemma, t.normalized, t.strong, t.morph,
                t.person, t.number, t.gender, t.case, t.tense, t.voice, t.mood, t.degree,
                t.domain, t.ln, t.frame, t.subjref, t.referent,
            )
            for t in tokens
        ],
    )


def insert_alignments(connection: sqlite3.Connection, alignments: list[TokenAlignment]) -> None:
    connection.executemany(
        "INSERT OR REPLACE INTO token_alignments (tagnt_token_id, macula_xml_id, status, evidence_json) "
        "VALUES (?,?,?,?)",
        [
            (a.tagnt_token_id, a.macula_xml_id, a.status, json.dumps(a.evidence, ensure_ascii=False))
            for a in alignments
        ],
    )


def insert_groups(
    connection: sqlite3.Connection, book: str, groups: list[MaculaGreekGroup], node_ref: dict[str, MaculaGreekToken]
) -> None:
    rows = []
    for g in groups:
        if not g.token_ids:
            continue
        first = node_ref.get(g.token_ids[0])
        if first is None:
            continue
        rows.append(
            (
                g.group_id, first.book, first.chapter, first.verse, g.group_class,
                g.rule, g.role, g.predication, json.dumps(g.token_ids), g.parent_group_id, g.depth,
            )
        )
    connection.executemany(
        "INSERT OR REPLACE INTO macula_groups "
        "(group_id, book, chapter, verse, group_class, rule, role, predication, token_ids_json, parent_group_id, depth) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )


_IMPLICIT_ARGUMENT_SENTINEL_RE = re.compile(r"^n0+$")


def insert_semantic_role_assignments(connection: sqlite3.Connection, tokens: list[MaculaGreekToken]) -> None:
    """Parses MACULA's ``frame`` column, e.g. ``"A0:n40001002001 A1:n40001002004"``
    (space-separated ``ROLE:xml_id`` pairs) into individual role-assignment rows.

    MACULA uses ``"n00000000000"`` (all-zero) as its OWN documented sentinel
    for an argument that is grammatically implicit/unexpressed (e.g. a
    passive participle's understood but unstated patient) — not a real
    token reference. Measured: 1,891 of 43,662 frame arguments corpus-wide
    (4.3%) are this sentinel; excluded here so "every referenced token
    exists" holds as a real invariant rather than needing an exception for
    a value that was never meant to identify a token.

    Separately, 4 frame arguments (e.g. ``n42001054008`` for Luke 1:54,
    which the TSV export only tokenizes up to ``n42001054006``) reference an
    xml:id that simply does not exist anywhere in this export — a tiny,
    measured upstream MACULA data inconsistency, not a bug in this parser.
    Filtered here (rather than skipped silently deeper in the pipeline) so
    the exclusion is visible at the one place it happens."""
    node_ids = {t.xml_id for t in tokens}
    rows = []
    for t in tokens:
        if not t.frame:
            continue
        for part in t.frame.split():
            if ":" not in part:
                continue
            role_code, _, argument_ids = part.partition(":")
            for argument_id in argument_ids.split(";"):
                argument_id = argument_id.strip()
                if not argument_id or _IMPLICIT_ARGUMENT_SENTINEL_RE.match(argument_id):
                    continue
                if argument_id not in node_ids:
                    continue
                rows.append((t.xml_id, role_code, argument_id))
    connection.executemany(
        "INSERT INTO semantic_role_assignments (predicate_xml_id, role_code, argument_xml_id) VALUES (?,?,?)",
        rows,
    )


def insert_coreference_links(connection: sqlite3.Connection, tokens: list[MaculaGreekToken]) -> None:
    """Parses ``referent`` (pronoun -> space-separated antecedent xml_id(s))
    and ``subjref`` (participle/infinitive -> implicit-subject xml_id) into
    individual link rows, tagged by ``link_type`` so the two distinct kinds
    of MACULA-supplied fact are never merged into one claim."""
    rows = []
    for t in tokens:
        for target in (t.referent or "").split():
            rows.append((t.xml_id, "referent", target))
        for target in (t.subjref or "").split():
            rows.append((t.xml_id, "subjref", target))
    connection.executemany(
        "INSERT INTO coreference_links (source_xml_id, link_type, target_xml_id) VALUES (?,?,?)",
        rows,
    )


def resolve_default_syntax_database_path() -> Path:
    import os

    env_value = os.environ.get("TEXTUS_GREEK_SYNTAX_DB_PATH")
    if env_value:
        return Path(env_value)
    from bible_engine.paths import GENERATED_DATA_DIR

    return GENERATED_DATA_DIR / "greek_syntax_dev.sqlite3"
