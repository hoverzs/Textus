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
    CoverageReport,
    HebrewAnalysisBundle,
    MorphologyFacts,
    TokenAnalysis,
    TokenProvenance,
    VerseAnalysis,
)
from bible_engine.hebrew_analysis_repository import SYNTAX_GROUNDING_NONE


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
    assert "Jelentése ebben a mondatban" in markdown_text
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
    info_text = " ".join(i.value for i in app.info)
    assert "nem érhető el" in info_text
