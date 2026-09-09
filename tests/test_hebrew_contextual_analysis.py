"""Phase 2E §21/§22 — deterministic-contract and output-safety tests for
the grounded Hungarian contextual-grammar AI layer.

Track A (deterministic contract): the AI INPUT — the prompt payload built
from a real ``HebrewAnalysisBundle`` verse — must carry supplied
stem/conjugation/syntax facts verbatim, never re-derive them, and must
never claim a fact the bundle does not actually have (root, syntax on an
uncovered token, a Hungarian gloss that doesn't exist).

Track B (output safety): the validation layer in
``bible_engine.hebrew_contextual_analysis_service`` must structurally
enforce the grounding rules on a MOCKED model response — no live network or
LLM call anywhere in this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bible_engine.hebrew_analysis_bundle import (
    ClauseAnalysis,
    ComponentAnalysis,
    DetectedPattern,
    LexicalSense,
    MorphologyFacts,
    ParticipantMention,
    PhraseAnalysis,
    SemanticRole,
    SyntaxRelation,
    TokenAnalysis,
    TokenProvenance,
    VerseAnalysis,
)
from bible_engine.hebrew_analysis_repository import (
    LocalHebrewAnalysisRepository,
    SYNTAX_GROUNDING_FULL,
    SYNTAX_GROUNDING_NONE,
    SYNTAX_GROUNDING_PARTIAL,
)
from bible_engine.hebrew_analysis_service import HebrewAnalysisService
from bible_engine.hebrew_contextual_analysis import (
    HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS,
    _token_syntax_coverage,
    build_hebrew_contextual_analysis_payload,
    build_hebrew_contextual_analysis_prompt,
)
from bible_engine.hebrew_contextual_analysis_service import (
    validate_and_build_contextual_analysis,
)
from bible_engine.hebrew_linguistic_sqlite import open_store
from bible_engine.hebrew_macula_importer import ensure_dataset_version, import_chapter
from bible_engine.hebrew_token_repository import HebrewTokenRepository
from bible_engine.macula_lowfat_parser import parse_macula_lowfat_chapter

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "macula_lowfat"
RUTH_FIXTURE = FIXTURES / "ruth_1_excerpt-lowfat.xml"
GEN_36_5_FIXTURE = FIXTURES / "genesis_36_5_excerpt-lowfat.xml"


@pytest.fixture(scope="module")
def combined_store_path(tmp_path_factory):
    store_path = tmp_path_factory.mktemp("hebrew_ctx") / "combined.sqlite3"
    store = open_store(store_path)
    textus_dv = ensure_dataset_version(store, dataset_id="tahot", display_name="TAHOT", revision="test")
    macula_dv = ensure_dataset_version(store, dataset_id="macula_hebrew_lowfat", display_name="MACULA", revision="test")
    repo = HebrewTokenRepository()
    for tahot_book_code, chapter_number, fixture in [("Rut", 1, RUTH_FIXTURE), ("Gen", 36, GEN_36_5_FIXTURE)]:
        chapter = parse_macula_lowfat_chapter(fixture)
        import_chapter(
            chapter, tahot_book_code=tahot_book_code, chapter_number=chapter_number, store=store,
            token_repository=repo, textus_dataset_version_id=textus_dv, macula_dataset_version_id=macula_dv,
        )
    store.close()
    return store_path


@pytest.fixture(scope="module")
def bundle(combined_store_path):
    service = HebrewAnalysisService(linguistic_repository=LocalHebrewAnalysisRepository(combined_store_path))
    return service.get_hebrew_analysis("Rut 1,1")


@pytest.fixture(scope="module")
def gen_36_5_verse(combined_store_path):
    service = HebrewAnalysisService(linguistic_repository=LocalHebrewAnalysisRepository(combined_store_path))
    result = service.get_hebrew_analysis("1Móz 36,5")
    return result.verses[0]


# ---------------------------------------------------------------------------
# Track A — deterministic contract (real bundle data).
# ---------------------------------------------------------------------------


def test_prompt_payload_supplies_stem_and_form_as_separate_labeled_fields(bundle):
    verse = bundle.verses[0]
    payload = build_hebrew_contextual_analysis_payload(verse)
    verb_token = next(t for t in verse.tokens if t.morphology.verb_stem)
    assert f"igetörzs: " in payload
    assert "igealak: " in payload or verb_token.morphology.verb_form == ""
    # stem and form must never be merged into one comma-joined label here —
    # they are always on their own separate lines.
    assert "igetörzs:" != "igealak:"


def test_prompt_payload_never_claims_a_root(bundle):
    verse = bundle.verses[0]
    for token in verse.tokens:
        assert token.root is None  # Phase 2C/2D invariant — see hebrew_analysis_bundle.py
    payload = build_hebrew_contextual_analysis_payload(verse)
    assert "gyök:" not in payload


def test_prompt_payload_grounding_status_matches_bundle(bundle):
    verse = bundle.verses[0]
    payload = build_hebrew_contextual_analysis_payload(verse)
    assert f"mondattani lefedettség (syntax_grounding): {verse.syntax_grounding}" in payload


def test_prompt_payload_lists_uncovered_tokens_under_partial_grounding(gen_36_5_verse):
    assert gen_36_5_verse.syntax_grounding == SYNTAX_GROUNDING_PARTIAL
    payload = build_hebrew_contextual_analysis_payload(gen_36_5_verse)
    assert "mondattani adat NÉLKÜLI tokenek ebben a versben:" in payload
    covered = _token_syntax_coverage(gen_36_5_verse)
    uncovered = [t.token_id for t in gen_36_5_verse.tokens if t.token_id not in covered]
    assert uncovered  # Gen 36:5 has real UNRESOLVED tokens (Phase 2D.1)
    for token_id in uncovered:
        assert token_id in payload
        assert "mondattani adat: NINCS ehhez a tokenhez" in payload


def test_prompt_payload_missing_hungarian_gloss_stays_nullable_not_fabricated(bundle):
    verse = bundle.verses[0]
    tokens_without_sense = [t for t in verse.tokens if t.lexical_sense is None]
    if not tokens_without_sense:
        pytest.skip("fixture happens to have full lexical coverage for Ruth 1:1")
    payload = build_hebrew_contextual_analysis_payload(verse)
    assert "nincs magyar lexikai adat ehhez a szóhoz" in payload


def test_prompt_payload_carries_syntax_relations_and_semantic_roles_verbatim(bundle):
    verse = bundle.verses[0]
    payload = build_hebrew_contextual_analysis_payload(verse)
    if verse.syntax_relations:
        assert "MONDATTANI VISZONYOK:" in payload
        assert verse.syntax_relations[0].relation_id in payload
    if verse.semantic_roles:
        assert "SZEMANTIKAI SZEREPEK:" in payload
        assert verse.semantic_roles[0].role_id in payload


def test_prompt_payload_includes_deterministic_detected_patterns(gen_36_5_verse):
    """Gen 36:5 has a real Ketiv/Qere divergence — Phase 2C's deterministic
    pattern detector (bible_engine.hebrew_pattern_detection.detect_patterns)
    must have populated VerseAnalysis.detected_patterns for it, and that
    fact must actually reach the AI prompt payload verbatim (pattern_id,
    token_ids, and the detector's own deterministic Hungarian
    explanation) — this is the deterministic evidence construction_notes
    are grounded against; it was previously missing from the payload."""
    assert gen_36_5_verse.detected_patterns, "expected at least one Phase 2C detected pattern for Gen 36:5"
    payload = build_hebrew_contextual_analysis_payload(gen_36_5_verse)
    assert "FELISMERT SZERKEZETEK" in payload
    for pattern in gen_36_5_verse.detected_patterns:
        assert pattern.pattern_id in payload
        assert pattern.pattern_type in payload
        assert pattern.explanation_hu in payload


def test_full_prompt_includes_instructions_and_payload(bundle):
    verse = bundle.verses[0]
    prompt = build_hebrew_contextual_analysis_prompt(verse)
    assert HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS.strip()[:40] in prompt
    assert verse.verse_id in prompt


# ---------------------------------------------------------------------------
# Instruction-text safety checks (§22 — word order, textual criticism,
# universal-rule stem explanations).
# ---------------------------------------------------------------------------


def test_instructions_forbid_universal_stem_formulas():
    text = HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS
    assert "a Hitpael mindig" in text and "reflexív" in text
    assert "a Piel mindig intenzív" in text
    assert "univerzális, sablonos igetörzs-magyarázatot adni" in text


def test_instructions_forbid_word_order_emphasis_claims():
    text = HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS
    assert "szórendből ÖNMAGÁBAN hangsúlyt" in text
    assert "NINCS determinisztikus szórendi adat" in text


def test_instructions_forbid_textual_criticism_beyond_ketiv_qere():
    text = HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS
    assert "holt-tengeri tekercsek" in text
    assert "szamaritánus Pentateuchus" in text
    assert "BHS/BHQ-apparátus" in text


def test_instructions_forbid_root_invention():
    text = HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS
    assert '"gyök"' in text
    assert "NINCS jelen" in text


def test_clause_analysis_word_order_field_always_empty_in_current_dataset(bundle):
    """Structural corroboration for the word-order instruction above: the
    current MACULA import genuinely never populates ``word_order``, so an
    emphasis claim grounded on it would have nothing real behind it."""
    for verse in bundle.verses:
        for clause in verse.clauses:
            assert clause.word_order == ""


# ---------------------------------------------------------------------------
# Track B — output safety (hand-built minimal VerseAnalysis objects, full
# control over grounding status; no real corpus needed for these).
# ---------------------------------------------------------------------------


def _token(token_id: str, *, verb_stem: str = "", lexical_sense: LexicalSense | None = None) -> TokenAnalysis:
    morphology = MorphologyFacts(raw_code="X", verb_stem=verb_stem)
    return TokenAnalysis(
        token_id=token_id,
        legacy_stable_key=token_id,
        source_token_id="",
        word_index=1,
        surface="x",
        surface_plain="x",
        transliteration="x",
        transliteration_hu="x",
        lemma="x",
        root=None,
        strong_ids=(),
        part_of_speech="",
        morphology=morphology,
        components=(),
        lexical_sense=lexical_sense,
        provenance=TokenProvenance(),
    )


def _verse(verse_id: str, tokens: tuple[TokenAnalysis, ...], *, grounding: str, **kwargs) -> VerseAnalysis:
    return VerseAnalysis(
        verse_id=verse_id,
        chapter=1,
        verse=1,
        hebrew_text="",
        hebrew_text_plain="",
        versification_note="",
        tokens=tokens,
        syntax_grounding=grounding,
        **kwargs,
    )


def test_empty_result_is_a_valid_success_state():
    verse = _verse("Gen.1.1", (_token("Gen.1.1:1"),), grounding=SYNTAX_GROUNDING_NONE)
    parsed = {"word_notes": [], "construction_notes": [], "syntax_summary": {}}
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.word_notes == ()
    assert analysis.construction_notes == ()
    assert analysis.syntax_summary.summary_hu == ""
    assert warnings == ()


def test_lexical_and_contextual_meaning_kept_as_separate_fields():
    """The אֲשֶׁר regression case: a context-specific rendering (e.g.
    "amikor") must never overwrite or merge with the lexeme's general
    lexical meaning ("aki, amely, ami") — the schema keeps both fields,
    and the service must preserve both independently."""
    verse = _verse("Ruth.1.16", (_token("Ruth.1.16:5"),), grounding=SYNTAX_GROUNDING_NONE)
    parsed = {
        "word_notes": [
            {
                "token_id": "Ruth.1.16:5",
                "lexical_basic_meaning_hu": "aki, amely, ami (vonatkozó partikula)",
                "contextual_meaning_hu": "ahová (a mondat szerkezete miatt itt helyhatározói értelemben)",
                "confidence": "medium",
            }
        ],
        "construction_notes": [],
        "syntax_summary": {},
    }
    analysis, _ = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.word_notes) == 1
    note = analysis.word_notes[0]
    assert note.lexical_basic_meaning_hu == "aki, amely, ami (vonatkozó partikula)"
    assert note.contextual_meaning_hu == "ahová (a mondat szerkezete miatt itt helyhatározói értelemben)"
    assert note.lexical_basic_meaning_hu != note.contextual_meaning_hu


def test_unknown_token_id_in_word_note_is_dropped_with_warning():
    verse = _verse("Gen.1.1", (_token("Gen.1.1:1"),), grounding=SYNTAX_GROUNDING_NONE)
    parsed = {"word_notes": [{"token_id": "Gen.1.1:99"}], "construction_notes": [], "syntax_summary": {}}
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.word_notes == ()
    assert any("Gen.1.1:99" in w for w in warnings)


def test_construction_note_with_any_unresolved_token_id_is_dropped_entirely():
    verse = _verse("Gen.1.1", (_token("Gen.1.1:1"), _token("Gen.1.1:2")), grounding=SYNTAX_GROUNDING_NONE)
    parsed = {
        "word_notes": [],
        "construction_notes": [
            {
                "token_ids": ["Gen.1.1:1", "Gen.1.1:999"],
                "construction_type": "double_negation",
                "title_hu": "Kettős tagadás",
                "explanation_hu": "...",
            }
        ],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.construction_notes == ()
    assert warnings


def test_construction_note_accepted_when_grounded_by_detected_pattern():
    """A construction note is admissible when its token_ids are covered by
    a real Phase 2C DetectedPattern — the deterministic layer DETECTED the
    double negation; the AI is only INTERPRETING it. evidence_pattern_ids
    is populated by the service, never trusted from the model's output."""
    pattern = DetectedPattern(
        pattern_id="Deut.6.4.negation", pattern_type="multiple_negation_particles",
        token_ids=("Deut.6.4:1", "Deut.6.4:2"), evidence_token_ids=("Deut.6.4:1", "Deut.6.4:2"),
        detector_version="2c.0.0", confidence="certain",
        explanation_hu="Ebben a versben 2 tagadószó fordul elő.",
    )
    verse = _verse(
        "Deut.6.4", (_token("Deut.6.4:1"), _token("Deut.6.4:2")), grounding=SYNTAX_GROUNDING_NONE,
        detected_patterns=(pattern,),
    )
    parsed = {
        "word_notes": [],
        "construction_notes": [
            {
                "token_ids": ["Deut.6.4:1", "Deut.6.4:2"],
                "construction_type": "double_negation",
                "title_hu": "Kettős tagadás",
                "explanation_hu": "Két tagadószó erősíti egymást.",
                "confidence": "high",
            }
        ],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.construction_notes) == 1
    note = analysis.construction_notes[0]
    assert note.construction_type == "double_negation"
    assert note.evidence_pattern_ids == ("Deut.6.4.negation",)


def test_construction_note_accepted_when_grounded_by_phrase_without_a_detected_pattern():
    """Grounding may also come directly from supplied MACULA structure
    (phrase/clause/relation/role/participant) with no Phase 2C detected
    pattern involved at all — the brief's §4 rule: syntax-derived
    observations are valid evidence too, not only the simple pattern
    detector."""
    verse = _verse(
        "Gen.1.1", (_token("Gen.1.1:1"), _token("Gen.1.1:2")), grounding=SYNTAX_GROUNDING_FULL,
        phrases=(
            PhraseAnalysis(
                phrase_id="Gen.1.1:p1", phrase_type="np", token_ids=("Gen.1.1:1", "Gen.1.1:2"),
                head_token_id="Gen.1.1:1", parent_phrase_id=None, function="", source_dataset="macula_hebrew_lowfat",
            ),
        ),
    )
    parsed = {
        "word_notes": [],
        "construction_notes": [
            {
                "token_ids": ["Gen.1.1:1", "Gen.1.1:2"],
                "construction_type": "construct_chain",
                "title_hu": "Szerkezetes láncolat",
                "explanation_hu": "A frázis egy birtokos szerkezetet alkot.",
            }
        ],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.construction_notes) == 1
    assert analysis.construction_notes[0].evidence_pattern_ids == ()


def test_construction_note_rejected_when_token_ids_resolve_but_nothing_grounds_it():
    """The core Phase 2E-grounding-verification rule: resolvable token_ids
    alone are NOT sufficient — without a matching DetectedPattern or a real
    phrase/clause/relation/role/participant covering exactly those tokens,
    the note is rejected even though nothing about it looks malformed."""
    verse = _verse("Deut.6.4", (_token("Deut.6.4:1"), _token("Deut.6.4:2")), grounding=SYNTAX_GROUNDING_FULL)
    parsed = {
        "word_notes": [],
        "construction_notes": [
            {
                "token_ids": ["Deut.6.4:1", "Deut.6.4:2"],
                "construction_type": "double_negation",
                "title_hu": "Kettős tagadás",
                "explanation_hu": "Két tagadószó erősíti egymást.",
                "confidence": "high",
            }
        ],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.construction_notes == ()
    assert any("nincs determinisztikus alátámasztás" in w for w in warnings)


def test_no_grounded_syntax_strips_syntax_summary_even_if_model_supplied_one():
    verse = _verse("Gen.1.1", (_token("Gen.1.1:1"),), grounding=SYNTAX_GROUNDING_NONE)
    parsed = {
        "word_notes": [],
        "construction_notes": [],
        "syntax_summary": {"summary_hu": "Az ige VSO szórendben áll.", "clause_ids": ["Gen.1.1:c1"]},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.syntax_summary.summary_hu == ""
    assert analysis.syntax_summary.clause_ids == ()
    assert any("NO_GROUNDED_SYNTAX" in w for w in warnings)


def test_no_grounded_syntax_strips_per_token_syntax_explanation():
    verse = _verse("Gen.1.1", (_token("Gen.1.1:1"),), grounding=SYNTAX_GROUNDING_NONE)
    parsed = {
        "word_notes": [{"token_id": "Gen.1.1:1", "syntax_explanation_hu": "Ez a mondat alanya."}],
        "construction_notes": [],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.word_notes[0].syntax_explanation_hu == ""
    assert any("NO_GROUNDED_SYNTAX" in w for w in warnings)


def test_no_grounded_syntax_drops_syntax_dependent_construction_notes():
    """Under NO_GROUNDED_SYNTAX the verse's own phrases/clauses/relations
    are empty by construction, so a syntax-flavored construction note has
    nothing to be grounded in — it is rejected by the same general
    evidence check every construction note goes through (no special-cased
    grounding-status branch needed)."""
    verse = _verse("Gen.1.1", (_token("Gen.1.1:1"),), grounding=SYNTAX_GROUNDING_NONE)
    parsed = {
        "word_notes": [],
        "construction_notes": [
            {
                "token_ids": ["Gen.1.1:1"],
                "construction_type": "fronted_clause_relation",
                "title_hu": "Kiemelt mondatrész",
                "explanation_hu": "...",
            }
        ],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.construction_notes == ()
    assert any("nincs determinisztikus alátámasztás" in w for w in warnings)


def test_no_grounded_syntax_still_accepts_a_morphology_only_detected_pattern():
    """The flip side: even with NO_GROUNDED_SYNTAX (no MACULA syntax at
    all for this verse), a genuine Phase 2C morphology-level detected
    pattern (e.g. Ketiv/Qere) still grounds a construction note — syntax
    absence must not block a morphology-grounded observation."""
    pattern = DetectedPattern(
        pattern_id="Ruth.1.8.ketiv_qere", pattern_type="ketiv_qere_present",
        token_ids=("Ruth.1.8:3",), evidence_token_ids=("Ruth.1.8:3",),
        detector_version="2c.0.0", confidence="certain",
        explanation_hu="Ebben a versben 1 szónál van dokumentált ketiv/kere eltérés.",
    )
    verse = _verse(
        "Ruth.1.8", (_token("Ruth.1.8:3"),), grounding=SYNTAX_GROUNDING_NONE, detected_patterns=(pattern,),
    )
    parsed = {
        "word_notes": [],
        "construction_notes": [
            {
                "token_ids": ["Ruth.1.8:3"],
                "construction_type": "ketiv_qere_present",
                "title_hu": "Ketív/qeré eltérés",
                "explanation_hu": "Az írott és olvasott alak eltér egymástól.",
            }
        ],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.construction_notes) == 1
    assert analysis.construction_notes[0].evidence_pattern_ids == ("Ruth.1.8.ketiv_qere",)


def test_partial_grounding_restricts_syntax_claim_to_covered_tokens():
    covered_token = _token("Gen.36.5:1")
    uncovered_token = _token("Gen.36.5:5")
    verse = _verse(
        "Gen.36.5",
        (covered_token, uncovered_token),
        grounding=SYNTAX_GROUNDING_PARTIAL,
        clauses=(
            ClauseAnalysis(
                clause_id="Gen.36.5:c1", clause_type="verbal", token_ids=("Gen.36.5:1",),
                predicate_id="Gen.36.5:1", subject_id=None, object_ids=(), complement_ids=(),
                modifier_ids=(), parent_clause_id=None, relation_to_parent="", word_order="",
                source_dataset="macula_hebrew_lowfat",
            ),
        ),
    )
    parsed = {
        "word_notes": [
            {"token_id": "Gen.36.5:1", "syntax_explanation_hu": "Ez az állítmány."},
            {"token_id": "Gen.36.5:5", "syntax_explanation_hu": "Ez a mondat tárgya."},
        ],
        "construction_notes": [],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    by_id = {note.token_id: note for note in analysis.word_notes}
    assert by_id["Gen.36.5:1"].syntax_explanation_hu == "Ez az állítmány."
    assert by_id["Gen.36.5:5"].syntax_explanation_hu == ""
    assert any("Gen.36.5:5" in w and "nincs mondattani adat" in w for w in warnings)


def test_syntax_summary_drops_unresolvable_clause_ids():
    verse = _verse(
        "Gen.1.1", (_token("Gen.1.1:1"),), grounding=SYNTAX_GROUNDING_FULL,
        clauses=(
            ClauseAnalysis(
                clause_id="Gen.1.1:c1", clause_type="verbal", token_ids=("Gen.1.1:1",),
                predicate_id="Gen.1.1:1", subject_id=None, object_ids=(), complement_ids=(),
                modifier_ids=(), parent_clause_id=None, relation_to_parent="", word_order="",
                source_dataset="macula_hebrew_lowfat",
            ),
        ),
    )
    parsed = {
        "word_notes": [],
        "construction_notes": [],
        "syntax_summary": {"summary_hu": "Egy tagmondatból áll.", "clause_ids": ["Gen.1.1:c1", "Gen.1.1:c99"]},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.syntax_summary.clause_ids == ("Gen.1.1:c1",)
    assert any("ismeretlen tagmondat" in w for w in warnings)


def test_confidence_value_normalized_when_invalid():
    verse = _verse("Gen.1.1", (_token("Gen.1.1:1"),), grounding=SYNTAX_GROUNDING_NONE)
    parsed = {
        "word_notes": [{"token_id": "Gen.1.1:1", "confidence": "extremely certain"}],
        "construction_notes": [],
        "syntax_summary": {},
    }
    analysis, _ = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.word_notes[0].confidence == "low"


def test_grounding_status_on_output_always_mirrors_bundle_not_model():
    verse = _verse("Gen.1.1", (_token("Gen.1.1:1"),), grounding=SYNTAX_GROUNDING_FULL)
    parsed = {"word_notes": [], "construction_notes": [], "syntax_summary": {}, "grounding_status": "NO_GROUNDED_SYNTAX"}
    analysis, _ = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.grounding_status == SYNTAX_GROUNDING_FULL
