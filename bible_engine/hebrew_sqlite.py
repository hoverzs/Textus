from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from bible_engine.hebrew_parser import HebrewComponent, HebrewToken, parse_tahot_row
from bible_engine.hebrew_books import OT_BOOK_ORDER
from bible_engine.paths import GENERATED_DATA_DIR
from bible_engine.tbesh_parser import HebrewLexiconEntry, parse_tbesh_row


# Héber kantilláció (te'amim) — Unicode "Hebrew accents" blokk (U+0591–
# U+05AF). A TAHOT lemma-mező gyakran tartalmaz ilyen jeleket (pl.
# "חֶ֫סֶד"), miközben egy felhasználó által beírt/beillesztett héber szó
# (pl. "חֶסֶד") szinte sosem — a lemma-keresésnek ezért a jelek
# figyelmen kívül hagyásával kell egyeznie, különben a pontos `=`
# egyezés hamis negatívot ad egy ténylegesen létező szóra is.
_HEBREW_CANTILLATION_RE = re.compile("[֑-֯]")


def _strip_hebrew_cantillation(text: str) -> str:
    return _HEBREW_CANTILLATION_RE.sub("", text or "")


TAHOT_DATABASE_NAME = "tahot_ot_runtime.sqlite3"
TBESH_DATABASE_NAME = "tbesh_lexicon_runtime.sqlite3"
DEFAULT_TAHOT_DATABASE_PATH = GENERATED_DATA_DIR / TAHOT_DATABASE_NAME
DEFAULT_TBESH_DATABASE_PATH = GENERATED_DATA_DIR / TBESH_DATABASE_NAME

@dataclass(frozen=True)
class HebrewImportReport:
    database_path: str
    rows_read: int
    tokens_imported: int
    lexicon_entries_imported: int
    books: tuple[str, ...]


@dataclass(frozen=True)
class HebrewDatabaseDiagnostics:
    path: str
    exists: bool
    is_file: bool
    size_bytes: int
    integrity_check: str
    required_tables_present: bool
    error: str = ""


def resolve_tahot_database_path(database_path: str | Path | None = None) -> Path:
    return Path(database_path) if database_path is not None else DEFAULT_TAHOT_DATABASE_PATH


def resolve_tbesh_database_path(database_path: str | Path | None = None) -> Path:
    return Path(database_path) if database_path is not None else DEFAULT_TBESH_DATABASE_PATH


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS books (
            book TEXT PRIMARY KEY,
            ordinal INTEGER NOT NULL,
            chapters_count INTEGER NOT NULL DEFAULT 0,
            verses_count INTEGER NOT NULL DEFAULT 0,
            tokens_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY,
            stable_token_key TEXT NOT NULL UNIQUE,
            book TEXT NOT NULL,
            chapter INTEGER NOT NULL,
            verse INTEGER NOT NULL,
            word_index INTEGER NOT NULL,
            token_index INTEGER NOT NULL,
            surface TEXT NOT NULL,
            surface_without_accents TEXT,
            transliteration TEXT,
            english_gloss TEXT,
            lemma TEXT,
            morphology_code TEXT,
            language TEXT NOT NULL,
            ketiv TEXT,
            qere TEXT,
            punctuation TEXT,
            maqaf INTEGER NOT NULL,
            source_token_id TEXT NOT NULL UNIQUE,
            source_edition TEXT,
            meaning_variant TEXT,
            spelling_variant TEXT,
            expanded_strong_tags TEXT,
            raw_fields_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS token_components (
            id INTEGER PRIMARY KEY,
            stable_token_key TEXT NOT NULL,
            component_index INTEGER NOT NULL,
            role TEXT NOT NULL,
            surface TEXT,
            strong_id TEXT,
            morphology_code TEXT,
            gloss TEXT,
            FOREIGN KEY(stable_token_key) REFERENCES tokens(stable_token_key)
        );

        CREATE TABLE IF NOT EXISTS token_strong_ids (
            stable_token_key TEXT NOT NULL,
            strong_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'token',
            PRIMARY KEY(stable_token_key, strong_id, role),
            FOREIGN KEY(stable_token_key) REFERENCES tokens(stable_token_key)
        );

        CREATE TABLE IF NOT EXISTS ketiv_qere (
            stable_token_key TEXT PRIMARY KEY,
            ketiv TEXT,
            qere TEXT,
            meaning_variant TEXT,
            spelling_variant TEXT,
            FOREIGN KEY(stable_token_key) REFERENCES tokens(stable_token_key)
        );

        CREATE TABLE IF NOT EXISTS lexicon_entries (
            strong_id TEXT PRIMARY KEY,
            estrong TEXT,
            dstrong TEXT,
            ustrong TEXT,
            hebrew TEXT,
            transliteration TEXT,
            morph TEXT,
            gloss TEXT,
            meaning TEXT,
            language TEXT,
            source_name TEXT NOT NULL,
            raw_fields_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS strong_aliases (
            source_id TEXT PRIMARY KEY,
            target_id TEXT NOT NULL,
            confidence TEXT NOT NULL,
            evidence TEXT NOT NULL,
            occurrence_count INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_tokens_reference ON tokens(book, chapter, verse, word_index);
        CREATE INDEX IF NOT EXISTS idx_tokens_lemma ON tokens(lemma);
        CREATE INDEX IF NOT EXISTS idx_tokens_source_token_id ON tokens(source_token_id);
        CREATE INDEX IF NOT EXISTS idx_tokens_language ON tokens(language);
        CREATE INDEX IF NOT EXISTS idx_components_strong ON token_components(strong_id);
        CREATE INDEX IF NOT EXISTS idx_components_role ON token_components(role);
        CREATE INDEX IF NOT EXISTS idx_token_strongs_strong ON token_strong_ids(strong_id);
        CREATE INDEX IF NOT EXISTS idx_lexicon_language ON lexicon_entries(language);
        """
    )


def import_hebrew_fixture_database(
    tahot_source_path: str | Path,
    tbesh_source_path: str | Path,
    database_path: str | Path,
    *,
    dataset_name: str = "TAHOT prototype",
    source_version: str = "STEPBible-Data master snapshot",
) -> HebrewImportReport:
    return import_tahot_database(
        [tahot_source_path],
        database_path,
        tbesh_source_path=tbesh_source_path,
        dataset_name=dataset_name,
        source_version=source_version,
        require_all_books=False,
        atomic=False,
    )


def import_tahot_database(
    tahot_source_paths: list[str | Path],
    database_path: str | Path,
    *,
    tbesh_source_path: str | Path | None = None,
    dataset_name: str = "TAHOT OT",
    source_version: str = "STEPBible-Data master snapshot",
    require_all_books: bool = True,
    atomic: bool = True,
    audit_output_path: str | Path | None = None,
) -> HebrewImportReport:
    sources = [Path(path).resolve() for path in tahot_source_paths]
    database = Path(database_path).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    target = _temporary_database_path(database) if atomic else database
    if target.exists():
        target.unlink()

    rows_read = 0
    tokens_imported = 0
    warnings: list[dict[str, str]] = []
    stable_keys: set[str] = set()

    connection = sqlite3.connect(target)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        create_schema(connection)
        for source in sources:
            for raw_line in source.read_text(encoding="utf-8-sig").splitlines():
                if not raw_line.strip() or "\t" not in raw_line:
                    continue
                try:
                    token = parse_tahot_row(raw_line, token_index=tokens_imported + 1)
                except ValueError as exc:
                    if raw_line and raw_line[0].isalnum():
                        warnings.append({"line": raw_line[:160], "warning": str(exc)})
                    continue
                rows_read += 1
                if token.stable_key in stable_keys:
                    warnings.append(
                        {
                            "line": raw_line[:160],
                            "warning": f"Skipped duplicate stable Hebrew token key: {token.stable_key}",
                        }
                    )
                    continue
                stable_keys.add(token.stable_key)
                _insert_token(connection, token)
                tokens_imported += 1

        lexicon_entries_imported = 0
        if tbesh_source_path is not None:
            lexicon_entries_imported = import_tbesh_lexicon(
                tbesh_source_path,
                connection=connection,
                needed_strongs=_all_token_strongs(connection),
            )

        _populate_books(connection)
        audit = _audit_connection(connection, sources, warnings)
        _validate_audit(audit, require_all_books=require_all_books)
        metadata = _metadata(
            dataset_name=dataset_name,
            source_version=source_version,
            sources=sources,
            audit=audit,
            lexicon_entries_imported=lexicon_entries_imported,
        )
        connection.executemany(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
            metadata.items(),
        )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"Invalid Hebrew SQLite integrity_check: {integrity}")
        connection.commit()
    finally:
        connection.close()

    if atomic:
        _replace_atomically(target, database)

    if audit_output_path is not None:
        Path(audit_output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(audit_output_path).write_text(
            json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    books = tuple(_read_scalar_list(database, "SELECT book FROM books ORDER BY ordinal"))
    return HebrewImportReport(
        database_path=str(database),
        rows_read=rows_read,
        tokens_imported=tokens_imported,
        lexicon_entries_imported=lexicon_entries_imported,
        books=books,
    )


def create_tbesh_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS lexicon_entries (
            strong_id TEXT PRIMARY KEY,
            estrong TEXT,
            dstrong TEXT,
            ustrong TEXT,
            hebrew TEXT,
            transliteration TEXT,
            morph TEXT,
            gloss TEXT,
            meaning TEXT,
            language TEXT,
            source_name TEXT NOT NULL,
            raw_fields_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tbesh_lexicon_estrong ON lexicon_entries(estrong);
        CREATE INDEX IF NOT EXISTS idx_tbesh_lexicon_dstrong ON lexicon_entries(dstrong);
        CREATE INDEX IF NOT EXISTS idx_tbesh_lexicon_ustrong ON lexicon_entries(ustrong);
        CREATE INDEX IF NOT EXISTS idx_tbesh_lexicon_language ON lexicon_entries(language);
        """
    )


def import_tbesh_lexicon_database(
    source_path: str | Path,
    database_path: str | Path,
    *,
    atomic: bool = True,
) -> int:
    source = Path(source_path).resolve()
    database = Path(database_path).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    target = _temporary_database_path(database) if atomic else database
    if target.exists():
        target.unlink()
    connection = sqlite3.connect(target)
    try:
        create_tbesh_schema(connection)
        count = import_tbesh_lexicon(source, connection=connection)
        metadata = {
            "dataset_name": "TBESH Hebrew lexicon",
            "source_file": str(source),
            "source_checksum_sha256": _sha256(source),
            "license": "CC BY 4.0",
            "attribution": "STEP Bible; www.STEPBible.org",
            "built_at": datetime.now(UTC).isoformat(),
            "lexicon_entry_count": str(count),
        }
        connection.executemany(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)", metadata.items()
        )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"Invalid TBESH SQLite integrity_check: {integrity}")
        connection.commit()
    finally:
        connection.close()
    if atomic:
        _replace_atomically(target, database)
    return count


def import_tbesh_lexicon(
    source_path: str | Path,
    *,
    connection: sqlite3.Connection,
    needed_strongs: set[str] | None = None,
) -> int:
    """Import TBESH, keying every entry by its OWN identity first.

    Phase 2A — two passes, because ``uStrong`` is a cross-reference, not an
    identity (see ``HebrewLexiconEntry.identity_strong_ids``):

    1. Every record is written under its eStrong/dStrong ids. These are real
       claims, so a later record may still legitimately replace an earlier one.
    2. uStrong-only ids are then filled in as a last-resort fallback with
       ``INSERT OR IGNORE`` semantics, so a derived record ("in Aramaic of",
       "a Name of", "combination of", ...) can never overwrite the genuine
       entry of the lexeme it merely points at.

    Before this change a single ``for strong_id in entry.strong_ids`` loop with
    ``INSERT OR REPLACE`` let derived records clobber base lexemes, which is how
    אֲשֶׁר (H0834A) came to display כַּאֲשֶׁר's gloss.
    """
    entries: list[HebrewLexiconEntry] = []
    for raw_line in Path(source_path).read_text(encoding="utf-8-sig").splitlines():
        if not raw_line.strip() or raw_line.startswith(("=", "$")) or raw_line.startswith("eStrong#"):
            continue
        try:
            entry = parse_tbesh_row(raw_line)
        except ValueError:
            continue
        if needed_strongs is not None and not needed_strongs.intersection(entry.strong_ids):
            continue
        entries.append(entry)

    count = 0
    claimed: set[str] = set()
    for entry in entries:
        for strong_id in entry.identity_strong_ids:
            if needed_strongs is not None and strong_id not in needed_strongs:
                continue
            _insert_lexicon_entry(connection, strong_id, entry)
            claimed.add(strong_id)
            count += 1

    for entry in entries:
        for strong_id in entry.reference_strong_ids:
            if strong_id in claimed:
                continue
            if needed_strongs is not None and strong_id not in needed_strongs:
                continue
            _insert_lexicon_entry(connection, strong_id, entry)
            claimed.add(strong_id)
            count += 1
    return count


def inspect_hebrew_database_path(database_path: str | Path | None = None) -> HebrewDatabaseDiagnostics:
    path = resolve_tahot_database_path(database_path)
    exists = path.exists()
    is_file = path.is_file()
    size = path.stat().st_size if is_file else 0
    if not is_file:
        return HebrewDatabaseDiagnostics(str(path), exists, is_file, size, "", False)
    try:
        with sqlite3.connect(path) as connection:
            # `quick_check` (nem a teljes `integrity_check`) — a futásidejű
            # DB-t build-időben már ellenőriztük, ez itt csak egy gyors
            # egészség-jelzés minden `HebrewTokenRepository()` példánynál
            # (Streamlit rerunonként újra lefut). A teljes integrity_check
            # ~2 mp a jelenlegi fájlméretnél (quick_check ~0.3 mp) — ez a
            # UI-válaszidőben közvetlenül érezhető, míg a védelmi értéke a
            # quick_check-hez képest itt marginális.
            integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
            tables = set(_read_scalar_list_from_connection(connection, "SELECT name FROM sqlite_master WHERE type='table'"))
        required = {"metadata", "books", "tokens", "token_strong_ids"}
        return HebrewDatabaseDiagnostics(str(path), exists, is_file, size, integrity, required <= tables)
    except sqlite3.Error as exc:
        return HebrewDatabaseDiagnostics(str(path), exists, is_file, size, "", False, str(exc))


def get_hebrew_passage_tokens(
    database_path: str | Path,
    book: str,
    chapter: int,
    verse_start: int,
    verse_end: int | None = None,
) -> list[HebrewToken]:
    end = verse_end or verse_start
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT *
            FROM tokens
            WHERE book = ? AND chapter = ? AND verse BETWEEN ? AND ?
            ORDER BY chapter, verse, word_index
            """,
            (book, chapter, verse_start, end),
        ).fetchall()
        if not rows and _table_exists(connection, "hebrew_tokens"):
            rows = connection.execute(
                """
                SELECT *
                FROM hebrew_tokens
                WHERE book = ? AND chapter = ? AND verse BETWEEN ? AND ?
                ORDER BY chapter, verse, word_index
                """,
                (book, chapter, verse_start, end),
            ).fetchall()
        return _tokens_from_database_rows(connection, rows)


def get_hebrew_token(database_path: str | Path, stable_token_key: str) -> HebrewToken | None:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM tokens WHERE stable_token_key = ?",
            (stable_token_key,),
        ).fetchone()
        tokens = _tokens_from_database_rows(connection, [row] if row else [])
    return tokens[0] if tokens else None


def find_hebrew_tokens_by_lemma(database_path: str | Path, lemma: str) -> list[HebrewToken]:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.create_function("HSTRIP_CANTILLATION", 1, _strip_hebrew_cantillation)
        rows = connection.execute(
            "SELECT * FROM tokens "
            "WHERE HSTRIP_CANTILLATION(lemma) = HSTRIP_CANTILLATION(?) "
            "ORDER BY book, chapter, verse, word_index",
            (lemma,),
        ).fetchall()
        return _tokens_from_database_rows(connection, rows)


def find_hebrew_tokens_by_strong_id(database_path: str | Path, strong_id: str) -> list[HebrewToken]:
    """A `strong_id` PONTOS egyezését keresi, DE emellett a STEPBible-
    adatban gyakori homográf-jelölő betűsuffixummal (pl. "H2617A",
    "H2617B") ellátott változatokat is — sok Strong-szám kizárólag
    lettered variánsként létezik a TAHOT-ban, egy sima "H2617" keresés
    tehát pontos egyezés hiányában is találjon rájuk. Ha a bemenet már
    tartalmaz betűt, a plusz `LIKE` feltétel ártalmatlan (nem talál
    semmit extra), a viselkedés lényegében változatlan marad."""
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        join_column = _token_strong_join_column(connection)
        rows = connection.execute(
            f"""
            SELECT t.*
            FROM tokens t
            JOIN token_strong_ids s ON s.{join_column} = t.{join_column}
            WHERE s.strong_id = ? OR s.strong_id LIKE ?
            ORDER BY t.book, t.chapter, t.verse, t.word_index
            """,
            (strong_id, strong_id + "_"),
        ).fetchall()
        return _tokens_from_database_rows(connection, rows)


def _tokens_from_database_rows(connection: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[HebrewToken]:
    if not rows:
        return []
    if "raw_fields_json" in rows[0].keys():
        return [
            parse_tahot_row("\t".join(json.loads(row["raw_fields_json"])), token_index=row["token_index"])
            for row in rows
        ]
    join_column = _token_strong_join_column(connection)
    strong_rows = _load_token_strong_rows(connection, rows, join_column)
    return [_token_from_normalized_row(row, strong_rows.get(row[join_column], ())) for row in rows]


def _token_strong_order_column(connection: sqlite3.Connection) -> str:
    """A lecsupaszított (pruned) runtime DB-ben `token_strong_ids` egy
    WITHOUT ROWID tábla, ahol nincs implicit `rowid` — az eredeti
    (prefix/core/suffix) beszúrási sorrendet ott az explicit `seq`
    oszlop őrzi meg (lásd scripts/prune_tahot_runtime_db.py). A nem
    metszett/teljes build DB-kben ilyen oszlop nincs, ott a `rowid`
    (a beszúrás sorrendjét tükröző implicit sorszám) a helyes forrás."""
    columns = {row[1] for row in connection.execute("PRAGMA table_info(token_strong_ids)")}
    return "seq" if "seq" in columns else "rowid"


def _load_token_strong_rows(
    connection: sqlite3.Connection,
    token_rows: list[sqlite3.Row],
    join_column: str,
) -> dict[object, tuple[sqlite3.Row, ...]]:
    order_column = _token_strong_order_column(connection)
    grouped: dict[object, list[sqlite3.Row]] = defaultdict(list)
    token_keys = [row[join_column] for row in token_rows]
    for chunk in _chunks(token_keys, 500):
        placeholders = ",".join("?" for _ in chunk)
        rows = connection.execute(
            f"""
            SELECT {join_column}, strong_id, role
            FROM token_strong_ids
            WHERE {join_column} IN ({placeholders})
            ORDER BY {order_column}
            """,
            chunk,
        ).fetchall()
        for row in rows:
            grouped[row[join_column]].append(row)
    return {key: tuple(value) for key, value in grouped.items()}


def _token_strong_join_column(connection: sqlite3.Connection) -> str:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(token_strong_ids)")}
    return "token_id" if "token_id" in columns else "stable_token_key"


def _chunks(items: list[object], size: int) -> list[list[object]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


_ROLE_SHORT_CODES = {"t": "token", "c": "core", "p": "prefix", "s": "suffix"}


def _decode_role(role: str) -> str:
    """A lecsupaszított runtime DB-kben a role egykarakteres kóddal tárolt
    (fájlméret-optimalizálás — lásd scripts/prune_tahot_runtime_db.py),
    a nem-metszett/teljes build DB-kben viszont a teljes szó szerepel.
    Mindkettőt visszaadja a Python-oldali `HebrewComponent.role` teljes
    szó alakjában, hogy a downstream (UI) kód (pl. hebrew_text_demo.py)
    változatlanul "prefix"/"core"/"suffix"/"token" ellen hasonlíthasson."""
    return _ROLE_SHORT_CODES.get(role, role)


def _token_from_normalized_row(row: sqlite3.Row, strong_rows: tuple[sqlite3.Row, ...]) -> HebrewToken:
    decoded_roles = [(_decode_role(item["role"]), item) for item in strong_rows]
    strong_ids = tuple(dict.fromkeys(item["strong_id"] for role, item in decoded_roles if role == "token"))
    components = tuple(
        HebrewComponent(
            surface=row["surface"] if role == "core" else "",
            strong_id=item["strong_id"],
            morphology_code=row["morphology_code"] or "",
            role=role,
        )
        for role, item in decoded_roles
        if role != "token"
    )
    core_component = next((item for item in components if item.role == "core"), None)
    return HebrewToken(
        book=row["book"],
        chapter=int(row["chapter"]),
        verse=int(row["verse"]),
        word_index=int(row["word_index"]),
        token_index=int(row["token_index"]),
        surface=row["surface"] or "",
        surface_without_accents=row["surface_without_accents"] or "",
        transliteration=row["transliteration"] or "",
        english_gloss=row["english_gloss"] or "",
        lemma=row["lemma"] or "",
        strong_ids=strong_ids,
        morphology_code=row["morphology_code"] or "",
        language=row["language"] or "",
        prefix_components=tuple(item for item in components if item.role == "prefix"),
        core_component=core_component,
        suffix_components=tuple(item for item in components if item.role == "suffix"),
        ketiv=row["ketiv"] or "",
        qere=row["qere"] or "",
        punctuation=row["punctuation"] or "",
        maqaf=bool(row["maqaf"]),
        # source_token_id / expanded_strong_tags: nagy, futásidőben sehol
        # nem megjelenített szöveges mezők — a lecsupaszított (pruned)
        # runtime DB-kben szándékosan hiányoznak a fájlméret miatt (lásd
        # scripts/prune_tahot_runtime_db.py), ezért defenzíven, a tábla
        # tényleges oszlopkészletétől függően olvassuk.
        source_token_id=(row["source_token_id"] if "source_token_id" in row.keys() else "") or "",
        source_edition=row["source_edition"] or "",
        meaning_variant=row["meaning_variant"] or "",
        spelling_variant=row["spelling_variant"] or "",
        expanded_strong_tags=(row["expanded_strong_tags"] if "expanded_strong_tags" in row.keys() else "") or "",
        raw_fields=(),
    )


def get_hebrew_books(database_path: str | Path) -> list[tuple[str, int, int, int]]:
    with sqlite3.connect(database_path) as connection:
        return [
            (row[0], int(row[1]), int(row[2]), int(row[3]))
            for row in connection.execute(
                "SELECT book, chapters_count, verses_count, tokens_count FROM books ORDER BY ordinal"
            )
        ]


def get_hebrew_lexicon_entry(database_path: str | Path, strong_id: str) -> HebrewLexiconEntry | None:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT estrong, dstrong, ustrong, hebrew, transliteration, morph, gloss, meaning, source_name
            FROM lexicon_entries
            WHERE strong_id = ?
            """,
            (strong_id,),
        ).fetchone()
        if row is None and _table_exists(connection, "hebrew_lexicon"):
            row = connection.execute(
                """
                SELECT estrong, dstrong, ustrong, hebrew, transliteration, morph, gloss, meaning, source_name
                FROM hebrew_lexicon
                WHERE strong_id = ?
                """,
                (strong_id,),
            ).fetchone()
    if row is None:
        return None
    return HebrewLexiconEntry(*[item or "" for item in row[:8]], source_name=row[8] or "STEPBible TBESH")


def _insert_token(connection: sqlite3.Connection, token: HebrewToken) -> None:
    connection.execute(
        """
        INSERT INTO tokens (
            stable_token_key, book, chapter, verse, word_index, token_index, surface,
            surface_without_accents, transliteration, english_gloss, lemma, morphology_code,
            language, ketiv, qere, punctuation, maqaf, source_token_id, source_edition,
            meaning_variant, spelling_variant, expanded_strong_tags, raw_fields_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            token.stable_key,
            token.book,
            token.chapter,
            token.verse,
            token.word_index,
            token.token_index,
            token.surface,
            token.surface_without_accents,
            token.transliteration,
            token.english_gloss,
            token.lemma,
            token.morphology_code,
            token.language,
            token.ketiv,
            token.qere,
            token.punctuation,
            1 if token.maqaf else 0,
            token.source_token_id,
            token.source_edition,
            token.meaning_variant,
            token.spelling_variant,
            token.expanded_strong_tags,
            json.dumps(token.raw_fields, ensure_ascii=False),
        ),
    )
    components = [*token.prefix_components]
    if token.core_component:
        components.append(token.core_component)
    components.extend(token.suffix_components)
    for index, component in enumerate(components, start=1):
        connection.execute(
            """
            INSERT INTO token_components(stable_token_key, component_index, role, surface, strong_id, morphology_code, gloss)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token.stable_key,
                index,
                component.role,
                component.surface,
                component.strong_id,
                component.morphology_code,
                component.gloss,
            ),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO token_strong_ids(stable_token_key, strong_id, role)
            VALUES (?, ?, ?)
            """,
            (token.stable_key, component.strong_id, component.role),
        )
    for strong_id in token.strong_ids:
        connection.execute(
            """
            INSERT OR IGNORE INTO token_strong_ids(stable_token_key, strong_id, role)
            VALUES (?, ?, 'token')
            """,
            (token.stable_key, strong_id),
        )
    if token.ketiv or token.qere or "Q" in token.source_edition.upper():
        connection.execute(
            """
            INSERT OR REPLACE INTO ketiv_qere(stable_token_key, ketiv, qere, meaning_variant, spelling_variant)
            VALUES (?, ?, ?, ?, ?)
            """,
            (token.stable_key, token.ketiv, token.qere, token.meaning_variant, token.spelling_variant),
        )


def _insert_lexicon_entry(connection: sqlite3.Connection, strong_id: str, entry: HebrewLexiconEntry) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO lexicon_entries (
            strong_id, estrong, dstrong, ustrong, hebrew, transliteration, morph, gloss,
            meaning, language, source_name, raw_fields_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            strong_id,
            entry.estrong,
            entry.dstrong,
            entry.ustrong,
            entry.hebrew,
            entry.transliteration,
            entry.morph,
            entry.gloss,
            entry.meaning,
            _language_from_morph(entry.morph),
            entry.source_name,
            json.dumps(asdict(entry), ensure_ascii=False),
        ),
    )


def _populate_books(connection: sqlite3.Connection) -> None:
    for ordinal, book in enumerate(OT_BOOK_ORDER, start=1):
        row = connection.execute(
            """
            SELECT COUNT(DISTINCT chapter), COUNT(DISTINCT chapter || ':' || verse), COUNT(*)
            FROM tokens
            WHERE book = ?
            """,
            (book,),
        ).fetchone()
        if row and row[2]:
            connection.execute(
                "INSERT OR REPLACE INTO books(book, ordinal, chapters_count, verses_count, tokens_count) VALUES (?, ?, ?, ?, ?)",
                (book, ordinal, int(row[0]), int(row[1]), int(row[2])),
            )


def _audit_connection(
    connection: sqlite3.Connection,
    sources: list[Path],
    warnings: list[dict[str, str]],
) -> dict[str, object]:
    per_book: dict[str, dict[str, int]] = {}
    for row in connection.execute(
        """
        SELECT book, COUNT(DISTINCT chapter), COUNT(DISTINCT chapter || ':' || verse), COUNT(*)
        FROM tokens
        GROUP BY book
        """
    ):
        per_book[row[0]] = {"chapters": int(row[1]), "verses": int(row[2]), "tokens": int(row[3])}
    language_counts = Counter(
        {row[0]: int(row[1]) for row in connection.execute("SELECT language, COUNT(*) FROM tokens GROUP BY language")}
    )
    role_counts = Counter(
        {row[0]: int(row[1]) for row in connection.execute("SELECT role, COUNT(*) FROM token_components GROUP BY role")}
    )
    missing = {
        "lemma": int(connection.execute("SELECT COUNT(*) FROM tokens WHERE COALESCE(lemma, '') = ''").fetchone()[0]),
        "morphology": int(connection.execute("SELECT COUNT(*) FROM tokens WHERE COALESCE(morphology_code, '') = ''").fetchone()[0]),
        "strong": int(
            connection.execute(
                "SELECT COUNT(*) FROM tokens t WHERE NOT EXISTS (SELECT 1 FROM token_strong_ids s WHERE s.stable_token_key = t.stable_token_key)"
            ).fetchone()[0]
        ),
    }
    multiple_strong = int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT stable_token_key, COUNT(DISTINCT strong_id) AS strong_count
                FROM token_strong_ids
                GROUP BY stable_token_key
                HAVING strong_count > 1
            )
            """
        ).fetchone()[0]
    )
    return {
        "source_files": [str(path) for path in sources],
        "source_checksums": {path.name: _sha256(path) for path in sources},
        "books": per_book,
        "books_count": len(per_book),
        "chapters_count": sum(item["chapters"] for item in per_book.values()),
        "verses_count": int(
            connection.execute("SELECT COUNT(DISTINCT book || ':' || chapter || ':' || verse) FROM tokens").fetchone()[0]
        ),
        "surface_words_count": int(connection.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]),
        "component_tokens_count": int(connection.execute("SELECT COUNT(*) FROM token_components").fetchone()[0]),
        "language_counts": dict(language_counts),
        "hebrew_token_count": language_counts.get("hebrew", 0),
        "aramaic_token_count": language_counts.get("aramaic", 0),
        "ketiv_qere_count": int(connection.execute("SELECT COUNT(*) FROM ketiv_qere").fetchone()[0]),
        "component_role_counts": dict(role_counts),
        "multiple_strong_tokens": multiple_strong,
        "missing": missing,
        "unknown_book_codes": sorted(set(per_book) - set(OT_BOOK_ORDER)),
        "parser_warnings": warnings[:1000],
        "parser_warning_count": len(warnings),
    }


def _validate_audit(audit: dict[str, object], *, require_all_books: bool) -> None:
    books = set((audit["books"] or {}).keys())  # type: ignore[index, union-attr]
    missing_books = [book for book in OT_BOOK_ORDER if book not in books]
    if require_all_books and missing_books:
        raise ValueError(f"Incomplete TAHOT import; missing books: {', '.join(missing_books)}")
    if audit["unknown_book_codes"]:  # type: ignore[index]
        raise ValueError(f"Unknown TAHOT book codes: {audit['unknown_book_codes']}")
    if audit["surface_words_count"] == 0:  # type: ignore[index]
        raise ValueError("Incomplete TAHOT import; no tokens imported.")


def _metadata(
    *,
    dataset_name: str,
    source_version: str,
    sources: list[Path],
    audit: dict[str, object],
    lexicon_entries_imported: int,
) -> dict[str, str]:
    return {
        "dataset_name": dataset_name,
        "source_version": source_version,
        "source_files": json.dumps([str(path) for path in sources], ensure_ascii=False),
        "source_checksums": json.dumps(audit["source_checksums"], ensure_ascii=False),
        "license": "CC BY 4.0",
        "attribution": "STEP Bible; www.STEPBible.org",
        "built_at": datetime.now(UTC).isoformat(),
        "books_count": str(audit["books_count"]),
        "chapters_count": str(audit["chapters_count"]),
        "verses_count": str(audit["verses_count"]),
        "surface_words_count": str(audit["surface_words_count"]),
        "component_tokens_count": str(audit["component_tokens_count"]),
        "hebrew_token_count": str(audit["hebrew_token_count"]),
        "aramaic_token_count": str(audit["aramaic_token_count"]),
        "ketiv_qere_count": str(audit["ketiv_qere_count"]),
        "lexicon_entry_count": str(lexicon_entries_imported),
    }


def _all_token_strongs(connection: sqlite3.Connection) -> set[str]:
    return set(_read_scalar_list_from_connection(connection, "SELECT DISTINCT strong_id FROM token_strong_ids"))


def _language_from_morph(morph: str) -> str:
    if morph.startswith("A"):
        return "aramaic"
    if morph.startswith("H"):
        return "hebrew"
    return ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _temporary_database_path(database: Path) -> Path:
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{database.stem}.",
        suffix=".tmp.sqlite3",
        dir=database.parent,
        delete=False,
    )
    handle.close()
    return Path(handle.name)


def _replace_atomically(source: Path, target: Path) -> None:
    for attempt in range(5):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.2 * (attempt + 1))


def _read_scalar_list(database: Path, sql: str) -> list[str]:
    with sqlite3.connect(database) as connection:
        return _read_scalar_list_from_connection(connection, sql)


def _read_scalar_list_from_connection(connection: sqlite3.Connection, sql: str) -> list[str]:
    return [str(row[0]) for row in connection.execute(sql)]


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (table,),
        ).fetchone()
        is not None
    )
