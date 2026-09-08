"""Phase 2D.1 §13 — Hungarian lexical coverage audit, kept explicitly
SEPARATE from token/morphology/syntax alignment coverage (Phase 2D/2D.1's
own concern). Missing Hungarian gloss coverage is expected for rare
lexemes and (especially) proper/place names — this script only measures
and reports it; it does NOT generate or flag missing translations for
action.

Measures, corpus-wide, over the full committed TAHOT production database:

A. token/morphology coverage       — already 100% per Phase 2A/2B/2C (not
                                      re-measured here; see those phases'
                                      own reports).
B. MACULA syntax alignment coverage — see docs/hebrew_analysis_v2_phase2d1.md
                                      (measured separately, by the corpus
                                      alignment run itself).
C. source lexical coverage          — every token already resolves to a
                                      TBESH lexicon entry (Phase 2A/2B); not
                                      re-measured here.
D. Hungarian translation coverage   — THIS script's subject: unique corpus
                                      lexemes (Strong ids) with vs. without
                                      a Hungarian lexical record, and how
                                      many token OCCURRENCES that gap
                                      touches, broken down by whether the
                                      TBESH record itself is tagged a
                                      proper name.

Usage:
    python scripts/audit_hungarian_lexical_coverage.py --output docs/phase2d1_hungarian_lexical_coverage.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_lexicon_hu import HebrewHungarianLexiconRepository  # noqa: E402
from bible_engine.hebrew_sqlite import DEFAULT_TAHOT_DATABASE_PATH  # noqa: E402

def _is_proper_name_morph(morph: str) -> bool:
    """TBESH's own ``morph`` field marks a proper name with a trailing
    ``-P`` segment (verified: H7327/Ruth -> "N:N-F-P", H0458/Elimelech ->
    "N:N-M-P"; a common noun like H0001H -> "H:N-M", no trailing -P)."""
    return morph.split(":")[-1].split("-")[-1] == "P"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--production-db", type=Path, default=DEFAULT_TAHOT_DATABASE_PATH)
    args = parser.parse_args()

    lexicon = HebrewHungarianLexiconRepository()

    conn = sqlite3.connect(args.production_db)
    conn.row_factory = sqlite3.Row

    join_column = "token_id" if _has_column(conn, "token_strong_ids", "token_id") else "stable_token_key"
    strong_rows = conn.execute(
        f"SELECT {join_column} AS token_key, strong_id, role FROM token_strong_ids WHERE role = 't'"
    ).fetchall()

    # H9xxx Strong ids are pure grammar markers (conjunction/preposition/
    # article/pronominal-suffix/punctuation placeholders — see Phase 2C's
    # is_grammar_marker convention) — they were never meant to carry their
    # own Hungarian lexical gloss, so counting them here would misleadingly
    # inflate "missing translation" with structural markers rather than
    # real lexical gaps (rare verbs, uncommon nouns, proper/place names).
    occurrences_by_strong: Counter = Counter()
    for row in strong_rows:
        if row["strong_id"].upper().startswith("H9"):
            continue
        occurrences_by_strong[row["strong_id"]] += 1

    unique_lexemes = sorted(occurrences_by_strong)
    covered_lexemes: list[str] = []
    uncovered_lexemes: list[str] = []
    covered_occurrences = 0
    uncovered_occurrences = 0
    proper_name_uncovered_lexemes: list[str] = []
    proper_name_uncovered_occurrences = 0
    common_uncovered_occurrences = 0
    pos_breakdown: Counter = Counter()

    for strong_id in unique_lexemes:
        resolution = lexicon.lookup(strong_id)
        occurrence_count = occurrences_by_strong[strong_id]
        is_covered = resolution.entry is not None
        if is_covered:
            covered_lexemes.append(strong_id)
            covered_occurrences += occurrence_count
            continue

        uncovered_lexemes.append(strong_id)
        uncovered_occurrences += occurrence_count

        tbesh_entry = resolution.tbesh_fallback.entry if resolution.tbesh_fallback else None
        morph = (tbesh_entry.morph if tbesh_entry else "") or ""
        is_proper_name = _is_proper_name_morph(morph)
        pos_breakdown[morph or "(unknown)"] += occurrence_count
        if is_proper_name:
            proper_name_uncovered_lexemes.append(strong_id)
            proper_name_uncovered_occurrences += occurrence_count
        else:
            common_uncovered_occurrences += occurrence_count

    total_lexemes = len(unique_lexemes)
    total_occurrences = sum(occurrences_by_strong.values())

    summary = {
        "unique_corpus_lexemes": total_lexemes,
        "unique_lexemes_with_hungarian_record": len(covered_lexemes),
        "unique_lexemes_without_hungarian_record": len(uncovered_lexemes),
        "unique_lexemes_without_hungarian_record_pct": round(100 * len(uncovered_lexemes) / total_lexemes, 2) if total_lexemes else 0,
        "token_occurrences_total": total_occurrences,
        "token_occurrences_with_hungarian_meaning": covered_occurrences,
        "token_occurrences_without_hungarian_meaning": uncovered_occurrences,
        "token_occurrences_without_hungarian_meaning_pct": round(100 * uncovered_occurrences / total_occurrences, 2) if total_occurrences else 0,
        "proper_name_lexemes_without_hungarian_record": len(proper_name_uncovered_lexemes),
        "proper_name_token_occurrences_without_hungarian_meaning": proper_name_uncovered_occurrences,
        "common_word_lexemes_without_hungarian_record": len(uncovered_lexemes) - len(proper_name_uncovered_lexemes),
        "common_word_token_occurrences_without_hungarian_meaning": common_uncovered_occurrences,
        "uncovered_by_pos_top20": dict(pos_breakdown.most_common(20)),
        "sample_uncovered_lexemes": uncovered_lexemes[:50],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False)[:3000])
    print(f"\nwritten: {args.output}")
    return 0


def _has_column(connection: sqlite3.Connection, table: str, column: str) -> bool:
    return column in {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


if __name__ == "__main__":
    raise SystemExit(main())
