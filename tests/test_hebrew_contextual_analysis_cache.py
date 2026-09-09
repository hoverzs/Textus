"""Phase 2E — ``HebrewContextualAnalysisCache`` and
``get_or_request_hebrew_contextual_analysis`` tests.

Proves the core Phase 2E performance/cost claim: ONE verse-level AI call
serves every subsequent word-click and verse-summary render for that verse,
as long as the dataset version, prompt version and model stay the same.
"""

from __future__ import annotations

import json

from bible_engine.hebrew_analysis_bundle import MorphologyFacts, TokenAnalysis, TokenProvenance, VerseAnalysis
from bible_engine.hebrew_analysis_repository import SYNTAX_GROUNDING_NONE
from bible_engine.hebrew_contextual_analysis_cache import (
    HebrewContextualAnalysisCache,
    get_or_request_hebrew_contextual_analysis,
)
from bible_engine.hebrew_contextual_analysis_service import (
    STATUS_INVALID_RESPONSE,
    STATUS_OK,
    HebrewContextualAnalysisResult,
)


def _token(token_id: str) -> TokenAnalysis:
    return TokenAnalysis(
        token_id=token_id, legacy_stable_key=token_id, source_token_id="", word_index=1,
        surface="x", surface_plain="x", transliteration="x", transliteration_hu="x",
        lemma="x", root=None, strong_ids=(), part_of_speech="", morphology=MorphologyFacts(raw_code="X"),
        components=(), lexical_sense=None, provenance=TokenProvenance(),
    )


def _verse(verse_id: str = "Gen.1.1") -> VerseAnalysis:
    return VerseAnalysis(
        verse_id=verse_id, chapter=1, verse=1, hebrew_text="", hebrew_text_plain="",
        versification_note="", tokens=(_token(f"{verse_id}:1"),), syntax_grounding=SYNTAX_GROUNDING_NONE,
    )


_VALID_JSON = json.dumps({"word_notes": [], "construction_notes": [], "syntax_summary": {}})


def test_second_call_for_same_verse_and_version_reuses_cache_no_new_call():
    cache = HebrewContextualAnalysisCache()
    calls = []

    def fake_generate(prompt, **kwargs):
        calls.append(prompt)
        return _VALID_JSON

    verse = _verse()
    kwargs = dict(dataset_version_signature="tahot:v1", model_id="gemini-2.5-flash", generate_fn=fake_generate, cache=cache)
    first = get_or_request_hebrew_contextual_analysis(verse, **kwargs)
    second = get_or_request_hebrew_contextual_analysis(verse, **kwargs)

    assert len(calls) == 1
    assert first.status == STATUS_OK
    assert second is first  # exact cached object returned, not a rebuilt equal one


def test_dataset_version_bump_triggers_a_fresh_call():
    cache = HebrewContextualAnalysisCache()
    calls = []

    def fake_generate(prompt, **kwargs):
        calls.append(prompt)
        return _VALID_JSON

    verse = _verse()
    get_or_request_hebrew_contextual_analysis(
        verse, dataset_version_signature="tahot:v1", model_id="m", generate_fn=fake_generate, cache=cache
    )
    get_or_request_hebrew_contextual_analysis(
        verse, dataset_version_signature="tahot:v2", model_id="m", generate_fn=fake_generate, cache=cache
    )
    assert len(calls) == 2


def test_model_change_triggers_a_fresh_call():
    cache = HebrewContextualAnalysisCache()
    calls = []

    def fake_generate(prompt, **kwargs):
        calls.append(prompt)
        return _VALID_JSON

    verse = _verse()
    get_or_request_hebrew_contextual_analysis(
        verse, dataset_version_signature="v1", model_id="model-a", generate_fn=fake_generate, cache=cache
    )
    get_or_request_hebrew_contextual_analysis(
        verse, dataset_version_signature="v1", model_id="model-b", generate_fn=fake_generate, cache=cache
    )
    assert len(calls) == 2


def test_prompt_version_change_triggers_a_fresh_call():
    cache = HebrewContextualAnalysisCache()
    calls = []

    def fake_generate(prompt, **kwargs):
        calls.append(prompt)
        return _VALID_JSON

    verse = _verse()
    get_or_request_hebrew_contextual_analysis(
        verse, dataset_version_signature="v1", model_id="m", generate_fn=fake_generate, cache=cache, prompt_version="1.0.0"
    )
    get_or_request_hebrew_contextual_analysis(
        verse, dataset_version_signature="v1", model_id="m", generate_fn=fake_generate, cache=cache, prompt_version="1.0.1"
    )
    assert len(calls) == 2


def test_different_verses_do_not_share_a_cache_entry():
    cache = HebrewContextualAnalysisCache()
    calls = []

    def fake_generate(prompt, **kwargs):
        calls.append(prompt)
        return _VALID_JSON

    get_or_request_hebrew_contextual_analysis(
        _verse("Gen.1.1"), dataset_version_signature="v1", model_id="m", generate_fn=fake_generate, cache=cache
    )
    get_or_request_hebrew_contextual_analysis(
        _verse("Gen.1.2"), dataset_version_signature="v1", model_id="m", generate_fn=fake_generate, cache=cache
    )
    assert len(calls) == 2
    assert cache.cache_size() == 2


def test_failed_result_is_never_cached_and_is_retried_on_next_call():
    cache = HebrewContextualAnalysisCache()
    calls = []

    def fake_generate(prompt, **kwargs):
        calls.append(prompt)
        return "not valid json"

    verse = _verse()
    kwargs = dict(dataset_version_signature="v1", model_id="m", generate_fn=fake_generate, cache=cache)
    first = get_or_request_hebrew_contextual_analysis(verse, **kwargs)
    second = get_or_request_hebrew_contextual_analysis(verse, **kwargs)

    assert first.status == STATUS_INVALID_RESPONSE
    assert second.status == STATUS_INVALID_RESPONSE
    assert len(calls) == 2  # retried, not cached as a failure
    assert cache.cache_size() == 0


def test_unknown_dataset_version_signature_disables_caching():
    cache = HebrewContextualAnalysisCache()
    calls = []

    def fake_generate(prompt, **kwargs):
        calls.append(prompt)
        return _VALID_JSON

    verse = _verse()
    kwargs = dict(dataset_version_signature="", model_id="m", generate_fn=fake_generate, cache=cache)
    get_or_request_hebrew_contextual_analysis(verse, **kwargs)
    get_or_request_hebrew_contextual_analysis(verse, **kwargs)

    assert len(calls) == 2
    assert cache.cache_size() == 0


def test_manual_set_only_stores_ok_status():
    cache = HebrewContextualAnalysisCache()
    failed = HebrewContextualAnalysisResult(status=STATUS_INVALID_RESPONSE)
    cache.set(verse_id="Gen.1.1", dataset_version_signature="v1", prompt_version="p1", model_id="m", result=failed)
    assert cache.cache_size() == 0


def test_cache_max_entries_evicts_least_recently_used():
    cache = HebrewContextualAnalysisCache(max_entries=2)
    ok = HebrewContextualAnalysisResult(status=STATUS_OK, analysis=None)
    cache.set(verse_id="Gen.1.1", dataset_version_signature="v1", prompt_version="p", model_id="m", result=ok)
    cache.set(verse_id="Gen.1.2", dataset_version_signature="v1", prompt_version="p", model_id="m", result=ok)
    cache.get(verse_id="Gen.1.1", dataset_version_signature="v1", prompt_version="p", model_id="m")  # touch
    cache.set(verse_id="Gen.1.3", dataset_version_signature="v1", prompt_version="p", model_id="m", result=ok)

    assert cache.cache_size() == 2
    assert cache.get(verse_id="Gen.1.2", dataset_version_signature="v1", prompt_version="p", model_id="m") is None
    assert cache.get(verse_id="Gen.1.1", dataset_version_signature="v1", prompt_version="p", model_id="m") is not None


def test_clear_empties_cache():
    cache = HebrewContextualAnalysisCache()
    ok = HebrewContextualAnalysisResult(status=STATUS_OK, analysis=None)
    cache.set(verse_id="Gen.1.1", dataset_version_signature="v1", prompt_version="p", model_id="m", result=ok)
    cache.clear()
    assert cache.cache_size() == 0
