"""Phase 2C tests for HebrewAnalysisBundle / HebrewAnalysisService /
pattern detection — see docs/hebrew_analysis_v2_phase2c.md.

Every regression case below uses a REAL corpus token (chapter/verse/surface
verified against the production TAHOT database), not synthetic data — per
the Phase 2C instruction to use real corpus examples wherever practical.
"""

from __future__ import annotations

import inspect

import pytest

from bible_engine.hebrew_analysis_bundle import BUNDLE_SCHEMA_VERSION
from bible_engine.hebrew_analysis_service import (
    HebrewAnalysisService,
    HebrewAnalysisUnavailable,
    get_hebrew_analysis,
)
from bible_engine.hebrew_token_identity import (
    TokenIdentityError,
    build_token_id,
    canonical_book_id_from_tahot_code,
    parse_token_id,
)
import bible_engine.hebrew_analysis_service as service_module
import bible_engine.hebrew_pattern_detection as pattern_module


# ---------------------------------------------------------------------------
# Deterministic bundle generation / rebuild equality
# ---------------------------------------------------------------------------


def test_deterministic_bundle_generation_gen_1_1():
    bundle = get_hebrew_analysis("1Móz 1,1")
    assert bundle.bundle_schema_version == BUNDLE_SCHEMA_VERSION
    assert bundle.reference == "Gen.1.1"
    assert bundle.language == "hebrew"
    assert len(bundle.verses) == 1
    assert len(bundle.verses[0].tokens) == 7


def test_deterministic_rebuild_equality():
    first = get_hebrew_analysis("1Móz 1,1")
    second = get_hebrew_analysis("1Móz 1,1")
    assert first == second


def test_deterministic_rebuild_equality_across_service_instances():
    a = HebrewAnalysisService().get_hebrew_analysis("Rut 1,1")
    b = HebrewAnalysisService().get_hebrew_analysis("Rut 1,1")
    assert a == b


# ---------------------------------------------------------------------------
# Hebrew vs Aramaic verse bundle + stem distinction
# ---------------------------------------------------------------------------


def test_hebrew_verse_bundle_language():
    bundle = get_hebrew_analysis("1Móz 1,1")
    assert bundle.language == "hebrew"
    assert all(t.morphology.language == "hebrew" for v in bundle.verses for t in v.tokens)


def test_aramaic_verse_bundle_language_and_stem_distinction():
    bundle = get_hebrew_analysis("Ezsdrás 4,8")
    assert bundle.language == "aramaic"
    verb_tokens = [t for v in bundle.verses for t in v.tokens if t.morphology.verb_stem]
    assert verb_tokens, "expected at least one decoded Aramaic verb in Ezra 4:8"
    # The Aramaic stem letter "q" must resolve to Peal, never the Hebrew
    # "q" -> Qal reading — the exact language-dependent-stem bug fixed in
    # Phase 2B (see bible_engine.hebrew_morphology.STEMS_BY_LANGUAGE).
    assert all(t.morphology.verb_stem != "Qal" for t in verb_tokens)
    assert any(t.morphology.verb_stem == "Peal" for t in verb_tokens)


# ---------------------------------------------------------------------------
# Stable token identity
# ---------------------------------------------------------------------------


def test_stable_token_id_format_and_bridging():
    assert build_token_id("Rut", 1, 1, 1) == "Ruth.1.1:1"
    assert build_token_id("1Sa", 1, 1, 1) == "1Sam.1.1:1"
    assert canonical_book_id_from_tahot_code("Exo") == "Exod"
    with pytest.raises(TokenIdentityError):
        canonical_book_id_from_tahot_code("Xyz")


def test_stable_token_id_roundtrip_parse():
    token_id = build_token_id("Gen", 1, 1, 5)
    parsed = parse_token_id(token_id)
    assert (parsed.book_id, parsed.chapter, parsed.verse, parsed.word_index) == ("Gen", 1, 1, 5)


def test_stable_token_ids_unique_within_verse():
    bundle = get_hebrew_analysis("1Móz 1,1")
    token_ids = [t.token_id for v in bundle.verses for t in v.tokens]
    assert len(token_ids) == len(set(token_ids))


def test_stable_token_id_stable_across_two_fetches():
    a = get_hebrew_analysis("1Móz 1,1")
    b = get_hebrew_analysis("1Móz 1,1")
    assert [t.token_id for v in a.verses for t in v.tokens] == [t.token_id for v in b.verses for t in v.tokens]


# ---------------------------------------------------------------------------
# Multi-component token preservation + component order
# ---------------------------------------------------------------------------


def test_multicomponent_hebrew_token_gen_1_1_bereshit():
    bundle = get_hebrew_analysis("1Móz 1,1")
    token = bundle.verses[0].tokens[0]
    assert token.surface == "בְּ/רֵאשִׁ֖ית"
    assert [c.role for c in token.components] == ["prefix", "core"]
    assert token.components[0].surface == "בְּ"
    assert token.components[0].gloss_en == "in"
    assert token.components[1].surface == "רֵאשִׁ֖ית"
    assert token.components[1].strong_id == "H7225G"


def test_component_order_prefix_core_suffix_gen_1_1():
    bundle = get_hebrew_analysis("1Móz 1,1")
    token = next(t for t in bundle.verses[0].tokens if t.surface.startswith("הָ/אָֽרֶץ"))
    assert [c.role for c in token.components] == ["prefix", "core", "suffix"]
    assert [c.component_index for c in token.components] == [0, 1, 2]
    assert token.components[2].is_grammar_marker  # sentence-final punctuation, H9016


def test_component_ids_are_addressable_sub_tokens():
    bundle = get_hebrew_analysis("1Móz 1,1")
    token = bundle.verses[0].tokens[0]
    assert token.components[0].component_id == f"{token.token_id}.0"
    assert token.components[1].component_id == f"{token.token_id}.1"


# ---------------------------------------------------------------------------
# Morphology fields preserved exactly — imperative / cohortative / jussive
# ---------------------------------------------------------------------------


def test_imperative_regression_gen_1_22():
    bundle = get_hebrew_analysis("1Móz 1,22")
    token = next(t for v in bundle.verses for t in v.tokens if t.surface.startswith("פְּ"))
    assert token.morphology.verb_stem == "Qal"
    assert token.morphology.verb_form == "Imperative"
    assert token.morphology.person == "Second"
    assert token.morphology.number == "Plural"
    assert token.morphology.confidence == "fully_decoded"


def test_cohortative_regression_gen_11_3():
    bundle = get_hebrew_analysis("1Móz 11,3")
    token = next(t for v in bundle.verses for t in v.tokens if t.surface.startswith("נִלְ"))
    assert token.morphology.verb_stem == "Qal"
    assert token.morphology.verb_form == "Cohortative"
    assert token.morphology.person == "First"
    assert token.morphology.number == "Plural"


def test_jussive_regression_gen_1_3():
    bundle = get_hebrew_analysis("1Móz 1,3")
    token = next(t for v in bundle.verses for t in v.tokens if t.surface.startswith("יְהִ֣י"))
    assert token.morphology.verb_form == "Jussive"


def test_single_component_token_morphology_not_lost():
    """Regression: a single-component token's own ComponentAnalysis must
    carry the same decoded fields as the token-level morphology, not an
    'unresolved' placeholder — see _align_component_payloads."""
    bundle = get_hebrew_analysis("1Móz 1,1")
    verb_token = next(t for v in bundle.verses for t in v.tokens if t.part_of_speech == "Verb")
    assert len(verb_token.components) == 1
    assert verb_token.components[0].morphology.confidence == "fully_decoded"
    assert verb_token.components[0].morphology.part_of_speech == "Verb"


# ---------------------------------------------------------------------------
# אֲשֶׁר / lexical source identity
# ---------------------------------------------------------------------------


def test_asher_lexical_sense_regression():
    """H0834A must resolve to its own correct sense — the Phase 2A/2B
    regression this whole rebuild was anchored on."""
    bundle = get_hebrew_analysis("1Móz 1,7")
    token = next(t for v in bundle.verses for t in v.tokens if "H0834A" in t.strong_ids)
    assert token.lexical_sense is not None
    assert token.lexical_sense.strong_id == "H0834A"
    assert "aki" in token.lexical_sense.base_meaning_hu or "amely" in token.lexical_sense.base_meaning_hu


# ---------------------------------------------------------------------------
# Ketiv/Qere
# ---------------------------------------------------------------------------


def test_ketiv_qere_regression_gen_9_21():
    bundle = get_hebrew_analysis("1Móz 9,21")
    verse = bundle.verses[0]
    token = next(t for t in verse.tokens if t.ketiv or t.qere)
    assert token.ketiv == "אָהֳלֹ/ה\\׃"
    assert token.qere == "אָהֳלֽ/וֹ\\׃"
    assert len(verse.text_critical) == 1
    assert verse.text_critical[0].token_id == token.token_id


# ---------------------------------------------------------------------------
# Nullable / never-fabricated root
# ---------------------------------------------------------------------------


def test_root_is_never_fabricated():
    bundle = get_hebrew_analysis("1Móz 1,1-5")
    all_tokens = [t for v in bundle.verses for t in v.tokens]
    assert all_tokens
    assert all(t.root is None for t in all_tokens)
    assert bundle.coverage.has_roots is False


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_dataset_provenance_present():
    bundle = get_hebrew_analysis("1Móz 1,1")
    dataset_ids = {d.dataset_id for d in bundle.datasets}
    assert {"tahot", "tehmc", "tbesh", "hebrew_component_fidelity", "textus_hu_lexicon"} <= dataset_ids
    for dataset in bundle.datasets:
        if dataset.dataset_id in {"tahot", "tehmc", "tbesh", "hebrew_component_fidelity"}:
            assert dataset.source_commit == service_module.STEPBIBLE_SOURCE_COMMIT
            assert dataset.license == "CC BY 4.0"


def test_token_provenance_present():
    bundle = get_hebrew_analysis("1Móz 1,1")
    token = bundle.verses[0].tokens[0]
    assert token.provenance.text_source == "tahot"
    assert token.provenance.morphology_source == "tahot"
    assert token.provenance.lexical_source == "tbesh"
    assert token.provenance.root_source == ""
    assert token.provenance.syntax_source == ""


# ---------------------------------------------------------------------------
# HebrewAnalysisService has no LLM / network dependency (static check)
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORT_MODULES = (
    "openai",
    "google.generativeai",
    "anthropic",
    "requests",
    "urllib.request",
    "httpx",
    "streamlit",
)


def _imported_module_names(module) -> set[str]:
    import ast

    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_hebrew_analysis_service_has_no_llm_or_network_dependency():
    imported = _imported_module_names(service_module)
    for forbidden in _FORBIDDEN_IMPORT_MODULES:
        assert not any(name == forbidden or name.startswith(forbidden + ".") for name in imported), (
            f"forbidden import found in hebrew_analysis_service: {forbidden}"
        )


def test_hebrew_analysis_bundle_module_has_no_llm_dependency():
    import bible_engine.hebrew_analysis_bundle as bundle_module

    imported = _imported_module_names(bundle_module)
    for forbidden in _FORBIDDEN_IMPORT_MODULES:
        assert not any(name == forbidden or name.startswith(forbidden + ".") for name in imported)


def test_invalid_reference_raises_without_any_network_call():
    with pytest.raises(HebrewAnalysisUnavailable):
        get_hebrew_analysis("Nincs Ilyen Könyv 1,1")


# ---------------------------------------------------------------------------
# Detected Features v1 — structural facts only, real corpus examples
# ---------------------------------------------------------------------------


def test_detected_feature_multiple_negation_1ch_15_13():
    bundle = get_hebrew_analysis("1Krón 15,13")
    verse = bundle.verses[0]
    negation_patterns = [p for p in verse.detected_patterns if p.pattern_type == "multiple_negation_particles"]
    assert negation_patterns
    assert len(negation_patterns[0].token_ids) >= 2


def test_detected_feature_construct_chain_gen_1_2():
    bundle = get_hebrew_analysis("1Móz 1,2")
    verse = bundle.verses[0]
    chains = [p for p in verse.detected_patterns if p.pattern_type == "construct_state_chain"]
    assert chains
    assert len(chains[0].token_ids) == 2


def test_detected_feature_repeated_lemma_gen_1_2():
    bundle = get_hebrew_analysis("1Móz 1,2")
    verse = bundle.verses[0]
    repeats = [p for p in verse.detected_patterns if p.pattern_type == "repeated_lemma_in_verse"]
    assert repeats


def test_detected_feature_multicomponent_prefix_gen_1_2():
    bundle = get_hebrew_analysis("1Móz 1,2")
    verse = bundle.verses[0]
    multi_prefix = [p for p in verse.detected_patterns if p.pattern_type == "multicomponent_prefix_structure"]
    assert multi_prefix
    assert multi_prefix[0].token_ids == ("Gen.1.2:1",)


def test_detected_feature_ketiv_qere_presence_gen_9_21():
    bundle = get_hebrew_analysis("1Móz 9,21")
    verse = bundle.verses[0]
    kq_patterns = [p for p in verse.detected_patterns if p.pattern_type == "ketiv_qere_present"]
    assert kq_patterns


def test_detected_feature_pronoun_verb_agreement_ruth_1_3():
    bundle = get_hebrew_analysis("Rut 1,3")
    verse = bundle.verses[0]
    agreement_patterns = [
        p for p in verse.detected_patterns if p.pattern_type == "explicit_pronoun_finite_verb_agreement"
    ]
    assert agreement_patterns


def test_no_fabricated_feature_interpretations():
    """CRITICAL per the Phase 2C spec: detectors must report structural
    facts, never an interpretation of what those facts mean (no 'emphasis',
    'highlights', 'ez azt jelenti' style language)."""
    source = inspect.getsource(pattern_module)
    forbidden_interpretive_hungarian = (
        "hangsúly",
        "kiemel",
        "nyomatékos",
        "ezt jelenti",
        "ez azt sugallja",
        "érzelmi",
    )
    for forbidden in forbidden_interpretive_hungarian:
        assert forbidden not in source, f"interpretive language leaked into detector source: {forbidden}"

    bundle = get_hebrew_analysis("1Móz 1,1-5")
    for verse in bundle.verses:
        for pattern in verse.detected_patterns:
            for forbidden in forbidden_interpretive_hungarian:
                assert forbidden not in pattern.explanation_hu
