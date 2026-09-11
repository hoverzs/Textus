from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bible_engine.tbesg_sqlite import (
    EXPECTED_HEADER,
    SQLiteGreekLexiconEntry,
    create_schema,
    get_sqlite_lexicon_entry,
    import_tbesg_lexicon,
    validate_tbesg_database,
)


ROOT = Path(__file__).parents[1]
TBESG_FIXTURE = ROOT / "tests" / "fixtures" / "tbesg_sample.tsv"


def test_creates_expected_schema(tmp_path: Path) -> None:
    database = tmp_path / "lexicon.sqlite3"

    with sqlite3.connect(database) as connection:
        create_schema(connection)
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(greek_lexicon)").fetchall()
        }

    assert {
        "strong_id",
        "dstrong_id",
        "ustrong_id",
        "lemma",
        "lemma_normalized",
        "transliteration",
        "morph",
        "gloss",
        "meaning_raw",
        "meaning_plain",
        "meaning_paragraphs_json",
        "references_json",
        "source_name",
        "source_version",
        "imported_at",
    } <= columns


def test_imports_tbesg_fixture_and_preserves_fields(tmp_path: Path) -> None:
    database = _import_fixture(tmp_path)

    entry = get_sqlite_lexicon_entry(database, "G0025")

    assert isinstance(entry, SQLiteGreekLexiconEntry)
    assert entry.strong_id == "G0025"
    assert entry.dstrong_id == "G0025 ="
    assert entry.ustrong_id == "G0025"
    assert entry.lemma == "ἀγαπάω"
    assert entry.transliteration == "agapaō"
    assert entry.morph == "G:V"
    assert entry.gloss == "to love"
    assert entry.meaning_raw
    assert entry.meaning_plain
    assert "<b>" not in entry.meaning_plain
    assert entry.meaning_paragraphs
    assert "Mat.5.43" in entry.references
    assert entry.source_name == "STEPBible TBESG"
    assert entry.source_version == "test-version"


def test_meaning_paragraphs_and_references_roundtrip_as_json(tmp_path: Path) -> None:
    database = _import_fixture(tmp_path)

    entry = get_sqlite_lexicon_entry(database, "G2889")

    assert entry is not None
    assert any("world" in paragraph for paragraph in entry.meaning_paragraphs)
    assert "Gen.2.1" in entry.references
    assert all(isinstance(value, str) for value in entry.meaning_paragraphs)
    assert all(isinstance(value, str) for value in entry.references)


def test_strong_normalization_and_lookup(tmp_path: Path) -> None:
    database = _import_fixture(tmp_path)

    assert get_sqlite_lexicon_entry(database, "G25") == get_sqlite_lexicon_entry(
        database, "G0025"
    )
    assert get_sqlite_lexicon_entry(database, "G9999") is None


def test_import_is_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "lexicon.sqlite3"

    first = import_tbesg_lexicon(TBESG_FIXTURE, database)
    second = import_tbesg_lexicon(TBESG_FIXTURE, database)
    validation = validate_tbesg_database(database)

    assert first.rows_imported == 3
    assert second.rows_imported == 0
    assert second.duplicate_rows == 3
    assert validation.entry_count == 3
    assert validation.duplicate_strong_count == 0


def test_duplicate_strong_rows_are_reported(tmp_path: Path) -> None:
    source = tmp_path / "duplicate.tsv"
    lines = TBESG_FIXTURE.read_text(encoding="utf-8").splitlines()
    source.write_text("\n".join([lines[0], lines[1], lines[1]]) + "\n", encoding="utf-8")

    report = import_tbesg_lexicon(source, tmp_path / "lexicon.sqlite3")

    assert report.rows_read == 2
    assert report.rows_imported == 1
    assert report.duplicate_rows == 1


def test_bad_rows_are_reported_without_stopping_import(tmp_path: Path) -> None:
    source = tmp_path / "bad.tsv"
    lines = TBESG_FIXTURE.read_text(encoding="utf-8").splitlines()
    bad_row = "H0157\tH0157 =\tH0157\tἀγάπη\tagapē\tG:N\tlove\tbad meaning"
    source.write_text("\n".join([lines[0], bad_row, lines[1]]) + "\n", encoding="utf-8")

    report = import_tbesg_lexicon(source, tmp_path / "lexicon.sqlite3")

    assert report.rows_read == 2
    assert report.parse_errors == 1
    assert report.rows_imported == 1


def test_missing_strong_rows_are_reported(tmp_path: Path) -> None:
    source = tmp_path / "missing.tsv"
    lines = TBESG_FIXTURE.read_text(encoding="utf-8").splitlines()
    missing_row = "\t\t\tἀγνοέω\tagnoeō\tG:V\tto be ignorant\tmeaning"
    source.write_text("\n".join([lines[0], missing_row, lines[1]]) + "\n", encoding="utf-8")

    report = import_tbesg_lexicon(source, tmp_path / "lexicon.sqlite3")

    assert report.missing_strong_rows == 1
    assert report.rows_imported == 1


def test_missing_source_file_has_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="TBESG source file not found"):
        import_tbesg_lexicon(tmp_path / "missing.tsv", tmp_path / "lexicon.sqlite3")


def test_invalid_database_schema_has_clear_error(tmp_path: Path) -> None:
    database = tmp_path / "invalid.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE greek_lexicon (strong_id TEXT)")

    with pytest.raises(ValueError, match="Invalid TBESG SQLite database schema"):
        get_sqlite_lexicon_entry(database, "G0025")
    with pytest.raises(ValueError, match="Invalid TBESG SQLite database schema"):
        validate_tbesg_database(database)


def test_validation_reports_counts_and_unicode(tmp_path: Path) -> None:
    database = _import_fixture(tmp_path)

    report = validate_tbesg_database(database)

    assert report.entry_count == 3
    assert report.unique_strong_count == 3
    assert report.missing_lemma_count == 0
    assert report.missing_gloss_count == 0
    assert report.missing_meaning_count == 0
    assert report.duplicate_strong_count == 0
    assert report.invalid_strong_count == 0
    assert report.unicode_warning_count == 0
    assert report.warnings == ()


def test_fixture_header_matches_documented_tbesg_header() -> None:
    header = tuple(TBESG_FIXTURE.read_text(encoding="utf-8").splitlines()[0].split("\t"))

    assert header == EXPECTED_HEADER


# ---------------------------------------------------------------------------
# Phase 2A regression: two disambiguated senses sharing one bare eStrong
# (G0001 = "Alpha" and the interjection "ah!") must both survive as distinct,
# independently-lookupable rows — the pre-fix importer keyed by bare eStrong,
# so the second row silently overwrote/collided with the first via
# UNIQUE(strong_id) + INSERT OR IGNORE, and neither disambiguated (dStrong-
# suffixed) id — the ONLY form real callers (TAGNT tokens, lexicon_hu.json)
# ever look up — could be found at all.
# ---------------------------------------------------------------------------


def test_disambiguated_senses_sharing_one_estrong_both_survive(tmp_path: Path) -> None:
    source = tmp_path / "ambiguous.tsv"
    header = "eStrong\tdStrong\tuStrong\tGreek\tTransliteration\tMorph\tGloss\tAbbott-Smith lexicon (AS), with gaps occationally filled from edited versions of  Middle LSJ "
    alpha = "G0001\tG0001G =\tG0001G\tα, Ἀλφα\tAlpha\tG:N-LI\tAlpha\tmeaning-alpha"
    ah = "G0001\tG0001H =\tG0001H\tἆ\ta\tG:INJ\tah!\tmeaning-ah"
    source.write_text("\n".join([header, alpha, ah]) + "\n", encoding="utf-8")

    database = tmp_path / "lexicon.sqlite3"
    report = import_tbesg_lexicon(source, database)

    assert report.rows_read == 2
    assert report.rows_imported == 2
    assert report.duplicate_rows == 0

    alpha_entry = get_sqlite_lexicon_entry(database, "G0001G")
    ah_entry = get_sqlite_lexicon_entry(database, "G0001H")
    assert alpha_entry is not None and alpha_entry.gloss == "Alpha"
    assert ah_entry is not None and ah_entry.gloss == "ah!"
    # Bare, undisambiguated eStrong is not a real lookup a caller performs —
    # neither disambiguated row claims it, by design.
    assert get_sqlite_lexicon_entry(database, "G0001") is None


def _import_fixture(tmp_path: Path) -> Path:
    database = tmp_path / "lexicon.sqlite3"
    report = import_tbesg_lexicon(TBESG_FIXTURE, database, source_version="test-version")
    assert report.rows_read == 3
    assert report.rows_imported == 3
    assert report.parse_errors == 0
    return database
