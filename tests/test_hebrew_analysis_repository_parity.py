"""Phase 2D.2 §10 — Local <-> Supabase repository parity.

Builds ONE small local linguistic store from every real MACULA lowfat
fixture already committed to the repo (Genesis 1:1-1:2, Ruth 1:1/1:2/1:3/
1:8/1:16, Ezra 4:8/4:9/4:10, Genesis 36:5 — the existing Ketiv/Qere +
UNRESOLVED-token regression passage), then, for EVERY verse that store
contains, compares ``LocalHebrewAnalysisRepository.get_verse_syntax()``
against ``SupabaseHebrewAnalysisRepository.get_verse_syntax()`` run against
a fake Postgrest client seeded with the SAME rows the real import script
(``scripts/import_macula_to_supabase.py``) would have written to Supabase —
i.e. this exercises exactly the two read paths a real deployment would have
to agree on, without needing a real network or real credentials.

This deliberately covers more ground than any fixed verse list: every verse
in these four fixtures, including the two structurally interesting cases
(Genesis 36:5's Ketiv/Qere + UNRESOLVED tokens, Ezra 4:9's UNRESOLVED
Aramaic token) that make PARTIALLY_GROUNDED_SYNTAX and mixed-alignment
behavior worth checking. "Any semantic difference is a failure until
explained" — every dataclass field is compared, not just presence/absence.

Genesis 1:22 and Genesis 11:3 (also named in the Phase 2D.2 brief) are
outside every fixture currently committed to the repo; the equivalent
real-corpus check for those two verses was run once, ad hoc, against the
full local Phase 2D.1 build in this session (see
docs/hebrew_analysis_v2_phase2d2.md §10 for the result) rather than adding
new fixture files whose sole purpose would be satisfying this one test.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import bible_engine.hebrew_analysis_repository as repository_module
from bible_engine.hebrew_analysis_repository import LocalHebrewAnalysisRepository, SupabaseHebrewAnalysisRepository
from bible_engine.hebrew_analysis_service import HebrewAnalysisService
from bible_engine.hebrew_linguistic_sqlite import open_store
from bible_engine.hebrew_macula_importer import ensure_dataset_version, import_chapter
from bible_engine.hebrew_token_repository import HebrewTokenRepository
from bible_engine.macula_lowfat_parser import parse_macula_lowfat_chapter

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "macula_lowfat"


def _build_combined_store(store_path: Path) -> None:
    store = open_store(store_path)
    textus_dv = ensure_dataset_version(store, dataset_id="tahot", display_name="TAHOT", revision="test")
    macula_dv = ensure_dataset_version(store, dataset_id="macula_hebrew_lowfat", display_name="MACULA", revision="test")
    repo = HebrewTokenRepository()
    for tahot_book_code, chapter_number, fixture_name in [
        ("Gen", 1, "genesis_excerpt-lowfat.xml"),
        ("Rut", 1, "ruth_1_excerpt-lowfat.xml"),
        ("Ezr", 4, "ezra_4_excerpt-lowfat.xml"),
        ("Gen", 36, "genesis_36_5_excerpt-lowfat.xml"),
    ]:
        chapter = parse_macula_lowfat_chapter(FIXTURES / fixture_name)
        import_chapter(
            chapter, tahot_book_code=tahot_book_code, chapter_number=chapter_number, store=store,
            token_repository=repo, textus_dataset_version_id=textus_dv, macula_dataset_version_id=macula_dv,
        )
    store.close()


def _all_verse_refs(store_path: Path) -> list[str]:
    conn = sqlite3.connect(store_path)
    refs = [row[0] for row in conn.execute("SELECT DISTINCT verse_ref FROM hebrew_verses ORDER BY verse_ref").fetchall()]
    conn.close()
    return refs


_SYNTAX_TABLES_WITH_VERSE_REF = (
    "hebrew_phrases", "hebrew_clauses", "hebrew_syntax_edges",
    "hebrew_semantic_roles", "hebrew_participants", "hebrew_coreference",
)


class _FakeResponse:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self._eq_filters: dict[str, object] = {}
        self._in_filters: dict[str, list] = {}
        self._limit: int | None = None

    def select(self, _columns: str) -> "_FakeQuery":
        return self

    def eq(self, key: str, value) -> "_FakeQuery":
        self._eq_filters[key] = value
        return self

    def in_(self, key: str, values: list) -> "_FakeQuery":
        self._in_filters[key] = values
        return self

    def limit(self, n: int) -> "_FakeQuery":
        self._limit = n
        return self

    def execute(self) -> _FakeResponse:
        matches = [
            row
            for row in self._rows
            if all(row.get(k) == v for k, v in self._eq_filters.items())
            and all(row.get(k) in values for k, values in self._in_filters.items())
        ]
        if self._limit is not None:
            matches = matches[: self._limit]
        return _FakeResponse(matches)


class _FakeTable:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def select(self, columns: str) -> _FakeQuery:
        return _FakeQuery(self.rows).select(columns)


class _FakeClient:
    """Seeded directly from the SAME local SQLite store the Local
    repository reads — i.e. simulates a Supabase project that received
    exactly what ``scripts/import_macula_to_supabase.py`` would have
    written, without needing a real import run or network access."""

    def __init__(self, tables: dict[str, list[dict]]) -> None:
        self._tables = tables

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(self._tables.get(name, []))


def _fake_client_from_local_store(store_path: Path) -> _FakeClient:
    conn = sqlite3.connect(store_path)
    conn.row_factory = sqlite3.Row
    tables: dict[str, list[dict]] = {}

    for table in _SYNTAX_TABLES_WITH_VERSE_REF:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        tables[table] = [dict(row) for row in rows]

    phrase_ids = {row["id"] for row in tables["hebrew_phrases"]}
    clause_ids = {row["id"] for row in tables["hebrew_clauses"]}
    membership_rows = conn.execute("SELECT * FROM hebrew_syntax_membership").fetchall()
    tables["hebrew_syntax_membership"] = [
        dict(row) for row in membership_rows
        if row["phrase_id"] in phrase_ids or row["clause_id"] in clause_ids
    ]

    tables["hebrew_verses"] = [dict(row) for row in conn.execute("SELECT id, verse_ref FROM hebrew_verses").fetchall()]
    tables["hebrew_tokens"] = [dict(row) for row in conn.execute("SELECT token_id, verse_id FROM hebrew_tokens").fetchall()]
    tables["hebrew_token_alignments"] = [
        dict(row) for row in conn.execute("SELECT token_id, alignment_type FROM hebrew_token_alignments").fetchall()
    ]
    conn.close()
    return _FakeClient(tables)


def test_local_and_supabase_repositories_agree_on_every_fixture_verse(tmp_path, monkeypatch):
    store_path = tmp_path / "combined.sqlite3"
    _build_combined_store(store_path)
    verse_refs = _all_verse_refs(store_path)
    assert len(verse_refs) >= 8  # sanity: all four fixtures actually contributed verses

    fake_client = _fake_client_from_local_store(store_path)
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: fake_client)

    local_repo = LocalHebrewAnalysisRepository(store_path)
    supabase_repo = SupabaseHebrewAnalysisRepository()

    mismatches = []
    for verse_ref in verse_refs:
        local_syntax = local_repo.get_verse_syntax(verse_ref)
        supabase_syntax = supabase_repo.get_verse_syntax(verse_ref)
        if local_syntax != supabase_syntax:
            mismatches.append((verse_ref, local_syntax, supabase_syntax))

    assert mismatches == [], (
        "Local/Supabase VerseSyntaxData mismatch for: "
        f"{[m[0] for m in mismatches]}\nFirst mismatch: {mismatches[0] if mismatches else None}"
    )


def test_partially_grounded_verse_present_and_agrees(tmp_path, monkeypatch):
    """Genesis 36:5 is a genuine PARTIALLY_GROUNDED_SYNTAX case (Phase 2D.1:
    2 of its tokens are UNRESOLVED, the rest confirmed) — verify parity
    holds specifically for the grounding-status field on this exact verse,
    not just in aggregate."""
    store_path = tmp_path / "combined.sqlite3"
    _build_combined_store(store_path)
    fake_client = _fake_client_from_local_store(store_path)
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: fake_client)

    local_syntax = LocalHebrewAnalysisRepository(store_path).get_verse_syntax("Gen.36.5")
    supabase_syntax = SupabaseHebrewAnalysisRepository().get_verse_syntax("Gen.36.5")

    assert local_syntax.syntax_grounding == repository_module.SYNTAX_GROUNDING_PARTIAL
    assert supabase_syntax.syntax_grounding == local_syntax.syntax_grounding
    assert local_syntax == supabase_syntax


def test_hungarian_lexical_sense_identical_regardless_of_syntax_backend(tmp_path, monkeypatch):
    """Phase 2D.2 §13: the Hungarian lexicon (``textus_hu_lexicon``,
    Phase 2C) is read entirely independently of which linguistic-syntax
    repository is configured — switching from Local to Supabase must not
    change a single token's ``lexical_sense`` (including its nullable
    ``base_meaning_hu``/``possible_meanings_hu`` gaps) or ``morphology`` or
    ``root``. Same authority-rule check as
    ``test_token_morphology_unchanged_by_syntax_layer`` in
    tests/test_hebrew_macula_alignment.py, extended to the Supabase
    backend."""
    store_path = tmp_path / "combined.sqlite3"
    _build_combined_store(store_path)
    fake_client = _fake_client_from_local_store(store_path)
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: fake_client)

    with_local = HebrewAnalysisService(linguistic_repository=LocalHebrewAnalysisRepository(store_path)).get_hebrew_analysis("Rut 1,1")
    with_supabase = HebrewAnalysisService(linguistic_repository=SupabaseHebrewAnalysisRepository()).get_hebrew_analysis("Rut 1,1")

    tokens_local = with_local.verses[0].tokens
    tokens_supabase = with_supabase.verses[0].tokens
    assert [t.lexical_sense for t in tokens_local] == [t.lexical_sense for t in tokens_supabase]
    assert [t.morphology for t in tokens_local] == [t.morphology for t in tokens_supabase]
    assert [t.root for t in tokens_local] == [t.root for t in tokens_supabase]
    # The syntax data itself must still differ from "no repository at all"
    # in the way expected -- i.e. this isn't passing merely because both
    # backends silently returned nothing.
    assert with_local.verses[0].phrases
    assert with_supabase.verses[0].phrases
