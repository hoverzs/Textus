"""Phase 2E — ``request_hebrew_contextual_analysis`` service-level tests.

All calls use a mocked ``generate_fn`` — no network, no real LLM, no
Streamlit. Exercises exactly one call per request, JSON parsing (including
a fenced-code-block response, which some models wrap despite
``responseMimeType: application/json``), and the fail-closed states
(provider failure text, malformed JSON, a raising callable).
"""

from __future__ import annotations

import json

from bible_engine.hebrew_analysis_bundle import MorphologyFacts, TokenAnalysis, TokenProvenance, VerseAnalysis
from bible_engine.hebrew_analysis_repository import SYNTAX_GROUNDING_NONE
from bible_engine.hebrew_contextual_analysis_service import (
    STATUS_INVALID_RESPONSE,
    STATUS_OK,
    STATUS_UNAVAILABLE,
    request_hebrew_contextual_analysis,
)


def _token(token_id: str) -> TokenAnalysis:
    return TokenAnalysis(
        token_id=token_id, legacy_stable_key=token_id, source_token_id="", word_index=1,
        surface="x", surface_plain="x", transliteration="x", transliteration_hu="x",
        lemma="x", root=None, strong_ids=(), part_of_speech="", morphology=MorphologyFacts(raw_code="X"),
        components=(), lexical_sense=None, provenance=TokenProvenance(),
    )


def _verse() -> VerseAnalysis:
    return VerseAnalysis(
        verse_id="Gen.1.1", chapter=1, verse=1, hebrew_text="", hebrew_text_plain="",
        versification_note="", tokens=(_token("Gen.1.1:1"),), syntax_grounding=SYNTAX_GROUNDING_NONE,
    )


_VALID_JSON = json.dumps(
    {
        "word_notes": [{"token_id": "Gen.1.1:1", "lexical_basic_meaning_hu": "kezdet"}],
        "construction_notes": [],
        "syntax_summary": {},
        "translation_notes": [],
        "exegetical_notes": [],
    }
)


def test_valid_json_response_produces_ok_result_with_one_call():
    calls = []

    def fake_generate(prompt, **kwargs):
        calls.append(prompt)
        return _VALID_JSON

    result = request_hebrew_contextual_analysis(_verse(), generate_fn=fake_generate)
    assert result.status == STATUS_OK
    assert len(calls) == 1
    assert result.analysis is not None
    assert result.analysis.word_notes[0].lexical_basic_meaning_hu == "kezdet"


def test_fenced_json_response_is_unwrapped_and_parsed():
    def fake_generate(prompt, **kwargs):
        return f"```json\n{_VALID_JSON}\n```"

    result = request_hebrew_contextual_analysis(_verse(), generate_fn=fake_generate)
    assert result.status == STATUS_OK
    assert result.analysis.word_notes[0].lexical_basic_meaning_hu == "kezdet"


def test_malformed_json_returns_invalid_response_status():
    def fake_generate(prompt, **kwargs):
        return "this is not json at all {broken"

    result = request_hebrew_contextual_analysis(_verse(), generate_fn=fake_generate)
    assert result.status == STATUS_INVALID_RESPONSE
    assert result.analysis is None


def test_json_array_instead_of_object_returns_invalid_response_status():
    def fake_generate(prompt, **kwargs):
        return "[1, 2, 3]"

    result = request_hebrew_contextual_analysis(_verse(), generate_fn=fake_generate)
    assert result.status == STATUS_INVALID_RESPONSE


def test_provider_failure_marker_text_returns_unavailable():
    def fake_generate(prompt, **kwargs):
        return "⚠️ **Hiányzó API kulcs.**"

    result = request_hebrew_contextual_analysis(_verse(), generate_fn=fake_generate)
    assert result.status == STATUS_UNAVAILABLE
    assert result.analysis is None


def test_empty_response_returns_unavailable():
    def fake_generate(prompt, **kwargs):
        return ""

    result = request_hebrew_contextual_analysis(_verse(), generate_fn=fake_generate)
    assert result.status == STATUS_UNAVAILABLE


def test_raising_generate_fn_does_not_crash_and_returns_unavailable():
    def fake_generate(prompt, **kwargs):
        raise RuntimeError("network exploded")

    result = request_hebrew_contextual_analysis(_verse(), generate_fn=fake_generate)
    assert result.status == STATUS_UNAVAILABLE
    assert result.analysis is None


def test_narrow_test_double_accepting_only_prompt_positional_still_works():
    """Mirrors ``run_original_language_analysis``'s own TypeError-narrowing
    fallback for callables that don't accept the extra kwargs."""

    def fake_generate(prompt):
        return _VALID_JSON

    result = request_hebrew_contextual_analysis(
        _verse(), generate_fn=fake_generate, generate_kwargs={"tab_label": "x"}
    )
    assert result.status == STATUS_OK


def test_exactly_one_call_even_when_verse_has_multiple_tokens():
    verse = VerseAnalysis(
        verse_id="Gen.1.2", chapter=1, verse=2, hebrew_text="", hebrew_text_plain="",
        versification_note="", tokens=(_token("Gen.1.2:1"), _token("Gen.1.2:2"), _token("Gen.1.2:3")),
        syntax_grounding=SYNTAX_GROUNDING_NONE,
    )
    calls = []

    def fake_generate(prompt, **kwargs):
        calls.append(prompt)
        return json.dumps({"word_notes": [], "construction_notes": [], "syntax_summary": {}})

    request_hebrew_contextual_analysis(verse, generate_fn=fake_generate)
    assert len(calls) == 1
