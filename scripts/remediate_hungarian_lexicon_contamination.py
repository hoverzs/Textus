"""Phase 2B — flag Hungarian lexicon records generated from a contaminated
TBESH source, without regenerating all 6,493 entries.

Background: the pre-Phase-2B ``tbesh_lexicon_runtime.sqlite3`` had 1,056 keys
held by a cross-reference record ("in Aramaic of", "a Name of", "combination
of", ...) that overwrote the genuine lexeme it merely pointed at (see
``docs/hebrew_analysis_v2_phase2a.md`` / ``phase2b.md``). The offline AI
translation pipeline (``hebrew_lexicon_translation_workflow.py``) ran against
that contaminated database, so 299 records in
``bible_engine/data/hebrew_lexicon_hu.json`` describe the wrong word.

Rebuilding the TBESH database (``scripts/build_hebrew_prototype_db.py`` /
``import_tbesh_lexicon_database``) from the authoritative source fixes the
ENGLISH layer. It does NOT fix the already-materialized Hungarian JSON, which
was translated at generation time and now lives independently.

This script performs the targeted, deterministic remediation the task calls
for, distinguishing SOURCE_CORRECTED (English source has since been fixed;
Hungarian record has not been regenerated) from HUMAN_REVIEWED (an actual
verified correction, review_status="reviewed" or a hand-checked fix like
H0834A in Phase 2A):

1. For every Hungarian record, compare its recorded ``lemma`` against the
   OLD (contaminated, pre-rebuild) and NEW (authoritative, post-rebuild)
   TBESH ``hebrew`` field for the same Strong id.
2. If the record's lemma matches the OLD contaminated value but the NEW
   value differs, the record was demonstrably generated from the wrong
   source. It is annotated (``warnings`` gains
   ``"source_corrected_pending_retranslation"``) — content fields are left
   UNCHANGED so the existing runtime guard
   (``HebrewHungarianLexiconRepository.lookup(expected_lemma=...)``, Phase 2A)
   keeps firing its lemma-mismatch warning at lookup time. Flagging without
   silently "fixing" the lemma is deliberate: changing lemma alone without
   retranslating base_meaning_hu would make the record LOOK consistent while
   still describing the wrong word's meaning — exactly the failure mode this
   phase exists to close.
3. Nothing is regenerated via a live LLM call. Actual retranslation is a
   separate, later, human/offline-pipeline task; this script only makes the
   299 records programmatically identifiable and keeps them from silently
   passing as trustworthy.

Usage:
    python scripts/remediate_hungarian_lexicon_contamination.py \\
        --old-tbesh OLD.sqlite3 --new-tbesh NEW.sqlite3 [--apply] [--json OUT.json]

Without --apply, only reports what WOULD change (dry run).
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

from bible_engine.hebrew_lexicon_hu import DEFAULT_HEBREW_LEXICON_HU_PATH  # noqa: E402

SOURCE_CORRECTED_WARNING = "source_corrected_pending_retranslation"


def load_hebrew_field(database_path: Path) -> dict[str, str]:
    with sqlite3.connect(database_path) as connection:
        return dict(connection.execute("SELECT strong_id, hebrew FROM lexicon_entries"))


def find_source_corrected(
    lexicon: list[dict], old_hebrew: dict[str, str], new_hebrew: dict[str, str]
) -> list[dict]:
    flagged = []
    for entry in lexicon:
        strong_id = entry["strong_id"]
        old_value = old_hebrew.get(strong_id)
        new_value = new_hebrew.get(strong_id)
        if old_value is None or new_value is None or old_value == new_value:
            continue
        if entry.get("lemma") == old_value:
            flagged.append(
                {
                    "strong_id": strong_id,
                    "old_lemma": old_value,
                    "new_lemma": new_value,
                    "base_meaning_hu": entry.get("base_meaning_hu"),
                    "already_flagged": SOURCE_CORRECTED_WARNING in entry.get("warnings", []),
                }
            )
    return flagged


def apply_flags(lexicon: list[dict], flagged_ids: set[str]) -> int:
    changed = 0
    for entry in lexicon:
        if entry["strong_id"] in flagged_ids and SOURCE_CORRECTED_WARNING not in entry.get("warnings", []):
            entry.setdefault("warnings", []).append(SOURCE_CORRECTED_WARNING)
            changed += 1
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lexicon", default=str(DEFAULT_HEBREW_LEXICON_HU_PATH))
    parser.add_argument("--old-tbesh", required=True, help="Pre-rebuild (contaminated) TBESH sqlite3")
    parser.add_argument("--new-tbesh", required=True, help="Post-rebuild (authoritative) TBESH sqlite3")
    parser.add_argument("--json", dest="json_path", default="")
    parser.add_argument("--apply", action="store_true", help="Write the flags into --lexicon (default: dry run)")
    args = parser.parse_args()

    lexicon_path = Path(args.lexicon)
    lexicon = json.loads(lexicon_path.read_text(encoding="utf-8"))
    old_hebrew = load_hebrew_field(Path(args.old_tbesh))
    new_hebrew = load_hebrew_field(Path(args.new_tbesh))

    flagged = find_source_corrected(lexicon, old_hebrew, new_hebrew)
    already = sum(1 for item in flagged if item["already_flagged"])
    new_flags = len(flagged) - already

    print(f"hungarian entries scanned      : {len(lexicon)}")
    print(f"traced to the TBESH hijack     : {len(flagged)}")
    print(f"already flagged                : {already}")
    print(f"newly flagged this run         : {new_flags}")
    print()
    for item in sorted(flagged, key=lambda x: x["strong_id"])[:20]:
        status = "already flagged" if item["already_flagged"] else "NEW"
        print(
            f"  {item['strong_id']:<9} old_lemma={item['old_lemma']!r:<14} "
            f"new_lemma={item['new_lemma']!r:<14} [{status}]"
        )

    if args.json_path:
        Path(args.json_path).write_text(json.dumps(flagged, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nWrote {args.json_path}")

    if args.apply:
        flagged_ids = {item["strong_id"] for item in flagged}
        changed = apply_flags(lexicon, flagged_ids)
        lexicon_path.write_text(json.dumps(lexicon, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nAPPLIED: {changed} records newly flagged in {lexicon_path}")
    else:
        print("\nDry run — pass --apply to write the flags.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
