"""Production quality-review hardening — closed-world validation for
morphological state claims and lexical meanings, deduplication of
construction notes.

Root cause trace (Gen 2:17 live smoke test): four observed AI-output
issues were traced against the exact deterministic data/prompt before any
behavior change (see the session's evidence trace against the real
Supabase-backed bundle):

1. "עֵץ and הַדַּעַת are both construct" — NOT a hallucination in the sense
   of being unrelated to any data: our PRIMARY (STEPBible/Westminster-
   derived TEHMC) morphology marks BOTH tokens ``state='Construct'``, and
   the prompt payload conveys this accurately. That is a fact about OUR
   dataset, not a settled linguistic fact — a noun in construct state
   carrying the definite article directly is grammatically exceptional in
   Biblical Hebrew (definiteness of a construct chain is normally marked
   on its LAST/absolute member instead), and other established Hebrew
   morphology datasets can and do parse this specific combination
   differently. The validator below allows the claim (it matches our
   source), but a SEPARATE anomaly detector (see
   hebrew_pattern_detection.py's ``_detect_construct_with_article_
   anomaly``) flags exactly this construct-state+article combination so
   the AI is steered toward "our primary source marks this construct"
   phrasing rather than unqualified certainty for these specific tokens
   — see test_h below.
2. "טוֹב וָרָע is an adjectival complement of דעת" — every syntax_relation
   edge touching these tokens is type='other' with no role_code; only
   phrase-nesting connects them. This is a real gap addressed by prompt
   hardening (see hebrew_contextual_analysis.py's updated instructions),
   not by a runtime validator — relation-type claims are free Hungarian
   prose and cannot be soundly validated with a keyword scan the way a
   construct/absolute state claim can.
3. "מִן means 'minden'" — pure model invention: the deterministic lexicon
   (and the prompt payload) both say "-tól/-től/-ból/-ből" for this
   lemma. Closed by a server-side override below (structured field only —
   see module docstring for why the free-text construction_notes case is
   prompt-hardened rather than validated).
4. Duplicate constructions for מוֹת/תָּמוּת — the deterministic pattern
   detector itself emitted TWO overlapping patterns
   (infinitive_absolute_with_finite_verb and repeated_lemma_in_verse) for
   the identical token pair; fixed at the source in
   hebrew_pattern_detection.py (see its own dedup test in
   tests/test_hebrew_analysis_bundle.py), with a service-level dedup
   safety net tested here too.

Fixture data below is HAND-BUILT (same convention as
tests/test_hebrew_contextual_analysis_service.py) using the REAL Gen 2:17
token ids, morphology, and lexical values traced against the live bundle —
not fetched via any repository backend, so these tests stay fast, offline,
and independent of which linguistic backend (local/Supabase) is configured.
The validators exercised here are GENERAL (see
hebrew_contextual_analysis_service.py's own docstrings) — nothing in
production logic special-cases this verse.
"""

from __future__ import annotations

from bible_engine.hebrew_analysis_bundle import (
    ComponentAnalysis,
    DetectedPattern,
    LexicalSense,
    MorphologyFacts,
    SyntaxRelation,
    TokenAnalysis,
    TokenProvenance,
    VerseAnalysis,
)
from bible_engine.hebrew_analysis_repository import SYNTAX_GROUNDING_FULL
from bible_engine.hebrew_contextual_analysis_service import validate_and_build_contextual_analysis


def _token(
    token_id: str, *, lemma: str, state: str = "", part_of_speech: str = "",
    lexical_sense: LexicalSense | None = None, components: tuple[ComponentAnalysis, ...] = (),
) -> TokenAnalysis:
    return TokenAnalysis(
        token_id=token_id, legacy_stable_key=token_id, source_token_id="", word_index=int(token_id.split(":")[-1]),
        surface=lemma, surface_plain=lemma, transliteration="", transliteration_hu="",
        lemma=lemma, root=None, strong_ids=(), part_of_speech=part_of_speech,
        morphology=MorphologyFacts(raw_code="X", state=state),
        components=components, lexical_sense=lexical_sense, provenance=TokenProvenance(),
    )


def _article_component(token_id: str) -> ComponentAnalysis:
    return ComponentAnalysis(
        component_id=f"{token_id}.0", component_index=0, role="prefix", role_label_hu="prefixum",
        surface="הַ", strong_id="H9009",
        morphology=MorphologyFacts(raw_code="HTd", particle_type="Article"),
        gloss_en="the", gloss_hu="", is_grammar_marker=True,
    )


def _gen_2_17_verse() -> VerseAnalysis:
    """Only the tokens/patterns/edges these tests actually reference — real
    ids and real morphology/lexical values, traced against the live
    Supabase-backed bundle for Gen 2:17."""
    token1 = _token("Gen.2.17:1", lemma="עֵץ", state="Construct", part_of_speech="Noun")
    token2 = _token(
        "Gen.2.17:2", lemma="דַּ֫עַת", state="Construct", part_of_speech="Article + Noun",
        components=(
            _article_component("Gen.2.17:2"),
            ComponentAnalysis(
                component_id="Gen.2.17:2.1", component_index=1, role="core", role_label_hu="alapszó",
                surface="דַּ֙עַת֙", strong_id="H1847",
                morphology=MorphologyFacts(raw_code="Ncfsc", part_of_speech="Noun", state="Construct"),
                gloss_en="knowledge", gloss_hu="", is_grammar_marker=False,
            ),
        ),
    )
    token3 = _token("Gen.2.17:3", lemma="טוֹב", state="Absolute", part_of_speech="Adjective")
    token4 = _token("Gen.2.17:4", lemma="רַע", state="Absolute", part_of_speech="Adjective")
    token7 = _token(
        "Gen.2.17:7", lemma="מִן־", part_of_speech="Preposition + Suffix",
        lexical_sense=LexicalSense(
            strong_id="H4480A", lemma="מִן־", transliteration="min", base_meaning_hu="-tól",
            possible_meanings_hu=("-tól", "-től", "-ból", "-ből"), lexical_note_hu="",
            review_status="draft", translation_method="ai_assisted", source="", warnings=(),
        ),
    )
    token12 = _token("Gen.2.17:12", lemma="מוּת", part_of_speech="Verb")
    token13 = _token("Gen.2.17:13", lemma="מוּת", part_of_speech="Verb")

    detected_patterns = (
        DetectedPattern(
            pattern_id="Gen.2.17.infabs.Gen.2.17:12.Gen.2.17:13",
            pattern_type="infinitive_absolute_with_finite_verb",
            token_ids=("Gen.2.17:12", "Gen.2.17:13"),
            evidence_token_ids=("Gen.2.17:12", "Gen.2.17:13"),
            detector_version="2c.0.0", confidence="certain",
            explanation_hu="Az abszolút infinitivus 'מות' ugyanabból a szótőből képzett véges igealak közelében fordul elő.",
        ),
        DetectedPattern(
            pattern_id="Gen.2.17.construct_article_anomaly.Gen.2.17:2",
            pattern_type="construct_state_with_article_anomaly",
            token_ids=("Gen.2.17:2",),
            evidence_token_ids=("Gen.2.17:2",),
            detector_version="2c.0.0", confidence="certain",
            explanation_hu=(
                "'דעת' az elsődleges morfológiai adatforrás szerint szerkezetes (constructus) állapotban áll, "
                "ugyanakkor határozott névelőt is visel — szokatlan alaktani kombináció."
            ),
        ),
    )
    syntax_relations = (
        SyntaxRelation(
            relation_id="macula:edge:1706", relation_type="other", source_role_code="",
            parent_token_id=None, child_token_id="Gen.2.17:3", source_dataset="test",
        ),
        SyntaxRelation(
            relation_id="macula:edge:1707", relation_type="other", source_role_code="",
            parent_token_id=None, child_token_id="Gen.2.17:4", source_dataset="test",
        ),
        SyntaxRelation(
            relation_id="macula:edge:1734", relation_type="modifier", source_role_code="adv",
            parent_token_id=None, child_token_id="Gen.2.17:12", source_dataset="test",
        ),
        SyntaxRelation(
            relation_id="macula:edge:1735", relation_type="predicate", source_role_code="v",
            parent_token_id=None, child_token_id="Gen.2.17:13", source_dataset="test",
        ),
    )
    return VerseAnalysis(
        verse_id="Gen.2.17", chapter=2, verse=17, hebrew_text="", hebrew_text_plain="",
        versification_note="", tokens=(token1, token2, token3, token4, token7, token12, token13),
        syntax_relations=syntax_relations, detected_patterns=detected_patterns,
        syntax_grounding=SYNTAX_GROUNDING_FULL,
    )


# ---------------------------------------------------------------------------
# A/B — construct-state claims are closed-world: allowed only when the
# deterministic morphology actually says Construct.
# ---------------------------------------------------------------------------


def test_a_construct_state_claim_allowed_when_morphology_actually_says_construct():
    """עֵץ (Gen.2.17:1) IS morphologically construct (state='Construct') —
    the AI is allowed to say so; this is NOT the model inventing a fact."""
    verse = _gen_2_17_verse()
    parsed = {
        "word_notes": [
            {
                "token_id": "Gen.2.17:1",
                "grammar_explanation_hu": "Ez a főnév szerkezetes állapotban áll a következő szóval.",
            }
        ],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    note = next(n for n in analysis.word_notes if n.token_id == "Gen.2.17:1")
    assert "szerkezetes állapot" in note.grammar_explanation_hu
    assert not any("alaktani állítás eldobva" in w for w in warnings)


def test_b_construct_state_claim_rejected_when_morphology_says_absolute():
    """טוֹב (Gen.2.17:3) is morphologically ABSOLUTE — a model claim of
    construct state for this specific token must be rejected server-side,
    never shown to the user. General mechanism: works for any token whose
    real state contradicts a claimed one, not a הַדַּעַת-specific carve-out
    (our PRIMARY dataset marks הַדַּעַת itself construct too, so a test
    asserting "cannot be called construct" for it would test a false
    premise against OUR data — see the module docstring for why that is a
    fact about our dataset, not a settled linguistic question, and
    test_h below for the anomaly this specific combination gets flagged
    with)."""
    verse = _gen_2_17_verse()
    parsed = {
        "word_notes": [
            {
                "token_id": "Gen.2.17:3",
                "grammar_explanation_hu": "Ez a melléknév szerkezetes állapotban áll.",
            }
        ],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    note = next(n for n in analysis.word_notes if n.token_id == "Gen.2.17:3")
    assert note.grammar_explanation_hu == ""
    assert any("alaktani állítás eldobva" in w for w in warnings)


# ---------------------------------------------------------------------------
# C — lexical meaning may not be rewritten.
# ---------------------------------------------------------------------------


def test_c_lexical_meaning_for_min_cannot_be_overridden_by_model():
    """Production finding: an AI output once replaced מִן's given "-tól"
    gloss with the unrelated word "minden". The deterministic lexicon is
    now ALWAYS authoritative for this structured field — the model's own
    value is discarded outright, not merely flagged."""
    verse = _gen_2_17_verse()
    parsed = {
        "word_notes": [
            {"token_id": "Gen.2.17:7", "lexical_basic_meaning_hu": "minden"},
        ],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    note = next(n for n in analysis.word_notes if n.token_id == "Gen.2.17:7")
    assert note.lexical_basic_meaning_hu == "-tól"
    assert note.lexical_basic_meaning_hu != "minden"
    assert any("lexikai alapjelentés felülírva" in w for w in warnings)


def test_c_lexical_meaning_unchanged_when_model_already_matches_deterministic_data():
    verse = _gen_2_17_verse()
    parsed = {
        "word_notes": [
            {"token_id": "Gen.2.17:7", "lexical_basic_meaning_hu": "-tól"},
        ],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    note = next(n for n in analysis.word_notes if n.token_id == "Gen.2.17:7")
    assert note.lexical_basic_meaning_hu == "-tól"
    assert not any("lexikai alapjelentés felülírva" in w for w in warnings)


# ---------------------------------------------------------------------------
# E — infinitive absolute + finite verb remains correctly explainable.
# ---------------------------------------------------------------------------


def test_e_infinitive_absolute_construction_remains_explainable():
    verse = _gen_2_17_verse()
    parsed = {
        "construction_notes": [
            {
                "construction_type": "infinitive_absolute_with_finite_verb",
                "title_hu": "Infinitivus absolutus + véges ige",
                "explanation_hu": "A 'מות' abszolút infinitivus a véges igealak mellett áll, nyomatékosítva az állítást.",
                "evidence_ids": ["Gen.2.17.infabs.Gen.2.17:12.Gen.2.17:13"],
            }
        ],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.construction_notes) == 1
    note = analysis.construction_notes[0]
    assert set(note.token_ids) == {"Gen.2.17:12", "Gen.2.17:13"}


# ---------------------------------------------------------------------------
# F — a generic repeated-lemma construction is suppressed when it
# duplicates a more specific infinitive-absolute construction (source-level
# fix in hebrew_pattern_detection.py; already covered directly by
# tests/test_hebrew_analysis_bundle.py's own dedup test). Here: the
# service-level safety net, for the case where the model itself produces
# two notes resolving to the identical token set from two DIFFERENT
# evidence ids.
# ---------------------------------------------------------------------------


def test_f_duplicate_construction_notes_for_same_token_set_are_deduplicated():
    verse = _gen_2_17_verse()
    parsed = {
        "construction_notes": [
            {
                "construction_type": "infinitive_absolute_with_finite_verb",
                "title_hu": "Első megfigyelés",
                "explanation_hu": "Első leírás ugyanarról a jelenségről.",
                "evidence_ids": ["Gen.2.17.infabs.Gen.2.17:12.Gen.2.17:13"],
            },
            {
                # Different evidence ids (two syntax edges), but they
                # resolve to the SAME token pair (12, 13) as the note above.
                "construction_type": "infinitive_absolute_with_finite_verb",
                "title_hu": "Második, átfedő megfigyelés",
                "explanation_hu": "Ugyanazon két tokenre vonatkozó második leírás.",
                "evidence_ids": ["macula:edge:1734", "macula:edge:1735"],
            },
        ],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.construction_notes) == 1
    assert analysis.construction_notes[0].title_hu == "Első megfigyelés"
    assert any("Duplikált szerkezet-megfigyelés eldobva" in w for w in warnings)


# ---------------------------------------------------------------------------
# G — unsupported model claims are rejected/fail closed, not shown to user.
# ---------------------------------------------------------------------------


def test_g_construction_note_with_unresolvable_evidence_is_rejected_not_shown():
    verse = _gen_2_17_verse()
    parsed = {
        "construction_notes": [
            {
                "construction_type": "invented_pattern",
                "title_hu": "Kitalált szerkezet",
                "explanation_hu": "Ez a szerkezet nem szerepel a determinisztikus adatban.",
                "evidence_ids": ["macula:phrase:does-not-exist"],
            }
        ],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.construction_notes == ()
    assert any("nincs érvényes evidence_id" in w for w in warnings)


def test_g_construction_note_with_unsupported_state_claim_is_rejected_not_shown():
    """A construction note describing tokens covered by its evidence must
    not assert a state one of those tokens doesn't actually have — here,
    citing evidence covering absolute-state טוֹב/וָרָע while claiming
    "szerkezetes állapot" (construct) for them."""
    verse = _gen_2_17_verse()
    parsed = {
        "construction_notes": [
            {
                "construction_type": "fabricated_construct_claim",
                "title_hu": "Hibás állapot-állítás",
                "explanation_hu": "Ez a két szó szerkezetes állapotban áll egymással.",
                "evidence_ids": ["macula:edge:1706", "macula:edge:1707"],
            }
        ],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.construction_notes == ()
    assert any("alaktani állítás nem támasztható alá" in w for w in warnings)


# ---------------------------------------------------------------------------
# H — construct+article anomaly (user correction): our primary source
# marking הַדַּעַת construct is a fact about OUR dataset, not a settled
# linguistic question — never state or imply otherwise in code/tests/docs.
# A plain claim matching our source is still allowed; a CATEGORICAL
# ("biztosan"-style) claim for the specific anomalous token is rejected.
# Ordinary, unambiguous construct tokens (עֵץ — no article) are unaffected.
# ---------------------------------------------------------------------------


def test_h_plain_construct_claim_for_article_bearing_anomalous_token_still_allowed():
    """הַדַּעַת (Gen.2.17:2) retains the primary-source construct tag — a
    plain (non-categorical) claim matching it is still shown to the user,
    exactly like any other token whose claim matches its real state."""
    verse = _gen_2_17_verse()
    parsed = {
        "word_notes": [
            {
                "token_id": "Gen.2.17:2",
                "grammar_explanation_hu": "Az elsődleges morfológiai adatforrás constructusnak jelöli.",
            }
        ],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    note = next(n for n in analysis.word_notes if n.token_id == "Gen.2.17:2")
    assert "constructusnak jelöli" in note.grammar_explanation_hu
    assert not any("eldobva" in w for w in warnings)


def test_h_categorical_construct_claim_for_article_bearing_anomalous_token_rejected():
    """The SAME claim, but phrased with unqualified certainty, must be
    rejected for this specific anomalous token — not because the state
    claim is wrong (it matches our source), but because the anomaly means
    it should never be presented as an unquestionable grammatical fact."""
    verse = _gen_2_17_verse()
    parsed = {
        "word_notes": [
            {
                "token_id": "Gen.2.17:2",
                "grammar_explanation_hu": "Ez a szó biztosan szerkezetes állapotban áll.",
            }
        ],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    note = next(n for n in analysis.word_notes if n.token_id == "Gen.2.17:2")
    assert note.grammar_explanation_hu == ""
    assert any("kategorikus bizonyosságú" in w for w in warnings)


def test_h_categorical_construct_claim_for_ordinary_non_anomalous_token_remains_allowed():
    """עֵץ (Gen.2.17:1) is construct with NO article — an entirely
    ordinary, unambiguous case. The anomaly rule must NOT apply to it:
    even confident/categorical phrasing is fine here (item 5 — "keep
    ordinary, unambiguous construct forms unchanged")."""
    verse = _gen_2_17_verse()
    parsed = {
        "word_notes": [
            {
                "token_id": "Gen.2.17:1",
                "grammar_explanation_hu": "Ez a szó biztosan szerkezetes állapotban áll.",
            }
        ],
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    note = next(n for n in analysis.word_notes if n.token_id == "Gen.2.17:1")
    assert "biztosan szerkezetes állapotban áll" in note.grammar_explanation_hu
    assert not any("eldobva" in w for w in warnings)


# ---------------------------------------------------------------------------
# Narrow polish-pass (prompt wording only): items 1 and 3 are free-text
# generation guidance for the model, not runtime-validatable claims (the
# same reason relation-type wording in issue 2 above is prompt-hardened
# rather than keyword-validated — see the module docstring). These tests
# assert the instruction text itself carries the required, GENERAL (not
# Gen-2:17-hardcoded) guidance rather than exercising the validator.
# ---------------------------------------------------------------------------


def test_prompt_gives_conservative_evidence_sensitive_prepositional_phrase_wording():
    """Item 1: for multicomponent_prefix_structure / prepositional-phrase
    tokens, the prompt must steer toward conservative, function-describing
    wording ("elöljárószós bővítmény") and explicitly forbid asserting a
    specific unsupported relation label unless the syntax data actually
    names it — general guidance, not a Gen 2:17 special case."""
    from bible_engine.hebrew_contextual_analysis import HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS

    text = " ".join(HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS.split())
    assert "multicomponent_prefix_structure" in text
    assert "elöljárószós bővítmény" in text
    assert "összetett körülményhatározói kifejezés" in text
    assert "TILOS konkrét mondattani szerepet nevesíteni" in text
    assert "1Móz 2,17" not in text and "וּמֵעֵץ" not in text


def test_prompt_separates_infinitive_absolute_grammatical_fact_from_interpretation():
    """Item 3: for infinitive_absolute_with_finite_verb, the prompt must
    prescribe a fact-level phrase ("az állítást nyomatékosító szerkezet"),
    require any stronger reading (e.g. "elkerülhetetlenség") to be marked
    as interpretation rather than grammatical fact, and steer away from
    unjustified generic textbook wording."""
    from bible_engine.hebrew_contextual_analysis import HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS

    text = " ".join(HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS.split())
    assert "infinitive_absolute_with_finite_verb" in text
    assert "az állítást nyomatékosító szerkezet" in text
    assert "elkerülhetetlenség" in text
    assert "SOSE grammatikai tényként" in text or "sosem mondattani/grammatikai tényt" in text


def test_prompt_anomaly_safeguard_wording_is_preserved():
    """Item 4: the earlier construct+article anomaly safeguard (source-
    aware wording: primary source marks it construct; article+construct is
    unusual; analysis may be source-dependent) must not be weakened or
    removed by the item-1/item-3 additions inserted right after it."""
    from bible_engine.hebrew_contextual_analysis import HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS

    text = " ".join(HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS.split())
    assert "construct_state_with_article_anomaly" in text
    assert "Az elsődleges morfológiai adatforrás constructusnak jelöli." in text
    assert "forrásfüggő lehet" in text
    assert "KIZÁRÓLAG az így megjelölt, kivételes esetekre vonatkozik" in text
