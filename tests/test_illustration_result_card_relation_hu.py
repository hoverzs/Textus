"""AppTest-based rendering checks for the "Kapcsolódás az igéhez: ..."
relation explanation in illustration_retrieval_ui._render_result_card
(Phase 14, 2026-09-13) -- reuses the same AppTest.from_function pattern
already established by tests/test_writing_desk_ui.py."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _render_card_with_relation() -> None:
    import illustration_retrieval_ui as ui
    from illustration_engine.retrieval import IllustrationRetrievalResult

    item = IllustrationRetrievalResult(
        unit_id=1, title_hu="Cím", modern_hu_text="Teljes szöveg.", summary_hu="Rövid összegzés.",
        moral_hu=None, topics=(), tone=None, homiletic_functions=(), source_title="Forrás",
        source_attribution="Forrás · hagyomány", provenance_status="published",
        rank_reason="Az apa feltétel nélküli visszafogadása miatt kapcsolódik.", rank_score=0.9,
        match_tier="DIRECT_ANALOGY", relation_hu="Az apa feltétel nélküli visszafogadása miatt kapcsolódik.",
    )
    ui._render_result_card(item)


def _render_card_without_relation() -> None:
    import illustration_retrieval_ui as ui
    from illustration_engine.retrieval import IllustrationRetrievalResult

    item = IllustrationRetrievalResult(
        unit_id=1, title_hu="Cím", modern_hu_text="Teljes szöveg.", summary_hu="Rövid összegzés.",
        moral_hu=None, topics=(), tone=None, homiletic_functions=(), source_title="Forrás",
        source_attribution="Forrás · hagyomány", provenance_status="published",
        rank_reason="", rank_score=0.9, match_tier="WEAK", relation_hu="",
    )
    ui._render_result_card(item)


def _render_card_whitespace_only_relation() -> None:
    """Defends against a relation_hu that survived parsing as pure
    whitespace (e.g. the LLM returned " ") -- must be treated the same
    as empty, never rendered as a blank label."""
    import illustration_retrieval_ui as ui
    from illustration_engine.retrieval import IllustrationRetrievalResult

    item = IllustrationRetrievalResult(
        unit_id=1, title_hu="Cím", modern_hu_text="Teljes szöveg.", summary_hu="Rövid összegzés.",
        moral_hu=None, topics=(), tone=None, homiletic_functions=(), source_title="Forrás",
        source_attribution="Forrás · hagyomány", provenance_status="published",
        rank_reason="   ", rank_score=0.9, match_tier="WEAK", relation_hu="   ",
    )
    ui._render_result_card(item)


def _page_markdown(app: AppTest) -> str:
    return "\n".join(m.value for m in app.markdown)


def test_result_card_shows_relation_hu_between_summary_and_expander() -> None:
    app = AppTest.from_function(_render_card_with_relation).run()
    assert not app.exception
    text = _page_markdown(app)
    assert "Kapcsolódás az igéhez:" in text
    assert "Az apa feltétel nélküli visszafogadása miatt kapcsolódik." in text


def test_result_card_without_relation_hu_does_not_crash_or_show_label() -> None:
    """Malformed/missing relation_hu must never break the result card --
    the label is simply omitted, fail-safe."""
    app = AppTest.from_function(_render_card_without_relation).run()
    assert not app.exception
    text = _page_markdown(app)
    assert "Kapcsolódás az igéhez:" not in text


def test_result_card_whitespace_only_relation_hu_not_shown() -> None:
    app = AppTest.from_function(_render_card_whitespace_only_relation).run()
    assert not app.exception
    text = _page_markdown(app)
    assert "Kapcsolódás az igéhez:" not in text
