from __future__ import annotations

import json
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from bible_engine.lexicon_text import parse_lexicon_meaning
from bible_engine.tbesg_parser import normalize_greek_strong_id, parse_tbesg_line


SOURCE_NAME = "STEPBible TBESG"
EXPECTED_HEADER = (
    "eStrong",
    "dStrong",
    "uStrong",
    "Greek",
    "Transliteration",
    "Morph",
    "Gloss",
    "Abbott-Smith lexicon (AS), with gaps occationally filled from edited versions of  Middle LSJ ",
)


@dataclass(frozen=True)
class SQLiteGreekLexiconEntry:
    strong_id: str
    dstrong_id: str | None
    ustrong_id: str | None
    lemma: str
    transliteration: str | None
    morph: str | None
    gloss: str | None
    meaning_raw: str | None
    meaning_plain: str | None
    meaning_paragraphs: tuple[str, ...]
    references: tuple[str, ...]
    source_name: str
    source_version: str | None


@dataclass(frozen=True)
class TBESGImportReport:
    source_path: str
    database_path: str
    rows_read: int
    rows_imported: int
    rows_skipped: int
    parse_errors: int
    duplicate_rows: int
    missing_strong_rows: int
    started_at: str
    completed_at: str


@dataclass(frozen=True)
class TBESGValidationReport:
    entry_count: int
    unique_strong_count: int
    missing_lemma_count: int
    missing_gloss_count: int
    missing_meaning_count: int
    duplicate_strong_count: int
    invalid_strong_count: int
    unicode_warning_count: int
    warnings: tuple[str, ...]


def create_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS greek_lexicon (
            id INTEGER PRIMARY KEY,
            strong_id TEXT NOT NULL,
            dstrong_id TEXT,
            ustrong_id TEXT,
            lemma TEXT,
            lemma_normalized TEXT,
            transliteration TEXT,
            morph TEXT,
            gloss TEXT,
            meaning_raw TEXT,
            meaning_plain TEXT,
            meaning_paragraphs_json TEXT,
            references_json TEXT,
            source_name TEXT NOT NULL,
            source_version TEXT,
            imported_at TEXT NOT NULL,
            UNIQUE(strong_id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_greek_lexicon_strong_id
        ON greek_lexicon(strong_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_greek_lexicon_lemma
        ON greek_lexicon(lemma)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_greek_lexicon_lemma_normalized
        ON greek_lexicon(lemma_normalized)
        """
    )


def import_tbesg_lexicon(
    source_path: str | Path,
    database_path: str | Path,
    source_version: str | None = None,
) -> TBESGImportReport:
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"TBESG source file not found: {source}")

    database = Path(database_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC).isoformat()
    imported_at = started_at

    rows_read = 0
    rows_imported = 0
    rows_skipped = 0
    parse_errors = 0
    duplicate_rows = 0
    missing_strong_rows = 0

    with sqlite3.connect(database) as connection:
        create_schema(connection)
        with connection:
            with source.open("r", encoding="utf-8-sig") as handle:
                header_seen = False
                for raw_line in handle:
                    line = raw_line.rstrip("\r\n")
                    if _is_header_line(line):
                        header_seen = True
                        continue
                    if not header_seen:
                        rows_skipped += 1
                        continue
                    if not line.strip() or _is_separator_line(line):
                        rows_skipped += 1
                        continue

                    rows_read += 1
                    if not line.split("\t", 1)[0].strip():
                        missing_strong_rows += 1
                        continue

                    try:
                        entry = parse_tbesg_line(line)
                        meaning = parse_lexicon_meaning(entry.meaning_raw)
                    except ValueError:
                        parse_errors += 1
                        continue
                    meaning_plain = _optional_text(
                        unicodedata.normalize("NFC", meaning.plain_text)
                    )

                    # Phase 2A — key by the DISAMBIGUATED identity
                    # (``canonical_strong_id``), never the bare eStrong
                    # (``entry.strong_id``). Multiple senses of one base
                    # number (e.g. G0001 = both "Alpha" and the interjection
                    # "ah!") share the same eStrong but have distinct
                    # dStrong-embedded ids; keying by eStrong let
                    # ``UNIQUE(strong_id)`` + INSERT OR IGNORE silently drop
                    # every sense but the first, and made every real,
                    # suffixed lookup (the only kind TAGNT tokens and
                    # lexicon_hu.json ever perform) miss. See
                    # ``GreekLexiconEntry.canonical_strong_id`` for the
                    # corpus-verified derivation.
                    cursor = _insert_entry(
                        connection,
                        entry=SQLiteGreekLexiconEntry(
                            strong_id=entry.canonical_strong_id,
                            dstrong_id=entry.dstrong_id,
                            ustrong_id=entry.ustrong_id,
                            lemma=entry.greek,
                            transliteration=entry.transliteration,
                            morph=entry.morph,
                            gloss=entry.gloss,
                            meaning_raw=entry.meaning_raw,
                            meaning_plain=meaning_plain,
                            meaning_paragraphs=tuple(
                                unicodedata.normalize("NFC", paragraph)
                                for paragraph in meaning.paragraphs
                            ),
                            references=meaning.references,
                            source_name=SOURCE_NAME,
                            source_version=source_version,
                        ),
                        imported_at=imported_at,
                    )
                    if cursor.rowcount:
                        rows_imported += 1
                    else:
                        duplicate_rows += 1

    completed_at = datetime.now(UTC).isoformat()
    return TBESGImportReport(
        source_path=str(source),
        database_path=str(database),
        rows_read=rows_read,
        rows_imported=rows_imported,
        rows_skipped=rows_skipped,
        parse_errors=parse_errors,
        duplicate_rows=duplicate_rows,
        missing_strong_rows=missing_strong_rows,
        started_at=started_at,
        completed_at=completed_at,
    )


def get_sqlite_lexicon_entry(
    database_path: str | Path,
    strong_id: str,
) -> SQLiteGreekLexiconEntry | None:
    database = Path(database_path)
    if not database.exists():
        raise FileNotFoundError(f"TBESG SQLite database not found: {database}")

    normalized = normalize_greek_strong_id(strong_id)
    try:
        with sqlite3.connect(database) as connection:
            row = connection.execute(
                """
                SELECT
                    strong_id,
                    dstrong_id,
                    ustrong_id,
                    lemma,
                    transliteration,
                    morph,
                    gloss,
                    meaning_raw,
                    meaning_plain,
                    meaning_paragraphs_json,
                    references_json,
                    source_name,
                    source_version
                FROM greek_lexicon
                WHERE strong_id = ?
                """,
                (normalized,),
            ).fetchone()
    except sqlite3.Error as error:
        raise ValueError(f"Invalid TBESG SQLite database schema: {error}") from error

    if row is None:
        return None
    return _entry_from_row(row)


def validate_tbesg_database(
    database_path: str | Path,
) -> TBESGValidationReport:
    database = Path(database_path)
    if not database.exists():
        raise FileNotFoundError(f"TBESG SQLite database not found: {database}")

    try:
        with sqlite3.connect(database) as connection:
            entry_count = connection.execute(
                "SELECT COUNT(*) FROM greek_lexicon"
            ).fetchone()[0]
            unique_strong_count = connection.execute(
                "SELECT COUNT(DISTINCT strong_id) FROM greek_lexicon"
            ).fetchone()[0]
            missing_lemma_count = connection.execute(
                "SELECT COUNT(*) FROM greek_lexicon WHERE lemma IS NULL OR lemma = ''"
            ).fetchone()[0]
            missing_gloss_count = connection.execute(
                "SELECT COUNT(*) FROM greek_lexicon WHERE gloss IS NULL OR gloss = ''"
            ).fetchone()[0]
            missing_meaning_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM greek_lexicon
                WHERE meaning_raw IS NULL OR meaning_raw = ''
                """
            ).fetchone()[0]
            duplicate_strong_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT strong_id, COUNT(*) AS total
                    FROM greek_lexicon
                    GROUP BY strong_id
                    HAVING total > 1
                )
                """
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT strong_id, lemma, meaning_plain FROM greek_lexicon"
            ).fetchall()
    except sqlite3.Error as error:
        raise ValueError(f"Invalid TBESG SQLite database schema: {error}") from error

    invalid_strong_count = 0
    unicode_warning_count = 0
    for strong_id, lemma, meaning_plain in rows:
        try:
            normalize_greek_strong_id(strong_id)
        except ValueError:
            invalid_strong_count += 1
        if lemma and unicodedata.normalize("NFC", lemma) != lemma:
            unicode_warning_count += 1
        if meaning_plain and unicodedata.normalize("NFC", meaning_plain) != meaning_plain:
            unicode_warning_count += 1

    warnings: list[str] = []
    if duplicate_strong_count:
        warnings.append(f"Duplicate normalized Strong identifiers: {duplicate_strong_count}")
    if invalid_strong_count:
        warnings.append(f"Invalid Greek Strong identifiers: {invalid_strong_count}")
    if unicode_warning_count:
        warnings.append(f"Unicode NFC warnings: {unicode_warning_count}")

    return TBESGValidationReport(
        entry_count=entry_count,
        unique_strong_count=unique_strong_count,
        missing_lemma_count=missing_lemma_count,
        missing_gloss_count=missing_gloss_count,
        missing_meaning_count=missing_meaning_count,
        duplicate_strong_count=duplicate_strong_count,
        invalid_strong_count=invalid_strong_count,
        unicode_warning_count=unicode_warning_count,
        warnings=tuple(warnings),
    )


def _insert_entry(
    connection: sqlite3.Connection,
    *,
    entry: SQLiteGreekLexiconEntry,
    imported_at: str,
) -> sqlite3.Cursor:
    return connection.execute(
        """
        INSERT OR IGNORE INTO greek_lexicon (
            strong_id,
            dstrong_id,
            ustrong_id,
            lemma,
            lemma_normalized,
            transliteration,
            morph,
            gloss,
            meaning_raw,
            meaning_plain,
            meaning_paragraphs_json,
            references_json,
            source_name,
            source_version,
            imported_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.strong_id,
            entry.dstrong_id,
            entry.ustrong_id,
            entry.lemma,
            _normalized_lemma(entry.lemma),
            entry.transliteration,
            entry.morph,
            entry.gloss,
            entry.meaning_raw,
            entry.meaning_plain,
            json.dumps(entry.meaning_paragraphs, ensure_ascii=False),
            json.dumps(entry.references, ensure_ascii=False),
            entry.source_name,
            entry.source_version,
            imported_at,
        ),
    )


def _entry_from_row(row: tuple[object, ...]) -> SQLiteGreekLexiconEntry:
    return SQLiteGreekLexiconEntry(
        strong_id=str(row[0]),
        dstrong_id=row[1] if row[1] is None else str(row[1]),
        ustrong_id=row[2] if row[2] is None else str(row[2]),
        lemma=str(row[3] or ""),
        transliteration=row[4] if row[4] is None else str(row[4]),
        morph=row[5] if row[5] is None else str(row[5]),
        gloss=row[6] if row[6] is None else str(row[6]),
        meaning_raw=row[7] if row[7] is None else str(row[7]),
        meaning_plain=row[8] if row[8] is None else str(row[8]),
        meaning_paragraphs=tuple(json.loads(str(row[9] or "[]"))),
        references=tuple(json.loads(str(row[10] or "[]"))),
        source_name=str(row[11]),
        source_version=row[12] if row[12] is None else str(row[12]),
    )


def _is_header_line(line: str) -> bool:
    return tuple(line.split("\t")) == EXPECTED_HEADER


def _is_separator_line(line: str) -> bool:
    stripped = line.strip("=\t ")
    return not stripped and "=" in line


def _normalized_lemma(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _optional_text(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None
