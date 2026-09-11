"""Phase 2B.1 §4 — full-corpus syntax-grounding status report.

Usage: python scripts/report_greek_syntax_grounding.py [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path  # noqa: E402

DEFAULT_OUT = ROOT / "data" / "generated" / "greek_syntax_grounding_report.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    store_path = resolve_default_syntax_database_path()
    if not store_path.exists():
        print(f"FAIL: syntax store not found: {store_path}")
        return 2

    conn = sqlite3.connect(store_path)
    rows = conn.execute("SELECT tagnt_token_id, status FROM token_alignments").fetchall()
    by_verse: dict[tuple[str, int, int], dict] = defaultdict(lambda: {"total": 0, "resolved": 0})
    for tagnt_token_id, status in rows:
        book, rest = tagnt_token_id.split(".", 1)
        chapter_str, rest2 = rest.split(".", 1)
        verse_str, _word = rest2.split(":", 1)
        key = (book.upper(), int(chapter_str), int(verse_str))
        by_verse[key]["total"] += 1
        if status in ("EXACT", "COMPOSITE", "VALIDATED_FALLBACK"):
            by_verse[key]["resolved"] += 1

    group_verses = set(conn.execute("SELECT DISTINCT book, chapter, verse FROM macula_groups").fetchall())

    node_verse = {
        row[0]: (row[1], row[2], row[3])
        for row in conn.execute("SELECT xml_id, book, chapter, verse FROM macula_source_nodes")
    }
    role_or_coref_verses: set[tuple[str, int, int]] = set()
    for (predicate_xml_id,) in conn.execute("SELECT predicate_xml_id FROM semantic_role_assignments"):
        v = node_verse.get(predicate_xml_id)
        if v:
            role_or_coref_verses.add(v)
    for (source_xml_id,) in conn.execute("SELECT source_xml_id FROM coreference_links"):
        v = node_verse.get(source_xml_id)
        if v:
            role_or_coref_verses.add(v)

    grounding_counts: Counter = Counter()
    book_grounding: dict[str, Counter] = defaultdict(Counter)
    for (book, chapter, verse), info in by_verse.items():
        has_group = (book, chapter, verse) in group_verses
        has_role_or_coref = (book, chapter, verse) in role_or_coref_verses
        if info["resolved"] == info["total"] and has_group:
            status = "FULLY_GROUNDED_SYNTAX"
        elif info["resolved"] > 0 and (has_group or has_role_or_coref):
            status = "PARTIALLY_GROUNDED_SYNTAX"
        else:
            status = "NO_GROUNDED_SYNTAX"
        grounding_counts[status] += 1
        book_grounding[book][status] += 1

    total_verses = sum(grounding_counts.values())
    report = {
        "total_verses": total_verses,
        "grounding_counts": dict(grounding_counts),
        "grounding_percentages": {k: round(v / total_verses * 100, 2) for k, v in grounding_counts.items()},
        "book_grounding": {book: dict(counts) for book, counts in book_grounding.items()},
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"total verses: {total_verses}")
    for status, count in grounding_counts.most_common():
        print(f"  {status}: {count} ({count / total_verses * 100:.2f}%)")
    print(f"\nFull report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
