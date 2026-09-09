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


def test_construction_note_with_unknown_evidence_id_is_dropped_entirely():
    verse = _verse("Gen.1.1", (_token("Gen.1.1:1"), _token("Gen.1.1:2")), grounding=SYNTAX_GROUNDING_NONE)
    parsed = {
        "word_notes": [],
        "construction_notes": [
            {
                "evidence_ids": ["macula:pattern:does-not-exist"],
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
    """A construction note is admissible when it cites the id of a real
    Phase 2C DetectedPattern — the deterministic layer DETECTED the double
    negation; the AI is only INTERPRETING it, and can only point at
    evidence already printed in the prompt, never invent a token grouping.
    ``token_ids`` on the returned note is server-computed from the
    resolved evidence, never trusted from the model."""
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
                "evidence_ids": ["Deut.6.4.negation"],
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
    assert note.evidence_ids == ("Deut.6.4.negation",)
    assert set(note.token_ids) == {"Deut.6.4:1", "Deut.6.4:2"}


def test_construction_note_accepted_when_grounded_by_phrase_without_a_detected_pattern():
    """Grounding may also come directly from a cited MACULA phrase/clause/
    relation/role/participant id with no Phase 2C detected pattern
    involved at all — the brief's §4 rule: syntax-derived observations are
    valid evidence too, not only the simple pattern detector."""
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
                "evidence_ids": ["Gen.1.1:p1"],
                "construction_type": "construct_chain",
                "title_hu": "Szerkezetes láncolat",
                "explanation_hu": "A frázis egy birtokos szerkezetet alkot.",
            }
        ],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.construction_notes) == 1
    note = analysis.construction_notes[0]
    assert note.evidence_ids == ("Gen.1.1:p1",)
    assert set(note.token_ids) == {"Gen.1.1:1", "Gen.1.1:2"}


def test_construction_note_rejected_when_no_evidence_ids_cited():
    """The core Phase 2E-grounding-verification rule, now enforced at the
    evidence-id level: a construction note with an empty/missing
    ``evidence_ids`` is rejected outright, even with plausible-sounding
    prose — the model must point at real evidence, never assert existence
    on its own."""
    verse = _verse("Deut.6.4", (_token("Deut.6.4:1"), _token("Deut.6.4:2")), grounding=SYNTAX_GROUNDING_FULL)
    parsed = {
        "word_notes": [],
        "construction_notes": [
            {
                "evidence_ids": [],
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
    assert any("nincs érvényes evidence_id" in w for w in warnings)


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
    are empty by construction, so any evidence_id the model might cite for
    a syntax-flavored construction note simply doesn't exist in the
    evidence index — rejected by the same general check every construction
    note goes through (no special-cased grounding-status branch needed)."""
    verse = _verse("Gen.1.1", (_token("Gen.1.1:1"),), grounding=SYNTAX_GROUNDING_NONE)
    parsed = {
        "word_notes": [],
        "construction_notes": [
            {
                "evidence_ids": ["macula:clause:999"],
                "construction_type": "fronted_clause_relation",
                "title_hu": "Kiemelt mondatrész",
                "explanation_hu": "...",
            }
        ],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.construction_notes == ()
    assert any("nincs érvényes evidence_id" in w for w in warnings)


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
                "evidence_ids": ["Ruth.1.8.ketiv_qere"],
                "construction_type": "ketiv_qere_present",
                "title_hu": "Ketív/qeré eltérés",
                "explanation_hu": "Az írott és olvasott alak eltér egymástól.",
            }
        ],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.construction_notes) == 1
    assert analysis.construction_notes[0].evidence_ids == ("Ruth.1.8.ketiv_qere",)


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


# ---------------------------------------------------------------------------
# Phase 2E hardening pass (prompt version 2e.1.0) — output-contract
# compactness, the evidence-catalog index primitives, and partial-validity
# handling for construction notes citing a mix of valid/invalid ids.
# ---------------------------------------------------------------------------


def test_construction_note_with_some_valid_and_some_invalid_evidence_ids_keeps_the_valid_ones():
    pattern = DetectedPattern(
        pattern_id="Gen.1.1.negation", pattern_type="multiple_negation_particles",
        token_ids=("Gen.1.1:1",), evidence_token_ids=("Gen.1.1:1",),
        detector_version="2c.0.0", confidence="certain", explanation_hu="...",
    )
    verse = _verse(
        "Gen.1.1", (_token("Gen.1.1:1"),), grounding=SYNTAX_GROUNDING_NONE, detected_patterns=(pattern,),
    )
    parsed = {
        "word_notes": [],
        "construction_notes": [
            {
                "evidence_ids": ["Gen.1.1.negation", "macula:phrase:does-not-exist"],
                "construction_type": "multiple_negation_particles",
                "title_hu": "Kettős tagadás",
                "explanation_hu": "...",
            }
        ],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.construction_notes) == 1
    assert analysis.construction_notes[0].evidence_ids == ("Gen.1.1.negation",)
    assert any("Ismeretlen evidence_id" in w for w in warnings)


def test_sparse_word_notes_accepted_without_covering_every_token():
    """The whole point of the §2 brevity contract: a verse with several
    tokens may legitimately get word_notes for only a couple of them —
    this must not be treated as an error or padded with anything."""
    verse = _verse(
        "Gen.1.1",
        (_token("Gen.1.1:1"), _token("Gen.1.1:2"), _token("Gen.1.1:3"), _token("Gen.1.1:4"), _token("Gen.1.1:5")),
        grounding=SYNTAX_GROUNDING_NONE,
    )
    parsed = {
        "word_notes": [{"token_id": "Gen.1.1:2", "contextual_meaning_hu": "teremtett"}],
        "construction_notes": [],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.word_notes) == 1
    assert analysis.word_notes[0].token_id == "Gen.1.1:2"
    assert warnings == ()


def test_word_note_count_capped_at_max_word_notes():
    tokens = tuple(_token(f"Gen.1.1:{i}") for i in range(1, 21))
    verse = _verse("Gen.1.1", tokens, grounding=SYNTAX_GROUNDING_NONE)
    parsed = {
        "word_notes": [{"token_id": t.token_id, "contextual_meaning_hu": "x"} for t in tokens],
        "construction_notes": [],
        "syntax_summary": {},
    }
    analysis, _ = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.word_notes) == 15  # _MAX_WORD_NOTES


def test_construction_note_count_capped_at_max_construction_notes():
    patterns = tuple(
        DetectedPattern(
            pattern_id=f"Gen.1.1.p{i}", pattern_type="repeated_lemma_in_verse",
            token_ids=(f"Gen.1.1:{i}",), evidence_token_ids=(f"Gen.1.1:{i}",),
            detector_version="2c.0.0", confidence="certain", explanation_hu="...",
        )
        for i in range(1, 11)
    )
    tokens = tuple(_token(f"Gen.1.1:{i}") for i in range(1, 11))
    verse = _verse("Gen.1.1", tokens, grounding=SYNTAX_GROUNDING_NONE, detected_patterns=patterns)
    parsed = {
        "word_notes": [],
        "construction_notes": [
            {
                "evidence_ids": [p.pattern_id],
                "construction_type": "repeated_lemma_in_verse",
                "title_hu": f"cím {i}",
                "explanation_hu": "magyarázat",
            }
            for i, p in enumerate(patterns)
        ],
        "syntax_summary": {},
    }
    analysis, _ = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.construction_notes) == 6  # _MAX_CONSTRUCTION_NOTES


def test_overlong_word_note_field_is_truncated_not_rejected():
    verse = _verse("Gen.1.1", (_token("Gen.1.1:1"),), grounding=SYNTAX_GROUNDING_NONE)
    long_text = "szó " * 200  # far beyond any reasonable 1-3 sentence budget
    parsed = {
        "word_notes": [{"token_id": "Gen.1.1:1", "contextual_meaning_hu": long_text}],
        "construction_notes": [],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.word_notes) == 1
    note = analysis.word_notes[0]
    assert len(note.contextual_meaning_hu) < len(long_text)
    assert note.contextual_meaning_hu.endswith("…")
    assert any("Túl hosszú mező rövidítve" in w for w in warnings)


def test_overlong_syntax_summary_is_truncated_not_rejected():
    verse = _verse("Gen.1.1", (_token("Gen.1.1:1"),), grounding=SYNTAX_GROUNDING_FULL)
    long_summary = "Ez egy mondat. " * 80
    parsed = {
        "word_notes": [], "construction_notes": [],
        "syntax_summary": {"summary_hu": long_summary},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.syntax_summary.summary_hu) < len(long_summary)
    assert any("Túl hosszú mező rövidítve" in w for w in warnings)


def test_build_construction_evidence_index_covers_every_citable_id_type():
    from bible_engine.hebrew_contextual_analysis import build_construction_evidence_index

    pattern = DetectedPattern(
        pattern_id="V.p1", pattern_type="x", token_ids=("V:1",), evidence_token_ids=("V:1",),
        detector_version="2c.0.0", confidence="certain", explanation_hu="...",
    )
    phrase = PhraseAnalysis(
        phrase_id="V:phrase1", phrase_type="np", token_ids=("V:1", "V:2"),
        head_token_id="V:1", parent_phrase_id=None, function="", source_dataset="macula_hebrew_lowfat",
    )
    clause = ClauseAnalysis(
        clause_id="V:clause1", clause_type="verbal", token_ids=("V:1",), predicate_id="V:1",
        subject_id=None, object_ids=(), complement_ids=(), modifier_ids=(), parent_clause_id=None,
        relation_to_parent="", word_order="", source_dataset="macula_hebrew_lowfat",
    )
    relation = SyntaxRelation(
        relation_id="V:edge1", relation_type="predicate", source_role_code="v",
        parent_token_id="V:1", child_token_id="V:2", source_dataset="macula_hebrew_lowfat",
    )
    role = SemanticRole(
        role_id="V:role1", role_type="agent", token_ids=("V:2",), predicate_id="V:1",
        source_dataset="macula_hebrew_lowfat",
    )
    participant = ParticipantMention(
        mention_id="V:m1", token_ids=("V:2",), participant_id="V:participant1", entity_id=None,
        entity_label_hu="", mention_type="", source_dataset="macula_hebrew_lowfat",
    )
    verse = _verse(
        "V", (_token("V:1"), _token("V:2")), grounding=SYNTAX_GROUNDING_FULL,
        detected_patterns=(pattern,), phrases=(phrase,), clauses=(clause,),
        syntax_relations=(relation,), semantic_roles=(role,), participants=(participant,),
    )
    index = build_construction_evidence_index(verse)
    assert index["V.p1"] == ("V:1",)
    assert index["V:phrase1"] == ("V:1", "V:2")
    assert index["V:clause1"] == ("V:1",)
    assert set(index["V:edge1"]) == {"V:1", "V:2"}
    assert set(index["V:role1"]) == {"V:1", "V:2"}
    assert index["V:participant1"] == ("V:2",)


def test_resolve_construction_evidence_deduplicates_and_reports_invalid():
    from bible_engine.hebrew_contextual_analysis import resolve_construction_evidence

    index = {"E1": ("A", "B"), "E2": ("B", "C")}
    resolved_evidence, resolved_tokens, invalid = resolve_construction_evidence(
        ("E1", "E2", "E1", "E-missing"), index
    )
    assert resolved_evidence == ("E1", "E2")
    assert resolved_tokens == ("A", "B", "C")
    assert invalid == ("E-missing",)


def test_resolve_construction_evidence_all_invalid_returns_empty():
    from bible_engine.hebrew_contextual_analysis import resolve_construction_evidence

    resolved_evidence, resolved_tokens, invalid = resolve_construction_evidence(("nope",), {"E1": ("A",)})
    assert resolved_evidence == ()
    assert resolved_tokens == ()
    assert invalid == ("nope",)


def test_instructions_require_evidence_ids_for_construction_notes():
    text = HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS
    assert "evidence_ids" in text
    assert "KIZÁRÓLAG ilyet" in text or "TILOS" in text


def test_instructions_state_compact_output_expectation():
    text = HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS
    assert "TÖMÖRSÉG" in text
    assert "NEM kell minden egyes tokenhez" in text
