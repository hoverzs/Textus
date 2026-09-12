"""Phase 2C §17/§20/§21 — UI-level integration tests for the Greek
contextual-analysis panel, wired into the REAL production word-detail
renderer (``bible_engine.greek_analysis_ui._render_analysis_panel``), not
a demo path — see ``bible_engine.greek_contextual_analysis_ui``'s module
docstring. Uses ``streamlit.testing.v1.AppTest`` against the REAL TAGNT
database (same convention every other original-language UI test uses)."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path

requires_syntax_store = pytest.mark.skipif(
    not resolve_default_syntax_database_path().exists(), reason="greek_syntax_dev.sqlite3 not built locally"
)


def _find_button(app: AppTest, label_substring: str):
    return next(button for button in app.button if label_substring in button.label)


def _render_without_generate_fn() -> None:
    import bible_engine.greek_analysis_ui as greek_ui

    greek_ui.render_greek_analysis_block(reference="Jn 3,16", key_prefix="ctx_off")


def test_no_ai_section_when_generate_fn_is_none() -> None:
    app = AppTest.from_function(_render_without_generate_fn).run(timeout=20)
    assert not app.exception
    markdown_text = " ".join(m.value for m in app.markdown)
    assert "Nyelvtani és mondattani elemzés" not in markdown_text
    assert not any("Kontextuális elemzés generálása" in b.label for b in app.button)


def _render_with_counting_generate_fn() -> None:
    import json

    import streamlit as st
    import bible_engine.greek_analysis_ui as greek_ui

    calls = st.session_state.setdefault("_test_call_count", {"n": 0})

    def counting_generate(prompt: str, **kwargs) -> str:
        calls["n"] += 1
        return json.dumps({
            "word_notes": [{
                # word_index=1 ("Οὕτως") is the default-selected token when
                # no explicit selection has been made yet.
                "token_id": "Jhn.3.16:1",
                "contextual_meaning_hu": "Isten szeretetének kifejezése ebben a kontextusban.",
                "morphological_explanation_hu": "határozószó, mondatkezdő elem",
                "confidence": "high",
            }],
            "construction_notes": [],
            "syntax_summary": {"summary_hu": "A vers fő állítása Isten szeretete."},
            "translation_notes": [], "exegetical_notes": [], "warnings": [],
        })

    greek_ui.render_greek_analysis_block(
        reference="Jn 3,16", key_prefix="ctx_on", greek_contextual_analysis_generate_fn=counting_generate,
    )


@requires_syntax_store
def test_ai_section_shows_generate_button_before_first_run() -> None:
    app = AppTest.from_function(_render_with_counting_generate_fn).run(timeout=20)
    assert not app.exception
    markdown_text = " ".join(m.value for m in app.markdown)
    assert "Nyelvtani és mondattani elemzés" in markdown_text
    assert _find_button(app, "Kontextuális elemzés generálása") is not None
    assert app.session_state["_test_call_count"]["n"] == 0


@requires_syntax_store
def test_initial_render_triggers_zero_gemini_calls() -> None:
    app = AppTest.from_function(_render_with_counting_generate_fn).run(timeout=20)
    assert app.session_state["_test_call_count"]["n"] == 0


@requires_syntax_store
def test_clicking_generate_button_triggers_exactly_one_call_and_renders_result() -> None:
    app = AppTest.from_function(_render_with_counting_generate_fn).run(timeout=20)
    _find_button(app, "Kontextuális elemzés generálása").click().run(timeout=20)
    assert not app.exception
    assert app.session_state["_test_call_count"]["n"] == 1
    markdown_text = " ".join(m.value for m in app.markdown)
    assert "Kontextuális jelentés" in markdown_text
    assert "Isten szeretetének kifejezése" in markdown_text


@requires_syntax_store
def test_selecting_a_different_word_in_the_same_verse_reuses_cache_zero_new_calls() -> None:
    app = AppTest.from_function(_render_with_counting_generate_fn).run(timeout=20)
    _find_button(app, "Kontextuális elemzés generálása").click().run(timeout=20)
    assert app.session_state["_test_call_count"]["n"] == 1

    fallback_selectors = [sel for sel in app.selectbox if "fallback_selector" in (sel.key or "")]
    assert fallback_selectors, "expected the fallback token selectbox to be present"
    fallback_selectors[0].select_index(1).run(timeout=20)
    assert not app.exception
    assert app.session_state["_test_call_count"]["n"] == 1, "selecting another word must NOT trigger a second call"


def _render_with_hanging_generate_fn() -> None:
    import bible_engine.greek_analysis_ui as greek_ui

    def hanging_generate(prompt: str, **kwargs) -> str:
        raise TimeoutError("simulated Gemini network timeout")

    greek_ui.render_greek_analysis_block(
        reference="Jn 3,16", key_prefix="ctx_timeout", greek_contextual_analysis_generate_fn=hanging_generate,
    )


@requires_syntax_store
def test_simulated_timeout_degrades_gracefully_deterministic_ui_still_usable() -> None:
    app = AppTest.from_function(_render_with_hanging_generate_fn).run(timeout=20)
    _find_button(app, "Kontextuális elemzés generálása").click().run(timeout=20)
    assert not app.exception, "a hung/failing Gemini call must never crash the Streamlit script"
    markdown_text = " ".join(m.value for m in app.markdown)
    assert "θεὸς" in markdown_text or "Strong" in markdown_text  # deterministic card still present
    warning_text = " ".join(w.value for w in app.warning)
    assert "nem érhető el" in warning_text


def _render_with_failing_json_generate_fn() -> None:
    import bible_engine.greek_analysis_ui as greek_ui

    def failing_generate(prompt: str, **kwargs) -> str:
        return "not valid json at all"

    greek_ui.render_greek_analysis_block(
        reference="Jn 3,16", key_prefix="ctx_fail", greek_contextual_analysis_generate_fn=failing_generate,
    )


@requires_syntax_store
def test_invalid_json_response_shows_graceful_notice() -> None:
    app = AppTest.from_function(_render_with_failing_json_generate_fn).run(timeout=20)
    _find_button(app, "Kontextuális elemzés generálása").click().run(timeout=20)
    assert not app.exception
    warning_text = " ".join(w.value for w in app.warning)
    assert "nem érhető el" in warning_text


def _render_bible_text_editor_with_generate_fn() -> None:
    import streamlit as st
    import bible_text_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot..."
    st.session_state["bible_translation"] = "RUF"

    def fake_generate(prompt: str, **kwargs) -> str:
        return "{}"

    bible_text_ui.render_bible_text_editor(greek_contextual_analysis_generate_fn=fake_generate)


@requires_syntax_store
def test_igehely_tab_bible_text_editor_forwards_greek_generate_fn() -> None:
    """The exact regression class the Hebrew Phase 2E wiring bug was: a
    call site silently not forwarding the generate_fn, making the whole
    section vanish with no error. Proven here for the Greek path, on the
    "Igehely" tab (bible_text_ui), the same call path that was broken for
    Hebrew."""
    app = AppTest.from_function(_render_bible_text_editor_with_generate_fn).run(timeout=20)
    assert not app.exception
    markdown_text = " ".join(m.value for m in app.markdown)
    assert "Nyelvtani és mondattani elemzés" in markdown_text
    assert any("Kontextuális elemzés generálása" in b.label for b in app.button)
