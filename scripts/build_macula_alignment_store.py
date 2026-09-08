"""Phase 2D — full-corpus offline MACULA import + alignment audit driver.

Reads every ``WLC/lowfat/*-lowfat.xml`` chapter file from a local MACULA-
Hebrew checkout (never committed to this repo — see
docs/hebrew_analysis_v2_phase2d.md §2/§17 for the pinned-tag fetch
instructions), aligns every TAHOT token against MACULA leaves, and writes
the normalized result into a local SQLite linguistic store
(``bible_engine.hebrew_linguistic_sqlite``). Produces a small,
git-committable JSON audit summary (aggregate statistics + a bounded list
of representative unresolved cases) — never the full per-token dataset.

The destination SQLite database is a large, corpus-scale artifact and is
NOT committed to git (see the Large File Policy in
docs/hebrew_analysis_v2_phase2d.md §17) — write it to a scratch/generated
path outside version control.

Usage:
    python scripts/build_macula_alignment_store.py \\
        --macula-lowfat-dir /path/to/macula-hebrew-src/WLC/lowfat \\
        --output /path/to/scratch/hebrew_macula_alignment.sqlite3 \\
        --audit-summary docs/phase2d_macula_alignment_audit.json \\
        --macula-revision 26.04.13 \\
        --macula-commit 09f8ea9e25025841ec45e2b6e7fc01595a080568
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_books import OT_BOOKS  # noqa: E402
from bible_engine.hebrew_linguistic_sqlite import open_store  # noqa: E402
from bible_engine.hebrew_macula_importer import ImportStats, ensure_dataset_version, import_chapter  # noqa: E402
from bible_engine.hebrew_token_repository import HebrewTokenRepository  # noqa: E402
from bible_engine.macula_lowfat_parser import parse_macula_lowfat_chapter  # noqa: E402

# Book code group allows a leading digit (1Sa/2Sa/1Ki/2Ki/1Ch/2Ch) — an
# earlier version of this pattern used [A-Za-z]+ only, which silently
# skipped all 167 Samuel/Kings/Chronicles chapter files as "could not
# parse chapter number" and produced a false "6 books missing from
# MACULA" finding during development. MACULA-hebrew has full 39/39 OT/
# Aramaic book coverage — see docs/hebrew_analysis_v2_phase2d.md §2.
_FILENAME_RE = re.compile(r"^\d+-([A-Za-z0-9]+)-(\d+)-lowfat\.xml$")
_BOOK_BY_UPPER = {book.tahot_code.upper(): book.tahot_code for book in OT_BOOKS}

MACULA_ATTRIBUTION = "MACULA Hebrew Linguistic Datasets, available at https://github.com/Clear-Bible/macula-hebrew/"
MACULA_LICENSE = "CC BY 4.0"
MACULA_REPOSITORY = "Clear-Bible/macula-hebrew"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--macula-lowfat-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-summary", type=Path, required=True)
    parser.add_argument("--macula-revision", default="26.04.13")
    parser.add_argument("--macula-commit", default="09f8ea9e25025841ec45e2b6e7fc01595a080568")
    parser.add_argument("--tahot-revision", default="phase2b")
    parser.add_argument("--component-fidelity-db", type=Path, default=None)
    parser.add_argument("--limit-books", type=int, default=0, help="0 = all available books")
    args = parser.parse_args()

    if not args.macula_lowfat_dir.exists():
        print(f"MACULA lowfat directory not found: {args.macula_lowfat_dir}")
        return 2

    files = sorted(args.macula_lowfat_dir.glob("*-lowfat.xml"))
    if not files:
        print(f"No *-lowfat.xml files found under {args.macula_lowfat_dir}")
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()
    store = open_store(args.output)

    textus_dv = ensure_dataset_version(
        store, dataset_id="tahot", display_name="TAHOT Hebrew/Aramaic OT", revision=args.tahot_revision,
        source_repository="STEPBible/STEPBible-Data",
        source_commit="ea47bd4c7eab7375f2dca07086ccc356e95a4128",
        license="CC BY 4.0", attribution="STEP Bible; www.STEPBible.org",
    )
    macula_dv = ensure_dataset_version(
        store, dataset_id="macula_hebrew_lowfat", display_name="MACULA Hebrew (lowfat)", revision=args.macula_revision,
        source_repository=MACULA_REPOSITORY, source_commit=args.macula_commit,
        license=MACULA_LICENSE, attribution=MACULA_ATTRIBUTION,
    )

    token_repository = HebrewTokenRepository()
    fidelity_path = str(args.component_fidelity_db) if args.component_fidelity_db else None

    totals = ImportStats()
    totals.unresolved_examples = []
    per_book: dict[str, dict] = {}
    books_seen: set[str] = set()
    hebrew_alignment_totals = {"exact": 0, "composite": 0, "validated_fallback": 0, "unresolved": 0}
    aramaic_alignment_totals = {"exact": 0, "composite": 0, "validated_fallback": 0, "unresolved": 0}
    ketiv_qere_exception_count = 0
    files_processed = 0
    files_skipped: list[str] = []

    start = time.time()
    for path in files:
        try:
            chapter = parse_macula_lowfat_chapter(path)
        except Exception as exc:  # noqa: BLE001
            files_skipped.append(f"{path.name}: parse error: {exc}")
            continue

        ref_book_code = next(
            (leaf.ref_book for sentence in chapter.sentences for leaf in sentence.leaves if leaf.ref_book), ""
        )
        tahot_code = _BOOK_BY_UPPER.get(ref_book_code)
        if tahot_code is None:
            files_skipped.append(f"{path.name}: unrecognized MACULA book code {ref_book_code!r}")
            continue

        match = _FILENAME_RE.match(path.name)
        chapter_number = int(match.group(2)) if match else 0
        if not chapter_number:
            files_skipped.append(f"{path.name}: could not parse chapter number")
            continue

        if args.limit_books and len(books_seen) >= args.limit_books and tahot_code not in books_seen:
            continue
        books_seen.add(tahot_code)

        is_aramaic_book = tahot_code in {"Ezr", "Dan"}  # coarse book-level hint; verse-level language recorded separately

        stats = import_chapter(
            chapter,
            tahot_book_code=tahot_code,
            chapter_number=chapter_number,
            store=store,
            token_repository=token_repository,
            textus_dataset_version_id=textus_dv,
            macula_dataset_version_id=macula_dv,
            component_fidelity_db_path=fidelity_path,
        )
        files_processed += 1

        book_totals = per_book.setdefault(
            tahot_code, {"verses": 0, "tokens": 0, "exact": 0, "composite": 0, "validated_fallback": 0, "unresolved": 0}
        )
        book_totals["verses"] += stats.verses_processed
        book_totals["tokens"] += stats.tokens_processed
        book_totals["exact"] += stats.exact
        book_totals["composite"] += stats.composite
        book_totals["validated_fallback"] += stats.validated_fallback
        book_totals["unresolved"] += stats.unresolved

        totals.verses_processed += stats.verses_processed
        totals.tokens_processed += stats.tokens_processed
        totals.macula_leaf_count += stats.macula_leaf_count
        totals.macula_group_count += stats.macula_group_count
        totals.exact += stats.exact
        totals.composite += stats.composite
        totals.validated_fallback += stats.validated_fallback
        totals.unresolved += stats.unresolved
        totals.phrases += stats.phrases
        totals.clauses += stats.clauses
        totals.syntax_edges += stats.syntax_edges
        totals.semantic_roles += stats.semantic_roles
        totals.participants += stats.participants
        totals.coreference += stats.coreference
        if len(totals.unresolved_examples) < 300:
            totals.unresolved_examples.extend(stats.unresolved_examples[: 300 - len(totals.unresolved_examples)])

        target = aramaic_alignment_totals if is_aramaic_book else hebrew_alignment_totals
        target["exact"] += stats.exact
        target["composite"] += stats.composite
        target["validated_fallback"] += stats.validated_fallback
        target["unresolved"] += stats.unresolved

        if files_processed % 25 == 0:
            elapsed = time.time() - start
            print(f"  ...{files_processed}/{len(files)} files, {totals.tokens_processed} tokens, {elapsed:.0f}s elapsed")

    total_alignments = totals.exact + totals.composite + totals.validated_fallback + totals.unresolved

    summary = {
        "macula_source": {
            "repository": MACULA_REPOSITORY,
            "revision_tag": args.macula_revision,
            "commit": args.macula_commit,
            "representation": "WLC/lowfat",
            "license": MACULA_LICENSE,
            "attribution": MACULA_ATTRIBUTION,
        },
        "tahot_source_revision": args.tahot_revision,
        "files_processed": files_processed,
        "files_skipped": files_skipped,
        "books_processed": sorted(books_seen),
        "books_missing_from_macula": sorted(set(b.tahot_code for b in OT_BOOKS) - books_seen),
        "verses_processed": totals.verses_processed,
        "tokens_processed": totals.tokens_processed,
        "macula_leaf_count": totals.macula_leaf_count,
        "macula_group_count": totals.macula_group_count,
        "alignment": {
            "exact": totals.exact,
            "composite": totals.composite,
            "validated_fallback": totals.validated_fallback,
            "unresolved": totals.unresolved,
            "total": total_alignments,
            "exact_pct": round(100 * totals.exact / total_alignments, 2) if total_alignments else 0,
            "composite_pct": round(100 * totals.composite / total_alignments, 2) if total_alignments else 0,
            "validated_fallback_pct": round(100 * totals.validated_fallback / total_alignments, 2) if total_alignments else 0,
            "unresolved_pct": round(100 * totals.unresolved / total_alignments, 2) if total_alignments else 0,
        },
        "alignment_by_language": {
            "hebrew_books": hebrew_alignment_totals,
            "aramaic_books": aramaic_alignment_totals,
        },
        "per_book": per_book,
        "phrases": totals.phrases,
        "clauses": totals.clauses,
        "syntax_edges": totals.syntax_edges,
        "semantic_roles": totals.semantic_roles,
        "participants": totals.participants,
        "coreference": totals.coreference,
        "unresolved_examples_sample": totals.unresolved_examples[:100],
        "elapsed_seconds": round(time.time() - start, 1),
    }

    args.audit_summary.parent.mkdir(parents=True, exist_ok=True)
    args.audit_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    store.close()

    print(f"\nfiles processed: {files_processed} ({len(files_skipped)} skipped)")
    print(f"verses: {totals.verses_processed}  tokens: {totals.tokens_processed}")
    print(f"alignment: EXACT={totals.exact} COMPOSITE={totals.composite} VALIDATED_FALLBACK={totals.validated_fallback} UNRESOLVED={totals.unresolved}")
    print(f"phrases={totals.phrases} clauses={totals.clauses} syntax_edges={totals.syntax_edges} semantic_roles={totals.semantic_roles} participants={totals.participants} coreference={totals.coreference}")
    print(f"output store: {args.output} ({args.output.stat().st_size:,} bytes)")
    print(f"audit summary: {args.audit_summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
