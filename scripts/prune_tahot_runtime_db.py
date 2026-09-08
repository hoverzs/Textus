"""A tahot_ot_runtime.sqlite3 futásidőben ténylegesen NEM olvasott
tábláinak/oszlopainak eltávolítása és tárolás-optimalizálása, hogy a
fájl git-be commitolható méretű maradjon (< 100 MB).

Miért biztonságos ez: a `bible_engine/hebrew_sqlite.py` olvasó
függvényei (`get_hebrew_passage_tokens`, `find_hebrew_tokens_by_lemma`,
`find_hebrew_tokens_by_strong_id`) `SELECT * FROM tokens ...`-ot
használnak, és a `_token_from_normalized_row` a `tokens` tábla saját
oszlopaiból + a `token_strong_ids` JOIN-ból építi fel a `HebrewToken`
objektumot — a `raw_fields_json` / `expanded_strong_tags` /
`source_token_id` mezőket, illetve a `token_components` /
`lexicon_entries` / `strong_aliases` táblákat semelyik futásidejű
olvasási út nem használja (lásd `hebrew_sqlite.py` és
`hebrew_token_repository.py` — a `_tokens_from_database_rows` explicit
lekérdezi az oszlopkészletet, és ha `raw_fields_json` hiányzik, a
"normalizált" (tábla-alapú) rekonstrukciós útvonalra esik vissza).

FONTOS — sorrend-megőrzés: a `token_strong_ids` sorai (prefix/core/
suffix komponensek) az EREDETI beszúrási sorrendben kell hogy
visszaadhatók legyenek (`_load_token_strong_rows` `ORDER BY seq`
szerint olvassa őket) — ezért a migráció explicit `seq` oszlopot ad
hozzá, ahelyett hogy a (WITHOUT ROWID táblánál nem létező) implicit
`rowid`-ra támaszkodna. Ha ezt elhagynánk, több-előtagos/utótagos
szavaknál a komponensek sorrendje összekeveredhetne.

Eltávolított táblák (csak import-időben/auditáláshoz kellenek):
  - token_components, lexicon_entries, strong_aliases

Eltávolított/átalakított `tokens` oszlopok:
  - raw_fields_json, expanded_strong_tags, source_token_id (dropped —
    egyik sem olvasott a normalizált rekonstrukciós úton)

`token_strong_ids` séma-váltás:
  - stable_token_key(TEXT) join kulcs -> token_id(INTEGER), a `tokens`
    tábla saját `token_id` oszlopára hivatkozva
  - role: teljes szó ('token'/'core'/'prefix'/'suffix') -> egykarakteres
    kód ('t'/'c'/'p'/'s') — a `hebrew_sqlite._decode_role` bővíti
    vissza teljes szóvá olvasáskor
  - explicit `seq` oszlop az eredeti beszúrási sorrend megőrzésére
  - WITHOUT ROWID tábla (a kompozit PK-t közvetlenül tárolja, nincs
    külön implicit rowid + PK-index)

Megtartott táblák (futásidőben ténylegesen használtak):
  - metadata, books, tokens, token_strong_ids, ketiv_qere

FONTOS — PHASE 2A, VISSZAÁLLÍTHATÓSÁGI SZERZŐDÉS
================================================
A metszés VESZTESÉGES a komponens-szintű adatra nézve, és a Phase 2B/2C
(összetett szerkezetek: elöljárószó+névelő, birtokos suffixum, status
constructus-lánc) pontosan ezt az adatot igényli. Konkrétan a futásidejű
DB-ből hiányzik, és a `_token_from_normalized_row()` ezért pótolja/torzítja:

  - komponensenkénti `surface`  -> prefix/suffix üres, a core a TELJES
    szóalakot kapja (a `/` elválasztóval együtt);
  - komponensenkénti `morphology_code` -> minden komponens az ÖSSZETETT
    kódot kapja (pl. `HR/Ncfsa`) a saját szegmense helyett;
  - komponensenkénti `gloss` -> mindig üres;
  - `source_token_id` (pl. `Rut.1.1#01=L`) -> a felfelé mutató, sorszintű
    kapcsolat az eredeti TAHOT sorhoz elveszik (a jövőbeli OSHB/MACULA
    illesztés horgonya).

Ez a veszteség NEM végleges: az adat determinisztikusan újraépíthető, mert
    (a) a metszés csak a KIMENETET csonkítja, a forrást nem;
    (b) a `bible_engine/hebrew_parser._build_components()` a négy hivatalos
        TAHOT TSV-ből mindezt hiánytalanul előállítja;
    (c) a teljes séma (`hebrew_sqlite.create_schema`) továbbra is tartalmazza
        a `token_components` táblát és a fenti oszlopokat.

Determinisztikus visszaállítási út (offline, a Phase 2C normalizált store
építésekor):

    1. Szerezd be a négy hivatalos TAHOT fájlt a STEPBible/STEPBible-Data
       repóból (CC BY 4.0), valamint a TBESH lexikont.
    2. `python scripts/build_hebrew_prototype_db.py`  ->  TELJES DB
       (`token_components`, `expanded_strong_tags`, `source_token_id`
       mind jelen van). EZT a fájlt NE metszd.
    3. A metszést csak a git-be commitolt, KIZÁRÓLAG megjelenítésre szolgáló
       futásidejű másolaton futtasd.

Amíg a Phase 2C nem szállítja a normalizált, több részre bontott store-t
(ld. docs/hebrew_analysis_v2_inventory.md §15.3), a metszett DB marad a
production artefaktum — de a fenti lépések garantálják, hogy a komponens-
szintű adat bármikor visszanyerhető, és nem kell újra levezetni.

Használat:
    python scripts/prune_tahot_runtime_db.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_sqlite import (
    DEFAULT_TAHOT_DATABASE_PATH,
    _token_strong_join_column,
)

DROP_TABLES = ("token_components", "lexicon_entries", "strong_aliases")
DROP_TOKEN_COLUMNS = ("raw_fields_json", "expanded_strong_tags", "source_token_id")
KEEP_TABLES = frozenset({"metadata", "books", "tokens", "token_strong_ids", "ketiv_qere"})
ROLE_SHORT_CODES = {"token": "t", "core": "c", "prefix": "p", "suffix": "s"}


def _drop_unused_tables(conn: sqlite3.Connection) -> None:
    for table in DROP_TABLES:
        conn.execute(f'DROP TABLE IF EXISTS "{table}"')


def _ensure_tokens_token_id_column(conn: sqlite3.Connection) -> None:
    """A friss `create_schema()` a `tokens` INTEGER PRIMARY KEY oszlopát
    `id`-nek nevezi — a `token_strong_ids` join-optimalizáláshoz (és a
    `bible_engine.hebrew_sqlite._token_strong_join_column` felismeréshez)
    `token_id` néven kell szerepelnie."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(tokens)").fetchall()}
    if "id" in columns and "token_id" not in columns:
        conn.execute("ALTER TABLE tokens RENAME COLUMN id TO token_id")


_TOKENS_PRUNED_SCHEMA = """
    CREATE TABLE tokens_pruned (
        token_id INTEGER PRIMARY KEY,
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
        source_edition TEXT,
        meaning_variant TEXT,
        spelling_variant TEXT
    )
"""
_TOKENS_PRUNED_COLUMNS = (
    "token_id", "stable_token_key", "book", "chapter", "verse", "word_index",
    "token_index", "surface", "surface_without_accents", "transliteration",
    "english_gloss", "lemma", "morphology_code", "language", "ketiv", "qere",
    "punctuation", "maqaf", "source_edition", "meaning_variant", "spelling_variant",
)


def _drop_unused_token_columns(conn: sqlite3.Connection) -> None:
    """Tábla-újraépítéssel távolítja el a nem használt oszlopokat.

    Nem elég egyszerű `ALTER TABLE ... DROP COLUMN`-t hívni: a
    `source_token_id` oszlopon UNIQUE megszorítás van, amit SQLite
    közvetlen DROP COLUMN-nal nem enged eltávolítani — ezért egy tiszta,
    a `token_id INTEGER PRIMARY KEY` / `stable_token_key UNIQUE`
    megszorításokat is megőrző séma szerinti újraépítés a megbízható út.
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(tokens)").fetchall()}
    if not (set(DROP_TOKEN_COLUMNS) & existing):
        return  # semmi eltávolítandó (pl. már metszett DB-n futtatva)

    conn.execute(_TOKENS_PRUNED_SCHEMA)
    column_list = ", ".join(f'"{c}"' for c in _TOKENS_PRUNED_COLUMNS)
    conn.execute(f"INSERT INTO tokens_pruned ({column_list}) SELECT {column_list} FROM tokens")
    old_count = conn.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]
    new_count = conn.execute("SELECT COUNT(*) FROM tokens_pruned").fetchone()[0]
    if old_count != new_count:
        raise SystemExit(f"tokens oszlop-metszés sorszám-eltérés: {old_count} -> {new_count}")
    conn.execute("DROP TABLE tokens")
    conn.execute("ALTER TABLE tokens_pruned RENAME TO tokens")
    conn.execute("CREATE INDEX idx_tokens_reference ON tokens(book, chapter, verse, word_index)")
    conn.execute("CREATE INDEX idx_tokens_lemma ON tokens(lemma)")


def _migrate_token_strong_ids(conn: sqlite3.Connection) -> None:
    """token_id join kulcs + rövid role-kód + explicit seq + WITHOUT ROWID."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(token_strong_ids)").fetchall()}
    join_column = "token_id" if "token_id" in columns else "stable_token_key"

    conn.execute(
        """
        CREATE TABLE token_strong_ids_new (
            token_id INTEGER NOT NULL,
            strong_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 't',
            seq INTEGER NOT NULL,
            PRIMARY KEY(token_id, seq)
        ) WITHOUT ROWID
        """
    )

    if join_column == "token_id":
        select_sql = "SELECT token_id, strong_id, role, rowid AS seq FROM token_strong_ids ORDER BY rowid"
    else:
        select_sql = (
            "SELECT t.token_id AS token_id, s.strong_id AS strong_id, s.role AS role, "
            "s.rowid AS seq FROM token_strong_ids s "
            "JOIN tokens t ON t.stable_token_key = s.stable_token_key "
            "ORDER BY s.rowid"
        )

    rows = conn.execute(select_sql).fetchall()
    conn.executemany(
        "INSERT INTO token_strong_ids_new (token_id, strong_id, role, seq) VALUES (?, ?, ?, ?)",
        (
            (row[0], row[1], ROLE_SHORT_CODES.get(row[2], row[2]), row[3])
            for row in rows
        ),
    )

    old_count = conn.execute("SELECT COUNT(*) FROM token_strong_ids").fetchone()[0]
    new_count = conn.execute("SELECT COUNT(*) FROM token_strong_ids_new").fetchone()[0]
    if old_count != new_count:
        raise SystemExit(
            f"token_strong_ids migráció sorszám-eltérés: {old_count} -> {new_count}"
        )

    conn.execute("DROP TABLE token_strong_ids")
    conn.execute("ALTER TABLE token_strong_ids_new RENAME TO token_strong_ids")
    conn.execute("CREATE INDEX idx_token_strongs_strong ON token_strong_ids(strong_id)")


def _verify_order_preserved(conn: sqlite3.Connection, before_rows: list[tuple]) -> None:
    """Regresszió-védelem: egy ismert, több-előtagos token komponens-
    sorrendje ne keveredjen össze a migráció során."""
    if not before_rows:
        return
    token_id = before_rows[0][0]
    after_rows = conn.execute(
        "SELECT strong_id, role FROM token_strong_ids WHERE token_id = ? ORDER BY seq",
        (token_id,),
    ).fetchall()
    expected = [(r[1], ROLE_SHORT_CODES.get(r[2], r[2])) for r in before_rows]
    actual = [(r[0], r[1]) for r in after_rows]
    if actual != expected:
        raise SystemExit(
            f"SORREND-REGRESSZIÓ token_id={token_id}: várt {expected}, kapott {actual}"
        )


def main() -> None:
    path = DEFAULT_TAHOT_DATABASE_PATH
    before_size = path.stat().st_size
    conn = sqlite3.connect(str(path))
    try:
        # A `tokens` PK-oszlopát elsőként `token_id`-re nevezzük át, hogy
        # utána mindenhol (mintavétel, migráció) egységesen erre
        # hivatkozhassunk.
        _ensure_tokens_token_id_column(conn)

        # Regresszió-védelmi mintavétel EGY, ismerten több-komponensű
        # tokenre, a migráció előtti állapotból — a join oszlop neve
        # build-változatonként eltérhet (token_id vs stable_token_key),
        # ezért a mintát mindig `token_id`-re normalizáljuk.
        pre_join_column = _token_strong_join_column(conn)
        sample_raw = conn.execute(
            f"""
            SELECT {pre_join_column}, strong_id, role, rowid FROM token_strong_ids
            WHERE {pre_join_column} = (
                SELECT {pre_join_column} FROM token_strong_ids
                WHERE role = 'prefix'
                GROUP BY {pre_join_column} HAVING COUNT(*) >= 2
                LIMIT 1
            )
            ORDER BY rowid
            """
        ).fetchall()
        if sample_raw and pre_join_column == "stable_token_key":
            key_row = conn.execute(
                "SELECT token_id FROM tokens WHERE stable_token_key = ?",
                (sample_raw[0][0],),
            ).fetchone()
            sample = [(key_row[0], *row[1:]) for row in sample_raw]
        else:
            sample = sample_raw

        _drop_unused_tables(conn)
        _drop_unused_token_columns(conn)
        _migrate_token_strong_ids(conn)
        _verify_order_preserved(conn, sample)

        conn.commit()
        conn.execute("VACUUM")
        integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            raise SystemExit(f"quick_check FAILED a metszés után: {integrity}")
        tables_left = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    after_size = path.stat().st_size
    print(f"Táblák a metszés után: {sorted(tables_left)}")
    assert tables_left == KEEP_TABLES, f"Váratlan táblakészlet metszés után: {tables_left}"
    print(f"Méret: {before_size / 1_000_000:.1f} MB -> {after_size / 1_000_000:.1f} MB")


if __name__ == "__main__":
    main()
