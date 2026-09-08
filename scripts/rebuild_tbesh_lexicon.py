"""Deterministic, reproducible rebuild of the TBESH lexicon database.

Phase 2B. This is the authoritative rebuild path for
``data/generated/tbesh_lexicon_runtime.sqlite3`` from the vendored STEPBible
source (``data/stepbible_sources/TBESH.txt`` — see
``docs/hebrew_analysis_v2_phase2b.md`` for exact upstream provenance: repo,
path, commit SHA, checksum, licence).

No network access is required — the source is vendored in the repository.
The script fails loudly rather than silently when:
  - the source file is missing;
  - its checksum does not match the recorded value (unless --skip-checksum);
  - the import produces a cross-reference (hijacked) key — impossible by
    construction with the two-pass importer, but checked anyway so a future
    importer regression cannot silently reintroduce the Phase 2A defect.

It also reports the full validation surface Phase 2B's acceptance criteria
require: record counts, collisions, unresolved references, and lemma
mismatches against the shipped TAHOT corpus (when available).

Usage:
    python scripts/rebuild_tbesh_lexicon.py [--source PATH] [--output PATH]
        [--skip-checksum] [--apply]

Without --apply, builds into a temp path and reports only (dry run) — does
not touch the production database.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_sqlite import (  # noqa: E402
    DEFAULT_TAHOT_DATABASE_PATH,
    DEFAULT_TBESH_DATABASE_PATH,
    import_tbesh_lexicon_database,
)
from bible_engine.tbesh_parser import HebrewLexiconEntry  # noqa: E402

DEFAULT_SOURCE = ROOT / "data" / "stepbible_sources" / "TBESH.txt"

# Recorded at vendoring time — see docs/hebrew_analysis_v2_phase2b.md for the
# full provenance record (upstream repo/path/commit).
EXPECTED_SHA256 = "464dccadd95fd8620dd05fa0d7a4caba58ec3c4d5db3ebf38e43d046ca25b591"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_no_hijacked_keys(database_path: Path) -> list[str]:
    hijacked: list[str] = []
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        for row in connection.execute(
            "SELECT strong_id, estrong, dstrong, ustrong FROM lexicon_entries"
        ):
            entry = HebrewLexiconEntry(
                estrong=row["estrong"] or "",
                dstrong=row["dstrong"] or "",
                ustrong=row["ustrong"] or "",
                hebrew="",
                transliteration="",
                morph="",
                gloss="",
                meaning="",
            )
            if not entry.claims_strong_id(row["strong_id"]):
                hijacked.append(row["strong_id"])
    return hijacked


def lemma_mismatch_report(tbesh_path: Path, tahot_path: Path) -> dict[str, object]:
    """Cross-check TBESH hebrew field against corpus lemmas, where the
    corpus is available. Mirrors scripts/audit_hebrew_lexicon_lemma_consistency.py
    but against the raw TBESH row rather than the derived Hungarian JSON."""
    import unicodedata

    def consonants(text: str) -> str:
        decomposed = unicodedata.normalize("NFD", text or "")
        return "".join(ch for ch in decomposed if not unicodedata.combining(ch))

    with sqlite3.connect(tahot_path) as tahot_connection:
        corpus_lemma_by_strong: dict[str, str] = {}
        counts: dict[str, int] = {}
        for strong_id, lemma, count in tahot_connection.execute(
            """
            SELECT s.strong_id, t.lemma, COUNT(*)
            FROM token_strong_ids s
            JOIN tokens t ON t.token_id = s.token_id
            WHERE t.lemma IS NOT NULL AND t.lemma <> ''
            GROUP BY s.strong_id, t.lemma
            """
        ):
            if count > counts.get(strong_id, 0):
                counts[strong_id] = count
                corpus_lemma_by_strong[strong_id] = lemma

    mismatches = []
    with sqlite3.connect(tbesh_path) as tbesh_connection:
        for strong_id, hebrew in tbesh_connection.execute("SELECT strong_id, hebrew FROM lexicon_entries"):
            corpus_lemma = corpus_lemma_by_strong.get(strong_id)
            if corpus_lemma and consonants(hebrew) != consonants(corpus_lemma):
                mismatches.append((strong_id, hebrew, corpus_lemma))

    return {
        "corpus_strong_ids": len(corpus_lemma_by_strong),
        "mismatches": len(mismatches),
        "examples": mismatches[:15],
    }


def build(source: Path, output: Path) -> dict[str, object]:
    count = import_tbesh_lexicon_database(source, output)
    with sqlite3.connect(output) as connection:
        distinct_keys = connection.execute("SELECT COUNT(*) FROM lexicon_entries").fetchone()[0]
    hijacked = validate_no_hijacked_keys(output)
    return {"inserts": count, "distinct_keys": distinct_keys, "hijacked_keys": hijacked}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_TBESH_DATABASE_PATH)
    parser.add_argument("--tahot", type=Path, default=DEFAULT_TAHOT_DATABASE_PATH)
    parser.add_argument("--skip-checksum", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Write to --output (default: dry run to a temp file)")
    args = parser.parse_args()

    if not args.source.exists():
        print(f"FAIL: source not found: {args.source}")
        print("This file is vendored in the repository — a clean clone should already have it.")
        print("If missing, re-fetch from STEPBible/STEPBible-Data (see docs/hebrew_analysis_v2_phase2b.md).")
        return 2

    actual_checksum = sha256_of(args.source)
    if not args.skip_checksum and actual_checksum != EXPECTED_SHA256:
        print("FAIL: source checksum mismatch.")
        print(f"  expected: {EXPECTED_SHA256}")
        print(f"  actual:   {actual_checksum}")
        print("The vendored source has changed — re-verify provenance before proceeding.")
        return 3
    print(f"source checksum OK: {actual_checksum}")

    target = args.output if args.apply else Path(tempfile.mkdtemp()) / "tbesh_lexicon_rebuild.sqlite3"
    result = build(args.source, target)

    print(f"target database          : {target}")
    print(f"total insert operations  : {result['inserts']}")
    print(f"distinct final keys      : {result['distinct_keys']}")
    print(f"hijacked (cross-ref) keys: {len(result['hijacked_keys'])}")
    if result["hijacked_keys"]:
        print(f"  FAIL — importer regression, keys: {result['hijacked_keys'][:20]}")

    if args.tahot.exists():
        report = lemma_mismatch_report(target, args.tahot)
        print()
        print(f"corpus Strong ids checked: {report['corpus_strong_ids']}")
        print(f"lemma mismatches vs corpus: {report['mismatches']}")
        for strong_id, hebrew, corpus_lemma in report["examples"]:  # type: ignore[union-attr]
            print(f"    {strong_id:<9} tbesh={hebrew!r:<14} corpus={corpus_lemma!r}")
    else:
        print(f"\n(TAHOT corpus not found at {args.tahot} — skipping lemma cross-check)")

    if not args.apply:
        print(f"\nDry run — built at {target}, production database NOT modified.")
        print("Pass --apply to write to the production path.")
    else:
        print(f"\nAPPLIED: {args.output} rebuilt.")

    return 1 if result["hijacked_keys"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
