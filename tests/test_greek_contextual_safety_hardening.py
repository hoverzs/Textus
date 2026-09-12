"""Greek contextual-analysis safety hardening — closes the paraphrase-
evasion gap the live Gemini quality test found (see
docs/greek_analysis_v2_production_validation.md §8): two real model
responses avoided the literal forbidden strings ("pontszerű cselekvés",
"befejezett múlt, amelynek eredménye fennáll") while making the exact same
oversimplified grammatical claim in different words ("pontszerű eseményt",
"az eredménye a jelenben is fennáll").

This file tests ``bible_engine.greek_contextual_analysis_service``'s new
paraphrase-resistant, grammatical-category-conditioned overclaim detector
(``_token_categorical_overclaim`` / ``_construction_categorical_overclaim``)
directly through the public ``validate_and_build_contextual_analysis`` entry
point — never a mock of the detector itself, so these tests would fail if
the wiring into ``_build_word_notes``/``_build_construction_notes`` broke.

Uses the real Jn 3:16 bundle for token identity/structure, with
``dataclasses.replace`` used only to force a specific token's own
DETERMINISTIC morphology for a test case (mirrors the existing
NO_GROUNDED_SYNTAX test's own pattern in test_greek_contextual_analysis_
grounding.py) — never to fabricate syntax data.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from bible_engine.greek_analysis_service import get_greek_analysis_with_syntax
from bible_engine.greek_contextual_analysis_service import validate_and_build_contextual_analysis
from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path

requires_syntax_store = pytest.mark.skipif(
    not resolve_default_syntax_database_path().exists(), reason="greek_syntax_dev.sqlite3 not built locally"
)


@requires_syntax_store
def _jn316_verse():
    return get_greek_analysis_with_syntax("Jn 3,16").verses[0]


def _verse_with_token_morphology(verse, token_id: str, **morph_overrides):
    """Returns a new verse where `token_id`'s own morphology has the given
    fields overridden — used to deterministically exercise a grammatical
    category (aorist/middle/passive/participle/genitive/article) regardless
    of which real forms happen to occur in the fixture verse."""
    tokens = []
    for t in verse.tokens:
        if t.token_id == token_id:
            tokens.append(replace(t, morphology=replace(t.morphology, **morph_overrides)))
        else:
            tokens.append(t)
    return replace(verse, tokens=tuple(tokens))


def _word_note_result(verse, token_id: str, *, morphological_explanation_hu: str = "", contextual_meaning_hu: str = ""):
    parsed = {
        "word_notes": [{
            "token_id": token_id,
            "morphological_explanation_hu": morphological_explanation_hu,
            "contextual_meaning_hu": contextual_meaning_hu,
        }],
        "construction_notes": [], "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    note = next((n for n in analysis.word_notes if n.token_id == token_id), None)
    return note, warnings


# ---------------------------------------------------------------------------
# AORIST
# ---------------------------------------------------------------------------


@requires_syntax_store
@pytest.mark.parametrize("explanation", [
    "Az aoristos pontszerű eseményt fejez ki.",
    "Az aoristos egyszeri cselekvést jelöl.",
    # the exact paraphrase the live Gemini test produced — this is the bug being closed
    "Az aoristos itt egy lezárt, pontszerű eseményt jelöl az elbeszélésben.",
    "Ez egyszer megtörtént eseményt ír le.",
    "A cselekvés csak once-for-all action jellegű.",
])
def test_aorist_categorical_overclaim_paraphrases_rejected(explanation: str) -> None:
    # Some of these parametrized cases repeat the pre-existing literal
    # forbidden phrase (caught by the older, exact-string backstop); others
    # are genuine paraphrases only the new grammatical-category-conditioned
    # detector catches. Either detection path is acceptable here — the
    # outcome (rejected) is what matters, not which layer fired.
    verse = _verse_with_token_morphology(_jn316_verse(), "Jhn.3.16:3", tense="aorisztoszi")
    note, warnings = _word_note_result(verse, "Jhn.3.16:3", morphological_explanation_hu=explanation)
    assert note.morphological_explanation_hu == ""
    assert warnings


@requires_syntax_store
def test_aorist_live_test_paraphrase_specifically_caught_by_new_detector() -> None:
    """Isolates the NEW paraphrase-resistant detector from the older
    literal-phrase backstop: this exact sentence contains no literally-
    forbidden substring, only the paraphrase the live Gemini test produced."""
    verse = _verse_with_token_morphology(_jn316_verse(), "Jhn.3.16:3", tense="aorisztoszi")
    explanation = "Az aoristos itt egy lezárt, pontszerű eseményt jelöl az elbeszélésben."
    from bible_engine.greek_contextual_analysis_service import _text_uses_forbidden_phrase

    assert _text_uses_forbidden_phrase(explanation) is None  # confirms this isolates the new path
    note, warnings = _word_note_result(verse, "Jhn.3.16:3", morphological_explanation_hu=explanation)
    assert note.morphological_explanation_hu == ""
    assert any("aorist" in w and "paraphrase" in w for w in warnings)


@requires_syntax_store
@pytest.mark.parametrize("explanation", [
    "Az ige aoristos indicativus alakban áll.",
    "Harmadik személy, egyes szám, aorisztoszi, aktív igenem, kijelentő mód.",
    # cautious, explicitly-hedged contextual explanation — must survive
    "Az aoristos az eseményt egészben szemlélő aspektuális nézőponttal kapcsolható össze, "
    "de önmagában nem mondja meg, hogy a cselekvés egyszeri, pontszerű vagy megismételhetetlen volt.",
    "Ebben a mondatban elbeszélő funkcióban jelenik meg.",
])
def test_aorist_cautious_wording_survives(explanation: str) -> None:
    verse = _verse_with_token_morphology(_jn316_verse(), "Jhn.3.16:3", tense="aorisztoszi")
    note, warnings = _word_note_result(verse, "Jhn.3.16:3", morphological_explanation_hu=explanation)
    assert note.morphological_explanation_hu == explanation
    assert not any("aorist" in w for w in warnings)


@requires_syntax_store
def test_aorist_overclaim_phrase_does_not_trigger_on_non_aorist_token() -> None:
    """The same text is fine when the token it describes is NOT aorist —
    proves the check is grammatical-category-conditioned, not a bare
    keyword ban (task requirement: don't reject unrelated occurrences)."""
    verse = _verse_with_token_morphology(_jn316_verse(), "Jhn.3.16:3", tense="jelen idő")
    note, warnings = _word_note_result(
        verse, "Jhn.3.16:3", morphological_explanation_hu="Ez egy pontszerű eseményre utalhat máshol a szövegben."
    )
    assert note.morphological_explanation_hu != ""
    assert not any("aorist" in w for w in warnings)


# ---------------------------------------------------------------------------
# PERFECT — the second live-test paraphrase-evasion finding
# ---------------------------------------------------------------------------


@requires_syntax_store
@pytest.mark.parametrize("explanation", [
    "A perfectum azt fejezi ki, hogy egy múltbeli cselekvésnek az eredménye a jelenben is fennáll.",
    "Ez befejezett múlt, aminek a hatása fennáll.",
])
def test_perfect_categorical_overclaim_paraphrases_rejected(explanation: str) -> None:
    verse = _verse_with_token_morphology(_jn316_verse(), "Jhn.3.16:3", tense="perfectum")
    note, warnings = _word_note_result(verse, "Jhn.3.16:3", morphological_explanation_hu=explanation)
    assert note.morphological_explanation_hu == ""
    assert any("perfect" in w for w in warnings)


@requires_syntax_store
def test_perfect_bare_morphological_fact_survives() -> None:
    verse = _verse_with_token_morphology(_jn316_verse(), "Jhn.3.16:3", tense="perfectum")
    note, warnings = _word_note_result(
        verse, "Jhn.3.16:3", morphological_explanation_hu="Az ige perfectum kijelentő módban áll."
    )
    assert note.morphological_explanation_hu != ""
    assert not any("perfect" in w for w in warnings)


# ---------------------------------------------------------------------------
# MIDDLE
# ---------------------------------------------------------------------------


@requires_syntax_store
def test_middle_voice_described_as_reflexive_is_rejected() -> None:
    # "visszaható" is already in the older literal-phrase backstop too —
    # either detection path rejecting it is the required outcome.
    verse = _verse_with_token_morphology(_jn316_verse(), "Jhn.3.16:3", voice="mediális igenem")
    note, warnings = _word_note_result(
        verse, "Jhn.3.16:3", morphological_explanation_hu="A mediális igenem itt visszaható jelentésű."
    )
    assert note.morphological_explanation_hu == ""
    assert warnings


@requires_syntax_store
def test_middle_voice_subject_affectedness_explanation_survives() -> None:
    verse = _verse_with_token_morphology(_jn316_verse(), "Jhn.3.16:3", voice="mediális igenem")
    explanation = (
        "A mediális igenem itt azt jelzi, hogy az alany maga is érintett a cselekvésben, "
        "vagy a cselekvés az alany javára/érdekében történik."
    )
    note, warnings = _word_note_result(verse, "Jhn.3.16:3", morphological_explanation_hu=explanation)
    assert note.morphological_explanation_hu == explanation
    assert not any("middle" in w for w in warnings)


# ---------------------------------------------------------------------------
# PASSIVE
# ---------------------------------------------------------------------------


@requires_syntax_store
def test_deponent_morphology_asserted_as_guaranteed_semantic_passive_is_rejected() -> None:
    verse = _verse_with_token_morphology(_jn316_verse(), "Jhn.3.16:3", voice="mediális vagy passzív deponens")
    note, warnings = _word_note_result(
        verse, "Jhn.3.16:3", morphological_explanation_hu="A deponens ige itt valódi szenvedő jelentésű."
    )
    assert note.morphological_explanation_hu == ""
    assert any("passive" in w for w in warnings)


@requires_syntax_store
def test_deponent_correctly_described_as_active_in_meaning_survives() -> None:
    verse = _verse_with_token_morphology(_jn316_verse(), "Jhn.3.16:3", voice="mediális vagy passzív deponens")
    note, warnings = _word_note_result(
        verse, "Jhn.3.16:3", morphological_explanation_hu="Deponens igeként aktív jelentéssel bír."
    )
    assert note.morphological_explanation_hu != ""
    assert not any("passive" in w for w in warnings)


# ---------------------------------------------------------------------------
# PARTICIPLE
# ---------------------------------------------------------------------------


@requires_syntax_store
def test_participle_morphology_assigned_causal_function_is_rejected() -> None:
    verse = _verse_with_token_morphology(_jn316_verse(), "Jhn.3.16:3", verb_form="participle")
    note, warnings = _word_note_result(
        verse, "Jhn.3.16:3", morphological_explanation_hu="Az igenév itt egyértelműen okhatározói funkciót tölt be."
    )
    assert note.morphological_explanation_hu == ""
    assert any("participle" in w for w in warnings)


@requires_syntax_store
def test_participle_function_offered_as_alternatives_survives() -> None:
    verse = _verse_with_token_morphology(_jn316_verse(), "Jhn.3.16:3", verb_form="participle")
    explanation = "Az igenév a főige cselekvésének előzményét vagy kísérő körülményét fejezheti ki."
    note, warnings = _word_note_result(verse, "Jhn.3.16:3", morphological_explanation_hu=explanation)
    assert note.morphological_explanation_hu == explanation
    assert not any("participle" in w for w in warnings)


# ---------------------------------------------------------------------------
# GENITIVE
# ---------------------------------------------------------------------------


@requires_syntax_store
def test_genitive_case_labeled_possessive_is_rejected() -> None:
    verse = _verse_with_token_morphology(_jn316_verse(), "Jhn.3.16:3", case="birtokos eset")
    note, warnings = _word_note_result(
        verse, "Jhn.3.16:3", morphological_explanation_hu="A birtokos eset itt egyértelműen birtokviszonyt fejez ki."
    )
    assert note.morphological_explanation_hu == ""
    assert any("genitive" in w for w in warnings)


@requires_syntax_store
def test_genitive_case_bare_morphological_fact_survives() -> None:
    verse = _verse_with_token_morphology(_jn316_verse(), "Jhn.3.16:3", case="birtokos eset")
    note, warnings = _word_note_result(
        verse, "Jhn.3.16:3", morphological_explanation_hu="A főnév birtokos esetben áll."
    )
    assert note.morphological_explanation_hu != ""
    assert not any("genitive" in w for w in warnings)


# ---------------------------------------------------------------------------
# Deterministic UI usability after a rejection (task §4 — fail closed on the
# generated field only, never on the deterministic Greek analysis)
# ---------------------------------------------------------------------------


@requires_syntax_store
def test_rejected_explanation_does_not_affect_deterministic_morphology_on_the_bundle() -> None:
    verse = _verse_with_token_morphology(_jn316_verse(), "Jhn.3.16:3", tense="aorisztoszi")
    token = next(t for t in verse.tokens if t.token_id == "Jhn.3.16:3")
    _note, _warnings = _word_note_result(
        verse, "Jhn.3.16:3", morphological_explanation_hu="Az aoristos pontszerű eseményt fejez ki."
    )
    # the deterministic bundle itself is untouched by the rejection
    assert token.morphology.tense == "aorisztoszi"
    assert token.token_id == "Jhn.3.16:3"


# ---------------------------------------------------------------------------
# Construction notes — the same category rules, anchored to evidence tokens
# ---------------------------------------------------------------------------


@requires_syntax_store
def test_construction_note_categorical_overclaim_about_an_evidence_token_is_rejected() -> None:
    from bible_engine.greek_construction_detection import detect_patterns

    base_verse = _jn316_verse()
    patterns = detect_patterns(base_verse)
    hina = next((p for p in patterns if p.pattern_type == "hina_clause_marker"), None)
    assert hina is not None
    # force one of the hina clause's own tokens to aorist so the construction
    # note's evidence set includes a token this rule applies to
    verse = _verse_with_token_morphology(base_verse, hina.token_ids[0], tense="aorisztoszi")

    parsed = {
        "word_notes": [],
        "construction_notes": [{
            "evidence_ids": [hina.pattern_id],
            "construction_type": "hina_clause",
            "title_hu": "ἵνα célhatározói mellékmondat",
            "explanation_hu": "A mellékmondat igéje pontszerű eseményt fejez ki.",
        }],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.construction_notes == ()
    assert any("aorist" in w for w in warnings)


@requires_syntax_store
def test_construction_note_valid_explanation_still_accepted() -> None:
    from bible_engine.greek_construction_detection import detect_patterns

    verse = _jn316_verse()
    patterns = detect_patterns(verse)
    hina = next((p for p in patterns if p.pattern_type == "hina_clause_marker"), None)
    assert hina is not None

    parsed = {
        "word_notes": [],
        "construction_notes": [{
            "evidence_ids": [hina.pattern_id],
            "construction_type": "hina_clause",
            "title_hu": "ἵνα célhatározói mellékmondat",
            "explanation_hu": "Az ἵνα kötőszó egy célhatározói tagmondatot vezet be.",
        }],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.construction_notes) == 1
