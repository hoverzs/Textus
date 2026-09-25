from __future__ import annotations

from passage_trace import traced as _traced_stage  # TEMPORARY passage-crash diagnostics

import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from bible_engine.paths import GENERATED_DATA_DIR, PROJECT_ROOT
from bible_engine.tagnt_books import parse_tagnt_bible_reference
from bible_engine.tagnt_books import tagnt_book_code_from_ruf_code
from bible_engine.tagnt_parser import GreekToken
from bible_engine.tagnt_sqlite import get_sqlite_verse_tokens


DEFAULT_TAGNT_DATABASE_PATH = GENERATED_DATA_DIR / "tagnt_nt.sqlite3"
TAGNT_DATABASE_ENV_VAR = "TEXTUS_TAGNT_DB_PATH"
REQUIRED_TAGNT_TABLES = frozenset({"greek_tokens"})

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GreekVerseTokens:
    book: str
    chapter: int
    verse: int
    tokens: tuple[GreekToken, ...]


@dataclass(frozen=True)
class TagntDatabaseDiagnostics:
    path: Path
    cwd: Path
    exists: bool
    is_file: bool
    size_bytes: int | None
    sqlite_openable: bool
    required_tables_present: bool
    error: str = ""


def resolve_tagnt_database_path() -> Path | None:
    env_value = os.environ.get(TAGNT_DATABASE_ENV_VAR)
    if env_value and env_value.strip():
        return _stable_database_path(env_value)

    secret_value = _tagnt_database_path_from_streamlit_secrets()
    if secret_value:
        return _stable_database_path(secret_value)

    return DEFAULT_TAGNT_DATABASE_PATH


@_traced_stage("greek_inspect_tagnt_sqlite")
def inspect_tagnt_database_path(database_path: str | Path | None = None) -> TagntDatabaseDiagnostics:
    path = Path(database_path) if database_path is not None else resolve_tagnt_database_path()
    if path is None:
        path = Path("")
    path = _stable_database_path(path)
    exists = path.exists()
    is_file = path.is_file()
    size_bytes = path.stat().st_size if is_file else None
    sqlite_openable = False
    required_tables_present = False
    error = ""

    if is_file:
        try:
            with sqlite3.connect(path) as connection:
                rows = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            tables = {str(row[0]) for row in rows}
            sqlite_openable = True
            required_tables_present = REQUIRED_TAGNT_TABLES.issubset(tables)
        except sqlite3.Error as exc:
            error = str(exc)

    return TagntDatabaseDiagnostics(
        path=path,
        cwd=Path.cwd(),
        exists=exists,
        is_file=is_file,
        size_bytes=size_bytes,
        sqlite_openable=sqlite_openable,
        required_tables_present=required_tables_present,
        error=error,
    )


def load_greek_verse_tokens(
    reference: str,
    database_path: str | Path | None = None,
) -> list[GreekToken]:
    verses = load_greek_passage_tokens(reference, database_path=database_path)
    if len(verses) != 1:
        raise ValueError(f"Only single verse references are supported: {reference!r}")
    return list(verses[0].tokens)


@_traced_stage("greek_load_passage_tokens")
def load_greek_passage_tokens(
    reference: str,
    database_path: str | Path | None = None,
) -> list[GreekVerseTokens]:
    parsed = parse_tagnt_bible_reference(reference)
    tagnt_book = tagnt_book_code_from_ruf_code(parsed.book.code)
    if tagnt_book is None:
        raise ValueError(
            f"Only New Testament books are available in the local TAGNT database: {reference!r}"
        )
    if parsed.verse_start is None:
        raise ValueError(f"Only verse references are supported: {reference!r}")

    path = _stable_database_path(database_path) if database_path is not None else resolve_tagnt_database_path()
    if path is None:
        raise FileNotFoundError("TAGNT SQLite database path is not configured.")
    diagnostics = inspect_tagnt_database_path(path)
    logger.info(
        "TAGNT database diagnostics: resolved_path=%s cwd=%s exists=%s is_file=%s size_bytes=%s sqlite_openable=%s required_tables_present=%s",
        diagnostics.path,
        diagnostics.cwd,
        diagnostics.exists,
        diagnostics.is_file,
        diagnostics.size_bytes,
        diagnostics.sqlite_openable,
        diagnostics.required_tables_present,
    )
    if not diagnostics.exists:
        raise FileNotFoundError(f"TAGNT SQLite database not found: {diagnostics.path}")

    verse_end = parsed.verse_end or parsed.verse_start
    verses: list[GreekVerseTokens] = []
    for verse in range(parsed.verse_start, verse_end + 1):
        tokens = get_sqlite_verse_tokens(path, tagnt_book, parsed.chapter, verse)
        if not tokens:
            continue
        verses.append(
            GreekVerseTokens(
                book=tagnt_book,
                chapter=parsed.chapter,
                verse=verse,
                tokens=tuple(sorted(tokens, key=lambda token: token.word_index)),
            )
        )
    return sorted(verses, key=lambda item: item.verse)


def _tagnt_database_path_from_streamlit_secrets() -> str | None:
    try:
        import streamlit as st

        tagnt_database = st.secrets.get("tagnt_database", {})
    except Exception:
        return None

    if isinstance(tagnt_database, dict):
        value = tagnt_database.get("path")
    else:
        value = getattr(tagnt_database, "path", None)

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _stable_database_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()
