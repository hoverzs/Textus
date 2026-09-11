"""Phase 2A §4/§5 — unit tests for the pure QA-screen/classification
functions in scripts/audit_greek_lexicon_quality.py, using small synthetic
inputs (not the full corpus — see test_greek_analysis_bundle.py and the
script's own printed report for corpus-scale numbers)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "audit_greek_lexicon_quality.py"
spec = importlib.util.spec_from_file_location("audit_greek_lexicon_quality", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)  # type: ignore[union-attr]


def _entry(**kwargs) -> SimpleNamespace:
    defaults = dict(
        strong_id="G0000", lemma="λόγος", primary_gloss="szó", senses=("szó",),
        note=None, source="test", review_status="draft",
        translation_method="ai_assisted", source_name="test", source_version="test",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _profile_entry(**kwargs) -> dict:
    defaults = {"dominant_pos": "", "dominant_lemma": "", "is_name": False}
    defaults.update(kwargs)
    return defaults


def test_qa_screen_flags_gloss_identical_to_english_source() -> None:
    entries = {"G0002": _entry(strong_id="G0002", primary_gloss="Aaron")}
    profile = {"G0002": _profile_entry(dominant_pos="tulajdonnév", dominant_lemma="Ἀαρών")}
    tbesg_gloss = {"G0002": "Aaron"}

    result = module.qa_screen(entries, profile, tbesg_gloss)

    assert result["counts"]["identical_to_english_source"] == 1


def test_qa_screen_flags_formatting_corruption() -> None:
    entries = {"G1421": _entry(strong_id="G1421", primary_gloss="kemény; nehéz  értelmez; fordít")}
    profile = {"G1421": _profile_entry(dominant_pos="melléknév", dominant_lemma="δυσερμήνευτος")}

    result = module.qa_screen(entries, profile, {})

    assert result["counts"]["formatting_corruption"] == 1


def test_qa_screen_flags_function_word_with_overlong_gloss() -> None:
    entries = {
        "G1223": _entry(strong_id="G1223", primary_gloss="egy hosszú és túl részletes körülírás itt")
    }
    profile = {"G1223": _profile_entry(dominant_pos="elöljárószó", dominant_lemma="διά")}

    result = module.qa_screen(entries, profile, {})

    assert result["counts"]["function_word_context_specific_gloss"] == 1
    assert result["counts"]["gloss_inconsistent_with_part_of_speech"] == 1


def test_qa_screen_does_not_flag_short_function_word_gloss() -> None:
    entries = {"G1063": _entry(strong_id="G1063", primary_gloss="mert")}
    profile = {"G1063": _profile_entry(dominant_pos="kötőszó", dominant_lemma="γάρ")}

    result = module.qa_screen(entries, profile, {})

    assert result["counts"]["function_word_context_specific_gloss"] == 0


def test_qa_screen_flags_empty_gloss() -> None:
    entries = {"G9999": _entry(strong_id="G9999", primary_gloss="")}
    profile = {"G9999": _profile_entry()}

    result = module.qa_screen(entries, profile, {})

    assert result["counts"]["empty_or_placeholder_gloss"] == 1


def test_qa_screen_flags_canonical_lemma_mismatch() -> None:
    entries = {"G0334": _entry(strong_id="G0334", lemma="ἀνάθημα", primary_gloss="fogadalmi ajándék")}
    profile = {"G0334": _profile_entry(dominant_pos="főnév", dominant_lemma="ἀνάθεμα")}

    result = module.qa_screen(entries, profile, {})

    assert result["counts"]["canonical_lemma_mismatch"] == 1


def test_build_strong_profile_uses_majority_vote_for_proper_name_classification() -> None:
    # A word tagged as a name in only 1 of 3 occurrences (e.g. participating
    # in a place-name construction once) must NOT be classified as a name.
    rows = [
        ("G3735", "ὄρος", "N-NSN"),  # ordinary common-noun occurrence
        ("G3735", "ὄρος", "N-NSN"),
        ("G3735", "ὄρος", "N-NSN-L"),  # one name-tagged occurrence
    ]
    profile = module.build_strong_profile(rows)

    assert profile["G3735"]["is_name"] is False


def test_build_strong_profile_classifies_predominantly_name_tagged_words_as_names() -> None:
    rows = [
        ("G2264G", "Ἡρώδης", "N-NSM-P"),
        ("G2264G", "Ἡρώδης", "N-NSM-P"),
    ]
    profile = module.build_strong_profile(rows)

    assert profile["G2264G"]["is_name"] is True


def test_priority_review_set_includes_function_words_top_frequency_and_qa_flagged() -> None:
    profile = {
        "G1063": {"dominant_pos": "kötőszó", "token_count": 100},
        "G0025": {"dominant_pos": "ige", "token_count": 50},
    }
    qa_findings = {"all_flagged_strong_ids": ["G0025"]}

    result = module.build_priority_review_set(profile, qa_findings, top_n=1)

    assert "G1063" in result["function_word_strong_ids"]
    assert result["top_frequency_strong_ids_sample"] == ["G1063"]
    assert result["qa_flagged_count"] == 1
    # G0025 isn't a function word and didn't make the top-1 frequency cut,
    # but it IS QA-flagged, so it must still be counted in the priority
    # union (the union also includes real regression-verse lexemes from
    # the live TAGNT database when present, so this only checks the floor,
    # not an exact size).
    assert result["union_priority_set_size"] >= 2
