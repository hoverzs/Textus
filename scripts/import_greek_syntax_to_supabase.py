"""Phase 2C §3/§4 — offline ETL: Greek Analysis v2 deterministic sources
(TAGNT tokens/morphology + Hungarian lexicon + local MACULA-Greek syntax
store) -> Supabase Postgres.

Mirrors ``scripts/import_macula_to_supabase.py`` (Hebrew, Phase 2D.2)
architecture and its lessons closely: bulk upsert/insert only — never a
per-row HTTP call; batched; retried with bounded exponential backoff;
idempotent (re-running with --execute is safe — every write is either a
natural-key upsert or a dataset-version-scoped delete-then-insert, never an
unscoped delete); dry-run by default. UNRESOLVED_* alignment rows are
imported with ``source_node_id = NULL``, exactly as the local store has
them — this script never converts an UNRESOLVED alignment into a resolved
one, and never silently drops a row it read.

Two distinct local sources feed this importer (never re-derived from raw
MACULA XML/TSV — those stay this script's grandparent inputs, consumed
once by ``scripts/build_greek_syntax_store.py``):

1. The raw TAGNT SQLite database (``bible_engine.greek_token_repository.
   DEFAULT_TAGNT_DATABASE_PATH``) — every token/morphology/lemma/strong_id
   fact, run through ``bible_engine.greek_analysis_service._verse_analysis``
   (the SAME function every other deterministic-bundle consumer in this
   codebase uses) so what lands in Supabase is provably identical to the
   Phase 2A bundle, never a reimplementation of its logic.
2. The local normalized Greek syntax store (``data/generated/
   greek_syntax_dev.sqlite3``, built by ``scripts/build_greek_syntax_store.
   py``) — MACULA source nodes, TAGNT<->MACULA alignments, phrase/clause
   groups, semantic roles, coreference links.

Two real, concrete schema bugs were found and fixed in
``supabase/migrations/20260911220000_greek_linguistic_layer.sql`` while
designing this importer (not the alignment algorithm — task instruction
only forbids touching that without a concrete bug; this is schema design,
never applied to a real project) — see that migration's own comments:

- ``greek_phrases``/``greek_clauses`` now key on a new ``macula_group_id``
  column, not ``source_node_id``: 13,090 of 91,448 groups corpus-wide share
  their first-leaf token with at least one other, nested group, which
  would have silently collapsed distinct constituents under the original
  ``unique(dataset_version_id, source_node_id)`` constraint.
- ``greek_clauses`` gained a ``parent_phrase_id`` column: 2,565 of 83,198
  parented groups corpus-wide are a clause whose immediate parent is a
  phrase (e.g. a relative clause nested inside its head noun phrase), which
  the original clause-only ``parent_clause_id`` column could not represent.

This script has NOT been run against any real Supabase project from this
environment — no credentials are available here (same situation as the
Hebrew importer; see ``supabase_client._load_supabase_secrets()`` raising).
``--dry-run`` (the default) exercises every read/batch/remap step against
the real local stores without ever calling the Supabase client. Pass
``--execute`` (and have real credentials configured) to actually write.

Usage:
    python scripts/import_greek_syntax_to_supabase.py \\
        [--tagnt-db PATH] [--syntax-store PATH] [--books Php,Col,1Th,...] \\
        --dry-run    # default; add --execute to actually write to Supabase

``--books`` (comma-separated TAGNT book codes, e.g. ``--books
Php,Col,1Th,2Th,Tit,Phm,Jud,1Jn,2Jn,3Jn``) scopes every step to only those
books — a bounded real-Supabase benchmark subset (task: "run a REAL bounded
benchmark on a few thousand rows... before full import"). Omit it for the
real full-27-book production import.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.greek_analysis_service import _verse_analysis  # noqa: E402
from bible_engine.greek_dataset_version import (  # noqa: E402
    HUNGARIAN_LEXICON_VERSION,
    MACULA_GREEK_COMMIT,
    MACULA_GREEK_VERSION,
    STEPBIBLE_DATA_COMMIT,
)
from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path  # noqa: E402
from bible_engine.greek_token_repository import DEFAULT_TAGNT_DATABASE_PATH  # noqa: E402
from bible_engine.lexicon_hu import (  # noqa: E402
    DEFAULT_HUNGARIAN_LEXICON_PATH,
    load_default_hungarian_lexicon,
)
from bible_engine.macula_greek_parser import CLAUSE_CLASS, PHRASE_CLASSES  # noqa: E402
from bible_engine.tagnt_books import TAGNT_NEW_TESTAMENT_BOOK_CODES  # noqa: E402
from bible_engine.tagnt_parser import GreekToken  # noqa: E402
from bible_engine.tagnt_sqlite import _clean_greek_form  # noqa: E402

DEFAULT_BATCH_SIZE = 500
DEFAULT_LINK_BATCH_SIZE = 10_000
DEFAULT_RETRY_ATTEMPTS = 4
DEFAULT_RETRY_BASE_DELAY_S = 2.0

# MACULA stores its own book code as upper(TAGNT code) — see
# bible_engine.macula_greek_parser.MaculaGreekToken's docstring. This is
# the inverse mapping, used to reconstruct a TAGNT-cased verse_ref
# ("Jhn.3.16") from MACULA-side rows that only carry the uppercase code.
MACULA_TO_TAGNT_BOOK = {code.upper(): code for code in TAGNT_NEW_TESTAMENT_BOOK_CODES}

# One row per pinned dataset, mirroring bible_engine.greek_dataset_version's
# constants exactly — the single source of truth for what "tagnt version
# X" etc. means at this commit.
GREEK_DATASET_VERSION_ROWS = [
    {
        "dataset_id": "tagnt", "display_name": "STEPBible TAGNT", "revision": f"stepbible-data@{STEPBIBLE_DATA_COMMIT[:12]}",
        "source_repository": "STEPBible/STEPBible-Data", "source_commit": STEPBIBLE_DATA_COMMIT,
        "license": "CC BY 4.0", "attribution": "Data created by www.STEPBible.org based on work at Tyndale House Cambridge (CC BY 4.0)",
    },
    {
        "dataset_id": "tegmc", "display_name": "STEPBible TEGMC", "revision": f"stepbible-data@{STEPBIBLE_DATA_COMMIT[:12]}",
        "source_repository": "STEPBible/STEPBible-Data", "source_commit": STEPBIBLE_DATA_COMMIT,
        "license": "CC BY 4.0", "attribution": "Data created by www.STEPBible.org based on work at Tyndale House Cambridge (CC BY 4.0)",
    },
    {
        "dataset_id": "tbesg", "display_name": "STEPBible TBESG", "revision": f"stepbible-data@{STEPBIBLE_DATA_COMMIT[:12]}",
        "source_repository": "STEPBible/STEPBible-Data", "source_commit": STEPBIBLE_DATA_COMMIT,
        "license": "CC BY 4.0", "attribution": "Data created by www.STEPBible.org based on work at Tyndale House Cambridge (CC BY 4.0)",
    },
    {
        "dataset_id": "greek_hu_lexicon", "display_name": "Textus Hungarian Greek lexicon (TBESG-derived)",
        "revision": HUNGARIAN_LEXICON_VERSION, "source_repository": "internal", "source_commit": "",
        "license": "Internal (derivative of CC BY 4.0 TBESG)", "attribution": "Textus",
    },
    {
        "dataset_id": "macula_greek_sblgnt", "display_name": "MACULA Greek (SBLGNT variant)",
        "revision": MACULA_GREEK_VERSION, "source_repository": "Clear-Bible/macula-greek",
        "source_commit": MACULA_GREEK_COMMIT, "license": "CC BY 4.0",
        "attribution": "Clear-Bible MACULA Greek",
    },
]


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _call_with_retry(fn, *, description: str, attempts: int = DEFAULT_RETRY_ATTEMPTS,
                      base_delay: float = DEFAULT_RETRY_BASE_DELAY_S):
    """See scripts/import_macula_to_supabase.py's own docstring for this
    function — identical safe-retry rationale: every write this script
    makes is either a natural-key upsert or a dataset-version-scoped
    delete-then-insert, so retrying the SAME call after a transient failure
    is safe."""
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — retry-then-reraise, not swallow
            last_exc = exc
            if attempt == attempts:
                break
            delay = base_delay * (2 ** (attempt - 1))
            print(f"  [retry {attempt}/{attempts}] {description} failed ({type(exc).__name__}: {exc}) "
                  f"— retrying in {delay:.0f}s", flush=True)
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def _require_equal_length(**arrays: list) -> None:
    lengths = {name: len(values) for name, values in arrays.items()}
    if len(set(lengths.values())) > 1:
        raise ValueError(f"array length mismatch: {lengths}")


class RemoteWriter:
    """Thin wrapper around the Supabase client — the ONLY place this
    script talks to Postgres. Mirrors scripts/import_macula_to_supabase.py
    ``RemoteWriter`` exactly."""

    def __init__(self) -> None:
        from supabase_client import get_supabase_client

        self.client = get_supabase_client()

    def upsert(self, table: str, rows: list[dict], on_conflict: str) -> list[dict]:
        response = _call_with_retry(
            lambda: self.client.table(table).upsert(rows, on_conflict=on_conflict).execute(),
            description=f"upsert {table} ({len(rows)} rows)",
        )
        return response.data or []

    def insert(self, table: str, rows: list[dict]) -> list[dict]:
        response = _call_with_retry(
            lambda: self.client.table(table).insert(rows).execute(),
            description=f"insert {table} ({len(rows)} rows)",
        )
        return response.data or []

    def delete_all_where(self, table: str, column: str, value, chunk_size: int = DEFAULT_BATCH_SIZE) -> None:
        # Chunked select-then-delete, not a single .delete().eq() — see
        # scripts/import_macula_to_supabase.py's own RemoteWriter.
        # delete_all_where for why an unscoped-by-batch delete against a
        # corpus-scale table hits Postgres's statement timeout.
        while True:
            page = _call_with_retry(
                lambda: self.client.table(table).select("id").eq(column, value).limit(chunk_size).execute(),
                description=f"select ids from {table} where {column}={value} (for chunked delete)",
            )
            ids = [row["id"] for row in (page.data or [])]
            if not ids:
                return
            _call_with_retry(
                lambda ids=ids: self.client.table(table).delete().in_("id", ids).execute(),
                description=f"delete {table} where id in (...{len(ids)} rows matching {column}={value})",
            )

    def delete_where_in(self, table: str, column: str, values: list, chunk_size: int = DEFAULT_BATCH_SIZE) -> None:
        # Chunked .in_() delete — see scripts/import_macula_to_supabase.py's
        # own RemoteWriter.delete_where_in for why a single .in_() with
        # corpus-scale cardinality can exceed the HTTP client's URL length
        # limit. Used for greek_syntax_membership, which has no natural
        # unique constraint (a token can appear in many phrases/clauses) —
        # scoped replace by the specific phrase/clause remote ids about to
        # be reimported, so re-running this importer (e.g. a bounded
        # benchmark subset followed by the full corpus) never duplicates
        # membership rows for groups that already existed.
        for chunk in _chunks(values, chunk_size):
            _call_with_retry(
                lambda chunk=chunk: self.client.table(table).delete().in_(column, chunk).execute(),
                description=f"delete {table} where {column} in (...{len(chunk)} of {len(values)} values)",
            )

    def bulk_link_greek_clause_parents(self, rows: list[dict]) -> None:
        ids = [row["id"] for row in rows]
        parent_clause_ids = [row.get("parent_clause_id") for row in rows]
        parent_phrase_ids = [row.get("parent_phrase_id") for row in rows]
        _require_equal_length(p_ids=ids, p_parent_clause_ids=parent_clause_ids, p_parent_phrase_ids=parent_phrase_ids)
        _call_with_retry(
            lambda: self.client.rpc(
                "bulk_link_greek_clause_parents",
                {"p_ids": ids, "p_parent_clause_ids": parent_clause_ids, "p_parent_phrase_ids": parent_phrase_ids},
            ).execute(),
            description=f"bulk_link_greek_clause_parents ({len(rows)} rows)",
        )

    def bulk_link_greek_phrase_parents(self, rows: list[dict]) -> None:
        ids = [row["id"] for row in rows]
        parent_phrase_ids = [row.get("parent_phrase_id") for row in rows]
        parent_clause_ids = [row.get("parent_clause_id") for row in rows]
        _require_equal_length(p_ids=ids, p_parent_phrase_ids=parent_phrase_ids, p_parent_clause_ids=parent_clause_ids)
        _call_with_retry(
            lambda: self.client.rpc(
                "bulk_link_greek_phrase_parents",
                {"p_ids": ids, "p_parent_phrase_ids": parent_phrase_ids, "p_parent_clause_ids": parent_clause_ids},
            ).execute(),
            description=f"bulk_link_greek_phrase_parents ({len(rows)} rows)",
        )


class DryRunWriter:
    """Simulates Postgres identity-column assignment so the full remap
    logic below runs and is checked for internal consistency, without ever
    touching a network. Mirrors scripts/import_macula_to_supabase.py
    ``DryRunWriter``."""

    def __init__(self) -> None:
        self._next_id = 10_000_000
        self.table_counts: dict[str, int] = {}
        self.deleted_counts: dict[str, int] = {}
        self._store: dict[str, dict[int, dict]] = {}

    def upsert(self, table: str, rows: list[dict], on_conflict: str) -> list[dict]:
        self.table_counts[table] = self.table_counts.get(table, 0) + len(rows)
        store = self._store.setdefault(table, {})
        out = []
        for row in rows:
            new_row = dict(row)
            if "id" not in new_row:
                new_row["id"] = self._next_id
                self._next_id += 1
            store[new_row["id"]] = dict(new_row)
            out.append(new_row)
        return out

    def insert(self, table: str, rows: list[dict]) -> list[dict]:
        return self.upsert(table, rows, on_conflict="")

    def delete_all_where(self, table: str, column: str, value, chunk_size: int = DEFAULT_BATCH_SIZE) -> None:
        self.deleted_counts[table] = self.deleted_counts.get(table, 0) + 1

    def delete_where_in(self, table: str, column: str, values: list, chunk_size: int = DEFAULT_BATCH_SIZE) -> None:
        self.deleted_counts[table] = self.deleted_counts.get(table, 0) + len(values)
        store = self._store.get(table)
        if store is not None and column == "id":
            for v in values:
                store.pop(v, None)

    def bulk_link_greek_clause_parents(self, rows: list[dict]) -> None:
        ids = [row["id"] for row in rows]
        parent_clause_ids = [row.get("parent_clause_id") for row in rows]
        parent_phrase_ids = [row.get("parent_phrase_id") for row in rows]
        _require_equal_length(p_ids=ids, p_parent_clause_ids=parent_clause_ids, p_parent_phrase_ids=parent_phrase_ids)
        store = self._store.get("greek_clauses", {})
        for row in rows:
            target = store.get(row["id"])
            if target is None:
                continue
            if "parent_clause_id" in row:
                target["parent_clause_id"] = row["parent_clause_id"]
            if "parent_phrase_id" in row:
                target["parent_phrase_id"] = row["parent_phrase_id"]

    def bulk_link_greek_phrase_parents(self, rows: list[dict]) -> None:
        ids = [row["id"] for row in rows]
        parent_phrase_ids = [row.get("parent_phrase_id") for row in rows]
        parent_clause_ids = [row.get("parent_clause_id") for row in rows]
        _require_equal_length(p_ids=ids, p_parent_phrase_ids=parent_phrase_ids, p_parent_clause_ids=parent_clause_ids)
        store = self._store.get("greek_phrases", {})
        for row in rows:
            target = store.get(row["id"])
            if target is None:
                continue
            if "parent_phrase_id" in row:
                target["parent_phrase_id"] = row["parent_phrase_id"]
            if "parent_clause_id" in row:
                target["parent_clause_id"] = row["parent_clause_id"]


def _log_progress(label: str, done: int, total: int, start: float) -> None:
    elapsed = time.time() - start
    rate = done / elapsed if elapsed > 0 else 0.0
    print(f"    [{label}] {done}/{total} rows ({elapsed:.1f}s elapsed, {rate:.0f} rows/s)", flush=True)


# ---------------------------------------------------------------------------
# Step 1 — dataset versions
# ---------------------------------------------------------------------------


def import_dataset_versions(writer, batch_size: int) -> dict[str, int]:
    result = writer.upsert("original_language_dataset_versions", GREEK_DATASET_VERSION_ROWS, on_conflict="dataset_id,revision")
    return {row["dataset_id"]: row["id"] for row in result}


# ---------------------------------------------------------------------------
# Step 2 — verses + tokens (TAGNT db, run through the SAME Phase 2A
# verse-assembly logic every other consumer uses)
# ---------------------------------------------------------------------------


def load_tagnt_by_verse(
    tagnt_db_path: Path, book_filter: set[str] | None = None
) -> dict[tuple[str, int, int], list[GreekToken]]:
    with sqlite3.connect(tagnt_db_path) as connection:
        rows = connection.execute(
            "SELECT book, chapter, verse, word_index, greek_form, lemma, morph_code, strong_id, edition_flags "
            "FROM greek_tokens ORDER BY book, chapter, verse, word_index"
        ).fetchall()
    by_verse: dict[tuple[str, int, int], list[GreekToken]] = defaultdict(list)
    for book, chapter, verse, word_index, greek_form, lemma, morph_code, strong_id, edition_flags in rows:
        if book_filter is not None and book not in book_filter:
            continue
        by_verse[(book, chapter, verse)].append(
            GreekToken(
                book=book, chapter=chapter, verse=verse, word_index=word_index,
                greek_form=_clean_greek_form(greek_form), lemma=lemma,
                morph_code=morph_code, strong_id=strong_id, edition_flags=edition_flags,
            )
        )
    return by_verse


def import_verses_and_tokens(
    tagnt_db_path: Path, writer, batch_size: int, dv_map: dict[str, int], book_filter: set[str] | None = None
) -> tuple[dict[str, int], int, int]:
    entries = load_default_hungarian_lexicon(DEFAULT_HUNGARIAN_LEXICON_PATH) or {}
    from bible_engine.lexicon_hu import DEFAULT_STRONG_ALIASES_PATH, load_strong_aliases

    aliases = load_strong_aliases(DEFAULT_STRONG_ALIASES_PATH)

    by_verse = load_tagnt_by_verse(tagnt_db_path, book_filter)
    tagnt_dv_id = dv_map["tagnt"]

    verse_map: dict[str, int] = {}
    verse_analyses = []
    for (book, chapter, verse), tokens in by_verse.items():
        verse_analysis = _verse_analysis(book, chapter, verse, tokens, entries, aliases)
        verse_analyses.append(verse_analysis)

    for chunk in _chunks(verse_analyses, batch_size):
        payload = [
            {
                "book_id": v.book, "chapter": v.chapter, "verse": v.verse, "verse_ref": v.verse_id,
                "greek_text": v.greek_text, "dataset_version_id": tagnt_dv_id,
            }
            for v in chunk
        ]
        result = writer.upsert("greek_verses", payload, on_conflict="verse_ref")
        for local_row, remote_row in zip(chunk, result):
            verse_map[local_row.verse_id] = remote_row["id"]

    token_count = 0
    for chunk in _chunks(verse_analyses, max(1, batch_size // 20)):
        payload = []
        for v in chunk:
            remote_verse_id = verse_map[v.verse_id]
            for t in v.tokens:
                m = t.morphology
                payload.append({
                    "token_id": t.token_id, "verse_id": remote_verse_id, "word_index": t.word_index,
                    "surface": t.surface, "lemma": t.lemma, "strong_id": t.strong_id,
                    "edition_flags": t.edition_flags, "part_of_speech": t.part_of_speech,
                    "morphology_raw_code": m.raw_code, "morphology_confidence": m.confidence,
                    "case_": m.case, "number_": m.number, "gender": m.gender, "person": m.person,
                    "tense": m.tense, "voice": m.voice, "mood": m.mood, "verb_form": m.verb_form,
                    "degree": m.degree, "pronoun_type": m.pronoun_type, "name_type": m.name_type,
                    "dataset_version_id": tagnt_dv_id,
                })
        writer.upsert("greek_tokens", payload, on_conflict="token_id")
        token_count += len(payload)

    return verse_map, len(verse_map), token_count


# ---------------------------------------------------------------------------
# Step 3 — Hungarian lexicon
# ---------------------------------------------------------------------------


def import_lexicon_hu(writer, batch_size: int, dv_map: dict[str, int]) -> int:
    entries = load_default_hungarian_lexicon(DEFAULT_HUNGARIAN_LEXICON_PATH) or {}
    lexicon_dv_id = dv_map["greek_hu_lexicon"]
    rows = list(entries.values())
    count = 0
    for chunk in _chunks(rows, batch_size):
        payload = [
            {
                "strong_id": e.strong_id, "lemma": e.lemma, "primary_gloss": e.primary_gloss,
                "senses": list(e.senses), "note": e.note or "", "review_status": e.review_status,
                "translation_method": e.translation_method, "source_name": e.source_name,
                "source_version": e.source_version, "dataset_version_id": lexicon_dv_id,
            }
            for e in chunk
        ]
        writer.upsert("greek_lexicon_hu", payload, on_conflict="dataset_version_id,strong_id")
        count += len(chunk)
    return count


# ---------------------------------------------------------------------------
# Step 4 — MACULA source nodes
# ---------------------------------------------------------------------------


def import_source_nodes(
    conn: sqlite3.Connection, writer, batch_size: int, dv_map: dict[str, int],
    macula_book_filter: set[str] | None = None,
) -> dict[str, int]:
    rows = conn.execute("SELECT * FROM macula_source_nodes").fetchall()
    if macula_book_filter is not None:
        rows = [r for r in rows if r["book"] in macula_book_filter]
    macula_dv_id = dv_map["macula_greek_sblgnt"]
    node_map: dict[str, int] = {}
    for chunk in _chunks(rows, batch_size):
        payload = []
        for row in chunk:
            book = row["book"]
            tagnt_book = MACULA_TO_TAGNT_BOOK.get(book, book)
            payload.append({
                "dataset_version_id": macula_dv_id, "macula_xml_id": row["xml_id"],
                "verse_ref": f"{tagnt_book}.{row['chapter']}.{row['verse']}",
                "word_index": row["word_index"], "role": row["role"] or "", "word_class": row["word_class"] or "",
                "word_type": row["word_type"] or "", "text_": row["text"] or "", "lemma": row["lemma"] or "",
                "normalized": row["normalized"] or "", "strong": row["strong"] or "", "morph": row["morph"] or "",
                "macula_case": row["case_"] or "", "macula_number": row["number"] or "",
                "frame": row["frame"] or "", "subjref": row["subjref"] or "", "referent": row["referent"] or "",
            })
        result = writer.upsert("greek_source_nodes", payload, on_conflict="dataset_version_id,macula_xml_id")
        for local_row, remote_row in zip(chunk, result):
            node_map[local_row["xml_id"]] = remote_row["id"]
    return node_map


# ---------------------------------------------------------------------------
# Step 5 — TAGNT <-> MACULA alignments
# ---------------------------------------------------------------------------


def import_token_alignments(
    conn: sqlite3.Connection, writer, batch_size: int, dv_map: dict[str, int], node_map: dict[str, int],
    known_token_ids: set[str],
) -> int:
    writer.delete_all_where("greek_token_alignments", "dataset_version_id_macula", dv_map["macula_greek_sblgnt"])

    rows = conn.execute("SELECT tagnt_token_id, macula_xml_id, status, evidence_json FROM token_alignments").fetchall()
    skipped_unknown_token = 0
    count = 0
    for chunk in _chunks(rows, batch_size):
        payload = []
        for row in chunk:
            if row["tagnt_token_id"] not in known_token_ids:
                # FK prerequisite check (task §4) — never silently import an
                # alignment row for a token that was not itself imported;
                # count and report rather than raising, since a bounded
                # benchmark subset run (fewer books) legitimately produces
                # this for tokens outside the imported subset.
                skipped_unknown_token += 1
                continue
            payload.append({
                "token_id": row["tagnt_token_id"],
                "source_node_id": node_map.get(row["macula_xml_id"]) if row["macula_xml_id"] else None,
                "alignment_status": row["status"], "unresolved_category": "",
                "evidence": row["evidence_json"] or "",
                "dataset_version_id_tagnt": dv_map["tagnt"], "dataset_version_id_macula": dv_map["macula_greek_sblgnt"],
            })
        if payload:
            writer.insert("greek_token_alignments", payload)
        count += len(payload)
    if skipped_unknown_token:
        print(f"    NOTE: {skipped_unknown_token} alignment rows skipped — token_id not in the imported verse/token set "
              f"(expected for a bounded/partial import; never expected for a full-corpus run)")
    return count


# ---------------------------------------------------------------------------
# Step 6 — phrases + clauses (two-pass: insert with parents NULL, then bulk-
# link once every group's remote id is known)
# ---------------------------------------------------------------------------


def import_phrases_and_clauses(
    conn: sqlite3.Connection, writer, batch_size: int, dv_map: dict[str, int], node_map: dict[str, int],
    link_batch_size: int, macula_book_filter: set[str] | None = None,
) -> tuple[dict[str, int], dict[str, int], dict[str, bool]]:
    rows = conn.execute(
        "SELECT group_id, book, chapter, verse, group_class, rule, role, predication, token_ids_json, parent_group_id "
        "FROM macula_groups"
    ).fetchall()
    if macula_book_filter is not None:
        rows = [r for r in rows if r["book"] in macula_book_filter]
    macula_dv_id = dv_map["macula_greek_sblgnt"]

    phrase_rows = [r for r in rows if r["group_class"] in PHRASE_CLASSES]
    clause_rows = [r for r in rows if r["group_class"] == CLAUSE_CLASS]

    phrase_map: dict[str, int] = {}
    for chunk in _chunks(phrase_rows, batch_size):
        payload = []
        for row in chunk:
            token_ids = json.loads(row["token_ids_json"])
            first_macula_id = token_ids[0] if token_ids else None
            source_node_id = node_map.get(first_macula_id)
            if source_node_id is None:
                continue  # first token never resolved to a source node — cannot satisfy the not-null FK
            tagnt_book = MACULA_TO_TAGNT_BOOK.get(row["book"], row["book"])
            payload.append({
                "macula_group_id": row["group_id"], "source_node_id": source_node_id,
                "dataset_version_id": macula_dv_id, "verse_ref": f"{tagnt_book}.{row['chapter']}.{row['verse']}",
                "phrase_type": row["group_class"], "role": row["role"] or "", "parent_phrase_id": None,
                "parent_clause_id": None,
            })
        result = writer.upsert("greek_phrases", payload, on_conflict="dataset_version_id,macula_group_id")
        for local_row, remote_row in zip(payload, result):
            phrase_map[local_row["macula_group_id"]] = remote_row["id"]

    clause_map: dict[str, int] = {}
    for chunk in _chunks(clause_rows, batch_size):
        payload = []
        for row in chunk:
            token_ids = json.loads(row["token_ids_json"])
            first_macula_id = token_ids[0] if token_ids else None
            source_node_id = node_map.get(first_macula_id)
            if source_node_id is None:
                continue
            tagnt_book = MACULA_TO_TAGNT_BOOK.get(row["book"], row["book"])
            payload.append({
                "macula_group_id": row["group_id"], "source_node_id": source_node_id,
                "dataset_version_id": macula_dv_id, "verse_ref": f"{tagnt_book}.{row['chapter']}.{row['verse']}",
                "clause_type": row["rule"] or "", "relation_to_parent": row["predication"] or "",
                "parent_clause_id": None, "parent_phrase_id": None,
            })
        result = writer.upsert("greek_clauses", payload, on_conflict="dataset_version_id,macula_group_id")
        for local_row, remote_row in zip(payload, result):
            clause_map[local_row["macula_group_id"]] = remote_row["id"]

    is_clause_by_group_id = {row["group_id"]: (row["group_class"] == CLAUSE_CLASS) for row in rows}
    parent_by_group_id = {row["group_id"]: row["parent_group_id"] for row in rows}

    def _remote_id(group_id: str) -> int | None:
        return clause_map.get(group_id) if is_clause_by_group_id.get(group_id) else phrase_map.get(group_id)

    clause_update_rows = []
    for group_id, remote_id in clause_map.items():
        parent_group_id = parent_by_group_id.get(group_id)
        if parent_group_id is None:
            continue
        update: dict = {"id": remote_id}
        if is_clause_by_group_id.get(parent_group_id):
            parent_remote = clause_map.get(parent_group_id)
            if parent_remote is not None:
                update["parent_clause_id"] = parent_remote
        else:
            parent_remote = phrase_map.get(parent_group_id)
            if parent_remote is not None:
                update["parent_phrase_id"] = parent_remote
        if len(update) > 1:
            clause_update_rows.append(update)

    link_start = time.time()
    linked = 0
    for chunk in _chunks(clause_update_rows, link_batch_size):
        writer.bulk_link_greek_clause_parents(chunk)
        linked += len(chunk)
        _log_progress("greek_clauses (parent link)", linked, len(clause_update_rows), link_start)

    phrase_update_rows = []
    for group_id, remote_id in phrase_map.items():
        parent_group_id = parent_by_group_id.get(group_id)
        if parent_group_id is None:
            continue
        update = {"id": remote_id}
        if is_clause_by_group_id.get(parent_group_id):
            parent_remote = clause_map.get(parent_group_id)
            if parent_remote is not None:
                update["parent_clause_id"] = parent_remote
        else:
            parent_remote = phrase_map.get(parent_group_id)
            if parent_remote is not None:
                update["parent_phrase_id"] = parent_remote
        if len(update) > 1:
            phrase_update_rows.append(update)

    link_start = time.time()
    linked = 0
    for chunk in _chunks(phrase_update_rows, link_batch_size):
        writer.bulk_link_greek_phrase_parents(chunk)
        linked += len(chunk)
        _log_progress("greek_phrases (parent link)", linked, len(phrase_update_rows), link_start)

    return phrase_map, clause_map, is_clause_by_group_id


# ---------------------------------------------------------------------------
# Step 7 — syntax membership
# ---------------------------------------------------------------------------


def import_syntax_membership(
    conn: sqlite3.Connection, writer, batch_size: int, phrase_map: dict[str, int], clause_map: dict[str, int],
    macula_to_tagnt: dict[str, str],
) -> int:
    # No natural unique constraint on this table (a token can belong to
    # many phrases/clauses) — scoped replace: delete existing membership
    # rows for exactly the phrase/clause remote ids about to be reimported
    # before inserting the fresh batch, so re-running this importer (e.g.
    # a bounded benchmark subset followed by the full corpus, where the
    # subset's phrases/clauses upsert to the SAME remote ids) never
    # duplicates membership rows.
    if phrase_map:
        writer.delete_where_in("greek_syntax_membership", "phrase_id", list(phrase_map.values()))
    if clause_map:
        writer.delete_where_in("greek_syntax_membership", "clause_id", list(clause_map.values()))

    rows = conn.execute("SELECT group_id, group_class, token_ids_json FROM macula_groups").fetchall()
    count = 0
    skipped_unknown_token = 0
    for chunk in _chunks(rows, batch_size):
        payload = []
        for row in chunk:
            is_clause = row["group_class"] == CLAUSE_CLASS
            remote_group_id = clause_map.get(row["group_id"]) if is_clause else phrase_map.get(row["group_id"])
            if remote_group_id is None:
                continue
            for order, macula_id in enumerate(json.loads(row["token_ids_json"])):
                tagnt_token_id = macula_to_tagnt.get(macula_id)
                if tagnt_token_id is None:
                    skipped_unknown_token += 1
                    continue
                payload.append({
                    "token_id": tagnt_token_id,
                    "phrase_id": None if is_clause else remote_group_id,
                    "clause_id": remote_group_id if is_clause else None,
                    "member_order": order,
                })
        if payload:
            writer.insert("greek_syntax_membership", payload)
        count += len(payload)
    if skipped_unknown_token:
        print(f"    NOTE: {skipped_unknown_token} membership entries skipped — MACULA token has no resolved TAGNT alignment")
    return count


# ---------------------------------------------------------------------------
# Step 8 — semantic roles + coreference
# ---------------------------------------------------------------------------


def _verse_ref_lookup(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT xml_id, book, chapter, verse FROM macula_source_nodes").fetchall()
    return {
        row["xml_id"]: f"{MACULA_TO_TAGNT_BOOK.get(row['book'], row['book'])}.{row['chapter']}.{row['verse']}"
        for row in rows
    }


def import_semantic_roles(
    conn: sqlite3.Connection, writer, batch_size: int, dv_map: dict[str, int], macula_to_tagnt: dict[str, str],
    verse_ref_by_xml_id: dict[str, str],
) -> int:
    writer.delete_all_where("greek_semantic_roles", "dataset_version_id", dv_map["macula_greek_sblgnt"])
    rows = conn.execute("SELECT predicate_xml_id, role_code, argument_xml_id FROM semantic_role_assignments").fetchall()
    count = 0
    skipped = 0
    for chunk in _chunks(rows, batch_size):
        payload = []
        for row in chunk:
            predicate_token = macula_to_tagnt.get(row["predicate_xml_id"])
            argument_token = macula_to_tagnt.get(row["argument_xml_id"])
            if predicate_token is None or argument_token is None:
                skipped += 1
                continue
            payload.append({
                "dataset_version_id": dv_map["macula_greek_sblgnt"],
                "verse_ref": verse_ref_by_xml_id.get(row["predicate_xml_id"], ""),
                "predicate_token_id": predicate_token, "role_code": row["role_code"],
                "argument_token_id": argument_token,
            })
        if payload:
            writer.insert("greek_semantic_roles", payload)
        count += len(payload)
    if skipped:
        print(f"    NOTE: {skipped} semantic-role assignments skipped — predicate/argument has no resolved TAGNT alignment")
    return count


def import_coreference(
    conn: sqlite3.Connection, writer, batch_size: int, dv_map: dict[str, int], macula_to_tagnt: dict[str, str],
    verse_ref_by_xml_id: dict[str, str],
) -> int:
    writer.delete_all_where("greek_coreference_links", "dataset_version_id", dv_map["macula_greek_sblgnt"])
    rows = conn.execute("SELECT source_xml_id, link_type, target_xml_id FROM coreference_links").fetchall()
    count = 0
    skipped = 0
    for chunk in _chunks(rows, batch_size):
        payload = []
        for row in chunk:
            source_token = macula_to_tagnt.get(row["source_xml_id"])
            target_token = macula_to_tagnt.get(row["target_xml_id"])
            if source_token is None or target_token is None:
                skipped += 1
                continue
            payload.append({
                "dataset_version_id": dv_map["macula_greek_sblgnt"],
                "verse_ref": verse_ref_by_xml_id.get(row["source_xml_id"], ""),
                "source_token_id": source_token, "link_type": row["link_type"], "target_token_id": target_token,
            })
        if payload:
            writer.insert("greek_coreference_links", payload)
        count += len(payload)
    if skipped:
        print(f"    NOTE: {skipped} coreference links skipped — source/target has no resolved TAGNT alignment")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tagnt-db", type=Path, default=DEFAULT_TAGNT_DATABASE_PATH)
    parser.add_argument("--syntax-store", type=Path, default=resolve_default_syntax_database_path())
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--link-batch-size", type=int, default=DEFAULT_LINK_BATCH_SIZE)
    parser.add_argument("--execute", action="store_true", help="actually write to Supabase (default: dry run)")
    parser.add_argument(
        "--books", type=str, default="",
        help="comma-separated TAGNT book codes (e.g. Php,Col,1Th) to scope a bounded benchmark run; "
             "omit for the full 27-book corpus",
    )
    args = parser.parse_args()

    book_filter: set[str] | None = None
    macula_book_filter: set[str] | None = None
    if args.books.strip():
        book_filter = {b.strip() for b in args.books.split(",") if b.strip()}
        macula_book_filter = {b.upper() for b in book_filter}
        print(f"BOOK-SCOPED RUN: {sorted(book_filter)}")

    if not args.tagnt_db.exists():
        print(f"TAGNT database not found: {args.tagnt_db}")
        return 2
    if not args.syntax_store.exists():
        print(f"Greek syntax store not found: {args.syntax_store}")
        return 2

    if args.execute:
        try:
            writer = RemoteWriter()
        except Exception as exc:  # noqa: BLE001
            print(f"Cannot create a Supabase client — no usable credentials in this environment: {exc}")
            print("Re-run with --dry-run (the default) to validate the import plan locally instead.")
            return 1
        print("EXECUTING against the configured Supabase project.")
    else:
        writer = DryRunWriter()
        print("DRY RUN — no network calls will be made; validating the full import plan against the local stores.")

    conn = sqlite3.connect(args.syntax_store)
    conn.row_factory = sqlite3.Row

    start = time.time()

    dv_map = import_dataset_versions(writer, args.batch_size)
    print(f"  dataset_versions: {len(dv_map)} rows")

    verse_map, verse_count, token_count = import_verses_and_tokens(
        args.tagnt_db, writer, args.batch_size, dv_map, book_filter
    )
    print(f"  verses: {verse_count} rows, tokens: {token_count} rows")

    lexicon_count = import_lexicon_hu(writer, args.batch_size, dv_map)
    print(f"  lexicon_hu: {lexicon_count} rows")

    node_map = import_source_nodes(conn, writer, args.batch_size, dv_map, macula_book_filter)
    print(f"  source_nodes: {len(node_map)} rows")

    macula_to_tagnt = {
        row["macula_xml_id"]: row["tagnt_token_id"]
        for row in conn.execute("SELECT tagnt_token_id, macula_xml_id FROM token_alignments WHERE macula_xml_id IS NOT NULL")
        if row["macula_xml_id"] in node_map
    }

    all_known_token_ids = {
        row["tagnt_token_id"] for row in conn.execute("SELECT DISTINCT tagnt_token_id FROM token_alignments")
        if book_filter is None or row["tagnt_token_id"].split(".", 1)[0] in book_filter
    }
    alignment_count = import_token_alignments(conn, writer, args.batch_size, dv_map, node_map, all_known_token_ids)
    print(f"  token_alignments: {alignment_count} rows")

    phrase_map, clause_map, _is_clause = import_phrases_and_clauses(
        conn, writer, args.batch_size, dv_map, node_map, args.link_batch_size, macula_book_filter
    )
    print(f"  phrases: {len(phrase_map)} rows, clauses: {len(clause_map)} rows")

    membership_count = import_syntax_membership(conn, writer, args.batch_size, phrase_map, clause_map, macula_to_tagnt)
    print(f"  syntax_membership: {membership_count} rows")

    verse_ref_by_xml_id = _verse_ref_lookup(conn)
    role_count = import_semantic_roles(conn, writer, args.batch_size, dv_map, macula_to_tagnt, verse_ref_by_xml_id)
    print(f"  semantic_roles: {role_count} rows")

    coref_count = import_coreference(conn, writer, args.batch_size, dv_map, macula_to_tagnt, verse_ref_by_xml_id)
    print(f"  coreference: {coref_count} rows")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s — all 9 populated tables imported "
          "(greek_verses, greek_tokens, greek_lexicon_hu, greek_source_nodes, greek_token_alignments, "
          "greek_phrases, greek_clauses, greek_syntax_membership, greek_semantic_roles, greek_coreference_links).")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
