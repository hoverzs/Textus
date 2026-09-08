"""Phase 2C — finalize the "content already valid" subset of the 443
Phase-2B-flagged Hungarian lexicon records.

Of the 443 records flagged ``source_corrected_pending_retranslation``, 98
were identified (see docs/hebrew_analysis_v2_phase2c.md, the same
gloss-similarity + lemma-consonant test used to split the 443 originally)
as cases where the CONTENT is still valid: the corrected TBESH source's
English gloss is unchanged or near-identical to the one the existing
Hungarian was translated from, and the lemma's consonantal skeleton is
identical (the difference between old and new TBESH is only pointing/
cantillation, or a wording refinement with the same sense).

For these records no retranslation is needed or performed. This script
only refreshes the DETERMINISTIC fields (lemma, transliteration, language,
source_gloss_en, source_note_en) from the corrected TBESH row and removes
the now-resolved flag — the Hungarian base_meaning_hu / possible_meanings_hu
/ lexical_note_hu are left byte-for-byte untouched.

Usage:
    python scripts/finalize_equivalent_lexicon_records.py --ids-json PATH
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_lexicon_hu import (  # noqa: E402
    DEFAULT_HEBREW_LEXICON_HU_PATH,
    HebrewHungarianLexiconEntry,
    validate_hebrew_hungarian_lexicon_entry,
)
from bible_engine.hebrew_sqlite import DEFAULT_TBESH_DATABASE_PATH  # noqa: E402

FLAG = "source_corrected_pending_retranslation"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids-json", required=True, help="JSON list of strong_ids to finalize")
    parser.add_argument("--lexicon", default=str(DEFAULT_HEBREW_LEXICON_HU_PATH))
    args = parser.parse_args()

    target_ids = set(json.loads(Path(args.ids_json).read_text(encoding="utf-8")))

    with sqlite3.connect(DEFAULT_TBESH_DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row
        tbesh = {
            row["strong_id"]: dict(row)
            for row in connection.execute(
                "SELECT strong_id, hebrew, transliteration, gloss, meaning, language FROM lexicon_entries"
            )
        }

    lexicon_path = Path(args.lexicon)
    lexicon = json.loads(lexicon_path.read_text(encoding="utf-8"))

    finalized = []
    for entry in lexicon:
        if entry["strong_id"] not in target_ids:
            continue
        tbesh_row = tbesh[entry["strong_id"]]
        entry["lemma"] = tbesh_row["hebrew"]
        entry["transliteration"] = tbesh_row["transliteration"]
        entry["language"] = tbesh_row["language"] or entry.get("language", "")
        entry["source_gloss_en"] = tbesh_row["gloss"]
        entry["source_note_en"] = tbesh_row["meaning"]
        entry["warnings"] = [w for w in entry.get("warnings", []) if w != FLAG]

        candidate = HebrewHungarianLexiconEntry(
            strong_id=entry["strong_id"],
            lemma=entry["lemma"],
            transliteration=entry["transliteration"],
            language=entry["language"],
            base_meaning_hu=entry["base_meaning_hu"],
            possible_meanings_hu=tuple(entry["possible_meanings_hu"]),
            lexical_note_hu=entry["lexical_note_hu"],
            source_gloss_en=entry["source_gloss_en"],
            source_note_en=entry["source_note_en"],
            translation_method=entry["translation_method"],
            review_status=entry["review_status"],
            source=entry["source"],
            source_record_id=entry["source_record_id"],
            aliases=tuple(entry.get("aliases", ())),
            warnings=tuple(entry["warnings"]),
        )
        validate_hebrew_hungarian_lexicon_entry(candidate)
        finalized.append(entry["strong_id"])

    lexicon_path.write_text(json.dumps(lexicon, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"finalized (deterministic fields refreshed, flag removed): {len(finalized)}")
    missing = target_ids - set(finalized)
    if missing:
        print(f"WARNING — requested ids not found in lexicon: {sorted(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
