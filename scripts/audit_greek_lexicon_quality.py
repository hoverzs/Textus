"""Phase 2A — Greek Hungarian lexicon: provenance classification, automated
QA screen, and high-frequency priority review set.

Deterministic, offline, read-only against the production sources:
``data/generated/tagnt_nt.sqlite3`` (corpus), ``bible_engine/data/
lexicon_hu.json`` (Hungarian lexicon), ``data/generated/tbesg_lexicon.sqlite3``
(English source, rebuilt by scripts/rebuild_tbesg_lexicon.py).

Per the task instruction: this script NEVER rewrites a flagged entry — it
only reports counts and representative examples. Section headers below
mirror the phase brief:

  §3  classification (reviewed/manual, ai-assisted draft, missing,
      proper-name/transliteration candidate) + lexeme-entry coverage (A)
      vs corpus token-occurrence coverage (B), measured separately.
  §4  automated QA screen (heuristic problem flags).
  §5  high-frequency priority review set.

Usage:
    python scripts/audit_greek_lexicon_quality.py [--out PATH]

Writes a JSON report (default: data/generated/greek_lexicon_quality_report.json)
and prints a human-readable summary.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.lexicon_hu import load_default_hungarian_lexicon, load_strong_aliases  # noqa: E402
from bible_engine.morphology_hu import parse_morphology_hu  # noqa: E402

TAGNT_DB = ROOT / "data" / "generated" / "tagnt_nt.sqlite3"
TBESG_DB = ROOT / "data" / "generated" / "tbesg_lexicon.sqlite3"
LEXICON_HU_PATH = ROOT / "bible_engine" / "data" / "lexicon_hu.json"
DEFAULT_OUT = ROOT / "data" / "generated" / "greek_lexicon_quality_report.json"

# The 15 Phase 1 audit regression verses (docs/greek_analysis_v2_inventory.md
# §12), for the "lexemes used in the regression verses" priority set.
REGRESSION_VERSES = [
    ("Jhn", 3, 16), ("Jhn", 1, 1), ("Jhn", 1, 14), ("Jhn", 19, 30),
    ("Mat", 28, 19), ("Mat", 28, 20), ("Mat", 9, 18), ("Php", 1, 21),
    ("1Co", 15, 13), ("1Co", 15, 14), ("Rom", 5, 1), ("1Ti", 3, 1),
    ("Mrk", 1, 9), ("Mrk", 1, 10), ("Mrk", 1, 11), ("Rom", 5, 12),
    ("2Pe", 1, 1), ("Rom", 3, 24), ("Rom", 3, 25),
]

_FUNCTION_POS = {"elöljárószó", "kötőszó", "partikula", "feltételes kötőszó", "kérdő partikula"}


def load_corpus_token_rows() -> list[tuple]:
    with sqlite3.connect(TAGNT_DB) as connection:
        return connection.execute(
            "SELECT strong_id, lemma, morph_code FROM greek_tokens"
        ).fetchall()


def build_strong_profile(rows: list[tuple]) -> dict[str, dict]:
    """Per canonical strong_id: token_count, dominant lemma, dominant POS
    (Hungarian, via the shared decoder), whether any occurrence is
    proper-name-flagged."""
    profile: dict[str, dict] = {}
    for strong_id, lemma, morph_code in rows:
        entry = profile.setdefault(
            strong_id,
            {"token_count": 0, "lemmas": Counter(), "pos": Counter(), "name_tagged_tokens": 0},
        )
        entry["token_count"] += 1
        if lemma:
            entry["lemmas"][lemma] += 1
        morphology = parse_morphology_hu(morph_code or "")
        components = morphology.components or (morphology,)
        is_name_occurrence = False
        for component in components:
            if component.part_of_speech:
                entry["pos"][component.part_of_speech] += 1
            if component.name_type is not None:
                is_name_occurrence = True
        if is_name_occurrence:
            entry["name_tagged_tokens"] += 1
    for entry in profile.values():
        entry["dominant_lemma"] = entry["lemmas"].most_common(1)[0][0] if entry["lemmas"] else ""
        entry["dominant_pos"] = entry["pos"].most_common(1)[0][0] if entry["pos"] else ""
        # Majority vote, not "any occurrence": a common noun/adjective that
        # occasionally participates in a toponym (e.g. ὄρος "mountain" in
        # "Mount X") should not be classified as a proper name overall.
        entry["is_name"] = entry["name_tagged_tokens"] > entry["token_count"] / 2
    return profile


def load_tbesg_gloss_by_strong() -> dict[str, str]:
    if not TBESG_DB.exists():
        return {}
    with sqlite3.connect(TBESG_DB) as connection:
        return {
            row[0]: (row[1] or "")
            for row in connection.execute("SELECT strong_id, gloss FROM greek_lexicon")
        }


# ---------------------------------------------------------------------------
# §3 — classification + coverage (A: lexeme-entry, B: token-occurrence)
# ---------------------------------------------------------------------------


def classify_and_measure_coverage(
    profile: dict[str, dict], hu_entries: dict, aliases: dict
) -> dict:
    corpus_strong_ids = set(profile)
    total_tokens = sum(e["token_count"] for e in profile.values())

    reviewed_manual: list[str] = []
    ai_assisted_draft: list[str] = []
    missing: list[str] = []
    proper_name_candidates: list[str] = []

    covered_tokens_direct = 0
    covered_tokens_alias = 0
    uncovered_tokens = 0

    for strong_id, info in profile.items():
        entry = hu_entries.get(strong_id)
        resolved_via_alias = False
        if entry is None:
            alias = aliases.get(strong_id)
            if alias is not None:
                entry = hu_entries.get(alias.target_strong_id)
                resolved_via_alias = entry is not None

        if entry is None:
            missing.append(strong_id)
            uncovered_tokens += info["token_count"]
        elif entry.review_status == "reviewed":
            reviewed_manual.append(strong_id)
            if resolved_via_alias:
                covered_tokens_alias += info["token_count"]
            else:
                covered_tokens_direct += info["token_count"]
        else:
            ai_assisted_draft.append(strong_id)
            if resolved_via_alias:
                covered_tokens_alias += info["token_count"]
            else:
                covered_tokens_direct += info["token_count"]

        if info["is_name"]:
            proper_name_candidates.append(strong_id)

    return {
        "lexeme_entry_coverage_A": {
            "corpus_unique_lexemes": len(corpus_strong_ids),
            "reviewed_manual": len(reviewed_manual),
            "ai_assisted_draft": len(ai_assisted_draft),
            "missing": len(missing),
            "proper_name_or_transliteration_candidates": len(proper_name_candidates),
        },
        "token_occurrence_coverage_B": {
            "corpus_total_tokens": total_tokens,
            "covered_direct": covered_tokens_direct,
            "covered_via_alias": covered_tokens_alias,
            "uncovered": uncovered_tokens,
            "covered_direct_percent": round(covered_tokens_direct / total_tokens * 100, 2),
            "covered_effective_percent": round(
                (covered_tokens_direct + covered_tokens_alias) / total_tokens * 100, 2
            ),
        },
        "missing_strong_ids_sample": sorted(missing)[:25],
        "proper_name_candidates_sample": sorted(proper_name_candidates)[:25],
    }


# ---------------------------------------------------------------------------
# §4 — automated QA screen
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"^\s*(TODO|N/?A|\?+|—|-|\.\.\.)\s*$", re.IGNORECASE)
_HTML_ARTIFACT_RE = re.compile(r"<[a-zA-Z/][^>]*>|<ref=|<BR")
_STRAY_EQUALS_RE = re.compile(r"(^|\s)=(\s|$)")
_DOUBLE_SPACE_RE = re.compile(r"  +")


def qa_screen(hu_entries: dict, profile: dict, tbesg_gloss: dict) -> dict:
    findings: dict[str, list[dict]] = {
        "identical_to_english_source": [],
        "suspiciously_long_gloss": [],
        "empty_or_placeholder_gloss": [],
        "formatting_corruption": [],
        "gloss_inconsistent_with_part_of_speech": [],
        "canonical_lemma_mismatch": [],
        "proper_name_as_common_noun": [],
        "function_word_context_specific_gloss": [],
    }

    for strong_id, entry in hu_entries.items():
        gloss = (entry.primary_gloss or "").strip()
        info = profile.get(strong_id)

        if not gloss or _PLACEHOLDER_RE.match(gloss):
            findings["empty_or_placeholder_gloss"].append({"strong_id": strong_id, "gloss": gloss})
            continue

        english = tbesg_gloss.get(strong_id, "")
        if english and gloss.strip().lower() == english.strip().lower():
            findings["identical_to_english_source"].append(
                {"strong_id": strong_id, "gloss": gloss, "english": english}
            )

        word_count = len(gloss.split())
        if word_count > 6 or gloss.count(",") >= 2:
            findings["suspiciously_long_gloss"].append(
                {"strong_id": strong_id, "gloss": gloss, "word_count": word_count}
            )

        if (
            _HTML_ARTIFACT_RE.search(gloss)
            or _STRAY_EQUALS_RE.search(gloss)
            or _DOUBLE_SPACE_RE.search(gloss)
        ):
            findings["formatting_corruption"].append({"strong_id": strong_id, "gloss": gloss})

        if info is not None:
            pos = info["dominant_pos"]
            if pos in _FUNCTION_POS:
                if word_count > 2:
                    findings["function_word_context_specific_gloss"].append(
                        {"strong_id": strong_id, "gloss": gloss, "pos": pos}
                    )
                    findings["gloss_inconsistent_with_part_of_speech"].append(
                        {"strong_id": strong_id, "gloss": gloss, "pos": pos, "reason": "function word, multi-word gloss"}
                    )

            if info["is_name"] and gloss and gloss[0].islower():
                findings["proper_name_as_common_noun"].append(
                    {"strong_id": strong_id, "gloss": gloss, "lemma": entry.lemma}
                )

            corpus_lemma = info["dominant_lemma"]
            if corpus_lemma and entry.lemma:
                if _consonant_skeleton(entry.lemma) != _consonant_skeleton(corpus_lemma):
                    findings["canonical_lemma_mismatch"].append(
                        {"strong_id": strong_id, "lexicon_lemma": entry.lemma, "corpus_lemma": corpus_lemma}
                    )

    all_flagged_strong_ids = sorted(
        {item["strong_id"] for bucket in findings.values() for item in bucket}
    )
    return {
        "counts": {key: len(value) for key, value in findings.items()},
        "examples": {key: value[:12] for key, value in findings.items()},
        "all_flagged_strong_ids": all_flagged_strong_ids,
    }


def _consonant_skeleton(text: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower().strip()


# ---------------------------------------------------------------------------
# §5 — high-frequency priority review set
# ---------------------------------------------------------------------------


def build_priority_review_set(profile: dict, qa_findings: dict, top_n: int = 300) -> dict:
    function_words = sorted(
        (sid for sid, info in profile.items() if info["dominant_pos"] in _FUNCTION_POS),
        key=lambda sid: -profile[sid]["token_count"],
    )

    by_frequency = sorted(profile.items(), key=lambda kv: -kv[1]["token_count"])
    top_frequency = [sid for sid, _ in by_frequency[:top_n]]

    regression_lexemes: set[str] = set()
    if TAGNT_DB.exists():
        with sqlite3.connect(TAGNT_DB) as connection:
            for book, chapter, verse in REGRESSION_VERSES:
                for (strong_id,) in connection.execute(
                    "SELECT DISTINCT strong_id FROM greek_tokens WHERE book=? AND chapter=? AND verse=?",
                    (book, chapter, verse),
                ):
                    regression_lexemes.add(strong_id)

    qa_flagged = set(qa_findings.get("all_flagged_strong_ids", []))

    priority_set = set(function_words) | set(top_frequency) | regression_lexemes | qa_flagged
    return {
        "function_word_count": len(function_words),
        "top_frequency_count": len(top_frequency),
        "regression_verse_lexeme_count": len(regression_lexemes),
        "qa_flagged_count": len(qa_flagged),
        "union_priority_set_size": len(priority_set),
        "function_word_strong_ids": function_words,
        "top_frequency_strong_ids_sample": top_frequency[:30],
        "regression_verse_strong_ids": sorted(regression_lexemes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not TAGNT_DB.exists():
        print(f"FAIL: TAGNT database not found: {TAGNT_DB}")
        return 2

    hu_entries = load_default_hungarian_lexicon(LEXICON_HU_PATH) or {}
    aliases = load_strong_aliases()
    rows = load_corpus_token_rows()
    profile = build_strong_profile(rows)
    tbesg_gloss = load_tbesg_gloss_by_strong()

    coverage = classify_and_measure_coverage(profile, hu_entries, aliases)
    qa = qa_screen(hu_entries, profile, tbesg_gloss)
    priority = build_priority_review_set(profile, qa)

    report = {
        "coverage": coverage,
        "qa_screen": qa,
        "priority_review_set": priority,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=== §3 lexeme-entry coverage (A) ===")
    for key, value in coverage["lexeme_entry_coverage_A"].items():
        print(f"  {key}: {value}")
    print("=== §3 token-occurrence coverage (B) ===")
    for key, value in coverage["token_occurrence_coverage_B"].items():
        print(f"  {key}: {value}")
    print("=== §4 QA screen counts ===")
    for key, value in qa["counts"].items():
        print(f"  {key}: {value}")
    print("=== §5 priority review set ===")
    print(f"  function words           : {priority['function_word_count']}")
    print(f"  top-{300} by frequency     : {priority['top_frequency_count']}")
    print(f"  regression-verse lexemes : {priority['regression_verse_lexeme_count']}")
    print(f"  QA-flagged               : {priority['qa_flagged_count']}")
    print(f"  union (deduplicated)     : {priority['union_priority_set_size']}")
    print(f"\nFull report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
