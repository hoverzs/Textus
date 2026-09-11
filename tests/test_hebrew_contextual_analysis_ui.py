"""Phase 2E §17-20 — UI-level integration tests for the additive
"Nyelvtani és mondattani elemzés (AI)" section on the Hebrew word-click
panel.

Uses ``streamlit.testing.v1.AppTest`` against the REAL default TAHOT
database (the same committed asset every other Hebrew UI test already
relies on for Gen 1:1) so the deterministic token panel above the new
section renders exactly as before. The Phase 2E ``HebrewAnalysisService``
is monkeypatched to a small in-memory fake bundle — no MACULA store, no
network — so these tests stay fast and fully offline.
"""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

import hebrew_text_demo
from bible_engine.hebrew_analysis_bundle import (
    ClauseAnalysis,
    CoverageReport,
    DetectedPattern,
    HebrewAnalysisBundle,
    MorphologyFacts,
    TokenAnalysis,
    TokenProvenance,
    VerseAnalysis,
)
from bible_engine.hebrew_analysis_repository import SYNTAX_GROUNDING_FULL, SYNTAX_GROUNDING_NONE


def _fake_bundle() -> HebrewAnalysisBundle:
    token = TokenAnalysis(
        token_id="Gen.1.1:1", legacy_stable_key="Gen:1:1:1", source_token_id="", word_index=1,
        surface="בְּ/רֵאשִׁית", surface_plain="בראשית", transliteration="berešit", transliteration_hu="berésit",
        lemma="רֵאשִׁית", root=None, strong_ids=("H7225G",), part_of_speech="Noun",
        morphology=MorphologyFacts(raw_code="HR/Ncfsa"), components=(), lexical_sense=None,
        provenance=TokenProvenance(),
    )
    verse = VerseAnalysis(
        verse_id="Gen.1.1", chapter=1, verse=1, hebrew_text="בְּרֵאשִׁית",
        hebrew_text_plain="בראשית", versification_note="", tokens=(token,),
        syntax_grounding=SYNTAX_GROUNDING_NONE,
    )
    return HebrewAnalysisBundle(
        bundle_schema_version="2e-test", reference="Gen.1.1", reference_hu="1Móz 1,1",
        book_id="Gen", language="hebrew", verses=(verse,), datasets=(),
        coverage=CoverageReport(
            has_morphology=True, has_component_fidelity=False, has_syntax=False,
            has_semantic_roles=False, has_participants=False, has_roots=False,
            token_count=1, fully_decoded_token_count=0,
        ),
    )


class _FakeHebrewAnalysisService:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def dataset_version_signature(self) -> str:
        return "test-v1"

    def get_hebrew_analysis(self, reference: str) -> HebrewAnalysisBundle:
        return _fake_bundle()


def _render_without_generate_fn() -> None:
    import hebrew_text_demo as demo

    demo.render_hebrew_original_language_panel("Gen", 1, 1, 1, key_prefix="ctx_ui_off")


def _labels(app: AppTest) -> list[str]:
    return [button.label for button in app.button]


def test_no_ai_section_when_generate_text_fn_is_none(monkeypatch):
    monkeypatch.setattr(hebrew_text_demo, "HebrewAnalysisService", _FakeHebrewAnalysisService)
    app = AppTest.from_function(_render_without_generate_fn).run(timeout=15)
    assert not app.exception
    markdown_text = " ".join(m.value for m in app.markdown)
    assert "Nyelvtani és mondattani elemzés" not in markdown_text
    assert not any("Kontextuális elemzés" in label for label in _labels(app))


def _render_with_generate_fn() -> None:
    import json

    import hebrew_text_demo as demo

    def fake_generate(prompt: str, **kwargs) -> str:
        return json.dumps(
            {
                "word_notes": [
                    {
                        "token_id": "Gen.1.1:1",
                        "lexical_basic_meaning_hu": "kezdet",
                        "contextual_meaning_hu": "a teremtés kezdete",
                        "grammar_explanation_hu": "főnév, nőnem, egyes szám",
                        "confidence": "high",
                    }
                ],
                "construction_notes": [],
                "syntax_summary": {},
            }
        )

    demo.render_hebrew_original_language_panel(
        "Gen", 1, 1, 1, key_prefix="ctx_ui_on", generate_text_fn=fake_generate
    )


def _find_button(app: AppTest, label_substring: str):
    return next(button for button in app.button if label_substring in button.label)


def test_ai_section_shows_generate_button_before_first_run(monkeypatch):
    monkeypatch.setattr(hebrew_text_demo, "HebrewAnalysisService", _FakeHebrewAnalysisService)
    app = AppTest.from_function(_render_with_generate_fn).run(timeout=15)
    assert not app.exception
    markdown_text = " ".join(m.value for m in app.markdown)
    assert "Nyelvtani és mondattani elemzés" in markdown_text
    assert _find_button(app, "Kontextuális elemzés generálása") is not None


def test_clicking_generate_button_renders_word_note_after_one_call(monkeypatch):
    monkeypatch.setattr(hebrew_text_demo, "HebrewAnalysisService", _FakeHebrewAnalysisService)
    app = AppTest.from_function(_render_with_generate_fn).run(timeout=15)
    _find_button(app, "Kontextuális elemzés generálása").click().run(timeout=15)
    assert not app.exception
    markdown_text = " ".join(m.value for m in app.markdown)
    assert "Lexikai alapjelentés" in markdown_text
    assert "kezdet" in markdown_text
    assert "Kontextuális jelentés" in markdown_text
    assert "a teremtés kezdete" in markdown_text


def _render_with_failing_generate_fn() -> None:
    import hebrew_text_demo as demo

    def failing_generate(prompt: str, **kwargs) -> str:
        return "not valid json at all"

    demo.render_hebrew_original_language_panel(
        "Gen", 1, 1, 1, key_prefix="ctx_ui_fail", generate_text_fn=failing_generate
    )


def test_ai_failure_shows_graceful_notice_deterministic_card_still_present(monkeypatch):
    monkeypatch.setattr(hebrew_text_demo, "HebrewAnalysisService", _FakeHebrewAnalysisService)
    app = AppTest.from_function(_render_with_failing_generate_fn).run(timeout=15)
    _find_button(app, "Kontextuális elemzés generálása").click().run(timeout=15)
    assert not app.exception
    markdown_text = " ".join(m.value for m in app.markdown)
    # The deterministic word card (rendered unconditionally above the AI
    # section) must still be present even though the AI call failed.
    assert "רֵאשִׁית" in markdown_text or "בְּ" in markdown_text
    warning_text = " ".join(w.value for w in app.warning)
    assert "nem érhető el" in warning_text


# ---------------------------------------------------------------------------
# Regression coverage for the production bug: bible_text_ui.py's calls into
# render_greek_analysis_block never forwarded hebrew_contextual_analysis_
# generate_fn, so render_hebrew_contextual_analysis_panel's very first line
# (`if generate_text_fn is None: return`) silently dropped the ENTIRE Phase
# 2E section on the "Igehely" tab — no caption, no button, nothing — even
# though the deterministic morphology/lexicon card above it (a completely
# independent data path) rendered fine. Caught here at both the wiring
# level (this test) and the full section-content level (the two tests
# below, via render_hebrew_original_language_panel directly).
# ---------------------------------------------------------------------------


def _render_bible_text_editor_with_generate_fn() -> None:
    import streamlit as st
    import bible_text_ui

    st.session_state["last_igehely"] = "1Móz 1,1"
    st.session_state["passage_text"] = "Kezdetben teremté Isten az eget és a földet."
    st.session_state["bible_translation"] = "RUF"

    def fake_generate(prompt: str, **kwargs) -> str:
        return "{}"

    bible_text_ui.render_bible_text_editor(
        hebrew_contextual_analysis_generate_fn=fake_generate,
    )


def test_igehely_tab_bible_text_editor_forwards_generate_fn_to_phase2e_section(monkeypatch):
    """The actual bug: on the "Igehely" tab, render_bible_text_editor() must
    forward its hebrew_contextual_analysis_generate_fn through to the
    Hebrew word panel so the Phase 2E section appears — this is the exact
    call path a real user hits immediately after loading a passage,
    BEFORE ever visiting the dedicated "Eredeti szöveg tanulmányozása" tab."""
    monkeypatch.setattr(hebrew_text_demo, "HebrewAnalysisService", _FakeHebrewAnalysisService)
    app = AppTest.from_function(_render_bible_text_editor_with_generate_fn).run(timeout=15)
    assert not app.exception
    markdown_text = " ".join(m.value for m in app.markdown)
    assert "Nyelvtani és mondattani elemzés" in markdown_text
    assert any("Kontextuális elemzés generálása" in b.label for b in app.button)


def _two_token_fake_bundle() -> HebrewAnalysisBundle:
    token1 = TokenAnalysis(
        token_id="Gen.1.1:1", legacy_stable_key="Gen:1:1:1", source_token_id="", word_index=1,
        surface="בְּ/רֵאשִׁית", surface_plain="בראשית", transliteration="berešit", transliteration_hu="berésit",
        lemma="רֵאשִׁית", root=None, strong_ids=("H7225G",), part_of_speech="Noun",
        morphology=MorphologyFacts(raw_code="HR/Ncfsa"), components=(), lexical_sense=None,
        provenance=TokenProvenance(),
    )
    token2 = TokenAnalysis(
        token_id="Gen.1.1:2", legacy_stable_key="Gen:1:1:2", source_token_id="", word_index=2,
        surface="בָּרָא", surface_plain="ברא", transliteration="bara", transliteration_hu="bárá",
        lemma="ברא", root=None, strong_ids=("H1254G",), part_of_speech="Verb",
        morphology=MorphologyFacts(raw_code="HVqp3ms"), components=(), lexical_sense=None,
        provenance=TokenProvenance(),
    )
    clause = ClauseAnalysis(
        clause_id="macula:clause:1", clause_type="", token_ids=("Gen.1.1:1", "Gen.1.1:2"),
        predicate_id="Gen.1.1:2", subject_id=None, object_ids=(), complement_ids=(), modifier_ids=(),
        parent_clause_id=None, relation_to_parent="", word_order="", source_dataset="test",
    )
    verse = VerseAnalysis(
        verse_id="Gen.1.1", chapter=1, verse=1, hebrew_text="בְּרֵאשִׁית בָּרָא",
        hebrew_text_plain="בראשית ברא", versification_note="", tokens=(token1, token2),
        clauses=(clause,), syntax_grounding=SYNTAX_GROUNDING_FULL,
    )
    return HebrewAnalysisBundle(
        bundle_schema_version="2e-test", reference="Gen.1.1", reference_hu="1Móz 1,1",
        book_id="Gen", language="hebrew", verses=(verse,), datasets=(),
        coverage=CoverageReport(
            has_morphology=True, has_component_fidelity=False, has_syntax=False,
            has_semantic_roles=False, has_participants=False, has_roots=False,
            token_count=2, fully_decoded_token_count=0,
        ),
    )


class _FakeTwoTokenHebrewAnalysisService:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def dataset_version_signature(self) -> str:
        return "test-v1"

    def get_hebrew_analysis(self, reference: str) -> HebrewAnalysisBundle:
        return _two_token_fake_bundle()


def _render_two_token_panel_with_counting_generate_fn() -> None:
    import json

    import streamlit as st
    import hebrew_text_demo as demo

    calls = st.session_state.setdefault("_test_generate_call_count", {"n": 0})

    def counting_generate(prompt: str, **kwargs) -> str:
        calls["n"] += 1
        return json.dumps(
            {
                "word_notes": [
                    {
                        "token_id": "Gen.1.1:1",
                        "lexical_basic_meaning_hu": "kezdet",
                        "contextual_meaning_hu": "a teremtés kezdete",
                        "grammar_explanation_hu": "főnév, nőnem, egyes szám",
                        "syntax_explanation_hu": "időhatározói szerkezet",
                        "confidence": "high",
                    },
                    {
                        "token_id": "Gen.1.1:2",
                        "lexical_basic_meaning_hu": "teremt",
                        "contextual_meaning_hu": "a teremtés cselekedete",
                        "grammar_explanation_hu": "ige, qal, 3. szem. hímnem egyes szám",
                        "syntax_explanation_hu": "állítmány",
                        "confidence": "high",
                    },
                ],
                "construction_notes": [
                    {
                        "construction_type": "word_order",
                        "title_hu": "Ige-alany inverzió",
                        "explanation_hu": "Az ige a mondat élén áll, ami elbeszélő nyitóformula.",
                        "translation_significance_hu": "",
                        "confidence": "high",
                        "evidence_ids": ["macula:clause:1"],
                    }
                ],
                "syntax_summary": {
                    "summary_hu": "A mondat egy egyszerű állító főmondat.",
                    "clause_ids": ["macula:clause:1"],
                },
                "translation_notes": [],
                "exegetical_notes": [],
                "warnings": [],
            }
        )

    demo.render_hebrew_original_language_panel(
        "Gen", 1, 1, 1, key_prefix="ctx_ui_cache", generate_text_fn=counting_generate
    )


def test_word_click_shows_contextual_meaning_grammar_and_verse_construction_notes_with_no_duplicate_generation(
    monkeypatch,
):
    """Task requirement: a selected word with a valid HebrewContextualAnalysis
    renders at least contextual meaning + grammar/syntax explanation; verse-
    level construction notes are visible; selecting a DIFFERENT word in the
    SAME verse reuses the cached analysis rather than calling generate_fn a
    second time (Gemini calls are expensive — one verse-level call must
    serve every word click within that verse)."""
    monkeypatch.setattr(hebrew_text_demo, "HebrewAnalysisService", _FakeTwoTokenHebrewAnalysisService)
    app = AppTest.from_function(_render_two_token_panel_with_counting_generate_fn).run(timeout=15)

    _find_button(app, "Kontextuális elemzés generálása").click().run(timeout=15)
    assert not app.exception
    assert app.session_state["_test_generate_call_count"]["n"] == 1

    markdown_text = " ".join(m.value for m in app.markdown)
    assert "Kontextuális jelentés" in markdown_text
    assert "a teremtés kezdete" in markdown_text
    assert "Nyelvtani magyarázat" in markdown_text
    assert "Mondattani szerep" in markdown_text
    assert "időhatározói szerkezet" in markdown_text
    # Verse-level construction notes must be visible (inside the expander).
    assert "Ige-alany inverzió" in markdown_text
    assert "elbeszélő nyitóformula" in markdown_text

    # Select the SECOND token in the same verse (simulates another word
    # click) via the fallback selectbox — must reuse the cached analysis.
    fallback_selector = next(
        sel for sel in app.selectbox if sel.key == "ctx_ui_cache_fallback_selector"
    )
    fallback_selector.select("Gen:1:1:2").run(timeout=15)
    assert not app.exception
    assert app.session_state["_test_generate_call_count"]["n"] == 1, (
        "selecting another word in the same verse must NOT trigger a second Gemini call"
    )
    markdown_text_2 = " ".join(m.value for m in app.markdown)
    assert "a teremtés cselekedete" in markdown_text_2
    assert "állítmány" in markdown_text_2


# ---------------------------------------------------------------------------
# Production hotfix regression (post-bb6400d): the Phase 2E button on the
# "Igehely" tab is now reachable for the first time in production, which
# means a hung/slow real Gemini call is now reachable too. These tests
# prove generation is STRICTLY button-gated (never on initial render, never
# on a mere word click) and that a hung/failed call degrades gracefully
# without ever raising past request_hebrew_contextual_analysis.
# ---------------------------------------------------------------------------


def _render_two_token_panel_with_counting_generate_fn_no_click() -> None:
    """Same fixture as the caching test above, but the test driver never
    clicks the generate button — used to prove 0 calls on render/word-select."""
    import streamlit as st
    import hebrew_text_demo as demo

    calls = st.session_state.setdefault("_test_generate_call_count", {"n": 0})

    def counting_generate(prompt: str, **kwargs) -> str:
        calls["n"] += 1
        return "{}"

    demo.render_hebrew_original_language_panel(
        "Gen", 1, 1, 1, key_prefix="ctx_ui_lazy", generate_text_fn=counting_generate
    )


def test_initial_render_triggers_zero_gemini_calls(monkeypatch):
    monkeypatch.setattr(hebrew_text_demo, "HebrewAnalysisService", _FakeTwoTokenHebrewAnalysisService)
    app = AppTest.from_function(_render_two_token_panel_with_counting_generate_fn_no_click).run(timeout=15)
    assert not app.exception
    assert app.session_state["_test_generate_call_count"]["n"] == 0


def test_selecting_a_different_hebrew_word_triggers_zero_gemini_calls(monkeypatch):
    """Selecting a word is a DIFFERENT Streamlit rerun than the one where
    the generate button was clicked — st.button() returns False on every
    rerun except the exact one immediately following its own click, so
    merely changing the selected token must never call generate_fn."""
    monkeypatch.setattr(hebrew_text_demo, "HebrewAnalysisService", _FakeTwoTokenHebrewAnalysisService)
    app = AppTest.from_function(_render_two_token_panel_with_counting_generate_fn_no_click).run(timeout=15)
    fallback_selector = next(
        sel for sel in app.selectbox if sel.key == "ctx_ui_lazy_fallback_selector"
    )
    fallback_selector.select("Gen:1:1:2").run(timeout=15)
    assert not app.exception
    assert app.session_state["_test_generate_call_count"]["n"] == 0


def _render_with_hanging_generate_fn() -> None:
    """Simulates a Gemini request that times out at the network layer
    (requests.exceptions.Timeout / a bare TimeoutError) rather than
    returning a malformed-response string — proves
    request_hebrew_contextual_analysis's own `except Exception` catches
    this too, not just the "invalid JSON text" failure mode already
    covered by test_ai_failure_shows_graceful_notice_deterministic_card_
    still_present."""
    import hebrew_text_demo as demo

    def hanging_generate(prompt: str, **kwargs) -> str:
        raise TimeoutError("simulated Gemini network timeout")

    demo.render_hebrew_original_language_panel(
        "Gen", 1, 1, 1, key_prefix="ctx_ui_timeout", generate_text_fn=hanging_generate
    )


def test_simulated_gemini_timeout_degrades_gracefully_deterministic_ui_still_renders(monkeypatch):
    monkeypatch.setattr(hebrew_text_demo, "HebrewAnalysisService", _FakeHebrewAnalysisService)
    app = AppTest.from_function(_render_with_hanging_generate_fn).run(timeout=15)
    _find_button(app, "Kontextuális elemzés generálása").click().run(timeout=15)
    assert not app.exception, "a hung/failing Gemini call must never crash the Streamlit script"
    markdown_text = " ".join(m.value for m in app.markdown)
    # Deterministic word card (independent data path) must still be usable.
    assert "רֵאשִׁית" in markdown_text or "בְּ" in markdown_text
    warning_text = " ".join(w.value for w in app.warning)
    assert "nem érhető el" in warning_text


def test_phase2e_gemini_call_uses_conservative_timeout_shorter_than_generate_text_default():
    """generate_hebrew_contextual_analysis_text must forward a
    conservative timeout_s (PHASE2E_GEMINI_TIMEOUT_S) to generate_text's
    real requests.post(...) call — shorter than GEMINI_TIMEOUT_S (120s),
    the value that let a hung Phase 2E call block a Streamlit session for
    up to two minutes after bb6400d made this path reachable in
    production for the first time."""

    def _capture_requests_post_timeout() -> None:
        import os
        os.environ["GEMINI_API_KEY"] = "test-fake-key-not-real"
        import streamlit as st
        import app

        captured: dict[str, object] = {}

        class _FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "candidates": [
                        {"content": {"parts": [{"text": "{}"}]}, "finishReason": "STOP"}
                    ]
                }

        def fake_post(url, headers=None, json=None, timeout=None, stream=False):
            captured["timeout"] = timeout
            return _FakeResponse()

        app.requests.post = fake_post
        app.generate_hebrew_contextual_analysis_text("test prompt")
        st.session_state["_captured_timeout"] = captured.get("timeout")
        st.session_state["_phase2e_timeout_const"] = app.PHASE2E_GEMINI_TIMEOUT_S
        st.session_state["_generic_timeout_const"] = app.GEMINI_TIMEOUT_S

    at = AppTest.from_function(_capture_requests_post_timeout)
    at.run(timeout=30)
    assert not at.exception
    captured = at.session_state["_captured_timeout"]
    phase2e_const = at.session_state["_phase2e_timeout_const"]
    generic_const = at.session_state["_generic_timeout_const"]
    assert captured == phase2e_const
    assert phase2e_const < generic_const


# ---------------------------------------------------------------------------
# Narrow polish-pass regression: production quality review found that a
# construction note covering the SELECTED word was rendered twice in the
# same view — once under "Kapcsolódó konstrukciók" (word-level) and again,
# unfiltered, under "Mondattani összefoglalás — kapcsolódó konstrukciók"
# (verse-level). The fix is display-only dedup by object identity in
# hebrew_text_demo.py; this test proves a construction already shown for
# the selected word is NOT repeated in the verse-level list, while a
# genuinely distinct construction (covering only the OTHER token) still
# appears there.
# ---------------------------------------------------------------------------


def _two_token_bundle_with_distinct_patterns() -> HebrewAnalysisBundle:
    token1 = TokenAnalysis(
        token_id="Gen.1.1:1", legacy_stable_key="Gen:1:1:1", source_token_id="", word_index=1,
        surface="בְּ/רֵאשִׁית", surface_plain="בראשית", transliteration="berešit", transliteration_hu="berésit",
        lemma="רֵאשִׁית", root=None, strong_ids=("H7225G",), part_of_speech="Noun",
        morphology=MorphologyFacts(raw_code="HR/Ncfsa"), components=(), lexical_sense=None,
        provenance=TokenProvenance(),
    )
    token2 = TokenAnalysis(
        token_id="Gen.1.1:2", legacy_stable_key="Gen:1:1:2", source_token_id="", word_index=2,
        surface="בָּרָא", surface_plain="ברא", transliteration="bara", transliteration_hu="bárá",
        lemma="ברא", root=None, strong_ids=("H1254G",), part_of_speech="Verb",
        morphology=MorphologyFacts(raw_code="HVqp3ms"), components=(), lexical_sense=None,
        provenance=TokenProvenance(),
    )
    pattern1 = DetectedPattern(
        pattern_id="pattern:word1-only", pattern_type="multicomponent_prefix_structure",
        token_ids=("Gen.1.1:1",), evidence_token_ids=("Gen.1.1:1",),
        detector_version="test-v1", confidence="certain",
        explanation_hu="Több prefixumból álló szó.",
    )
    pattern2 = DetectedPattern(
        pattern_id="pattern:word2-only", pattern_type="multicomponent_prefix_structure",
        token_ids=("Gen.1.1:2",), evidence_token_ids=("Gen.1.1:2",),
        detector_version="test-v1", confidence="certain",
        explanation_hu="Egy másik, különálló szerkezet.",
    )
    verse = VerseAnalysis(
        verse_id="Gen.1.1", chapter=1, verse=1, hebrew_text="בְּרֵאשִׁית בָּרָא",
        hebrew_text_plain="בראשית ברא", versification_note="", tokens=(token1, token2),
        detected_patterns=(pattern1, pattern2), syntax_grounding=SYNTAX_GROUNDING_FULL,
    )
    return HebrewAnalysisBundle(
        bundle_schema_version="2e-test", reference="Gen.1.1", reference_hu="1Móz 1,1",
        book_id="Gen", language="hebrew", verses=(verse,), datasets=(),
        coverage=CoverageReport(
            has_morphology=True, has_component_fidelity=False, has_syntax=False,
            has_semantic_roles=False, has_participants=False, has_roots=False,
            token_count=2, fully_decoded_token_count=0,
        ),
    )


class _FakeDistinctPatternHebrewAnalysisService:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def dataset_version_signature(self) -> str:
        return "test-v1"

    def get_hebrew_analysis(self, reference: str) -> HebrewAnalysisBundle:
        return _two_token_bundle_with_distinct_patterns()


def _render_two_distinct_construction_panel() -> None:
    import json

    import hebrew_text_demo as demo

    def fake_generate(prompt: str, **kwargs) -> str:
        return json.dumps(
            {
                "word_notes": [
                    {
                        "token_id": "Gen.1.1:1",
                        "lexical_basic_meaning_hu": "kezdet",
                        "contextual_meaning_hu": "a teremtés kezdete",
                        "grammar_explanation_hu": "főnév, nőnem, egyes szám",
                        "confidence": "high",
                    },
                    {
                        "token_id": "Gen.1.1:2",
                        "lexical_basic_meaning_hu": "teremt",
                        "contextual_meaning_hu": "a teremtés cselekedete",
                        "grammar_explanation_hu": "ige, qal, 3. szem. hímnem egyes szám",
                        "confidence": "high",
                    },
                ],
                "construction_notes": [
                    {
                        "construction_type": "prefix_structure",
                        "title_hu": "Több prefixumból álló szó (1. token)",
                        "explanation_hu": "Ez a szó több prefixumból épül fel.",
                        "translation_significance_hu": "",
                        "confidence": "high",
                        "evidence_ids": ["pattern:word1-only"],
                    },
                    {
                        "construction_type": "prefix_structure",
                        "title_hu": "Egyedi szerkezet (2. token)",
                        "explanation_hu": "Ez egy különálló, csak a második tokent érintő szerkezet.",
                        "translation_significance_hu": "",
                        "confidence": "high",
                        "evidence_ids": ["pattern:word2-only"],
                    },
                ],
                "syntax_summary": {},
                "translation_notes": [],
                "exegetical_notes": [],
                "warnings": [],
            }
        )

    demo.render_hebrew_original_language_panel(
        "Gen", 1, 1, 1, key_prefix="ctx_ui_dedup", generate_text_fn=fake_generate
    )


def test_construction_note_shown_for_selected_word_is_not_repeated_in_verse_level_summary(
    monkeypatch,
):
    monkeypatch.setattr(hebrew_text_demo, "HebrewAnalysisService", _FakeDistinctPatternHebrewAnalysisService)
    app = AppTest.from_function(_render_two_distinct_construction_panel).run(timeout=15)
    _find_button(app, "Kontextuális elemzés generálása").click().run(timeout=15)
    assert not app.exception

    markdown_text = " ".join(m.value for m in app.markdown)
    # Word-level note for the selected (first) token must show its own
    # construction exactly once.
    assert markdown_text.count("Több prefixumból álló szó (1. token)") == 1
    # The genuinely distinct construction (covering only the OTHER token)
    # must still appear in the verse-level summary — dedup must not drop
    # constructions that were never shown at word-level.
    assert "Egyedi szerkezet (2. token)" in markdown_text
