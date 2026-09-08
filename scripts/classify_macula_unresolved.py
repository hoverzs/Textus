"""Phase 2D.1 — classify every remaining UNRESOLVED alignment in a built
normalized store into the fixed diagnostic taxonomy
(``bible_engine.hebrew_macula_diagnostics.CATEGORIES``), directly from the
already-stored token/alignment data (no MACULA XML re-parse needed — the
alignment evidence text and token columns already carry every signal this
classification needs).

Produces a compact, git-committable JSON: category counts, direction
sub-counts for component_segmentation_mismatch, and a bounded sample of
representative cases per category (not a full corpus dump).

Usage:
    python scripts/classify_macula_unresolved.py \\
        --store /path/to/hebrew_macula_alignment_2d1.sqlite3 \\
        --output docs/phase2d1_unresolved_taxonomy.json
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

# Reuse the EXACT same component-filtering logic the aligner itself used
# (punctuation-only / Aramaic determinative-state-suffix exclusion) so this
# classifier's "alignable component count" cannot silently drift out of
# sync with what bible_engine.hebrew_macula_alignment actually computed.
from bible_engine.hebrew_macula_alignment import is_aramaic_state_suffix, is_punctuation_only  # noqa: E402

_SUPPLIED_TEXT_WORD_INDEX_THRESHOLD = 500
_SAMPLE_LIMIT_PER_CATEGORY = 15


class _StoredComponent:
    """Minimal stand-in for HebrewComponent, built from a stored DB row —
    just enough attribute surface for is_punctuation_only/is_aramaic_state_suffix."""

    def __init__(self, role: str, surface: str) -> None:
        self.role = role
        self.surface = surface


def _alignable_component_count(conn: sqlite3.Connection, token_id: str) -> int:
    rows = conn.execute(
        "SELECT role, surface FROM hebrew_token_components WHERE token_id = ? ORDER BY component_index",
        (token_id,),
    ).fetchall()
    count = 0
    for row in rows:
        component = _StoredComponent(row["role"], row["surface"])
        if not is_punctuation_only(component.surface) and not is_aramaic_state_suffix(component):
            count += 1
    return count


def classify_row(row: sqlite3.Row, alignable_component_count: int) -> tuple[str, str]:
    """Returns (category, direction). direction is only meaningful for
    component_segmentation_mismatch."""
    if row["ketiv"] or row["qere"]:
        return "ketiv_qere", ""
    if row["word_index"] >= _SUPPLIED_TEXT_WORD_INDEX_THRESHOLD:
        return "textual_reference_numbering_gap", ""
    if alignable_component_count == 0:
        return "punctuation_non_lexical_node_difference", ""
    if row["maqaf"]:
        return "maqaf_related_segmentation", ""
    if (row["language"] or "").lower() == "aramaic":
        return "aramaic_specific_segmentation", ""

    evidence = row["evidence"] or ""
    if "no MACULA leaves found" in evidence:
        return "macula_missing_node", ""
    if "ambiguous ref-number recovery" in evidence:
        return "component_segmentation_mismatch", "ambiguous_recovery"
    if "zero corroborating" in evidence:
        # Component/leaf COUNT already matches by position (see
        # bible_engine.hebrew_macula_alignment's zero-corroboration
        # downgrade, Phase 2D.1 §10) but nothing about surface/lemma/
        # Strong id agrees — a genuine representational difference at a
        # position that is not itself in doubt, not a segmentation
        # mismatch. Real recurring sub-pattern found corpus-wide: a
        # trailing 3fs pronominal suffix (-ָה/-ּה) whose own surface
        # MACULA does not represent the same way TAHOT's suffix component
        # does (see docs/hebrew_analysis_v2_phase2d1.md §5 for examples).
        return "surface_normalization_difference", ""
    if "count mismatch" in evidence:
        import re

        match = re.search(r"TAHOT (\d+) vs MACULA (\d+)", evidence)
        if match:
            tahot_n, macula_n = int(match.group(1)), int(match.group(2))
            direction = "tahot_more" if tahot_n > macula_n else ("macula_more" if macula_n > tahot_n else "equal")
            return "component_segmentation_mismatch", direction
        return "component_segmentation_mismatch", ""
    return "unknown", ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    conn = sqlite3.connect(args.store)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT a.token_id, a.evidence, t.surface, t.word_index, t.ketiv, t.qere, t.maqaf, v.language, v.verse_ref
        FROM hebrew_token_alignments a
        JOIN hebrew_tokens t ON t.token_id = a.token_id
        JOIN hebrew_verses v ON v.id = t.verse_id
        WHERE a.alignment_type = 'UNRESOLVED'
        """
    ).fetchall()

    category_counts: Counter = Counter()
    direction_counts: Counter = Counter()
    samples: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        alignable_count = _alignable_component_count(conn, row["token_id"])
        category, direction = classify_row(row, alignable_count)
        category_counts[category] += 1
        if direction:
            direction_counts[f"{category}:{direction}"] += 1
        if len(samples[category]) < _SAMPLE_LIMIT_PER_CATEGORY:
            samples[category].append(
                {
                    "verse_ref": row["verse_ref"],
                    "token_id": row["token_id"],
                    "surface": row["surface"],
                    "word_index": row["word_index"],
                    "language": row["language"],
                    "direction": direction,
                    "evidence": row["evidence"],
                }
            )

    summary = {
        "total_unresolved": len(rows),
        "category_counts": dict(category_counts),
        "direction_counts": dict(direction_counts),
        "samples": {k: v for k, v in samples.items()},
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"total unresolved: {len(rows)}")
    for category, count in category_counts.most_common():
        print(f"  {category}: {count} ({100 * count / len(rows):.1f}%)")
    print(f"written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
