"""Phase 2B §7/§9 — safety rules: syntax/construction data must never be
overinterpreted into a stronger grammatical claim than the source actually
encodes. Locked in as executable assertions against the real dataclasses
and detector output (not prose the model might later ignore)."""

from __future__ import annotations

import pytest

from bible_engine.greek_analysis_bundle import (
    GreekClauseAnalysis,
    GreekCoreferenceLink,
    GreekPhraseAnalysis,
    GreekSemanticRole,
)
from bible_engine.greek_analysis_service import get_greek_analysis_with_syntax
from bible_engine.greek_construction_detection import detect_patterns
from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path
from bible_engine.morphology_hu import parse_morphology_hu

requires_syntax_store = pytest.mark.skipif(
    not resolve_default_syntax_database_path().exists(), reason="greek_syntax_dev.sqlite3 not built locally"
)


def test_greek_phrase_analysis_has_no_semantic_function_claim_field() -> None:
    """Phrase co-membership != automatically adjectival modification (§7):
    the dataclass carries only ``function`` (the source's OWN role code,
    e.g. "s"/"o", verbatim) — no field named/shaped to claim a stronger
    semantic relationship (e.g. "modifies", "describes")."""
    fields = set(GreekPhraseAnalysis.__dataclass_fields__)
    assert fields == {
        "phrase_id", "phrase_type", "token_ids", "head_token_id", "parent_phrase_id", "function",
        # Phase 2C addition — a phrase's immediate parent can be a clause,
        # not just another phrase (measured via real cross-verse parity
        # testing); still a structural id, not a semantic-function claim.
        "parent_clause_id",
    }
    assert "modifies" not in fields
    assert "semantic_relation" not in fields


def test_greek_clause_analysis_relation_to_parent_is_source_verbatim_not_a_new_label() -> None:
    fields = set(GreekClauseAnalysis.__dataclass_fields__)
    assert "relation_to_parent" in fields
    assert "interpretation" not in fields
    assert "theological_significance" not in fields


def test_greek_semantic_role_role_type_is_the_sources_own_code_not_a_named_relation() -> None:
    """Dependency proximity != automatically semantic emphasis (§7): role
    codes are stored verbatim (e.g. "A0"/"A1"), never translated into an
    interpretive label like "emphasized argument" at the data-model level —
    that translation, if ever done, belongs to a later AI-explanation
    layer, not this deterministic one."""
    fields = set(GreekSemanticRole.__dataclass_fields__)
    assert fields == {"role_id", "role_type", "predicate_id", "token_ids"}


def test_greek_coreference_link_type_distinguishes_referent_from_subjref() -> None:
    """The two MACULA-supplied coreference facts (pronoun->antecedent vs.
    participle->implicit-subject) are kept as distinct, source-labeled
    ``link_type`` values — never merged into one undifferentiated claim."""
    fields = set(GreekCoreferenceLink.__dataclass_fields__)
    assert "link_type" in fields


@requires_syntax_store
def test_participle_form_alone_never_yields_a_temporal_causal_or_concessive_pattern_type() -> None:
    """Participle morphology != automatically temporal/causal/concessive
    function (§7/§9) — no detector in this phase emits a pattern_type
    naming such a function; the infinitive/participle detectors report
    only the FORM."""
    bundle = get_greek_analysis_with_syntax("Mt 9,18")
    forbidden = {"temporal_participle", "causal_participle", "concessive_participle", "adverbial_participle"}
    for verse in bundle.verses:
        patterns = detect_patterns(verse)
        pattern_types = {p.pattern_type for p in patterns}
        assert not (pattern_types & forbidden)


@requires_syntax_store
def test_genitive_case_alone_never_yields_a_possessive_genitive_pattern_type() -> None:
    """Genitive case != automatically possessive genitive (§7/§9) — the
    genitive-absolute detector reports "genitive_absolute_candidate" (a
    structural fact: genitive noun + genitive participle in their own
    non-root clause), never a semantic subtype like "possessive_genitive"
    or "genitive_of_source" that the data does not itself distinguish."""
    bundle = get_greek_analysis_with_syntax("Mt 9,18")
    forbidden = {"possessive_genitive", "genitive_of_source", "subjective_genitive", "objective_genitive"}
    for verse in bundle.verses:
        patterns = detect_patterns(verse)
        pattern_types = {p.pattern_type for p in patterns}
        assert not (pattern_types & forbidden)


@requires_syntax_store
def test_genitive_absolute_detector_is_confidence_probable_not_certain() -> None:
    """The detector cannot rule out every alternative reading of a
    genitive noun+participle pair from structure alone — it is reported as
    "probable", matching the Hebrew pattern-detector convention for
    structurally-grounded-but-not-airtight findings."""
    bundle = get_greek_analysis_with_syntax("Mt 9,18")
    for verse in bundle.verses:
        for pattern in detect_patterns(verse):
            if pattern.pattern_type == "genitive_absolute_candidate":
                assert pattern.confidence == "probable"


def test_detected_pattern_explanation_never_uses_interpretive_vocabulary() -> None:
    """Structural-fact-only wording check across ALL detectors on a real
    verse — no explanation may use interpretive/theological vocabulary the
    detectors were never given evidence for."""
    forbidden_substrings = (
        "hangsúly", "jelentőség", "teológiai", "elkerülhetetlen", "biztosan azt jelenti",
    )
    from bible_engine.greek_analysis_service import get_greek_analysis

    bundle = get_greek_analysis("Jn 3,16")
    for verse in bundle.verses:
        for pattern in detect_patterns(verse):
            lowered = pattern.explanation_hu.lower()
            for forbidden in forbidden_substrings:
                assert forbidden not in lowered, f"{pattern.pattern_type}: {pattern.explanation_hu!r}"


def test_article_participle_detector_requires_morphological_agreement() -> None:
    """Article+participle adjacency alone is not sufficient (would be a
    coincidental-proximity false positive) — case AND number agreement is
    required, matching real Greek concord rules the detector can verify
    deterministically."""
    from bible_engine.greek_construction_detection import _agree

    hu1 = parse_morphology_hu("T-NSM")
    hu2 = parse_morphology_hu("V-PAP-NSM")
    hu3 = parse_morphology_hu("V-PAP-GSM")

    class _Fake:
        def __init__(self, m):
            self.morphology = m

    assert _agree(_Fake(hu1), _Fake(hu2)) is True
    assert _agree(_Fake(hu1), _Fake(hu3)) is False
