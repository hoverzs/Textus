"""Phase 2C — apply hand-verified Hungarian retranslations to the flagged
Hungarian lexicon records identified in Phase 2B.

Reads a batch of {strong_id: {base_meaning_hu, possible_meanings_hu,
lexical_note_hu, [proper_name: bool]}} translations, looks up each record's
CORRECTED TBESH source row (post Phase-2B rebuild) for lemma/transliteration/
language/source_gloss_en/source_note_en, and writes a fully-updated entry:

- lemma / transliteration / language: taken from the corrected TBESH row
  (deterministic, not translated);
- base_meaning_hu / possible_meanings_hu / lexical_note_hu: the supplied
  Hungarian translation;
- source_gloss_en / source_note_en: the corrected TBESH gloss/meaning,
  replacing the stale (contaminated-source) values;
- translation_method stays "ai_assisted" (this is a fresh AI-authored
  translation, explicitly not promoted to "human");
- review_status stays "draft";
- source_corrected_pending_retranslation is removed from warnings (the
  record has now actually been rebuilt from the corrected source);
- proper-name records keep/gain the "proper_name_review" warning, matching
  house style for every other proper-name entry in the file.

Records not present in the supplied batch are left untouched (including
their pending flag) — this script is applied incrementally across several
batches, and only ever touches records it has an actual translation for.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_lexicon_hu import (  # noqa: E402
    DEFAULT_HEBREW_LEXICON_HU_PATH,
    validate_hebrew_hungarian_lexicon_entry,
    HebrewHungarianLexiconEntry,
)
from bible_engine.hebrew_sqlite import DEFAULT_TBESH_DATABASE_PATH  # noqa: E402

FLAG = "source_corrected_pending_retranslation"


def load_tbesh() -> dict[str, dict]:
    with sqlite3.connect(DEFAULT_TBESH_DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row
        return {
            row["strong_id"]: dict(row)
            for row in connection.execute(
                "SELECT strong_id, hebrew, transliteration, gloss, meaning, language FROM lexicon_entries"
            )
        }


def apply_batch(translations: dict[str, dict], *, lexicon_path: Path = DEFAULT_HEBREW_LEXICON_HU_PATH) -> dict:
    tbesh = load_tbesh()
    lexicon = json.loads(lexicon_path.read_text(encoding="utf-8"))
    by_id = {e["strong_id"]: e for e in lexicon}

    applied = []
    missing_from_lexicon = []
    missing_from_tbesh = []

    for strong_id, translation in translations.items():
        entry = by_id.get(strong_id)
        if entry is None:
            missing_from_lexicon.append(strong_id)
            continue
        tbesh_row = tbesh.get(strong_id)
        if tbesh_row is None:
            missing_from_tbesh.append(strong_id)
            continue

        entry["lemma"] = tbesh_row["hebrew"]
        entry["transliteration"] = tbesh_row["transliteration"]
        entry["language"] = tbesh_row["language"] or entry.get("language", "")
        entry["base_meaning_hu"] = translation["base_meaning_hu"]
        entry["possible_meanings_hu"] = translation["possible_meanings_hu"]
        entry["lexical_note_hu"] = translation["lexical_note_hu"]
        entry["source_gloss_en"] = tbesh_row["gloss"]
        entry["source_note_en"] = tbesh_row["meaning"]
        entry["translation_method"] = "ai_assisted"
        entry["review_status"] = "draft"
        entry["source"] = "STEPBible TBESH alapján készített magyar munkaváltozat (Phase 2C újrafordítás)"

        warnings = [w for w in entry.get("warnings", []) if w != FLAG]
        if translation.get("proper_name") and "proper_name_review" not in warnings:
            warnings.append("proper_name_review")
        entry["warnings"] = warnings

        # Re-validate through the same schema check the offline import
        # pipeline uses, so a malformed batch entry fails loudly here rather
        # than silently corrupting the production file.
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
        applied.append(strong_id)

    lexicon_path.write_text(json.dumps(lexicon, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "applied": applied,
        "missing_from_lexicon": missing_from_lexicon,
        "missing_from_tbesh": missing_from_tbesh,
    }
