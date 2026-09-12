"""Production correction pass — four issues confirmed in a new live Jn
3:16 run, after the first production-polish pass (see
tests/test_greek_jn316_production_polish.py):

1. "A két koordinált tagmondat (μὴ ἀπόληται ἀλλ᾽ ἔχῃ...)" — the "két
   tagmondat" (two CLAUSES) framing survived even after the first pass's
   fix, because that fix only collapsed construction_notes citing separate
   clause EVIDENCE — it never screened free TEXT saying "két tagmondat" in
   any field. This pass adds a text-pattern guard applied to every
   generated field.
2. "folyamatos, aktív cselekvés" for ὁ πιστεύων (present participle) —
   unsupported durative/persistence overreach from present-tense
   morphology alone. New categorical-overclaim rule, same architecture as
   the existing aorist/perfect/etc. rules.
3. Categorical theological claims ("κόσμος = teljes bűnös emberiség",
   "μονογενής Krisztus isteni mivoltát hangsúlyozza") presented in
   exegetical_notes without interpretive framing. New check requiring one
   of the approved framing markers for theological-shaped claims.
4. Stray backslash artifacts — traced (not guessed) by capturing real raw
   API responses and scanning every parsed field for a literal backslash:
   found ZERO in six live captures, but found a REAL, concrete gap by
   re-reading the validator itself — ``model_warnings`` (the "warnings"
   field on GreekContextualAnalysis, rendered directly in the UI's
   "Figyelmeztetések" expander) was built via ``_string_list`` alone,
   bypassing ``_truncate``/``_sanitize_generated_text`` entirely. Fixed by
   routing it through ``_truncate`` like every other generated field.
"""

from __future__ import annotations

import re

import pytest

from bible_engine.greek_analysis_service import get_greek_analysis_with_syntax
from bible_engine.greek_contextual_analysis import GREEK_CONTEXTUAL_ANALYSIS_INSTRUCTIONS
from bible_engine.greek_contextual_analysis_service import validate_and_build_contextual_analysis
from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path

requires_syntax_store = pytest.mark.skipif(
    not resolve_default_syntax_database_path().exists(), reason="greek_syntax_dev.sqlite3 not built locally"
)


@requires_syntax_store
def _jn316_verse():
    return get_greek_analysis_with_syntax("Jn 3,16").verses[0]


def _normalized(text: str) -> str:
    """Collapses the prompt's own line-wrapping so multi-word phrase
    assertions don't depend on exactly where a line happens to break."""
    return re.sub(r"\s+", " ", text)


def _word_note_result(verse, token_id: str, **fields):
    parsed = {
        "word_notes": [{"token_id": token_id, **fields}],
        "construction_notes": [], "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    note = next((n for n in analysis.word_notes if n.token_id == token_id), None)
    return note, warnings


# ---------------------------------------------------------------------------
# 1. "két tagmondat" clause-count overclaim — ALL generated fields
# ---------------------------------------------------------------------------


@requires_syntax_store
def test_word_note_calling_coordinated_predicates_two_clauses_is_rejected() -> None:
    verse = _jn316_verse()
    note, warnings = _word_note_result(
        verse, "Jhn.3.16:22",
        contextual_meaning_hu="A két tagmondat (μὴ ἀπόληται ἀλλ᾽ ἔχῃ) a cél kettősségét fejezi ki.",
    )
    assert note.contextual_meaning_hu == ""
    assert any("két tagmondat" in w for w in warnings)


@requires_syntax_store
def test_syntax_summary_calling_coordinated_predicates_two_clauses_is_rejected() -> None:
    verse = _jn316_verse()
    parsed = {
        "word_notes": [], "construction_notes": [],
        "syntax_summary": {"summary_hu": "A vers végén két mellékmondat fejezi ki a cél kettősségét."},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.syntax_summary.summary_hu == ""
    assert any("két tagmondat" in w for w in warnings)


@requires_syntax_store
def test_translation_note_calling_coordinated_predicates_two_clauses_is_dropped() -> None:
    verse = _jn316_verse()
    parsed = {
        "word_notes": [], "construction_notes": [], "syntax_summary": {},
        "translation_notes": ["A fordításban érdemes a két tagmondat ellentétét megtartani."],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.translation_notes == ()
    assert any("két tagmondat" in w for w in warnings)


@requires_syntax_store
def test_exegetical_note_calling_coordinated_predicates_two_clauses_is_dropped() -> None:
    verse = _jn316_verse()
    parsed = {
        "word_notes": [], "construction_notes": [], "syntax_summary": {},
        "exegetical_notes": ["A két tagmondat (a pusztulás elkerülése és az örök élet) egyensúlyt alkot."],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.exegetical_notes == ()
    assert any("két tagmondat" in w for w in warnings)


@requires_syntax_store
def test_model_warning_calling_coordinated_predicates_two_clauses_is_dropped() -> None:
    verse = _jn316_verse()
    parsed = {
        "word_notes": [], "construction_notes": [], "syntax_summary": {},
        "warnings": ["Figyelem: a két tagmondat között finom jelentésbeli különbség lehet."],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.warnings == ()
    assert any("két tagmondat" in w for w in warnings)


@requires_syntax_store
def test_approved_coordinated_predicate_phrasing_survives() -> None:
    verse = _jn316_verse()
    text = "Az ugyanazon ἵνα-tagmondaton belüli két koordinált állítmányról van szó (μὴ ἀπόληται, ἀλλ᾽ ἔχῃ)."
    note, warnings = _word_note_result(verse, "Jhn.3.16:22", contextual_meaning_hu=text)
    assert note.contextual_meaning_hu == text
    assert not any("két tagmondat" in w for w in warnings)


@requires_syntax_store
def test_negated_two_clauses_phrasing_survives() -> None:
    verse = _jn316_verse()
    text = "Nem két tagmondatról van szó, hanem egy tagmondaton belüli két koordinált állítmányról."
    note, warnings = _word_note_result(verse, "Jhn.3.16:22", contextual_meaning_hu=text)
    assert note.contextual_meaning_hu == text
    assert not any("két tagmondat" in w for w in warnings)


def test_prompt_states_the_guard_applies_to_all_fields() -> None:
    text = _normalized(GREEK_CONTEXTUAL_ANALYSIS_INSTRUCTIONS)
    assert "EZ A SZABÁLY MINDEN GENERÁLT" in text
    assert "az ugyanazon ἵνα-tagmondaton belüli két koordinált állítmány" in text


# ---------------------------------------------------------------------------
# 2. Present participle — no durative/persistence overreach from morphology
# ---------------------------------------------------------------------------


@requires_syntax_store
@pytest.mark.parametrize("explanation", [
    "A jelen idejű igenév folyamatos, aktív cselekvést fejez ki.",
    "Az igenév állandó hitet jelöl.",
    "Ez egy kitartó, élethosszig tartó hitet ír le.",
])
def test_present_participle_durative_faith_claim_is_rejected(explanation: str) -> None:
    verse = _jn316_verse()
    # Jhn.3.16:18 (πιστεύων) is a real present-tense participle in this verse
    note, warnings = _word_note_result(verse, "Jhn.3.16:18", morphological_explanation_hu=explanation)
    assert note.morphological_explanation_hu == ""
    assert any("present_participle_duration" in w or "paraphrase" in w for w in warnings)


@requires_syntax_store
def test_present_participle_substantival_expression_survives() -> None:
    verse = _jn316_verse()
    explanation = "A határozott névelő és a jelen idejű igenév együtt főnévi értelmű szerkezetet alkot: 'aki hisz'."
    note, warnings = _word_note_result(verse, "Jhn.3.16:18", morphological_explanation_hu=explanation)
    assert note.morphological_explanation_hu == explanation
    assert not any("present_participle_duration" in w for w in warnings)


@requires_syntax_store
def test_aorist_participle_with_durative_wording_not_caught_by_present_participle_rule() -> None:
    """Category-conditioning check: the new rule is scoped to PRESENT-tense
    participles specifically — an aorist participle is a structurally
    different case this rule does not (and should not) police."""
    from dataclasses import replace

    verse = _jn316_verse()
    token = next(t for t in verse.tokens if t.token_id == "Jhn.3.16:18")
    aorist_participle = replace(token, morphology=replace(token.morphology, tense="aorisztoszi"))
    tokens = tuple(aorist_participle if t.token_id == "Jhn.3.16:18" else t for t in verse.tokens)
    verse2 = replace(verse, tokens=tokens)
    note, warnings = _word_note_result(
        verse2, "Jhn.3.16:18", morphological_explanation_hu="Az igenév folyamatos cselekvést jelöl."
    )
    assert not any("present_participle_duration" in w for w in warnings)


def test_prompt_instructs_against_present_participle_duration_overreach() -> None:
    text = _normalized(GREEK_CONTEXTUAL_ANALYSIS_INSTRUCTIONS)
    assert "JELEN IDEJŰ IGENÉV" in text
    assert '"aki hisz" / "a hívő"' in text or "aki hisz" in text


# ---------------------------------------------------------------------------
# 3. Exegetical claims require explicit interpretive framing
# ---------------------------------------------------------------------------


@requires_syntax_store
def test_unmarked_theological_claim_in_exegetical_notes_is_dropped() -> None:
    verse = _jn316_verse()
    parsed = {
        "word_notes": [], "construction_notes": [], "syntax_summary": {},
        "exegetical_notes": ["A μονογενής kifejezés Krisztus isteni mivoltát hangsúlyozza."],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.exegetical_notes == ()
    assert any("explicit értelmezés-jelölés" in w for w in warnings)


@requires_syntax_store
@pytest.mark.parametrize("framing_prefix", [
    "Értelmezhető úgy, hogy ",
    "Az egyik lehetséges olvasat szerint ",
    "János tágabb teológiájában ",
    "Egyes magyarázók szerint ",
])
def test_theological_claim_with_interpretive_framing_survives(framing_prefix: str) -> None:
    verse = _jn316_verse()
    text = framing_prefix + "a μονογενής kifejezés Krisztus isteni mivoltát hangsúlyozza."
    parsed = {
        "word_notes": [], "construction_notes": [], "syntax_summary": {},
        "exegetical_notes": [text],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.exegetical_notes) == 1
    assert not any("explicit értelmezés-jelölés" in w for w in warnings)


@requires_syntax_store
def test_ordinary_non_theological_exegetical_note_is_not_touched() -> None:
    verse = _jn316_verse()
    text = "Az ige aoristos alakja a narratív szerkezetben a fő eseményláncot viszi előre."
    parsed = {
        "word_notes": [], "construction_notes": [], "syntax_summary": {},
        "exegetical_notes": [text],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.exegetical_notes) == 1
    assert not any("explicit értelmezés-jelölés" in w for w in warnings)


def test_prompt_requires_interpretive_framing_for_exegetical_notes() -> None:
    text = _normalized(GREEK_CONTEXTUAL_ANALYSIS_INSTRUCTIONS).lower()
    assert "exegetikai állítás vs. nyelvi tény" in text
    assert "értelmezhető úgy" in text
    assert "egyik lehetséges olvasat" in text
    assert "jános tágabb teológiájában" in text


# ---------------------------------------------------------------------------
# 4. Backslash artifacts — the real, traced gap (model_warnings)
# ---------------------------------------------------------------------------


@requires_syntax_store
def test_model_warnings_field_strips_stray_backslashes() -> None:
    """The exact live artifact representation used to prove the ORIGINAL
    sanitizer (added for word_notes/construction_notes/syntax_summary)
    works — reused here to prove the newly-fixed model_warnings field gets
    the identical treatment, closing the one field that bypassed
    ``_truncate`` entirely before this pass."""
    verse = _jn316_verse()
    dirty = 'Figyelem: ne keverd össze a \\"ἀλλ\\᾽ ἔχῃ\\" szerkezetet két önálló taggal.'
    parsed = {
        "word_notes": [], "construction_notes": [], "syntax_summary": {},
        "warnings": [dirty],
    }
    analysis, _warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.warnings) == 1
    assert "\\" not in analysis.warnings[0]
    assert "ἀλλ᾽ ἔχῃ" in analysis.warnings[0]


@requires_syntax_store
def test_model_warnings_field_is_length_capped_like_other_fields() -> None:
    verse = _jn316_verse()
    long_text = "Ez egy nagyon hosszú figyelmeztetés. " * 20
    parsed = {
        "word_notes": [], "construction_notes": [], "syntax_summary": {},
        "warnings": [long_text],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.warnings) == 1
    assert len(analysis.warnings[0]) <= 321  # _MAX_FIELD_CHARS + the "…" marker
    assert any("model_warning" in w and "levágva" in w for w in warnings)
