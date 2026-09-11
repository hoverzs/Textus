"""Phase 2A §7 — Greek-specific terminology rules.

Locks in the audit's §4/§5 terminology findings as executable assertions
against ``bible_engine.morphology_hu`` (the shared Greek/Hebrew decoder's
Greek code tables) so a future edit cannot silently reintroduce a
semantic-overreach label without a test failing.
"""

from __future__ import annotations

import sqlite3

from bible_engine.greek_token_repository import DEFAULT_TAGNT_DATABASE_PATH
from bible_engine.morphology_hu import _TENSES, _VOICES, parse_morphology_hu

import pytest

requires_tagnt = pytest.mark.skipif(
    not DEFAULT_TAGNT_DATABASE_PATH.exists(), reason="TAGNT database not built locally"
)


def test_aorist_is_not_labeled_as_universal_past_tense() -> None:
    """The aorist tense-form label must not claim "múlt idő" (past tense) —
    aorist is a tense-FORM, not inherently a temporal claim outside the
    indicative mood (audit §4.1/§5.1)."""
    label = _TENSES["A"]
    assert label == "aorisztoszi"
    assert "múlt idő" not in label
    assert "múlt" not in label


def test_imperfect_is_not_labeled_as_universal_continuous_past() -> None:
    label = _TENSES["I"]
    assert label == "imperfektum"
    assert "folyamatos múlt" not in label


def test_middle_voice_is_not_labeled_as_universally_reflexive() -> None:
    label = _VOICES["M"]
    assert label == "mediális igenem"
    assert "visszaható" not in label


def test_passive_voice_label_does_not_assert_semantic_passive_function() -> None:
    label = _VOICES["P"]
    assert label == "passzív igenem"
    # "igenem" (grammatical voice) is a morphology-form word, not
    # "szenvedő" used as a semantic-function claim.


def test_deponent_voice_forms_are_kept_distinct_from_genuine_middle_and_passive() -> None:
    """Deponent must never collapse into the same label as genuine
    middle/passive — the audit's §4.1/§4.3 mitigation depends on this
    distinction already existing at the code-table level."""
    assert _VOICES["D"] == "mediális deponens"
    assert _VOICES["O"] == "passzív deponens"
    assert _VOICES["N"] == "mediális vagy passzív deponens"
    assert _VOICES["D"] != _VOICES["M"]
    assert _VOICES["O"] != _VOICES["P"]


def test_participle_form_does_not_encode_syntactic_function() -> None:
    """A participle's decoded morphology may report tense/voice/case/number/
    gender — never an attributive/adverbial/circumstantial/substantival
    function claim, since TAGNT does not supply that fact (audit §5.1/§7)."""
    participle = parse_morphology_hu("V-AAP-NSM")
    assert participle.verb_form == "participle"
    assert participle.tense == "aorisztoszi"
    assert participle.voice == "aktív igenem"
    # No field on HungarianMorphology claims a syntactic function — this
    # assertion documents the absence explicitly, matching audit §7's "not
    # a field the source encodes" rule (see GreekMorphologyFacts.aspect
    # having the identical rationale in bible_engine.greek_analysis_bundle).
    assert not hasattr(participle, "syntactic_function")


def test_morphology_facts_never_synthesize_an_aspect_field() -> None:
    from bible_engine.greek_analysis_bundle import GreekMorphologyFacts

    facts = GreekMorphologyFacts(raw_code="V-AAI-3S", tense="aorisztoszi")
    assert facts.aspect == ""


@requires_tagnt
def test_corpus_deponent_share_is_material_not_negligible() -> None:
    """Quantitative backing for why this rule matters in practice (audit
    §4.3): deponent forms are roughly one in eight verb occurrences, not a
    rare edge case worth ignoring."""
    with sqlite3.connect(DEFAULT_TAGNT_DATABASE_PATH) as connection:
        rows = connection.execute("SELECT morph_code FROM greek_tokens").fetchall()

    deponent = 0
    total_verbs = 0
    for (morph_code,) in rows:
        morphology = parse_morphology_hu(morph_code or "")
        components = morphology.components or (morphology,)
        for component in components:
            if component.part_of_speech == "ige":
                total_verbs += 1
                if component.voice and "deponens" in component.voice:
                    deponent += 1

    assert total_verbs > 0
    share = deponent / total_verbs
    assert 0.10 <= share <= 0.15
