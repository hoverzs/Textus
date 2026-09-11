"""Phase 2A §11 — export the audit's 15 regression verses as static developer
fixtures (NOT expert goldens — see the "unreviewed" marker on every record).

Usage:
    python scripts/export_greek_regression_fixtures.py

Writes tests/fixtures/greek_analysis_v2_regression_verses.json.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.greek_analysis_service import get_greek_analysis  # noqa: E402

OUTPUT_PATH = ROOT / "tests" / "fixtures" / "greek_analysis_v2_regression_verses.json"

# docs/greek_analysis_v2_inventory.md §12 — Hungarian book abbreviations used
# only for the human-readable "phenomenon" label, not for lookup.
VERSES = [
    ("Jn 3,16", "ἵνα clause; aorist"),
    ("Jn 1,1", "article usage / anarthrous predicate nominative; imperfect"),
    ("Jn 1,14", "aorist; participial-construction candidate"),
    ("Jn 19,30", "perfect"),
    ("Mt 28,19-20", "chained participles + finite imperative"),
    ("Mt 9,18", "genitive absolute"),
    ("Fil 1,21", "articular infinitives"),
    ("1Kor 15,13-14", "first-class conditional chain"),
    ("Róm 5,1", "aorist passive participle (genuine passive, not deponent)"),
    ("1Tim 3,1", "middle voice, non-reflexive-but-not-passive reading"),
    ("Mk 1,9-11", "deponent aorist forms — voice-label risk case"),
    ("Róm 5,12", "difficult/disputed syntax (ἐφ' ᾧ)"),
    ("2Pt 1,1", "article + coordinated nouns (Granville-Sharp-shaped)"),
    ("Róm 3,24-25", "preposition + case chain"),
    ("Lk 10,25-37", "mixed relative clauses, participles, conditional-like constructions"),
]


def _serialize(bundle) -> dict:
    return dataclasses.asdict(bundle)


def main() -> int:
    records = []
    failures = []
    for reference, phenomenon in VERSES:
        try:
            bundle = get_greek_analysis(reference)
        except Exception as exc:  # noqa: BLE001 — report and continue
            failures.append({"reference": reference, "error": str(exc)})
            continue
        records.append(
            {
                "reference": reference,
                "phenomenon": phenomenon,
                "reviewed": False,
                "review_note": (
                    "Developer fixture only — deterministic token/morphology/"
                    "lexical data as decoded by Phase 2A tooling. NOT an "
                    "expert-verified golden. See docs/greek_analysis_v2_"
                    "phase2a_foundation.md §11."
                ),
                "bundle": _serialize(bundle),
            }
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps({"verses": records, "failures": failures}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"exported: {len(records)} verses, {len(failures)} failures")
    for failure in failures:
        print(f"  FAILED {failure['reference']}: {failure['error']}")
    print(f"written to {OUTPUT_PATH}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
