"""Phase 2C — build the compact Hebrew component-fidelity store.

Restores exactly the two things the Phase 2A pruning step (see
``scripts/prune_tahot_runtime_db.py``) removed and that Phase 2B/2C's
architecture actually needs, without re-shipping the ~302 MB unpruned
full-fidelity database that made pruning necessary in the first place:

1. **Per-component surface and gloss** — the pruned production database
   (``tahot_ot_runtime.sqlite3``) reconstructs a token's prefix/core/suffix
   *split* from ``token_strong_ids`` (role + Strong id are already there),
   but the prefix/suffix **surface text** and **gloss** were dropped, and the
   reconstruction falls back to giving every component the *whole token's*
   surface and *composite* morphology code (see
   ``bible_engine.hebrew_sqlite._token_from_normalized_row``). This store
   adds the missing surface/gloss text back, keyed to the SAME integer
   ``token_id`` the production database already uses, so no other file needs
   to change shape.

   Per-component *morphology* is deliberately NOT duplicated here: it is
   already correctly and cheaply derivable at read time via
   ``decode_hebrew_morphology(token.morphology_code).components[i]``
   (verified against the authoritative STEPBible TEHMC source in Phase 2B;
   see ``bible_engine/hebrew_morphology.py``). Storing it again here would
   only add bytes for data the deterministic decoder already reconstructs
   correctly.

   Per-component *role* and *Strong id* are likewise NOT duplicated: they
   already live in the production database's ``token_strong_ids`` table
   (role codes ``p``/``c``/``s``, in insertion order via the ``seq`` column).
   This build verifies at construction time that ``token_components``
   ordered by ``component_index`` aligns exactly with the p/c/s subset of
   ``token_strong_ids`` ordered by ``seq`` for every token, so the two
   tables can be zipped together at read time without re-storing either
   field. See ``bible_engine/hebrew_component_repository.py``.

2. **Stable source token id** (e.g. ``Rut.1.1#01=L``) — the anchor Phase 2D's
   MACULA/OSHB alignment will need. It is NOT reliably reconstructible from
   the production database's own columns (measured: ~22,000 mismatches out
   of 305,635 tokens), for two reasons: word-index zero-padding is variable
   (STEPBible pads to the width the book needs, not always 2 digits — e.g.
   ``#0501``), and the Masoretic/English versification divergence notation
   (e.g. ``Gen.31.55(32.1)``, see ``hebrew_parser.py``'s versification
   comment) is resolved away by the time the production ``chapter``/``verse``
   columns are populated. This store keeps the original string.

Source: the same four official STEPBible TAHOT files already used to build
the production database (verified by checksum match against the production
database's own recorded provenance — see the assertion below), vendored
nowhere in this repository (see docs/hebrew_analysis_v2_phase2c.md for the
exact retrieval and checksums recorded when this store was built). This
script downloads nothing itself — point ``--tahot-source`` at four already-
obtained TAHOT TSV files (see docs/hebrew_analysis_v2_phase2b.md §1 for the
exact STEPBible-Data commit and retrieval method used for the sibling
TEHMC/TBESH sources).

Usage:
    python scripts/build_hebrew_component_fidelity_store.py \\
        --tahot-source "TAHOT Gen-Deu.txt" \\
        --tahot-source "TAHOT Jos-Est.txt" \\
        --tahot-source "TAHOT Job-Sng.txt" \\
        --tahot-source "TAHOT Isa-Mal.txt" \\
        --output data/generated/hebrew_component_fidelity.sqlite3
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_sqlite import (  # noqa: E402
    DEFAULT_TAHOT_DATABASE_PATH,
    import_tahot_database,
)

SOURCE_COMMIT = "ea47bd4c7eab7375f2dca07086ccc356e95a4128"
SOURCE_REPOSITORY = "STEPBible/STEPBible-Data"


def build(tahot_sources: list[Path], production_db: Path, output: Path) -> dict[str, int]:
    with tempfile.TemporaryDirectory() as tmp:
        full_fidelity_path = Path(tmp) / "tahot_full_fidelity.sqlite3"
        report = import_tahot_database(
            tahot_sources,
            full_fidelity_path,
            tbesh_source_path=None,
            dataset_name="TAHOT Hebrew/Aramaic OT component fidelity (Phase 2C)",
            source_version=f"STEPBible-Data commit {SOURCE_COMMIT}",
            require_all_books=True,
            atomic=False,
        )

        src = sqlite3.connect(full_fidelity_path)
        src.row_factory = sqlite3.Row
        prod = sqlite3.connect(production_db)
        prod.row_factory = sqlite3.Row
        prod_ids = {row["stable_token_key"]: row["token_id"] for row in prod.execute("SELECT stable_token_key, token_id FROM tokens")}

        if len(prod_ids) != report.tokens_imported:
            raise AssertionError(
                f"Token count mismatch — production has {len(prod_ids)}, "
                f"freshly-built full-fidelity has {report.tokens_imported}. "
                "The supplied TAHOT sources may not match the production database's provenance."
            )

        # Structural pre-condition this store's design depends on: verify
        # token_components (component_index order) aligns exactly with the
        # p/c/s subset of token_strong_ids (seq order) for every token, so
        # role/strong_id never need duplicating here.
        _verify_component_alignment(src, prod, prod_ids)

        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()
        out = sqlite3.connect(output)
        out.executescript(
            """
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE token_components (
                token_id INTEGER NOT NULL,
                component_index INTEGER NOT NULL,
                surface TEXT NOT NULL,
                gloss TEXT NOT NULL,
                PRIMARY KEY (token_id, component_index)
            ) WITHOUT ROWID;
            CREATE TABLE token_source_ids (
                token_id INTEGER PRIMARY KEY,
                source_token_id TEXT NOT NULL UNIQUE
            ) WITHOUT ROWID;
            """
        )

        component_rows = [
            (prod_ids[row["stable_token_key"]], row["component_index"], row["surface"], row["gloss"] or "")
            for row in src.execute("SELECT stable_token_key, component_index, surface, gloss FROM token_components")
            if row["stable_token_key"] in prod_ids
        ]
        out.executemany("INSERT INTO token_components VALUES (?,?,?,?)", component_rows)

        source_id_rows = [
            (prod_ids[row["stable_token_key"]], row["source_token_id"])
            for row in src.execute("SELECT stable_token_key, source_token_id FROM tokens")
            if row["stable_token_key"] in prod_ids and row["source_token_id"]
        ]
        out.executemany("INSERT INTO token_source_ids VALUES (?,?)", source_id_rows)

        for key, value in {
            "dataset_name": "TAHOT Hebrew/Aramaic OT component fidelity",
            "source_repository": SOURCE_REPOSITORY,
            "source_commit": SOURCE_COMMIT,
            "license": "CC BY 4.0",
            "attribution": "STEP Bible; www.STEPBible.org",
            "component_count": str(len(component_rows)),
            "token_count": str(len(source_id_rows)),
            "production_token_count": str(len(prod_ids)),
        }.items():
            out.execute("INSERT INTO metadata VALUES (?, ?)", (key, value))

        out.execute("CREATE INDEX idx_token_components_token ON token_components(token_id)")
        out.commit()
        out.execute("VACUUM")
        out.close()
        src.close()
        prod.close()

        return {
            "component_rows": len(component_rows),
            "token_source_id_rows": len(source_id_rows),
            "production_tokens": len(prod_ids),
        }


def _verify_component_alignment(src: sqlite3.Connection, prod: sqlite3.Connection, prod_ids: dict[str, int]) -> None:
    """Batch equivalent of the per-token check this replaced: for every
    token, does ``token_components`` ordered by ``component_index`` list the
    same role sequence as the p/c/s subset of ``token_strong_ids`` ordered by
    ``seq``? A single GROUP_CONCAT-over-sorted-subquery pass per side (SQLite
    resolves GROUP BY over an already-ordered stream in scan order, so the
    concatenation preserves the ORDER BY) replaces what was originally one
    Python-loop SQL round trip per token (~305,635 tokens, two queries
    each) — that version was still running, unfinished, after several
    minutes and was killed in favour of this O(1)-round-trip version.
    """
    join_column = "token_id" if _has_column(prod, "token_strong_ids", "token_id") else "stable_token_key"
    order_column = "seq" if _has_column(prod, "token_strong_ids", "seq") else "rowid"
    role_map = {"p": "prefix", "c": "core", "s": "suffix", "t": "token"}

    expected_by_key = {
        row["stable_token_key"]: row["roles"]
        for row in src.execute(
            """
            SELECT stable_token_key, GROUP_CONCAT(role, ',') AS roles FROM (
                SELECT stable_token_key, role FROM token_components
                ORDER BY stable_token_key, component_index
            )
            GROUP BY stable_token_key
            """
        )
    }

    actual_by_join_value: dict[object, str] = {}
    for row in prod.execute(
        f"""
        SELECT {join_column} AS jv, GROUP_CONCAT(role, ',') AS roles FROM (
            SELECT {join_column}, role FROM token_strong_ids
            WHERE role != 't'
            ORDER BY {join_column}, {order_column}
        )
        GROUP BY {join_column}
        """
    ):
        roles = ",".join(role_map.get(r, r) for r in row["roles"].split(",")) if row["roles"] else ""
        actual_by_join_value[row["jv"]] = roles

    mismatches = 0
    checked = 0
    for key, token_id in prod_ids.items():
        expected = expected_by_key.get(key, "")
        if not expected:
            continue  # tokens with no prefix/suffix components have nothing to align
        checked += 1
        join_value = token_id if join_column == "token_id" else key
        actual = actual_by_join_value.get(join_value, "")
        if expected != actual:
            mismatches += 1
            if mismatches <= 5:
                print(f"  alignment mismatch at {key}: components={expected} token_strong_ids={actual}")
    print(f"  alignment check: {checked} tokens with components checked, {mismatches} mismatches")
    if mismatches:
        raise AssertionError(f"{mismatches} tokens have misaligned component/token_strong_ids ordering")


def _has_column(connection: sqlite3.Connection, table: str, column: str) -> bool:
    return column in {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tahot-source", type=Path, action="append", required=True)
    parser.add_argument("--production-db", type=Path, default=DEFAULT_TAHOT_DATABASE_PATH)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    missing = [p for p in args.tahot_source if not p.exists()]
    if missing:
        print(f"Missing TAHOT source file(s): {missing}")
        return 2
    if not args.production_db.exists():
        print(f"Production TAHOT database not found: {args.production_db}")
        return 2

    result = build(args.tahot_source, args.production_db, args.output)
    print(f"component rows        : {result['component_rows']}")
    print(f"token_source_id rows   : {result['token_source_id_rows']}")
    print(f"production token count : {result['production_tokens']}")
    print(f"output                 : {args.output} ({args.output.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
