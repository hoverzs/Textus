"""Phase 2B.1 §2 — classifies EVERY unresolved TAGNT<->MACULA alignment
into a deterministic root-cause category. No "unknown" bucket is left
unexplained; the rarest residual is reported with concrete examples rather
than swept away.

Reads the built ``greek_syntax_dev.sqlite3`` store (for alignment status)
plus the vendored MACULA flat TSV (for verse-level pool re-inspection) and
TAGNT database (for the same).

Usage:
    python scripts/audit_greek_alignment_unresolved.py --macula-tsv PATH
        [--out PATH]
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

from bible_engine.greek_token_alignment import _morphology_compatible  # noqa: E402
from bible_engine.greek_token_repository import DEFAULT_TAGNT_DATABASE_PATH  # noqa: E402
from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path  # noqa: E402
from bible_engine.macula_greek_parser import normalize_greek_surface, parse_macula_greek_tsv  # noqa: E402
from bible_engine.tagnt_parser import GreekToken  # noqa: E402
from bible_engine.tagnt_sqlite import _clean_greek_form  # noqa: E402

DEFAULT_OUT = ROOT / "data" / "generated" / "greek_alignment_unresolved_audit.json"


def _consonant_skeleton(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


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


def classify(
    token: GreekToken,
    macula_pool: list,
    tagnt_count: int,
    macula_count: int,
    consumed_xml_ids: set[str],
) -> tuple[str, str]:
    """Returns (category, detail)."""
    if not (token.edition_flags or "").lower().count("n"):
        return "textual_variant_edition_difference", f"edition_flags={token.edition_flags}"

    if macula_count == 0:
        return "macula_missing_verse", "verse has zero MACULA tokens"

    norm_surface = normalize_greek_surface(token.greek_form)
    surface_candidates = [m for m in macula_pool if normalize_greek_surface(m.text) == norm_surface]
    if len(surface_candidates) >= 2:
        return "genuinely_ambiguous_duplicate", f"{len(surface_candidates)} identical-surface MACULA candidates in verse"

    lemma_skel = _consonant_skeleton(token.lemma)
    lemma_candidates = [m for m in macula_pool if _consonant_skeleton(m.lemma) == lemma_skel and lemma_skel]
    if lemma_candidates:
        incompatible = [m for m in lemma_candidates if not _morphology_compatible(token, m)]
        if len(incompatible) == len(lemma_candidates) and incompatible:
            return "morphology_incompatible_candidate", (
                f"{len(lemma_candidates)} same-lemma MACULA candidate(s) found, "
                f"all morphology-incompatible (TAGNT case/number vs MACULA)"
            )
        compatible = [m for m in lemma_candidates if m not in incompatible]
        if compatible and all(m.xml_id in consumed_xml_ids for m in compatible):
            return "candidate_claimed_by_another_tagnt_token", (
                f"{len(compatible)} morphology-compatible candidate(s) exist but were already "
                "consumed by another TAGNT token's alignment in this verse (a repeated common "
                "word — e.g. καί/δέ/the article — with more TAGNT occurrences than MACULA ones)"
            )

    if abs(tagnt_count - macula_count) >= 2:
        return "tokenization_segmentation_difference", (
            f"verse token counts differ: TAGNT={tagnt_count} MACULA={macula_count}"
        )

    if not lemma_candidates and not surface_candidates:
        return "macula_missing_node", "no surface or lemma candidate anywhere in the verse's MACULA pool"

    return "other_unexplained", "no deterministic rule matched"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--macula-tsv", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    store_path = resolve_default_syntax_database_path()
    if not store_path.exists():
        print(f"FAIL: syntax store not found: {store_path}")
        return 2

    macula_tokens = parse_macula_greek_tsv(args.macula_tsv)
    macula_by_verse: dict[tuple[str, int, int], list] = defaultdict(list)
    for t in macula_tokens:
        macula_by_verse[(t.book.upper(), t.chapter, t.verse)].append(t)
    for key in macula_by_verse:
        macula_by_verse[key].sort(key=lambda t: t.word_index)

    tagnt_by_verse = load_tagnt_by_verse()

    with sqlite3.connect(store_path) as connection:
        unresolved_rows = connection.execute(
            "SELECT tagnt_token_id, status FROM token_alignments "
            "WHERE status IN ('UNRESOLVED_TEXTUAL_VARIANT', 'UNRESOLVED_OTHER')"
        ).fetchall()
        resolved_rows = connection.execute(
            "SELECT tagnt_token_id, macula_xml_id FROM token_alignments WHERE macula_xml_id IS NOT NULL"
        ).fetchall()

    consumed_by_verse: dict[tuple[str, int, int], set[str]] = defaultdict(set)
    for tagnt_token_id, macula_xml_id in resolved_rows:
        book, rest = tagnt_token_id.split(".", 1)
        chapter_str, rest2 = rest.split(".", 1)
        verse_str, _word = rest2.split(":", 1)
        consumed_by_verse[(book.upper(), int(chapter_str), int(verse_str))].add(macula_xml_id)

    token_by_id: dict[str, GreekToken] = {}
    for tokens in tagnt_by_verse.values():
        for t in tokens:
            token_by_id[f"{t.book}.{t.chapter}.{t.verse}:{t.word_index}"] = t

    category_counts: Counter = Counter()
    category_examples: dict[str, list[dict]] = defaultdict(list)
    book_category_counts: dict[str, Counter] = defaultdict(Counter)

    for tagnt_token_id, status in unresolved_rows:
        token = token_by_id.get(tagnt_token_id)
        if token is None:
            category_counts["untraceable_token_id"] += 1
            continue
        verse_key = (token.book.upper(), token.chapter, token.verse)
        macula_pool = macula_by_verse.get(verse_key, [])
        tagnt_count = len(tagnt_by_verse.get(verse_key, []))
        macula_count = len(macula_pool)
        consumed = consumed_by_verse.get(verse_key, set())
        category, detail = classify(token, macula_pool, tagnt_count, macula_count, consumed)
        category_counts[category] += 1
        book_category_counts[token.book.upper()][category] += 1
        if len(category_examples[category]) < 8:
            category_examples[category].append(
                {
                    "token_id": tagnt_token_id, "surface": token.greek_form, "lemma": token.lemma,
                    "edition_flags": token.edition_flags, "detail": detail,
                }
            )

    total = sum(category_counts.values())
    report = {
        "total_unresolved": total,
        "category_counts": dict(category_counts),
        "category_percentages": {k: round(v / total * 100, 3) for k, v in category_counts.items()},
        "category_examples": category_examples,
        "book_category_counts": {book: dict(counts) for book, counts in book_category_counts.items()},
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"total unresolved tokens: {total}")
    for category, count in category_counts.most_common():
        print(f"  {category:45} {count:6}  ({count / total * 100:6.2f}%)")
    print(f"\nFull report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
