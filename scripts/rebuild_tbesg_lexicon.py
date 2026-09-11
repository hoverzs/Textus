"""Deterministic, reproducible rebuild of the TBESG lexicon database.

Phase 2A of Greek Analysis v2. This is the authoritative rebuild path for
``data/generated/tbesg_lexicon.sqlite3`` from the vendored STEPBible source
(``data/stepbible_sources/TBESG.txt`` — see
``docs/greek_analysis_v2_phase2a_foundation.md`` for exact upstream
provenance: repo, path, commit SHA, checksum, licence).

No network access is required — the source is vendored in the repository.
The script fails loudly rather than silently when:
  - the source file is missing;
  - its checksum does not match the recorded value (unless --skip-checksum);
  - the import produces a row NOT claimed by its own canonical identity
    (impossible by construction with ``GreekLexiconEntry.canonical_strong_id``,
    but checked anyway so a future importer regression cannot silently
    reintroduce the eStrong-collision defect this rebuild fixes — see
    ``GreekLexiconEntry.canonical_strong_id``'s docstring).

It also reports insert/collision counts and a corpus lemma cross-check
against the shipped TAGNT database (when available).

Usage:
    python scripts/rebuild_tbesg_lexicon.py [--source PATH] [--output PATH]
        [--skip-checksum] [--apply]

Without --apply, builds into a temp path and reports only (dry run) — does
not touch the production database.
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
import tempfile
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.greek_lexicon_repository import DEFAULT_TBESG_DATABASE_PATH  # noqa: E402
from bible_engine.greek_token_repository import DEFAULT_TAGNT_DATABASE_PATH  # noqa: E402
from bible_engine.tbesg_parser import GreekLexiconEntry  # noqa: E402
from bible_engine.tbesg_sqlite import import_tbesg_lexicon  # noqa: E402

DEFAULT_SOURCE = ROOT / "data" / "stepbible_sources" / "TBESG.txt"

# Recorded at vendoring time — see docs/greek_analysis_v2_phase2a_foundation.md
# for the full provenance record (upstream repo/path/commit).
EXPECTED_SHA256 = "312f723d7b8ef263bbdfb0451c9b8057125804dfff390b6f8544cff2a84b57f4"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_every_row_claims_its_own_key(database_path: Path) -> list[str]:
    """Corpus-wide invariant: every stored ``strong_id`` must be a key the
    row's OWN ``dstrong_id``/eStrong data actually claims — never a key it
    merely references via ``uStrong`` (the Greek analogue of the Hebrew
    TBESH cross-reference hijack check)."""
    unclaimed: list[str] = []
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        for row in connection.execute(
            "SELECT strong_id, dstrong_id, ustrong_id FROM greek_lexicon"
        ):
            entry = GreekLexiconEntry(
                strong_id=_estrong_of(row["strong_id"]),
                dstrong_id=row["dstrong_id"] or "",
                ustrong_id=row["ustrong_id"] or "",
                greek="",
                transliteration=None,
                morph=None,
                gloss=None,
                meaning_raw=None,
            )
            if not entry.claims_strong_id(row["strong_id"]):
                unclaimed.append(row["strong_id"])
    return unclaimed


def _estrong_of(strong_id: str) -> str:
    """Base eStrong for a possibly-suffixed canonical id (``G0001G`` -> ``G0001``)."""
    import re

    match = re.fullmatch(r"(G\d{4,5})[A-Z]?", strong_id)
    return match.group(1) if match else strong_id


def lemma_mismatch_report(tbesg_path: Path, tagnt_path: Path) -> dict[str, object]:
    """Cross-check TBESG's ``lemma`` (Greek headword) against the TAGNT
    corpus's own lemma for the same Strong id, where the corpus is
    available. Mirrors ``rebuild_tbesh_lexicon.py``'s ``lemma_mismatch_report``."""

    def consonants(text: str) -> str:
        decomposed = unicodedata.normalize("NFD", text or "")
        return "".join(ch for ch in decomposed if not unicodedata.combining(ch))

    with sqlite3.connect(tagnt_path) as tagnt_connection:
        corpus_lemma_by_strong: dict[str, str] = {}
        counts: dict[str, int] = {}
        for strong_id, lemma, count in tagnt_connection.execute(
            """
            SELECT strong_id, lemma, COUNT(*)
            FROM greek_tokens
            WHERE lemma IS NOT NULL AND lemma <> ''
            GROUP BY strong_id, lemma
            """
        ):
            if count > counts.get(strong_id, 0):
                counts[strong_id] = count
                corpus_lemma_by_strong[strong_id] = lemma

    mismatches = []
    with sqlite3.connect(tbesg_path) as tbesg_connection:
        for strong_id, lemma in tbesg_connection.execute("SELECT strong_id, lemma FROM greek_lexicon"):
            corpus_lemma = corpus_lemma_by_strong.get(strong_id)
            if corpus_lemma and consonants(lemma) != consonants(corpus_lemma):
                mismatches.append((strong_id, lemma, corpus_lemma))

    return {
        "corpus_strong_ids": len(corpus_lemma_by_strong),
        "mismatches": len(mismatches),
        "examples": mismatches[:15],
    }


def build(source: Path, output: Path) -> dict[str, object]:
    report = import_tbesg_lexicon(source, output)
    with sqlite3.connect(output) as connection:
        distinct_keys = connection.execute("SELECT COUNT(*) FROM greek_lexicon").fetchone()[0]
    unclaimed = validate_every_row_claims_its_own_key(output)
    return {
        "rows_read": report.rows_read,
        "rows_imported": report.rows_imported,
        "duplicate_rows": report.duplicate_rows,
        "distinct_keys": distinct_keys,
        "unclaimed_keys": unclaimed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_TBESG_DATABASE_PATH)
    parser.add_argument("--tagnt", type=Path, default=DEFAULT_TAGNT_DATABASE_PATH)
    parser.add_argument("--skip-checksum", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Write to --output (default: dry run to a temp file)")
    args = parser.parse_args()

    if not args.source.exists():
        print(f"FAIL: source not found: {args.source}")
        print("This file is vendored in the repository — a clean clone should already have it.")
        print("If missing, re-fetch from STEPBible/STEPBible-Data (see docs/greek_analysis_v2_phase2a_foundation.md).")
        return 2

    actual_checksum = sha256_of(args.source)
    if not args.skip_checksum and actual_checksum != EXPECTED_SHA256:
        print("FAIL: source checksum mismatch.")
        print(f"  expected: {EXPECTED_SHA256}")
        print(f"  actual:   {actual_checksum}")
        print("The vendored source has changed — re-verify provenance before proceeding.")
        return 3
    print(f"source checksum OK: {actual_checksum}")

    target = args.output if args.apply else Path(tempfile.mkdtemp()) / "tbesg_lexicon_rebuild.sqlite3"
    result = build(args.source, target)

    print(f"target database          : {target}")
    print(f"rows read                : {result['rows_read']}")
    print(f"rows imported            : {result['rows_imported']}")
    print(f"duplicate (collision) rows: {result['duplicate_rows']}")
    print(f"distinct final keys      : {result['distinct_keys']}")
    print(f"unclaimed (hijacked) keys: {len(result['unclaimed_keys'])}")
    if result["unclaimed_keys"]:
        print(f"  FAIL — importer regression, keys: {result['unclaimed_keys'][:20]}")

    if args.tagnt.exists():
        report = lemma_mismatch_report(target, args.tagnt)
        print()
        print(f"corpus Strong ids checked : {report['corpus_strong_ids']}")
        print(f"lemma mismatches vs corpus: {report['mismatches']}")
        for strong_id, lemma, corpus_lemma in report["examples"]:  # type: ignore[union-attr]
            print(f"    {strong_id:<9} tbesg={lemma!r:<14} corpus={corpus_lemma!r}")
    else:
        print(f"\n(TAGNT corpus not found at {args.tagnt} — skipping lemma cross-check)")

    if not args.apply:
        print(f"\nDry run — built at {target}, production database NOT modified.")
        print("Pass --apply to write to the production path.")
    else:
        print(f"\nAPPLIED: {args.output} rebuilt.")

    return 1 if result["unclaimed_keys"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
