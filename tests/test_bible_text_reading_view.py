"""Formázott Bibliai szöveg olvasónézet — escape és versparser tesztek."""

from __future__ import annotations

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_text_ui import (
    DURABLE_SOURCE,
    DURABLE_SOURCE_CACHE_STATUS,
    RESYNC_FLAG,
    SOURCE_TYPE_CACHED_API,
    SOURCE_TYPE_EXTERNAL_API,
    SOURCE_TYPE_LOCAL_STORE,
    SOURCE_TYPE_USER_OVERRIDE,
    build_formatted_bible_text_html,
    format_passage_text_blocks,
    get_bible_text_snapshot,
    normalize_verse_number_spacing,
    parse_passage_text_blocks,
    save_bible_text_from_widgets,
)
from ruf_bible_service import SOURCE_ATTRIBUTION, SOURCE_NAME

errors: list[str] = []


def ok(cond: bool, msg: str) -> None:
    if not cond:
        errors.append(msg)


def session_value(session_state: object, key: str, default: object = "") -> object:
    return session_state[key] if key in session_state else default


def _render_empty_bible_text_editor() -> None:
    import streamlit as st

    import bible_text_ui

    st.session_state["igehely_input"] = "Jn 3,16"
    bible_text_ui.render_bible_text_editor()


def _render_editor_with_greek_text() -> None:
    import streamlit as st

    import bible_text_ui

    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "16. Mert úgy szerette Isten a világot."
    bible_text_ui.render_bible_text_editor()


def _render_editor_with_ruf_error() -> None:
    import streamlit as st

    import bible_text_ui

    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["_bible_text_ruf_last_error"] = (
        "Külső szolgáltatási kapcsolat hibája: mock hiba."
    )
    st.session_state["_bible_text_ruf_last_error_ref"] = "Jn 3,16"
    bible_text_ui.render_bible_text_editor()


def _ruf_result(reference: str, verses: list[tuple[int, str]]) -> dict[str, object]:
    return {
        "success": True,
        "requested_reference": reference,
        "normalized_reference": reference,
        "translation": "RÚF 2014",
        "text": "\n".join(f"{number}. {text}" for number, text in verses),
        "verses": [{"number": number, "text": text} for number, text in verses],
        "source_name": SOURCE_NAME,
        "source_url": f"https://szentiras.eu/api/idezet/{reference}/RUF",
        "copyright_notice": "Revideált új fordítás, © Magyar Bibliatársulat, 2014.",
        "warnings": [],
        "error": "",
        "cache_status": "live",
    }


def test_ruf_button_click_does_not_refetch_on_plain_rerun() -> None:
    import bible_text_ui

    calls: list[str] = []
    original_fetch = bible_text_ui.fetch_ruf_passage

    def fake_fetch(reference: str) -> dict[str, object]:
        calls.append(reference)
        return {
            "success": True,
            "requested_reference": reference,
            "normalized_reference": "Jn 3,16",
            "translation": "RÚF 2014",
            "text": "16. Mert úgy szerette Isten a világot.",
            "verses": [{"number": 16, "text": "Mert úgy szerette Isten a világot."}],
            "source_name": "szentiras.hu",
            "source_url": "https://szentiras.hu/biblia/ruf/JHN/3",
            "copyright_notice": "",
            "warnings": [],
            "error": "",
        }

    def render_editor() -> None:
        import streamlit as st

        import bible_text_ui

        st.session_state["igehely_input"] = "Jn 3,16"
        bible_text_ui.render_bible_text_editor()

    bible_text_ui.fetch_ruf_passage = fake_fetch
    try:
        app = AppTest.from_function(render_editor).run()
        app.button[0].click().run()
        assert calls == ["Jn 3,16"]

        app.run()
        assert calls == ["Jn 3,16"]
        assert app.session_state["passage_text"].startswith("16. Mert úgy szerette")
    finally:
        bible_text_ui.fetch_ruf_passage = original_fetch


def test_manual_text_area_is_hidden_by_default() -> None:
    app = AppTest.from_function(_render_empty_bible_text_editor).run()

    assert not app.exception
    assert len(app.text_area) == 0
    assert all(button.label != "Bibliai szöveg mentése" for button in app.button)
    assert any(
        expander.label == "Bibliai szöveg kézi beillesztése"
        for expander in app.expander
    )
    assert not any(SOURCE_ATTRIBUTION in markdown.value for markdown in app.markdown)


def test_manual_text_area_renders_when_expander_is_open() -> None:
    app = AppTest.from_function(_render_empty_bible_text_editor).run()

    app.session_state["_bible_text_manual_paste_expander"] = True
    app.run()

    assert len(app.text_area) == 1
    assert app.text_area[0].label == "Teljes bibliai szöveg"
    assert any(button.label == "Bibliai szöveg mentése" for button in app.button)


def test_manual_text_save_still_works_and_survives_rerun() -> None:
    state = {
        "igehely_input": "Jn 3,16",
        "passage_text_input": "16Mert úgy szerette Isten a világot.",
    }

    saved = save_bible_text_from_widgets(state)

    assert saved["passage_text"] == "16. Mert úgy szerette Isten a világot."
    assert state["passage_text"] == "16. Mert úgy szerette Isten a világot."
    assert state["passage_text_input"] == "16Mert úgy szerette Isten a világot."

    app = AppTest.from_function(_render_empty_bible_text_editor).run()
    app.session_state["_bible_text_manual_paste_expander"] = True
    app.session_state["passage_text_input"] = "16Mert úgy szerette Isten a világot."
    app.run()

    assert app.text_area[0].value == "16Mert úgy szerette Isten a világot."
    app.run()
    assert app.session_state["passage_text_input"] == "16Mert úgy szerette Isten a világot."


def test_successful_ruf_load_does_not_open_manual_section() -> None:
    import bible_text_ui

    original_fetch = bible_text_ui.fetch_ruf_passage

    def fake_fetch(reference: str) -> dict[str, object]:
        return {
            "success": True,
            "requested_reference": reference,
            "normalized_reference": "Jn 3,16",
            "translation": "RÚF 2014",
            "text": "16. Mert úgy szerette Isten a világot.",
            "verses": [{"number": 16, "text": "Mert úgy szerette Isten a világot."}],
            "source_name": "szentiras.hu",
            "source_url": "https://szentiras.hu/biblia/ruf/JHN/3",
            "copyright_notice": "",
            "warnings": [],
            "error": "",
        }

    bible_text_ui.fetch_ruf_passage = fake_fetch
    try:
        app = AppTest.from_function(_render_empty_bible_text_editor).run()
        app.button[0].click().run()

        assert len(app.text_area) == 0
        assert app.session_state["passage_text"].startswith("16. Mert")
    finally:
        bible_text_ui.fetch_ruf_passage = original_fetch


def test_szentiras_eu_ruf_load_preserves_source_attribution_and_text() -> None:
    import bible_text_ui

    original_fetch = bible_text_ui.fetch_ruf_passage

    def fake_fetch(reference: str) -> dict[str, object]:
        return {
            "success": True,
            "requested_reference": reference,
            "normalized_reference": "Ef 1,1–4",
            "translation": "RÚF 2014",
            "text": "1. Pál, Krisztus Jézus apostola.",
            "verses": [{"number": 1, "text": "Pál, Krisztus Jézus apostola."}],
            "source_name": SOURCE_NAME,
            "source_url": "https://szentiras.eu/api/idezet/Ef%201%2C1-4/RUF",
            "copyright_notice": "Revideált új fordítás, © Magyar Bibliatársulat, 2014.",
            "warnings": [],
            "error": "",
            "cache_status": "live",
        }

    def render_editor() -> None:
        import streamlit as st

        import bible_text_ui

        st.session_state["igehely_input"] = "Ef 1,1–4"
        bible_text_ui.render_bible_text_editor()

    bible_text_ui.fetch_ruf_passage = fake_fetch
    try:
        app = AppTest.from_function(render_editor).run()
        app.button[0].click().run()

        assert app.session_state["passage_text_source"] == SOURCE_TYPE_EXTERNAL_API
        markdown_values = [markdown.value for markdown in app.markdown]
        assert any("Pál, Krisztus Jézus apostola." in value for value in markdown_values)
        assert any(SOURCE_ATTRIBUTION in value for value in markdown_values)
        assert any("szentiras.eu/api/idezet/Ef%201%2C1-4/RUF" in value for value in markdown_values)
    finally:
        bible_text_ui.fetch_ruf_passage = original_fetch


def test_main_ui_ruf_load_survives_prefetch_flush_and_renders_luke_3() -> None:
    import bible_text_ui

    original_fetch = bible_text_ui.fetch_ruf_passage
    calls: list[str] = []

    def fake_fetch(reference: str) -> dict[str, object]:
        calls.append(reference)
        return _ruf_result(
            reference,
            [
                (1, "Tibérius császár uralkodásának tizenötödik évében."),
                (2, "Annás és Kajafás főpapok idején."),
                (3, "János hirdette a megtérés keresztségét."),
                (4, "Ahogyan meg van írva Ézsaiás próféta könyvében."),
                (5, "Minden völgyet töltsetek fel."),
                (6, "És meglátja minden halandó az Isten szabadítását."),
                (7, "A sokaságnak ezt mondta."),
                (8, "Teremjetek megtéréshez méltó gyümölcsöket."),
                (9, "A fejsze pedig már a fák gyökerén van."),
                (10, "Mit tegyünk tehát?"),
            ],
        )

    def render_main_like_editor() -> None:
        import streamlit as st

        import bible_text_ui

        st.session_state["igehely_input"] = "Lk 3,1-10"
        if bible_text_ui.KEY_PASSAGE_TEXT_INPUT in st.session_state:
            bible_text_ui.save_bible_text_from_widgets(st.session_state)
        bible_text_ui.render_bible_text_editor()

    bible_text_ui.fetch_ruf_passage = fake_fetch
    try:
        app = AppTest.from_function(render_main_like_editor).run()
        assert session_value(app.session_state, "passage_text_input", "") == ""

        app.button[0].click().run()

        assert calls == ["Lk 3,1-10"]
        assert app.session_state["passage_text"].startswith(
            "1. Tibérius császár uralkodásának"
        )
        assert app.session_state["passage_text_input"].startswith(
            "1. Tibérius császár uralkodásának"
        )
        assert app.session_state["passage_text_source"] == SOURCE_TYPE_EXTERNAL_API
        assert "10. Mit tegyünk tehát?" in app.session_state["passage_text"]
        markdown_values = [markdown.value for markdown in app.markdown]
        assert any("Tibérius császár uralkodásának" in value for value in markdown_values)
        assert any(SOURCE_ATTRIBUTION in value for value in markdown_values)

        app.run()
        markdown_values = [markdown.value for markdown in app.markdown]
        assert calls == ["Lk 3,1-10"]
        assert app.session_state["passage_text"].startswith(
            "1. Tibérius császár uralkodásának"
        )
        assert any("Tibérius császár uralkodásának" in value for value in markdown_values)
    finally:
        bible_text_ui.fetch_ruf_passage = original_fetch


def test_main_ui_ruf_load_renders_ephesians_in_both_views() -> None:
    import bible_text_ui

    original_fetch = bible_text_ui.fetch_ruf_passage

    def fake_fetch(reference: str) -> dict[str, object]:
        return _ruf_result(
            reference,
            [
                (1, "Kérlek tehát titeket."),
                (2, "Teljes alázatossággal."),
                (3, "Igyekezzetek megtartani."),
                (4, "Egy a test."),
                (5, "Egy az Úr."),
                (6, "Egy az Istene és Atyja mindeneknek."),
            ],
        )

    def render_editor() -> None:
        import streamlit as st

        import bible_text_ui

        st.session_state["igehely_input"] = "Ef 4,1-6"
        bible_text_ui.render_bible_text_editor()

    bible_text_ui.fetch_ruf_passage = fake_fetch
    try:
        app = AppTest.from_function(render_editor).run()
        app.button[0].click().run()
        line_values = [markdown.value for markdown in app.markdown]
        assert any("Kérlek tehát titeket." in value for value in line_values)
        assert any("bible-verse-num" in value for value in line_values)

        app.radio[0].set_value("Folyamatos nézet").run()
        continuous_values = [markdown.value for markdown in app.markdown]
        for needle in ("1.", "Kérlek tehát titeket.", "6.", "Egy az Istene"):
            assert any(needle in value for value in continuous_values)
        assert any("bible-inline-num" in value for value in continuous_values)
    finally:
        bible_text_ui.fetch_ruf_passage = original_fetch


def test_main_ui_ruf_load_renders_john_single_verse() -> None:
    import bible_text_ui

    original_fetch = bible_text_ui.fetch_ruf_passage

    def fake_fetch(reference: str) -> dict[str, object]:
        return _ruf_result(reference, [(16, "Mert úgy szerette Isten a világot.")])

    bible_text_ui.fetch_ruf_passage = fake_fetch
    try:
        app = AppTest.from_function(_render_empty_bible_text_editor).run()
        app.button[0].click().run()

        assert app.session_state["passage_text"] == "16. Mert úgy szerette Isten a világot."
        assert any(
            "Mert úgy szerette Isten a világot." in markdown.value
            for markdown in app.markdown
        )
    finally:
        bible_text_ui.fetch_ruf_passage = original_fetch


def test_empty_canonical_passage_does_not_set_success_flash() -> None:
    import bible_text_ui

    original_fetch = bible_text_ui.fetch_ruf_passage

    def fake_fetch(reference: str) -> dict[str, object]:
        return {
            "success": True,
            "requested_reference": reference,
            "normalized_reference": reference,
            "translation": "RÚF 2014",
            "text": "",
            "verses": [],
            "source_name": SOURCE_NAME,
            "source_url": "https://szentiras.eu/api/idezet/Jn%203%2C16/RUF",
            "warnings": [],
            "error": "",
        }

    bible_text_ui.fetch_ruf_passage = fake_fetch
    try:
        app = AppTest.from_function(_render_empty_bible_text_editor).run()
        app.button[0].click().run()

        assert not str(session_value(app.session_state, "passage_text", "") or "").strip()
        assert not any("betöltődött" in success.value for success in app.success)
        assert any(
            "nem tartalmazott megjeleníthető RÚF-szöveget" in error.value
            for error in app.error
        )
    finally:
        bible_text_ui.fetch_ruf_passage = original_fetch


def test_bible_widget_resync_prevents_stale_empty_widget_overwrite() -> None:
    state = {
        "igehely_input": "Lk 3,1-10",
        "passage_text": "1. Tibérius császár uralkodásának tizenötödik évében.",
        "passage_text_input": "",
        RESYNC_FLAG: True,
    }

    saved = save_bible_text_from_widgets(state)

    assert saved["passage_text"].startswith("1. Tibérius császár")
    assert state["passage_text"].startswith("1. Tibérius császár")
    assert state["passage_text_input"].startswith("1. Tibérius császár")


def test_ruf_error_does_not_open_manual_section() -> None:
    app = AppTest.from_function(_render_editor_with_ruf_error).run()

    assert not app.exception
    assert len(app.text_area) == 0
    assert any(button.label == "Újrapróbálás" for button in app.button)
    assert any(
        expander.label == "Bibliai szöveg kézi beillesztése"
        for expander in app.expander
    )


def test_greek_text_rendering_remains_available_with_manual_section_closed() -> None:
    app = AppTest.from_function(_render_editor_with_greek_text).run()

    assert not app.exception
    assert len(app.text_area) == 0
    assert any("Görög eredeti szöveg" in value for value in [m.value for m in app.markdown])


def test_missing_space_after_verse_number_is_normalized() -> None:
    blocks = parse_passage_text_blocks("16Mert úgy szerette Isten a világot.")

    assert blocks == [("16", "Mert úgy szerette Isten a világot.")]
    assert normalize_verse_number_spacing("16Mert úgy szerette Isten a világot.") == (
        "16. Mert úgy szerette Isten a világot."
    )


def test_already_formatted_verse_text_is_preserved() -> None:
    text = "16. Mert úgy szerette Isten a világot.\n17. Mert Isten nem azért küldte."

    assert normalize_verse_number_spacing(text) == text


def test_two_and_three_digit_verse_numbers_are_formatted() -> None:
    text = "22 Így szól az, aki ezekről bizonyságot tesz.\n100Dicsérjetek az Urat!"

    assert parse_passage_text_blocks(text) == [
        ("22", "Így szól az, aki ezekről bizonyságot tesz."),
        ("100", "Dicsérjetek az Urat!"),
    ]
    assert normalize_verse_number_spacing(text).splitlines() == [
        "22. Így szól az, aki ezekről bizonyságot tesz.",
        "100. Dicsérjetek az Urat!",
    ]


def test_manual_pasted_text_formats_without_touching_unicode() -> None:
    text = "1Nincsen azért most már semmiféle kárhoztató ítélet.\n2 mert az élet Lelkének törvénye."

    normalized = normalize_verse_number_spacing(text)

    assert normalized == (
        "1. Nincsen azért most már semmiféle kárhoztató ítélet.\n"
        "2. mert az élet Lelkének törvénye."
    )
    assert "ítélet" in normalized
    assert "Lelkének" in normalized


def test_formatted_html_has_separate_verse_number_span() -> None:
    markup = build_formatted_bible_text_html("16Mert úgy szerette Isten a világot.")

    assert '<span class="bible-verse-num">16.</span>' in markup
    assert "16Mert" not in markup
    assert "Mert úgy szerette Isten" in markup


def test_continuous_and_line_views_contain_same_text() -> None:
    text = "16. Mert úgy szerette Isten a világot.\n17. Mert Isten nem azért küldte."

    line_markup = build_formatted_bible_text_html(text, view_mode="Versenkénti nézet")
    continuous_markup = build_formatted_bible_text_html(text, view_mode="Folyamatos nézet")

    for needle in (
        "16.",
        "Mert úgy szerette Isten a világot.",
        "17.",
        "Mert Isten nem azért küldte.",
    ):
        assert needle in line_markup
        assert needle in continuous_markup
    assert "bible-inline-num" in continuous_markup


def test_embedded_cross_reference_anchor_is_stripped_not_shown_raw_or_escaped() -> None:
    """A bug jelentés pontos esete: a Szentírás.eu API néhány vers szövegébe
    közvetlenül beágyazott szakaszcím-/kereszthivatkozás-HTML-t ad vissza."""
    text = (
        "1. Péter halfogása <a href='Mt 4,18-22'>Mt 4,18-22</a>; "
        "<a href='Mk 1,16-20'>Mk 1,16-20</a> Miután pedig elvégezte a szólást."
    )
    markup = build_formatted_bible_text_html(text)

    assert "<a " not in markup
    assert "<a href" not in markup
    assert "&lt;a " not in markup
    assert "href=" not in markup
    assert "&lt;/a&gt;" not in markup


def test_section_heading_reference_text_remains_as_clean_readable_text() -> None:
    """A hivatkozás SZÖVEGE (pl. 'Mt 4,18-22') olvasható sima szövegként
    megmaradhat — csak a nyers HTML-jelölés tűnik el, nem az információ."""
    text = "1. Péter halfogása <a href='Mt 4,18-22'>Mt 4,18-22</a> Miután pedig."
    markup = build_formatted_bible_text_html(text)

    assert "Péter halfogása" in markup
    assert "Mt 4,18-22" in markup
    assert "Miután pedig" in markup


def test_verse_number_and_text_spacing_survives_tag_removal() -> None:
    """A tag eltávolítása nem hagyhat dupla szóközt vagy hiányzó szóközt a
    versszám és a szöveg, illetve a megmaradt szövegrészek között."""
    text = "1. Bevezetés <a href='Mt 4,18-22'>Mt 4,18-22</a> folytatás."
    markup = build_formatted_bible_text_html(text)

    assert "  " not in markup
    assert "Bevezetés Mt 4,18-22 folytatás." in markup
    assert '<span class="bible-verse-num">1.</span>' in markup


def test_normal_verse_text_without_any_markup_is_unaffected() -> None:
    """Sima, tag nélküli versszöveg tartalma és formázása változatlan."""
    text = "16. Mert úgy szerette Isten a világot, hogy egyszülött Fiát adta."
    markup = build_formatted_bible_text_html(text)

    assert "Mert úgy szerette Isten a világot, hogy egyszülött Fiát adta." in markup
    assert '<span class="bible-verse-num">16.</span>' in markup


def test_tag_stripping_applies_identically_in_both_view_modes() -> None:
    text = "1. Cím <a href='Mt 4,18-22'>Mt 4,18-22</a> szöveg."
    line_markup = build_formatted_bible_text_html(text, view_mode="Versenkénti nézet")
    continuous_markup = build_formatted_bible_text_html(text, view_mode="Folyamatos nézet")

    for markup in (line_markup, continuous_markup):
        assert "<a " not in markup
        assert "href=" not in markup
        assert "Cím Mt 4,18-22 szöveg." in markup


def test_raw_data_storage_helpers_are_untouched_by_the_display_fix() -> None:
    """A javítás kizárólag a megjelenítést érinti — a nyers szöveg
    feldolgozása (versszám-parsolás, sortörés-normalizálás) a beágyazott
    HTML-t érintetlenül hagyja, azt csak a megjelenítési réteg szűri ki."""
    text = "1. Cím <a href='X'>X</a> szöveg."
    blocks = parse_passage_text_blocks(text)
    assert blocks == [("1", "Cím <a href='X'>X</a> szöveg.")]
    normalized = normalize_verse_number_spacing(text)
    assert "<a href='X'>X</a>" in normalized


# --- 2026-09 audit fix: RÚF source metadata semantics ----------------------
#
# Root cause of the bug these guard against: _apply_ruf_fetch_success()
# labeled EVERY non-"live" cache_status (i.e. a process-memory cache hit,
# fresh or stale-fallback) as SOURCE_TYPE_LOCAL_STORE — but this module
# never reads ruf_bible_local_db's actual local SQLite store at all, so a
# saved project's passage_text_source metadata was misleading. The fix
# introduces SOURCE_TYPE_CACHED_API for the memory-cache case, and a
# separate DURABLE_SOURCE_CACHE_STATUS field carrying the raw
# fresh/stale_fallback distinction.

def _render_editor() -> None:
    import streamlit as st

    import bible_text_ui

    st.session_state["igehely_input"] = "Jn 3,16"
    bible_text_ui.render_bible_text_editor()


def _run_editor_with_fake_fetch(cache_status: str) -> AppTest:
    """Monkeypatches bible_text_ui.fetch_ruf_passage (module level, so the
    AppTest-executed script picks it up) and drives the real button-click
    flow — the same established pattern as
    test_szentiras_eu_ruf_load_preserves_source_attribution_and_text above."""
    import bible_text_ui

    original_fetch = bible_text_ui.fetch_ruf_passage

    def fake_fetch(reference: str) -> dict[str, object]:
        result = _ruf_result(reference, [(16, "Mert úgy szerette Isten a világot.")])
        result["cache_status"] = cache_status
        return result

    bible_text_ui.fetch_ruf_passage = fake_fetch
    try:
        app = AppTest.from_function(_render_editor).run()
        app.button[0].click().run()
        return app
    finally:
        bible_text_ui.fetch_ruf_passage = original_fetch


def test_live_api_result_is_labeled_external_api() -> None:
    app = _run_editor_with_fake_fetch("live")
    assert not app.exception
    assert app.session_state[DURABLE_SOURCE] == SOURCE_TYPE_EXTERNAL_API
    assert app.session_state[DURABLE_SOURCE_CACHE_STATUS] == "live"


def test_fresh_memory_cache_result_is_labeled_cached_api_not_local_store() -> None:
    app = _run_editor_with_fake_fetch("fresh")
    assert not app.exception
    assert app.session_state[DURABLE_SOURCE] == SOURCE_TYPE_CACHED_API
    assert app.session_state[DURABLE_SOURCE] != SOURCE_TYPE_LOCAL_STORE
    assert app.session_state[DURABLE_SOURCE_CACHE_STATUS] == "fresh"


def test_stale_fallback_result_is_labeled_cached_api_and_distinguishable_from_fresh() -> None:
    app = _run_editor_with_fake_fetch("stale_fallback")
    assert not app.exception
    assert app.session_state[DURABLE_SOURCE] == SOURCE_TYPE_CACHED_API
    # The coarse source type alone no longer distinguishes fresh from
    # stale — that is exactly what the separate cache-status field is for.
    assert app.session_state[DURABLE_SOURCE_CACHE_STATUS] == "stale_fallback"


def test_old_saved_project_with_legacy_local_store_value_still_loads() -> None:
    """A project saved BEFORE this fix may have passage_text_source ==
    "local_store" persisted from a cache hit. Loading it must not break,
    and get_bible_text_snapshot must still surface that legacy value
    verbatim (no silent/forced rewrite of already-saved data), even
    though the new cache-status field never existed in that old project."""
    state = {
        "last_igehely": "Jn 3,16",
        "passage_text": "16. Mert úgy szerette Isten a világot.",
        "passage_text_source": "local_store",
        "passage_text_source_url": "",
        # Legacy project predates the cache-status field entirely — no
        # "passage_text_cache_status" key at all.
    }
    snap = get_bible_text_snapshot(state)
    assert snap["passage_text_source"] == SOURCE_TYPE_LOCAL_STORE
    assert snap["passage_text_cache_status"] == ""  # missing key defaults empty, no crash


def test_user_override_clears_cache_status() -> None:
    """Manually overriding the text must not leave a stale cache_status
    from a PRIOR fetch lingering behind a now-unrelated user_override
    source."""
    import bible_text_ui

    state = {
        "igehely_input": "Jn 3,16",
        DURABLE_SOURCE: SOURCE_TYPE_CACHED_API,
        DURABLE_SOURCE_CACHE_STATUS: "fresh",
        "passage_text_last_fetched_text": "16. Eredeti szöveg.",
        "passage_text_input": "16. Kézzel átírt szöveg.",
    }

    bible_text_ui.save_bible_text_from_widgets(state)

    assert state[DURABLE_SOURCE] == SOURCE_TYPE_USER_OVERRIDE
    assert state[DURABLE_SOURCE_CACHE_STATUS] == ""


def main() -> None:
    # Versszám formák
    blocks = parse_passage_text_blocks(
        "17 Ti azonban, szeretteim...\n"
        "18. Azt mondták ugyanis...\n"
        "19  Ezek szakadásokat okoznak...\n"
        "Bevezető megjegyzés sortörés nélkül\n"
        "20 Ti azonban, szeretteim..."
    )
    ok(blocks[0] == ("17", "Ti azonban, szeretteim..."), f"b0 {blocks[0]}")
    ok(blocks[1] == ("18", "Azt mondták ugyanis..."), f"b1 {blocks[1]}")
    ok(blocks[2] == ("19", "Ezek szakadásokat okoznak..."), f"b2 {blocks[2]}")
    ok(blocks[3] == (None, "Bevezető megjegyzés sortörés nélkül"), f"b3 {blocks[3]}")
    ok(blocks[4] == ("20", "Ti azonban, szeretteim..."), f"b4 {blocks[4]}")

    # HTML tag stripping (2026-08-19 korrekció): a beágyazott tagek — akár
    # kereszthivatkozás-anchor, akár bármi más — sem nyersen, sem escape-elt
    # formában nem maradhatnak láthatók; a szöveges tartalom megmarad.
    markup = build_formatted_bible_text_html('16 <script>alert("x")</script> & "idézet"')
    ok("<script>" not in markup, "script tag must not appear raw")
    ok("&lt;script&gt;" not in markup, "script tag must not appear escaped either — stripped")
    ok("&amp;" in markup, "amp in remaining plain text still escaped")
    ok("bible-verse-num" in markup and "bible-verse-text" in markup, "structure")
    ok("alert" in markup, "tag-free text content preserved")

    # Üres
    ok(build_formatted_bible_text_html("   \n  ") == "", "empty")

    # Hosszú sor — struktúra megmarad
    long = "1 " + ("szó " * 80)
    m = build_formatted_bible_text_html(long)
    ok("bible-verse-text" in m, "long verse")
    ok("table" not in m.lower(), "no table")

    # Júd jellegű 4 vers
    jude = (
        "17 Ti azonban, szeretteim, emlékezzetek meg...\n"
        "18 Azt mondták ugyanis...\n"
        "19 Ezek szakadásokat okoznak...\n"
        "20 Ti azonban, szeretteim, épüljetek..."
    )
    jb = parse_passage_text_blocks(jude)
    ok(len(jb) == 4, "jude 4")
    ok([n for n, _ in jb] == ["17", "18", "19", "20"], "jude nums")

    if errors:
        print("FAIL")
        for e in errors:
            print(" -", e)
        raise SystemExit(1)
    print("OK bible reading view tests passed")


if __name__ == "__main__":
    main()
