"""Phase 2B — builds the normalized local Greek syntax store
(``data/generated/greek_syntax_dev.sqlite3``) from:

1. The full-NT MACULA SBLGNT flat TSV (token alignment + semantic roles +
   coreference — full 27-book corpus coverage);
2. A bounded set of per-book MACULA lowfat XML files (phrase/clause
   constituent structure — see the phase doc §1 for the book-scope
   decision).

Neither raw MACULA source is vendored in this repository (too large — see
the phase doc §1); both must be supplied via ``--macula-tsv`` and
``--macula-lowfat-dir`` (a directory of ``{book}.xml`` files, book name
lowercase, matching what this script downloaded during Phase 2B — see the
phase doc for the exact download commands / URLs / commit pin used).

Usage:
    python scripts/build_greek_syntax_store.py \\
        --macula-tsv PATH/to/macula-greek-SBLGNT.tsv \\
        --macula-lowfat-dir PATH/to/lowfat_books/ \\
        [--output PATH] [--apply]

Dry-run by default (reports statistics only); --apply writes the database.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.greek_syntax_sqlite import (  # noqa: E402
    create_schema,
    insert_alignments,
    insert_coreference_links,
    insert_groups,
    insert_semantic_role_assignments,
    insert_source_nodes,
    resolve_default_syntax_database_path,
)
from bible_engine.greek_token_alignment import align_verse_tokens  # noqa: E402
from bible_engine.greek_token_repository import DEFAULT_TAGNT_DATABASE_PATH  # noqa: E402
from bible_engine.macula_greek_parser import (  # noqa: E402
    parse_macula_greek_lowfat_book,
    parse_macula_greek_tsv,
)
from bible_engine.tagnt_parser import GreekToken  # noqa: E402
from bible_engine.tagnt_sqlite import _clean_greek_form  # noqa: E402

# Books whose lowfat XML this phase downloaded — see phase doc §1 for the
# exact files/URLs/commit. Book code -> expected filename (lowercase book
# name, no accents, matching the source repo's own naming).
LOWFAT_BOOK_FILES = {
    "MAT": "matthew.xml", "MRK": "mark.xml", "LUK": "luke.xml", "JHN": "john.xml",
    "ROM": "romans.xml", "1CO": "1corinthians.xml", "PHP": "philippians.xml",
    "1TI": "1timothy.xml", "2PE": "2peter.xml",
}


def load_tagnt_by_verse() -> dict[tuple[str, int, int], list[GreekToken]]:
    with sqlite3.connect(DEFAULT_TAGNT_DATABASE_PATH) as connection:
        rows = connection.execute(
            "SELECT book, chapter, verse, word_index, greek_form, lemma, morph_code, strong_id, edition_flags "
            "FROM greek_tokens ORDER BY book, chapter, verse, word_index"
        ).fetchall()
    by_verse: dict[tuple[str, int, int], list[GreekToken]] = defaultdict(list)
    for book, chapter, verse, word_index, greek_form, lemma, morph_code, strong_id, edition_flags in rows:
        by_verse[(book.upper(), chapter, verse)].append(
            GreekToken(
                book=book, chapter=chapter, verse=verse, word_index=word_index,
                greek_form=_clean_greek_form(greek_form), lemma=lemma,
                morph_code=morph_code, strong_id=strong_id, edition_flags=edition_flags,
            )
        )
    return by_verse


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--macula-tsv", type=Path, required=True)
    parser.add_argument("--macula-lowfat-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=resolve_default_syntax_database_path())
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not args.macula_tsv.exists():
        print(f"FAIL: MACULA TSV not found: {args.macula_tsv}")
        return 2

    t0 = time.time()
    macula_tokens = parse_macula_greek_tsv(args.macula_tsv)
    print(f"parsed {len(macula_tokens)} MACULA tokens in {time.time() - t0:.2f}s")

    macula_by_verse: dict[tuple[str, int, int], list] = defaultdict(list)
    for t in macula_tokens:
        macula_by_verse[(t.book.upper(), t.chapter, t.verse)].append(t)
    for key in macula_by_verse:
        macula_by_verse[key].sort(key=lambda t: t.word_index)

    tagnt_by_verse = load_tagnt_by_verse()
    print(f"loaded {sum(len(v) for v in tagnt_by_verse.values())} TAGNT tokens")

    t0 = time.time()
    all_alignments = []
    status_counts: dict[str, int] = defaultdict(int)
    for key, tagnt_tokens in tagnt_by_verse.items():
        results = align_verse_tokens(tagnt_tokens, macula_by_verse.get(key, []))
        all_alignments.extend(results)
        for r in results:
            status_counts[r.status] += 1
    print(f"aligned {len(all_alignments)} tokens in {time.time() - t0:.2f}s")
    for status, count in sorted(status_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {status}: {count} ({count / len(all_alignments) * 100:.2f}%)")

    groups_by_book: dict[str, list] = {}
    for book, filename in LOWFAT_BOOK_FILES.items():
        path = args.macula_lowfat_dir / filename
        if not path.exists():
            print(f"  WARNING: lowfat file missing for {book}: {path}")
            continue
        groups_by_book[book] = parse_macula_greek_lowfat_book(path)
        print(f"  {book}: {len(groups_by_book[book])} phrase/clause groups")

    if not args.apply:
        print(f"\nDry run — database NOT written. Pass --apply to write to {args.output}.")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()
    with sqlite3.connect(args.output) as connection:
        create_schema(connection)
        with connection:
            insert_source_nodes(connection, macula_tokens)
            insert_alignments(connection, all_alignments)
            insert_semantic_role_assignments(connection, macula_tokens)
            insert_coreference_links(connection, macula_tokens)
            node_by_id = {t.xml_id: t for t in macula_tokens}
            for book, groups in groups_by_book.items():
                insert_groups(connection, book, groups, node_by_id)

    size = args.output.stat().st_size
    print(f"\nAPPLIED: {args.output} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
