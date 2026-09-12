"""Helyi, teljes Biblia szintű RÚF 2014 szövegtár — SQLite + FTS5.

JOGI MEGJEGYZÉS — FELHASZNÁLÁSI ALAP ÉS KORLÁTOK
--------------------------------------------------
A RÚF 2014 fordítás teljes szövegének ebben a modulban történő helyi
tárolása (nem csak igeszakaszonkénti, átmeneti megjelenítése) a TEXTUS
üzemeltetője és a Magyar Bibliatársulat között fennálló, érvényes
szerződés/engedély alapján történik, amely kifejezetten lefedi a bulk
(teljes szövegű) helyi tárolást is. A szerződés az alábbi négy feltételt
szabja — ezek a KÓDBAN is betartandó, nem csak dokumentációs elvárások:

1. SZÓ SZERINTI TÁROLÁS. A `verses.text` mező a Szentírás.eu API által
   visszaadott szöveget kizárólag whitespace-normalizálással tárolja
   (lásd `upsert_chapter_verses` — csak `.strip()`, más átalakítás
   TILOS). Ne adj hozzá rövidítést, bővítést, parafrazálást vagy
   bármilyen tartalmi módosítást ehhez a réteghez.
2. KIZÁRÓLAG BELSŐ HASZNÁLAT. Ez a DB SOSE váljon külső, exportálható
   vagy nyilvánosan lekérdezhető adatforrássá. Ehhez a modulhoz TILOS
   olyan hálózati/HTTP végpontot, fájl-export funkciót vagy publikus
   API-t hozzáadni, amin keresztül BÁRMILYEN KÜLSŐ FÉL kiolvashatná a
   szöveget — csak az alkalmazás saját Python-folyamatán belüli,
   programozott hívás (`lookup_local`, `search_literal`) férhet hozzá.
   Ez NEM zárja ki a `ensure_local_database()` BEFELÉ irányuló
   betöltését egy PRIVÁT, csak a szerverfolyamat saját hitelesítő
   adataival elérhető tárolóból (Supabase Storage privát bucket) —
   ez a DB egyetlen tartós, kanonikus forrásának provizionálása, nem
   egy kifelé mutató export-végpont. A DB fájl NEM kerülhet
   verziókezelésbe (lásd `.gitignore` — a `*.sqlite3` blokkoló szabály
   alól a `data/generated/ruf_bible.sqlite3`-hoz SOSE adj
   negation-kivételt, szemben a `tahot`/`tbesh` DB-kkel, amik más,
   permisszívebb forrásból származnak). A Supabase bucket, ahonnan a
   betöltés történik, SOSE lehet publikus (lásd
   `scripts/setup_ruf_bible_storage.py` — explicit `public: False`).
3. LÁTHATÓ COPYRIGHT. A `COPYRIGHT_NOTICE`/`SOURCE_ATTRIBUTION`
   (`ruf_bible_service.py`) minden, ebből a DB-ből származó szövegnek meg
   KELL jelennie bármely felhasználói felületen, amely ezt a réteget
   fogyasztja. **2026-09 audit megjegyzés:** ez a modul (`lookup_local`,
   `search_literal`) önmagában nyers verssorokat ad vissza, semmilyen
   copyright-becsomagolást nem végez, és a jelenlegi fogyasztók
   (`concordance_ui.py`, `original_language_concordance.py`,
   `concept_concordance.py`) sem jelenítenek meg ilyen jelzést — ez tehát
   ma egy KÖVETELMÉNY, nem egy már teljesült garancia. Bármely új
   fogyasztónak (vagy egy jövőbeli javításnak a meglévőknél) a copyright
   szöveget explicit meg kell jelenítenie.
4. TELJES, EGYLÉPÉSES TÖRÖLHETŐSÉG. A teljes szöveg egyetlen fájlban
   (`DEFAULT_DATABASE_PATH`) él, semmilyen más helyen nincs tartósan
   duplikálva. Szerződés megszűnése esetén: `purge_database()` (vagy
   `python scripts/purge_ruf_bible_db.py --yes`) azonnal és teljesen
   eltávolítja.

SZEREP A RENDSZERBEN (2026-09 audit fix — a korábbi állítás pontatlan volt)
---------------------------------------------------------------------------
Ez a modul egy ÖNÁLLÓ, KÜLÖNÁLLÓ adatforrás — NEM a fő RÚF-olvasási
útvonal elé kapcsolt, elsődleges gyorstár. A `ruf_bible_service.
fetch_ruf_passage` (a fő "Igehely" nézet és minden más, szakaszonkénti
igehely-betöltő funkció mögötti hívás) SOHA nem éri el ezt a DB-t —
kizárólag az élő Szentírás.eu API-t és a saját, folyamat-szintű memória-
cache-ét használja (lásd `ruf_bible_service.py` modul-docstringje és
`tests/test_ruf_bible_local_db.py::test_fetch_ruf_passage_never_consults_
local_db`, amely ezt explicit regressziós teszttel rögzíti).

Ezt a helyi, teljes szövegű snapshotot ma kizárólag a Konkordancia-réteg
fogyasztja: `concordance_ui.py` (`search_literal`), `original_language_
concordance.py` és `concept_concordance.py` (mindkettő `lookup_local`).
A snapshot build-je (`scripts/build_ruf_bible_db.py`) kizárólag manuális
futtatással történik, minden már `'ok'` státuszú fejezetet kihagyva —
nincs automatikus/időzített frissítés, és nincs semmilyen kód, ami a
snapshot frissességét összevetné az élő forrással. Ebből következik: ha
az élő forrás egy verset a snapshot építése után javít, a fő olvasónézet
(élő API) és a Konkordancia (helyi snapshot) EGY IDŐBEN eltérő szöveget
mutathat ugyanarra a versre — ezt a UI ma sehol nem jelzi.

A `lookup_local` / `search_literal` visszatérési értéke tehát nem
"gyorsítótárazott" változata a fő olvasónézet szövegének, hanem egy
elvileg AZONOS, de gyakorlatilag függetlenül frissülő, autoritásban
alárendelt másolat.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bible_engine.paths import GENERATED_DATA_DIR


DATABASE_NAME = "ruf_bible.sqlite3"
DEFAULT_DATABASE_PATH = GENERATED_DATA_DIR / DATABASE_NAME

SCHEMA_VERSION = 1

# Privát Supabase Storage bucket — kizárólag a szerverfolyamat saját
# hitelesítő adataival (SUPABASE_URL/SUPABASE_KEY) elérhető, SOSE publikus.
# Lásd scripts/setup_ruf_bible_storage.py (egyszeri feltöltés/bucket-létrehozás).
STORAGE_BUCKET_ID = "ruf-bible-private"
STORAGE_OBJECT_PATH = "ruf_bible.sqlite3"


def resolve_database_path(database_path: str | Path | None = None) -> Path:
    return Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH


def get_connection(database_path: str | Path | None = None) -> sqlite3.Connection:
    path = resolve_database_path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS verses (
            id INTEGER PRIMARY KEY,
            book_code TEXT NOT NULL,
            book_abbr TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            chapter INTEGER NOT NULL,
            verse INTEGER NOT NULL,
            text TEXT NOT NULL,
            reference TEXT,
            fetched_at REAL NOT NULL,
            UNIQUE(book_code, chapter, verse)
        );

        CREATE INDEX IF NOT EXISTS idx_verses_book_chapter
            ON verses(book_code, chapter, verse);

        CREATE VIRTUAL TABLE IF NOT EXISTS verses_fts USING fts5(
            text,
            content='verses',
            content_rowid='id',
            tokenize='unicode61'
        );

        CREATE TRIGGER IF NOT EXISTS verses_ai AFTER INSERT ON verses BEGIN
            INSERT INTO verses_fts(rowid, text) VALUES (new.id, new.text);
        END;

        CREATE TRIGGER IF NOT EXISTS verses_ad AFTER DELETE ON verses BEGIN
            INSERT INTO verses_fts(verses_fts, rowid, text) VALUES ('delete', old.id, old.text);
        END;

        CREATE TRIGGER IF NOT EXISTS verses_au AFTER UPDATE ON verses BEGIN
            INSERT INTO verses_fts(verses_fts, rowid, text) VALUES ('delete', old.id, old.text);
            INSERT INTO verses_fts(rowid, text) VALUES (new.id, new.text);
        END;

        CREATE TABLE IF NOT EXISTS fetch_log (
            book_code TEXT NOT NULL,
            chapter INTEGER NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            fetched_at REAL NOT NULL,
            PRIMARY KEY (book_code, chapter)
        );

        CREATE TABLE IF NOT EXISTS import_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    connection.commit()


def set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        "INSERT INTO import_meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_meta(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute(
        "SELECT value FROM import_meta WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None


def chapter_already_ok(
    connection: sqlite3.Connection, book_code: str, chapter: int
) -> bool:
    return get_chapter_status(connection, book_code, chapter) == "ok"


def get_chapter_status(
    connection: sqlite3.Connection, book_code: str, chapter: int
) -> str | None:
    """'ok' | 'error' | None (még sosem próbálta lekérni)."""
    row = connection.execute(
        "SELECT status FROM fetch_log WHERE book_code = ? AND chapter = ?",
        (book_code, chapter),
    ).fetchone()
    return row["status"] if row else None


def record_fetch_error(
    connection: sqlite3.Connection,
    book_code: str,
    chapter: int,
    error_message: str,
) -> None:
    connection.execute(
        "INSERT INTO fetch_log(book_code, chapter, status, error_message, fetched_at) "
        "VALUES (?, ?, 'error', ?, ?) "
        "ON CONFLICT(book_code, chapter) DO UPDATE SET "
        "status = excluded.status, error_message = excluded.error_message, "
        "fetched_at = excluded.fetched_at",
        (book_code, chapter, error_message, time.time()),
    )


def upsert_chapter_verses(
    connection: sqlite3.Connection,
    *,
    book_code: str,
    book_abbr: str,
    ordinal: int,
    chapter: int,
    verses: list[dict[str, Any]],
) -> int:
    """Egy fejezet összes versét beírja (INSERT OR REPLACE), majd 'ok' log-bejegyzést ír.

    Visszaadja a beírt verssorok számát.
    """
    now = time.time()
    count = 0
    for verse in verses:
        number = verse.get("verse_number") or verse.get("number")
        text = (verse.get("text") or "").strip()
        if number is None or not text:
            continue
        reference = verse.get("reference") or ""
        connection.execute(
            "INSERT INTO verses(book_code, book_abbr, ordinal, chapter, verse, text, reference, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(book_code, chapter, verse) DO UPDATE SET "
            "text = excluded.text, reference = excluded.reference, fetched_at = excluded.fetched_at",
            (book_code, book_abbr, ordinal, chapter, int(number), text, reference, now),
        )
        count += 1
    connection.execute(
        "INSERT INTO fetch_log(book_code, chapter, status, error_message, fetched_at) "
        "VALUES (?, ?, 'ok', NULL, ?) "
        "ON CONFLICT(book_code, chapter) DO UPDATE SET "
        "status = 'ok', error_message = NULL, fetched_at = excluded.fetched_at",
        (book_code, chapter, now),
    )
    return count


def lookup_local(
    book_code: str,
    chapter: int,
    verse_start: int | None,
    verse_end: int | None,
    *,
    database_path: str | Path | None = None,
) -> list[dict[str, Any]] | None:
    """A helyi DB-ből próbálja visszaadni a kért verseket.

    Visszaad egy listát a talált versekről (API-válasszal kompatibilis
    dict-alakban), vagy `None`-t, ha a DB nem elérhető / a kért igehely
    nincs (teljesen) benne — ez utóbbi esetben a hívó fél az élő
    API-útvonalra esik vissza.
    """
    path = resolve_database_path(database_path)
    if not path.is_file():
        return None
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return None
    try:
        if verse_start is None:
            rows = conn.execute(
                "SELECT verse, text, reference FROM verses "
                "WHERE book_code = ? AND chapter = ? ORDER BY verse",
                (book_code, chapter),
            ).fetchall()
        else:
            end = verse_end if verse_end is not None else verse_start
            rows = conn.execute(
                "SELECT verse, text, reference FROM verses "
                "WHERE book_code = ? AND chapter = ? AND verse BETWEEN ? AND ? "
                "ORDER BY verse",
                (book_code, chapter, verse_start, end),
            ).fetchall()
            expected = set(range(verse_start, end + 1))
            found = {int(r["verse"]) for r in rows}
            if expected - found:
                return None
        if not rows:
            return None
        return [
            {
                "verse_number": int(r["verse"]),
                "number": int(r["verse"]),
                "text": r["text"],
                "reference": r["reference"] or "",
            }
            for r in rows
        ]
    finally:
        conn.close()


@dataclass(frozen=True)
class LiteralSearchHit:
    book_code: str
    book_abbr: str
    ordinal: int
    chapter: int
    verse: int
    text: str
    snippet: str = ""


def _fts_phrase_query(query: str) -> str:
    """A felhasználói bevitelt mindig szó szerinti FTS5 kifejezéssé alakítja.

    A UI-n szabad szöveget kap (nem FTS5-szintaxist) — idézőjelbe zárva
    elkerüljük, hogy pl. egy kötőjel vagy kettőspont FTS5-operátorként
    okozzon szintaxishibát, és a keresés mindig pontos kifejezés-egyezés
    marad (nem AND/OR/NEAR kombinátor).
    """
    escaped = query.replace('"', '""')
    return f'"{escaped}"'


def _open_readonly(path: Path) -> sqlite3.Connection | None:
    if not path.is_file():
        return None
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def _testament_filter_sql(
    book_code: str | None, book_codes: list[str] | None
) -> tuple[str, list[Any]]:
    if book_code:
        return " AND v.book_code = ?", [book_code]
    if book_codes:
        placeholders = ",".join("?" for _ in book_codes)
        return f" AND v.book_code IN ({placeholders})", list(book_codes)
    return "", []


def search_literal(
    query: str,
    *,
    limit: int = 50,
    offset: int = 0,
    book_code: str | None = None,
    book_codes: list[str] | None = None,
    database_path: str | Path | None = None,
) -> list[LiteralSearchHit]:
    """Szó szerinti keresés a helyi RÚF szövegben — mindig kifejezés-egyezés.

    A `query` bármilyen szabad szöveg lehet (nem kell FTS5-szintaxist
    ismerni) — belül automatikusan idézőjelezett, pontos kifejezésként
    kerül lekérdezésre. `book_code` egyetlen könyvre szűr, `book_codes`
    egy könyvlistára (pl. testamentum szerint) — a kettő közül csak az
    egyik adható meg egyszerre; `book_code` élvez elsőbbséget. Üres DB
    vagy hiányzó fájl esetén üres listát ad, hibás/üres lekérdezésnél is.
    """
    q = (query or "").strip()
    if not q:
        return []
    path = resolve_database_path(database_path)
    conn = _open_readonly(path)
    if conn is None:
        return []
    try:
        filter_sql, filter_params = _testament_filter_sql(book_code, book_codes)
        sql = (
            "SELECT v.book_code, v.book_abbr, v.ordinal, v.chapter, v.verse, v.text, "
            "snippet(verses_fts, 0, '**', '**', '…', 64) AS snip "
            "FROM verses_fts f JOIN verses v ON v.id = f.rowid "
            "WHERE f.text MATCH ?" + filter_sql +
            " ORDER BY v.ordinal, v.chapter, v.verse LIMIT ? OFFSET ?"
        )
        params: list[Any] = [_fts_phrase_query(q), *filter_params, limit, offset]
        rows = conn.execute(sql, params).fetchall()
        return [
            LiteralSearchHit(
                book_code=r["book_code"],
                book_abbr=r["book_abbr"],
                ordinal=r["ordinal"],
                chapter=r["chapter"],
                verse=r["verse"],
                text=r["text"],
                snippet=r["snip"] or r["text"],
            )
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def count_literal(
    query: str,
    *,
    book_code: str | None = None,
    book_codes: list[str] | None = None,
    database_path: str | Path | None = None,
) -> int:
    """A `search_literal`-lal megegyező szűrés melletti összes találatszám."""
    q = (query or "").strip()
    if not q:
        return 0
    path = resolve_database_path(database_path)
    conn = _open_readonly(path)
    if conn is None:
        return 0
    try:
        filter_sql, filter_params = _testament_filter_sql(book_code, book_codes)
        sql = (
            "SELECT COUNT(*) AS n FROM verses_fts f JOIN verses v ON v.id = f.rowid "
            "WHERE f.text MATCH ?" + filter_sql
        )
        params: list[Any] = [_fts_phrase_query(q), *filter_params]
        row = conn.execute(sql, params).fetchone()
        return int(row["n"]) if row else 0
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def database_exists(database_path: str | Path | None = None) -> bool:
    return resolve_database_path(database_path).is_file()


def ensure_local_database(database_path: str | Path | None = None) -> bool:
    """Ha a helyi DB hiányzik (pl. friss/újraindult konténer), letölti a
    privát Supabase Storage bucketből — API-hívások és a 15-30 perces
    bulk-import nélkül, másodpercek alatt.

    Idempotens: ha a fájl már megvan, azonnal True-val tér vissza, nem
    tölt le semmit újra. Hálózati/hitelesítési hiba esetén False-t ad
    (nem dob kivételt) — a hívó fél ilyenkor a "még nem elérhető"
    állapotra esik vissza, ahogy eddig is, ha egyáltalán nincs DB.
    """
    path = resolve_database_path(database_path)
    if path.is_file():
        return True
    try:
        from supabase_client import get_supabase_client

        client = get_supabase_client()
        data = client.storage.from_(STORAGE_BUCKET_ID).download(STORAGE_OBJECT_PATH)
    except Exception:  # noqa: BLE001 — hálózat/hitelesítés hibája sose akassza meg az appot
        return False
    if not data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".part")
    try:
        tmp_path.write_bytes(data)
        tmp_path.replace(path)
    except OSError:
        return False
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return path.is_file()


def purge_database(database_path: str | Path | None = None) -> list[str]:
    """Teljesen és véglegesen törli a helyi RÚF-szövegtárat.

    A szerződéses feltétel (4. pont, lásd modul-docstring) miatt: ha a
    Magyar Bibliatársulattal fennálló engedély megszűnik, ennek az egy
    függvénynek a meghívása (vagy a `scripts/purge_ruf_bible_db.py`
    parancssori wrapper) azonnal eltávolítja a teljes szöveget — a fő
    DB-fájlt és minden SQLite melléktermék-fájlt (`-journal`, `-wal`,
    `-shm`), amit egy megszakadt tranzakció esetleg hátrahagyott.

    Visszaadja a ténylegesen törölt fájlok elérési útjait (üres lista,
    ha nem volt mit törölni — pl. ha a DB sosem lett létrehozva).
    """
    path = resolve_database_path(database_path)
    removed: list[str] = []
    for candidate in (
        path,
        path.with_name(path.name + "-journal"),
        path.with_name(path.name + "-wal"),
        path.with_name(path.name + "-shm"),
    ):
        if candidate.is_file():
            candidate.unlink()
            removed.append(str(candidate))
    return removed


__all__ = [
    "DATABASE_NAME",
    "DEFAULT_DATABASE_PATH",
    "SCHEMA_VERSION",
    "resolve_database_path",
    "get_connection",
    "ensure_schema",
    "set_meta",
    "get_meta",
    "chapter_already_ok",
    "get_chapter_status",
    "record_fetch_error",
    "upsert_chapter_verses",
    "lookup_local",
    "search_literal",
    "count_literal",
    "database_exists",
    "ensure_local_database",
    "STORAGE_BUCKET_ID",
    "STORAGE_OBJECT_PATH",
    "purge_database",
    "LiteralSearchHit",
]
