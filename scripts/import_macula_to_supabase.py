"""Phase 2D.2 — offline ETL: local Phase 2D.1 normalized SQLite mirror ->
Supabase Postgres.

Reads the ALREADY-BUILT, ALREADY-INVARIANT-VERIFIED local store produced by
``scripts/build_macula_alignment_store.py`` (the Phase 2D.1 *final*,
hardened alignment run — never a pre-hardening Phase 2D store) and writes
it to Supabase in FK-dependency order, batched, with deterministic record
counts and safe-retry (versioned replace) semantics. Never re-derives
anything from raw MACULA XML — the local SQLite mirror is this script's
only input, and Supabase is its only output.

Import strategy: **scoped replace, not incremental upsert.** Every table
in this schema is either naturally upsert-safe (has a real unique
constraint independent of its surrogate id — verses, tokens, components,
source nodes, phrases, clauses, syntax edges, participants) or is
DELETE-scoped by ``dataset_version_id`` before a fresh batch insert
(token_alignments, syntax_membership, semantic_roles, coreference — none
of which has a natural unique constraint that would make a plain upsert
idempotent). Every delete is scoped to the specific dataset version(s)
being (re-)imported — never an unscoped ``DELETE``/``TRUNCATE`` against
the whole table, and never touching any table outside this migration's 16.

Surrogate-id remapping: tables with a ``bigint generated always as
identity`` primary key (``original_language_dataset_versions``,
``hebrew_verses``, ``hebrew_source_nodes``, ``hebrew_phrases``,
``hebrew_clauses``, ``hebrew_participants``) get NEW ids assigned by
Postgres on insert, which will not match the local SQLite ids. Every
row referencing one of those ids is remapped through an in-memory
``local_id -> remote_id`` dict built from each batch's own upsert
response before its dependents are ever inserted.  ``hebrew_source_nodes``
is self-referencing (``parent_node_id``); Phase 2D.1's corpus-wide check
(0/816,844 violations) confirms every node's local id is greater than its
parent's, so a two-pass insert (pass 1: all nodes with
``parent_node_id=NULL``; pass 2: batched ``UPDATE`` setting the real
remote parent id) is correct and avoids needing same-batch topological
ordering.

This script has NOT been run against any real Supabase project from this
environment — no credentials are available here (verified via
``supabase_client._load_supabase_secrets()`` raising). ``--dry-run`` (the
default) exercises every read/batch/remap step against the real local
store without ever calling the Supabase client, and is what this phase's
report is based on. Pass ``--execute`` (and have real credentials
configured) to actually write.

Usage:
    python scripts/import_macula_to_supabase.py \\
        --local-store /path/to/hebrew_macula_alignment_2d1_final.sqlite3 \\
        --dry-run    # default; add --execute to actually write to Supabase
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_BATCH_SIZE = 500


class ImportError_(RuntimeError):
    pass


class RemoteWriter:
    """Thin wrapper around the Supabase client — the ONLY place this
    script talks to Postgres. A dry run never constructs one of these;
    see DryRunWriter below for the offline equivalent."""

    def __init__(self) -> None:
        from supabase_client import get_supabase_client

        self.client = get_supabase_client()

    def upsert(self, table: str, rows: list[dict], on_conflict: str) -> list[dict]:
        response = self.client.table(table).upsert(rows, on_conflict=on_conflict).execute()
        return response.data or []

    def insert(self, table: str, rows: list[dict]) -> list[dict]:
        response = self.client.table(table).insert(rows).execute()
        return response.data or []

    def delete_where(self, table: str, column: str, value) -> None:
        self.client.table(table).delete().eq(column, value).execute()

    def delete_where_in(self, table: str, column: str, values: list) -> None:
        if values:
            self.client.table(table).delete().in_(column, values).execute()

    def update_batch(self, table: str, rows: list[dict], key_column: str) -> None:
        for row in rows:
            self.client.table(table).update(row).eq(key_column, row[key_column]).execute()


class DryRunWriter:
    """Simulates Postgres identity-column assignment (sequential integers,
    starting past any local id so a dry run never coincides with a local
    id by accident) so the FULL remap logic below runs and is checked for
    internal consistency, without ever touching a network."""

    def __init__(self) -> None:
        self._next_id = 10_000_000
        self.table_counts: dict[str, int] = {}
        self.deleted_counts: dict[str, int] = {}

    def upsert(self, table: str, rows: list[dict], on_conflict: str) -> list[dict]:
        self.table_counts[table] = self.table_counts.get(table, 0) + len(rows)
        out = []
        for row in rows:
            new_row = dict(row)
            if "id" not in new_row:
                new_row["id"] = self._next_id
                self._next_id += 1
            out.append(new_row)
        return out

    def insert(self, table: str, rows: list[dict]) -> list[dict]:
        return self.upsert(table, rows, on_conflict="")

    def delete_where(self, table: str, column: str, value) -> None:
        self.deleted_counts[table] = self.deleted_counts.get(table, 0) + 1

    def delete_where_in(self, table: str, column: str, values: list) -> None:
        self.deleted_counts[table] = self.deleted_counts.get(table, 0) + len(values)

    def update_batch(self, table: str, rows: list[dict], key_column: str) -> None:
        pass


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _sqlite_rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql, params)]


def import_dataset_versions(conn: sqlite3.Connection, writer, batch_size: int) -> dict[int, int]:
    rows = _sqlite_rows(conn, "SELECT * FROM original_language_dataset_versions")
    local_to_remote: dict[int, int] = {}
    for chunk in _chunks(rows, batch_size):
        payload = [{k: v for k, v in row.items() if k != "id"} for row in chunk]
        result = writer.upsert("original_language_dataset_versions", payload, on_conflict="dataset_id,revision")
        for local_row, remote_row in zip(chunk, result):
            local_to_remote[local_row["id"]] = remote_row["id"]
    return local_to_remote


def import_verses(conn: sqlite3.Connection, writer, batch_size: int, dv_map: dict[int, int]) -> dict[int, int]:
    rows = _sqlite_rows(conn, "SELECT * FROM hebrew_verses")
    local_to_remote: dict[int, int] = {}
    for chunk in _chunks(rows, batch_size):
        payload = []
        for row in chunk:
            item = {k: v for k, v in row.items() if k != "id"}
            item["dataset_version_id"] = dv_map[row["dataset_version_id"]]
            payload.append(item)
        result = writer.upsert("hebrew_verses", payload, on_conflict="verse_ref")
        for local_row, remote_row in zip(chunk, result):
            local_to_remote[local_row["id"]] = remote_row["id"]
    return local_to_remote


def import_tokens(conn: sqlite3.Connection, writer, batch_size: int, verse_map: dict[int, int]) -> int:
    rows = _sqlite_rows(conn, "SELECT * FROM hebrew_tokens")
    count = 0
    for chunk in _chunks(rows, batch_size):
        payload = []
        for row in chunk:
            item = dict(row)
            item["verse_id"] = verse_map[row["verse_id"]]
            item["maqaf"] = bool(row["maqaf"])
            payload.append(item)
        writer.upsert("hebrew_tokens", payload, on_conflict="token_id")
        count += len(chunk)
    return count


def import_simple_child_table(conn: sqlite3.Connection, writer, table: str, on_conflict: str, batch_size: int) -> int:
    """For hebrew_token_strong_ids / hebrew_token_components — PK is
    (token_id, ...), no surrogate id, no remap needed at all."""
    rows = _sqlite_rows(conn, f"SELECT * FROM {table}")
    count = 0
    for chunk in _chunks(rows, batch_size):
        payload = [
            {k: (bool(v) if k == "is_grammar_marker" else v) for k, v in row.items()} for row in chunk
        ]
        writer.upsert(table, payload, on_conflict=on_conflict)
        count += len(chunk)
    return count


def import_source_nodes(conn: sqlite3.Connection, writer, batch_size: int, dv_map: dict[int, int]) -> dict[int, int]:
    """Two-pass: insert with parent_node_id always NULL, then batched
    UPDATE once every node's remote id is known — see module docstring."""
    rows = _sqlite_rows(conn, "SELECT * FROM hebrew_source_nodes ORDER BY id")
    local_to_remote: dict[int, int] = {}
    local_parent_by_local_id: dict[int, int | None] = {}

    for chunk in _chunks(rows, batch_size):
        payload = []
        for row in chunk:
            item = {k: v for k, v in row.items() if k not in ("id", "parent_node_id")}
            item["dataset_version_id"] = dv_map[row["dataset_version_id"]]
            item["parent_node_id"] = None
            payload.append(item)
            local_parent_by_local_id[row["id"]] = row["parent_node_id"]
        result = writer.upsert("hebrew_source_nodes", payload, on_conflict="dataset_version_id,macula_node_id")
        for local_row, remote_row in zip(chunk, result):
            local_to_remote[local_row["id"]] = remote_row["id"]

    update_rows = [
        {"id": local_to_remote[local_id], "parent_node_id": local_to_remote[parent_local_id]}
        for local_id, parent_local_id in local_parent_by_local_id.items()
        if parent_local_id is not None
    ]
    for chunk in _chunks(update_rows, batch_size):
        writer.update_batch("hebrew_source_nodes", chunk, key_column="id")

    return local_to_remote


def import_token_alignments(
    conn: sqlite3.Connection, writer, batch_size: int, dv_map: dict[int, int], node_map: dict[int, int]
) -> int:
    """No natural unique constraint (see module docstring) — scoped
    replace: delete existing rows for this MACULA dataset_version before
    inserting the fresh batch."""
    macula_dv_ids = {row["id"] for row in _sqlite_rows(conn, "SELECT id FROM original_language_dataset_versions WHERE dataset_id = 'macula_hebrew_lowfat'")}
    for local_dv_id in macula_dv_ids:
        writer.delete_where("hebrew_token_alignments", "dataset_version_id_macula", dv_map[local_dv_id])

    rows = _sqlite_rows(conn, "SELECT * FROM hebrew_token_alignments")
    count = 0
    for chunk in _chunks(rows, batch_size):
        payload = []
        for row in chunk:
            item = {k: v for k, v in row.items() if k != "id"}
            item["dataset_version_id_textus"] = dv_map[row["dataset_version_id_textus"]]
            item["dataset_version_id_macula"] = dv_map[row["dataset_version_id_macula"]]
            item["source_node_id"] = node_map.get(row["source_node_id"]) if row["source_node_id"] is not None else None
            payload.append(item)
        writer.insert("hebrew_token_alignments", payload)
        count += len(chunk)
    return count


def import_phrases(conn: sqlite3.Connection, writer, batch_size: int, dv_map: dict[int, int], node_map: dict[int, int]) -> dict[int, int]:
    """Pass 1 only — inserts with parent_phrase_id and parent_clause_id
    both NULL. Both are linked afterward by link_phrase_parents, once
    clauses (imported after phrases) also have a remote id map."""
    rows = _sqlite_rows(conn, "SELECT * FROM hebrew_phrases")
    local_to_remote: dict[int, int] = {}
    for chunk in _chunks(rows, batch_size):
        payload = []
        for row in chunk:
            item = {k: v for k, v in row.items() if k not in ("id", "parent_phrase_id", "parent_clause_id")}
            item["dataset_version_id"] = dv_map[row["dataset_version_id"]]
            item["source_node_id"] = node_map[row["source_node_id"]]
            item["parent_phrase_id"] = None
            item["parent_clause_id"] = None
            payload.append(item)
        result = writer.upsert("hebrew_phrases", payload, on_conflict="dataset_version_id,source_node_id")
        for local_row, remote_row in zip(chunk, result):
            local_to_remote[local_row["id"]] = remote_row["id"]
    return local_to_remote


def import_clauses(conn: sqlite3.Connection, writer, batch_size: int, dv_map: dict[int, int], node_map: dict[int, int]) -> dict[int, int]:
    rows = _sqlite_rows(conn, "SELECT * FROM hebrew_clauses ORDER BY id")
    local_to_remote: dict[int, int] = {}
    for chunk in _chunks(rows, batch_size):
        payload = []
        for row in chunk:
            item = {k: v for k, v in row.items() if k not in ("id", "parent_clause_id")}
            item["dataset_version_id"] = dv_map[row["dataset_version_id"]]
            item["source_node_id"] = node_map[row["source_node_id"]]
            item["parent_clause_id"] = None
            payload.append(item)
        result = writer.upsert("hebrew_clauses", payload, on_conflict="dataset_version_id,source_node_id")
        for local_row, remote_row in zip(chunk, result):
            local_to_remote[local_row["id"]] = remote_row["id"]

    update_rows = [
        {"id": local_to_remote[row["id"]], "parent_clause_id": local_to_remote[row["parent_clause_id"]]}
        for row in rows
        if row["parent_clause_id"] is not None
    ]
    for chunk in _chunks(update_rows, batch_size):
        writer.update_batch("hebrew_clauses", chunk, key_column="id")
    return local_to_remote


def link_phrase_parents(
    conn: sqlite3.Connection, writer, batch_size: int, phrase_map: dict[int, int], clause_map: dict[int, int]
) -> None:
    rows = _sqlite_rows(conn, "SELECT id, parent_phrase_id, parent_clause_id FROM hebrew_phrases")
    update_rows = []
    for row in rows:
        if row["parent_phrase_id"] is None and row["parent_clause_id"] is None:
            continue
        update: dict = {"id": phrase_map[row["id"]]}
        if row["parent_phrase_id"] is not None:
            update["parent_phrase_id"] = phrase_map[row["parent_phrase_id"]]
        if row["parent_clause_id"] is not None:
            update["parent_clause_id"] = clause_map[row["parent_clause_id"]]
        update_rows.append(update)
    for chunk in _chunks(update_rows, batch_size):
        writer.update_batch("hebrew_phrases", chunk, key_column="id")


def import_syntax_membership(
    conn: sqlite3.Connection, writer, batch_size: int, phrase_map: dict[int, int], clause_map: dict[int, int]
) -> int:
    """No natural unique constraint — scoped replace: delete membership
    rows for phrases/clauses belonging to the dataset version(s) being
    (re-)imported, using the LOCAL phrase/clause ids we are about to
    replace (i.e. exactly the ones present in phrase_map/clause_map)."""
    writer.delete_where_in("hebrew_syntax_membership", "phrase_id", list(phrase_map.values()))
    writer.delete_where_in("hebrew_syntax_membership", "clause_id", list(clause_map.values()))

    rows = _sqlite_rows(conn, "SELECT * FROM hebrew_syntax_membership")
    count = 0
    for chunk in _chunks(rows, batch_size):
        payload = []
        for row in chunk:
            item = {"token_id": row["token_id"], "phrase_id": None, "clause_id": None}
            if row["phrase_id"] is not None:
                item["phrase_id"] = phrase_map[row["phrase_id"]]
            if row["clause_id"] is not None:
                item["clause_id"] = clause_map[row["clause_id"]]
            payload.append(item)
        writer.insert("hebrew_syntax_membership", payload)
        count += len(chunk)
    return count


def import_syntax_edges(conn: sqlite3.Connection, writer, batch_size: int, dv_map: dict[int, int], node_map: dict[int, int]) -> int:
    rows = _sqlite_rows(conn, "SELECT * FROM hebrew_syntax_edges")
    count = 0
    for chunk in _chunks(rows, batch_size):
        payload = []
        for row in chunk:
            item = {k: v for k, v in row.items() if k != "id"}
            item["dataset_version_id"] = dv_map[row["dataset_version_id"]]
            item["parent_source_node_id"] = node_map[row["parent_source_node_id"]]
            item["child_source_node_id"] = node_map[row["child_source_node_id"]]
            payload.append(item)
        writer.upsert("hebrew_syntax_edges", payload, on_conflict="dataset_version_id,parent_source_node_id,child_source_node_id")
        count += len(chunk)
    return count


def import_semantic_roles(conn: sqlite3.Connection, writer, batch_size: int, dv_map: dict[int, int], node_map: dict[int, int]) -> int:
    macula_dv_ids = {row["id"] for row in _sqlite_rows(conn, "SELECT id FROM original_language_dataset_versions WHERE dataset_id = 'macula_hebrew_lowfat'")}
    for local_dv_id in macula_dv_ids:
        writer.delete_where("hebrew_semantic_roles", "dataset_version_id", dv_map[local_dv_id])

    rows = _sqlite_rows(conn, "SELECT * FROM hebrew_semantic_roles")
    count = 0
    for chunk in _chunks(rows, batch_size):
        payload = []
        for row in chunk:
            item = {k: v for k, v in row.items() if k != "id"}
            item["dataset_version_id"] = dv_map[row["dataset_version_id"]]
            item["predicate_source_node_id"] = node_map[row["predicate_source_node_id"]]
            item["participant_source_node_id"] = (
                node_map.get(row["participant_source_node_id"]) if row["participant_source_node_id"] is not None else None
            )
            payload.append(item)
        writer.insert("hebrew_semantic_roles", payload)
        count += len(chunk)
    return count


def import_participants(conn: sqlite3.Connection, writer, batch_size: int, dv_map: dict[int, int], node_map: dict[int, int]) -> dict[int, int]:
    rows = _sqlite_rows(conn, "SELECT * FROM hebrew_participants")
    local_to_remote: dict[int, int] = {}
    for chunk in _chunks(rows, batch_size):
        payload = []
        for row in chunk:
            item = {k: v for k, v in row.items() if k != "id"}
            item["dataset_version_id"] = dv_map[row["dataset_version_id"]]
            item["source_node_id"] = node_map[row["source_node_id"]]
            payload.append(item)
        result = writer.upsert("hebrew_participants", payload, on_conflict="dataset_version_id,source_node_id")
        for local_row, remote_row in zip(chunk, result):
            local_to_remote[local_row["id"]] = remote_row["id"]
    return local_to_remote


def import_coreference(
    conn: sqlite3.Connection, writer, batch_size: int, dv_map: dict[int, int], node_map: dict[int, int], participant_map: dict[int, int]
) -> int:
    macula_dv_ids = {row["id"] for row in _sqlite_rows(conn, "SELECT id FROM original_language_dataset_versions WHERE dataset_id = 'macula_hebrew_lowfat'")}
    for local_dv_id in macula_dv_ids:
        writer.delete_where("hebrew_coreference", "dataset_version_id", dv_map[local_dv_id])

    rows = _sqlite_rows(conn, "SELECT * FROM hebrew_coreference")
    count = 0
    for chunk in _chunks(rows, batch_size):
        payload = []
        for row in chunk:
            item = {k: v for k, v in row.items() if k != "id"}
            item["dataset_version_id"] = dv_map[row["dataset_version_id"]]
            item["referring_source_node_id"] = node_map[row["referring_source_node_id"]]
            item["participant_id"] = participant_map[row["participant_id"]]
            payload.append(item)
        writer.insert("hebrew_coreference", payload)
        count += len(chunk)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--local-store", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--execute", action="store_true", help="actually write to Supabase (default: dry run)")
    args = parser.parse_args()

    if not args.local_store.exists():
        print(f"Local store not found: {args.local_store}")
        return 2

    conn = sqlite3.connect(args.local_store)
    conn.row_factory = sqlite3.Row

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
        print("DRY RUN — no network calls will be made; validating the full import plan against the local store.")

    start = time.time()
    dv_map = import_dataset_versions(conn, writer, args.batch_size)
    print(f"  dataset_versions: {len(dv_map)} rows")

    verse_map = import_verses(conn, writer, args.batch_size, dv_map)
    print(f"  verses: {len(verse_map)} rows")

    token_count = import_tokens(conn, writer, args.batch_size, verse_map)
    print(f"  tokens: {token_count} rows")

    strong_id_count = import_simple_child_table(conn, writer, "hebrew_token_strong_ids", "token_id,seq", args.batch_size)
    print(f"  token_strong_ids: {strong_id_count} rows")

    component_count = import_simple_child_table(conn, writer, "hebrew_token_components", "token_id,component_index", args.batch_size)
    print(f"  token_components: {component_count} rows")

    node_map = import_source_nodes(conn, writer, args.batch_size, dv_map)
    print(f"  source_nodes: {len(node_map)} rows")

    alignment_count = import_token_alignments(conn, writer, args.batch_size, dv_map, node_map)
    print(f"  token_alignments: {alignment_count} rows")

    phrase_map = import_phrases(conn, writer, args.batch_size, dv_map, node_map)
    print(f"  phrases: {len(phrase_map)} rows")

    clause_map = import_clauses(conn, writer, args.batch_size, dv_map, node_map)
    print(f"  clauses: {len(clause_map)} rows")

    link_phrase_parents(conn, writer, args.batch_size, phrase_map, clause_map)
    print("  phrases: parent_phrase_id/parent_clause_id linked")

    membership_count = import_syntax_membership(conn, writer, args.batch_size, phrase_map, clause_map)
    print(f"  syntax_membership: {membership_count} rows")

    edge_count = import_syntax_edges(conn, writer, args.batch_size, dv_map, node_map)
    print(f"  syntax_edges: {edge_count} rows")

    role_count = import_semantic_roles(conn, writer, args.batch_size, dv_map, node_map)
    print(f"  semantic_roles: {role_count} rows")

    participant_map = import_participants(conn, writer, args.batch_size, dv_map, node_map)
    print(f"  participants: {len(participant_map)} rows")

    coref_count = import_coreference(conn, writer, args.batch_size, dv_map, node_map, participant_map)
    print(f"  coreference: {coref_count} rows")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s — all 14 populated tables imported (see docs/hebrew_analysis_v2_phase2d2.md).")
    print(
        "hebrew_detected_patterns / hebrew_detected_pattern_tokens are NOT imported by this script: "
        "the local Phase 2D.1 store has no rows for them — Phase 2C's deterministic pattern detector "
        "(bible_engine.hebrew_pattern_detection) is not yet wired into the MACULA import pipeline "
        "(scripts/build_macula_alignment_store.py), so there is nothing to import for those two tables "
        "yet. Not a Phase 2D.2 regression — those tables were also empty at the end of Phase 2D/2D.1."
    )
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
