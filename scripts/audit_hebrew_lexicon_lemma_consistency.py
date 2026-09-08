"""Detect Hungarian lexicon records whose lemma disagrees with the corpus.

Phase 2A. The אֲשֶׁר defect was not a translation slip: TBESH cross-reference
rows ("in Aramaic of", "a Name of", "a Spelling of", "combination of", ...) were
indexed under the Strong id of the lexeme they merely point at, so the Hungarian
batch pipeline translated the WRONG source record. See
``HebrewLexiconEntry.identity_strong_ids``.

This audit finds the remaining contamination mechanically, without reviewing
6493 records by hand: for each Hungarian record it compares the stored ``lemma``
against the lemma that TAHOT actually assigns to the tokens carrying that Strong
id. A mismatch means the Hungarian record almost certainly describes a different
word from the one users will click.

Consonantal comparison is used (vowel points and cantillation stripped), so
pointing differences alone are not reported.

Usage:
    python scripts/audit_hebrew_lexicon_lemma_consistency.py [--json OUT.json] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_lexicon_hu import (  # noqa: E402
    DEFAULT_HEBREW_LEXICON_HU_PATH,
    load_hebrew_hungarian_lexicon,
)
from bible_engine.hebrew_sqlite import (  # noqa: E402
    DEFAULT_TAHOT_DATABASE_PATH,
    DEFAULT_TBESH_DATABASE_PATH,
)
from bible_engine.tbesh_parser import HebrewLexiconEntry  # noqa: E402


def consonants(text: str) -> str:
    """Strip Hebrew points/accents so only the consonantal skeleton remains."""
    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).replace("־", "").strip()


def corpus_lemmas(database_path: Path) -> dict[str, Counter[str]]:
    """Map Strong id -> Counter of TAHOT lemmas for the tokens carrying it."""
    by_strong: dict[str, Counter[str]] = defaultdict(Counter)
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT s.strong_id, t.lemma, COUNT(*)
            FROM token_strong_ids s
            JOIN tokens t ON t.token_id = s.token_id
            GROUP BY s.strong_id, t.lemma
            """
        )
        for strong_id, lemma, count in rows:
            if lemma:
                by_strong[strong_id][lemma] += count
    return by_strong


def cross_reference_keys(database_path: Path) -> dict[str, str]:
    """Strong ids whose TBESH row is a cross-reference rather than the lexeme."""
    hijacked: dict[str, str] = {}
    if not database_path.exists():
        return hijacked
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        for row in connection.execute(
            "SELECT strong_id, estrong, dstrong, ustrong, hebrew, gloss FROM lexicon_entries"
        ):
            entry = HebrewLexiconEntry(
                estrong=row["estrong"] or "",
                dstrong=row["dstrong"] or "",
                ustrong=row["ustrong"] or "",
                hebrew=row["hebrew"] or "",
                transliteration="",
                morph="",
                gloss=row["gloss"] or "",
                meaning="",
            )
            if not entry.claims_strong_id(row["strong_id"]):
                hijacked[row["strong_id"]] = entry.dstrong
    return hijacked


def build_report(
    lexicon_path: Path, tahot_path: Path, tbesh_path: Path, limit: int
) -> dict[str, object]:
    entries = load_hebrew_hungarian_lexicon(lexicon_path)
    lemmas = corpus_lemmas(tahot_path)
    hijacked = cross_reference_keys(tbesh_path)

    mismatches: list[dict[str, object]] = []
    checked = 0
    unused = 0
    for strong_id, entry in entries.items():
        corpus = lemmas.get(strong_id)
        if not corpus:
            unused += 1
            continue
        checked += 1
        dominant, dominant_count = corpus.most_common(1)[0]
        if consonants(entry.lemma) == consonants(dominant):
            continue
        mismatches.append(
            {
                "strong_id": strong_id,
                "hungarian_lemma": entry.lemma,
                "corpus_lemma": dominant,
                "corpus_tokens": dominant_count,
                "base_meaning_hu": entry.base_meaning_hu,
                "review_status": entry.review_status,
                "translation_method": entry.translation_method,
                "tbesh_cross_reference": hijacked.get(strong_id, ""),
            }
        )

    mismatches.sort(key=lambda item: -int(item["corpus_tokens"]))
    affected_tokens = sum(int(item["corpus_tokens"]) for item in mismatches)
    from_cross_reference = sum(1 for item in mismatches if item["tbesh_cross_reference"])
    return {
        "hungarian_entries": len(entries),
        "entries_used_by_corpus": checked,
        "entries_not_used_by_corpus": unused,
        "lemma_mismatches": len(mismatches),
        "affected_corpus_tokens": affected_tokens,
        "mismatches_explained_by_tbesh_cross_reference": from_cross_reference,
        "tbesh_cross_reference_keys": len(hijacked),
        "examples": mismatches[:limit],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lexicon", default=str(DEFAULT_HEBREW_LEXICON_HU_PATH))
    parser.add_argument("--tahot", default=str(DEFAULT_TAHOT_DATABASE_PATH))
    parser.add_argument("--tbesh", default=str(DEFAULT_TBESH_DATABASE_PATH))
    parser.add_argument("--json", dest="json_path", default="")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    tahot_path = Path(args.tahot)
    if not tahot_path.exists():
        print(f"Hebrew database not found: {tahot_path}")
        return 2

    report = build_report(Path(args.lexicon), tahot_path, Path(args.tbesh), args.limit)

    print(f"hungarian entries                     : {report['hungarian_entries']}")
    print(f"entries actually used by the corpus   : {report['entries_used_by_corpus']}")
    print(f"lemma mismatches                      : {report['lemma_mismatches']}")
    print(f"corpus tokens behind those mismatches : {report['affected_corpus_tokens']}")
    print(f"explained by TBESH cross-reference    : {report['mismatches_explained_by_tbesh_cross_reference']}")
    print(f"TBESH cross-reference keys in total   : {report['tbesh_cross_reference_keys']}")
    print("\nworst offenders (by corpus frequency):")
    for item in report["examples"]:  # type: ignore[union-attr]
        print(
            f"  {item['strong_id']:<9} {item['corpus_tokens']:>6}  "
            f"corpus={item['corpus_lemma']:<12} hu={item['hungarian_lemma']:<12} "
            f"base={item['base_meaning_hu']!r}"
        )

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nWrote {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
