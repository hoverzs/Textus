"""Íróasztal shell + RÚF / eredeti nyelvi olvasóblokk tesztek."""

from __future__ import annotations

import re
from contextlib import nullcontext
from pathlib import Path

from streamlit.testing.v1 import AppTest

import writing_desk_ui
from writing_desk_ui import (
    WRITING_DESK_BIBLE_VIEW_KEY,
    WRITING_DESK_DRAFT_RESYNC_FLAG,
    WRITING_DESK_DRAFT_REVISION_KEY,
    WRITING_DESK_DRAFT_WIDGET_KEY,
    WRITING_DESK_LABEL,
    WRITING_DESK_MODE,
    WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX,
)
from writing_desk_data import (
    draft_html_for_editor,
    draft_visible_text,
    plain_text_to_draft_html,
    writing_desk_draft_widget_html,
)


def _patch_streamlit_shell(
    monkeypatch,
    st,
    session: dict | None = None,
    *,
    click_key: str | None = None,
) -> dict[str, list]:
    calls: dict[str, list] = {
        "columns": [],
        "markdown": [],
        "caption": [],
        "radio": [],
        "buttons": [],
        "rerun": [],
        "text_area": [],
        "draft_editor": [],
        "download_button": [],
        "chat_input": [],
        "chat_message": [],
    }
    monkeypatch.setattr(st, "session_state", session if session is not None else {})
    monkeypatch.setattr(st, "container", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(st, "spinner", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        st,
        "caption",
        lambda body, *args, **kwargs: calls["caption"].append(str(body)),
    )
    monkeypatch.setattr(
        st,
        "rerun",
        lambda *args, **kwargs: calls["rerun"].append(True),
    )

    def _columns(spec, *args, **kwargs):
        calls["columns"].append((spec, kwargs.get("gap")))
        n = spec if isinstance(spec, int) else len(spec)
        return [nullcontext() for _ in range(n)]

    def _markdown(body, *args, **kwargs):
        calls["markdown"].append(str(body))

    def _radio(label, options, *args, **kwargs):
        calls["radio"].append(kwargs.get("key"))
        return options[0]

    def _button(label, *args, **kwargs):
        key = kwargs.get("key")
        calls["buttons"].append((str(label), key))
        return bool(click_key) and key == click_key

    def _text_area(label, *args, **kwargs):
        key = kwargs.get("key")
        value = args[0] if args else kwargs.get("value")
        if key and key in st.session_state:
            value = st.session_state[key]
        elif value is None:
            value = ""
        if key is not None:
            st.session_state[key] = value
        calls["text_area"].append(
            {
                "label": str(label),
                "key": key,
                "value": value,
                "height": kwargs.get("height"),
                "placeholder": kwargs.get("placeholder"),
                "on_change": kwargs.get("on_change"),
            }
        )
        return value

    def _draft_editor(*, html, revision, key, on_html_change=None, height=700):
        calls["draft_editor"].append(
            {
                "html": html,
                "revision": revision,
                "key": key,
                "height": height,
                "on_html_change": on_html_change,
            }
        )
        if key is not None and key not in st.session_state:
            st.session_state[key] = {"html": html}

    def _download_button(label, *args, **kwargs):
        calls["download_button"].append(
            {
                "label": str(label),
                "file_name": kwargs.get("file_name"),
                "disabled": bool(kwargs.get("disabled")),
                "key": kwargs.get("key"),
                "data": kwargs.get("data", args[0] if args else None),
            }
        )
        return False

    def _chat_input(placeholder="", *args, **kwargs):
        calls["chat_input"].append(
            {"placeholder": str(placeholder), "key": kwargs.get("key")}
        )
        return None

    def _chat_message(role, *args, **kwargs):
        calls["chat_message"].append(str(role))
        return nullcontext()

    monkeypatch.setattr(st, "columns", _columns)
    monkeypatch.setattr(st, "markdown", _markdown)
    monkeypatch.setattr(st, "radio", _radio)
    monkeypatch.setattr(st, "button", _button)
    monkeypatch.setattr(st, "text_area", _text_area)
    monkeypatch.setattr(st, "download_button", _download_button)
    monkeypatch.setattr(st, "chat_input", _chat_input)
    monkeypatch.setattr(st, "chat_message", _chat_message)
    monkeypatch.setattr(writing_desk_ui, "writing_desk_draft_editor", _draft_editor)
    return calls


def _joined_markdown(calls: dict[str, list]) -> str:
    return "\n".join(str(item) for item in calls.get("markdown", []))


def _widget_visible(session: dict) -> str:
    return draft_visible_text(
        writing_desk_draft_widget_html(session.get(WRITING_DESK_DRAFT_WIDGET_KEY))
    )


def test_writing_desk_shell_stacks_notes_above_work_material(monkeypatch):
    import streamlit as st

    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st)

    writing_desk_ui.render_writing_desk_shell()

    joined = _joined_markdown(calls)
    assert calls["columns"][0] == (3, "small")
    assert "Íróasztal" in joined
    assert "Munkaanyag" in joined
    assert "Jegyzet / vázlat" in joined
    assert "Eredeti szöveg" in joined
    assert "Kortörténet" in joined
    assert "Teológia" in joined
    assert joined.index("Jegyzet / vázlat") < joined.index("Munkaanyag")
    src = Path(writing_desk_ui.__file__).read_text(encoding="utf-8")
    assert src.find('title="Bibliai szöveg és eredeti nyelv"') < src.find(
        'title="Jegyzet / vázlat"'
    )
    assert src.find('title="Jegyzet / vázlat"') < src.find('title="Munkaanyag"')
    assert src.find('title="Munkaanyag"') < src.find('title="Segítő chat"')
    assert "Letöltés DOCX" in {item["label"] for item in calls["download_button"]}
    assert calls["chat_input"]
    assert "st.columns([1, 2]" not in src
    assert "st.columns(3, gap=\"small\")" in src
    assert "A jegyzet- és vázlatszerkesztő a következő fázisban kerül ide." not in joined
    assert "Szerkesztő helye" not in joined
    assert calls["text_area"] == []
    assert calls["draft_editor"]
    assert calls["draft_editor"][0]["key"] == WRITING_DESK_DRAFT_WIDGET_KEY
    assert calls["draft_editor"][0]["height"] == 700
    assert calls["draft_editor"][0]["on_html_change"] is (
        writing_desk_ui._on_writing_desk_draft_change
    )


def test_writing_desk_renders_ruf_reading_block(monkeypatch):
    import streamlit as st

    import bible_text_ui

    ruf_texts: list[str] = []
    ruf_view_keys: list[str | None] = []
    orig_calls: list[dict] = []

    def _capture_ruf(text, **kwargs):
        ruf_texts.append(str(text))
        ruf_view_keys.append(kwargs.get("view_key"))

    monkeypatch.setattr(
        bible_text_ui,
        "render_formatted_bible_text",
        _capture_ruf,
    )
    monkeypatch.setattr(
        bible_text_ui,
        "render_greek_analysis_block",
        lambda **kwargs: orig_calls.append(kwargs),
    )

    session = {
        "last_igehely": "Jn 3,16",
        "passage_text": "16. Mert úgy szerette Isten a világot.",
        "bible_translation": "RÚF 2014",
    }
    calls = _patch_streamlit_shell(monkeypatch, st, session)

    writing_desk_ui.render_writing_desk_shell()

    assert ruf_texts == ["16. Mert úgy szerette Isten a világot."]
    assert ruf_view_keys == [WRITING_DESK_BIBLE_VIEW_KEY]
    assert orig_calls[0]["reference"] == "Jn 3,16"
    assert orig_calls[0]["key_prefix"] == WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX
    assert orig_calls[0]["display_mode"] == "compact"
    joined = _joined_markdown(calls)
    assert "Jn 3,16" in joined
    assert "RÚF 2014" in joined
    assert "Munkaanyag" in joined


def test_writing_desk_nt_routes_to_greek_not_hebrew(monkeypatch):
    import streamlit as st

    import bible_engine.greek_analysis_ui as greek_analysis_ui
    import hebrew_text_demo

    greek_refs: list[str] = []
    hebrew_calls: list[tuple] = []

    monkeypatch.setattr(
        greek_analysis_ui,
        "load_greek_passage_tokens",
        lambda reference: greek_refs.append(reference) or [],
    )
    monkeypatch.setattr(
        hebrew_text_demo,
        "render_hebrew_original_language_reference",
        lambda *args, **kwargs: hebrew_calls.append((args, kwargs)),
    )

    session = {
        "last_igehely": "Jn 3,16",
        "passage_text": "16. Mert úgy szerette Isten a világot.",
    }
    calls = _patch_streamlit_shell(monkeypatch, st, session)

    writing_desk_ui.render_writing_desk_shell()

    assert greek_refs == ["Jn 3,16"]
    assert hebrew_calls == []
    assert WRITING_DESK_BIBLE_VIEW_KEY in calls["radio"]
    assert "Munkaanyag" in _joined_markdown(calls)


def test_writing_desk_ot_routes_to_hebrew_not_greek(monkeypatch):
    import streamlit as st

    import bible_engine.greek_analysis_ui as greek_analysis_ui
    import hebrew_text_demo

    greek_refs: list[str] = []
    hebrew_calls: list[tuple] = []

    monkeypatch.setattr(
        greek_analysis_ui,
        "load_greek_passage_tokens",
        lambda reference: greek_refs.append(reference) or [],
    )

    def _hebrew(reference, *, key_prefix, **kwargs):
        hebrew_calls.append((reference, key_prefix, kwargs.get("display_mode")))

    monkeypatch.setattr(
        hebrew_text_demo,
        "render_hebrew_original_language_reference",
        _hebrew,
    )

    session = {
        "last_igehely": "Zsolt 23,1",
        "passage_text": "1. Az Úr az én pásztorom.",
    }
    calls = _patch_streamlit_shell(monkeypatch, st, session)

    writing_desk_ui.render_writing_desk_shell()

    assert greek_refs == []
    assert hebrew_calls == [
        ("Zsolt 23,1", WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX, "compact")
    ]
    assert "Munkaanyag" in _joined_markdown(calls)
    assert "Jegyzet / vázlat" in _joined_markdown(calls)


def test_missing_ruf_with_reference_still_renders_original_language(monkeypatch):
    import streamlit as st

    import bible_text_ui

    orig_calls: list[dict] = []
    monkeypatch.setattr(
        bible_text_ui,
        "render_formatted_bible_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("empty RÚF text should not be formatted")
        ),
    )
    monkeypatch.setattr(
        bible_text_ui,
        "render_greek_analysis_block",
        lambda **kwargs: orig_calls.append(kwargs),
    )

    calls = _patch_streamlit_shell(
        monkeypatch,
        st,
        {"last_igehely": "Jn 3,16", "passage_text": ""},
    )
    writing_desk_ui.render_writing_desk_shell()

    assert orig_calls[0]["reference"] == "Jn 3,16"
    assert orig_calls[0]["key_prefix"] == WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX
    assert orig_calls[0]["display_mode"] == "compact"
    assert any("Még nincs RÚF szöveg" in caption for caption in calls["caption"])
    assert "Munkaanyag" in _joined_markdown(calls)
    assert "Jegyzet / vázlat" in _joined_markdown(calls)


def test_missing_ruf_or_original_language_does_not_block_shell(monkeypatch):
    import streamlit as st

    calls = _patch_streamlit_shell(monkeypatch, st, {})
    writing_desk_ui.render_writing_desk_shell()

    joined = _joined_markdown(calls)
    assert "Munkaanyag" in joined
    assert "Jegyzet / vázlat" in joined
    assert "Teológia" in joined
    assert any("Nincs megadott igehely" in caption for caption in calls["caption"])

    def _boom(*args, **kwargs):
        raise RuntimeError("scripture unavailable")

    monkeypatch.setattr(writing_desk_ui, "render_bible_text_reading_block", _boom)
    failing = _patch_streamlit_shell(
        monkeypatch,
        st,
        {"last_igehely": "Jn 3,16", "passage_text": "16. szöveg"},
    )
    writing_desk_ui.render_writing_desk_shell()
    failed_joined = _joined_markdown(failing)
    assert "Munkaanyag" in failed_joined
    assert "Jegyzet / vázlat" in failed_joined
    assert "A bibliai szöveg most nem jeleníthető meg" in failed_joined


def test_writing_desk_uses_unique_original_language_widget_keys():
    src = Path(writing_desk_ui.__file__).read_text(encoding="utf-8")
    assert WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX == "writing_desk_original_language"
    assert WRITING_DESK_BIBLE_VIEW_KEY == "writing_desk_bible_text_view_mode"
    assert "bible_text_ui" not in WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX
    assert "textus_original_language" not in src
    assert 'key_prefix="bible_text_ui"' not in src
    assert "render_bible_text_editor" not in src
    assert "generate_text" not in src
    assert 'display_mode="compact"' in src

    app_src = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")
    assert 'display_mode="compact"' not in app_src


def test_writing_desk_ui_mode_is_not_a_durable_session_key():
    from workspace_data import EXCLUDED_SESSION_KEYS, PROJECT_DATA_KEYS, PROJECT_NESTED_KEYS
    from writing_desk_data import WRITING_DESK_KEY

    assert "ui_mode" in EXCLUDED_SESSION_KEYS
    assert WRITING_DESK_DRAFT_WIDGET_KEY in EXCLUDED_SESSION_KEYS
    assert WRITING_DESK_DRAFT_RESYNC_FLAG in EXCLUDED_SESSION_KEYS
    assert "_wd_draft_resync_bumped" in EXCLUDED_SESSION_KEYS
    assert WRITING_DESK_DRAFT_REVISION_KEY in EXCLUDED_SESSION_KEYS
    from writing_desk_chat import WRITING_DESK_CHAT_INPUT_KEY, WRITING_DESK_CHAT_KEY

    # 2026-09 audit fix: the Segítő chat is now part of the persisted
    # project (PROJECT_NESTED_KEYS), not excluded — only its live input
    # widget key stays session-only, same as every other widget key here.
    assert WRITING_DESK_CHAT_KEY not in EXCLUDED_SESSION_KEYS
    assert WRITING_DESK_CHAT_KEY in PROJECT_DATA_KEYS
    assert WRITING_DESK_CHAT_KEY in PROJECT_NESTED_KEYS
    assert WRITING_DESK_CHAT_INPUT_KEY in EXCLUDED_SESSION_KEYS
    assert "writing_desk_docx_download" in EXCLUDED_SESSION_KEYS
    assert WRITING_DESK_KEY in PROJECT_DATA_KEYS
    assert WRITING_DESK_KEY in PROJECT_NESTED_KEYS
    assert WRITING_DESK_KEY == WRITING_DESK_MODE
    assert WRITING_DESK_LABEL == "Íróasztal"


def test_notes_editor_loads_existing_draft(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY, set_writing_desk_draft

    session: dict = {}
    set_writing_desk_draft(session, "Meglévő vázlat\nmásodik sor")
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell()

    expected_html = plain_text_to_draft_html("Meglévő vázlat\nmásodik sor")
    assert calls["draft_editor"][0]["key"] == WRITING_DESK_DRAFT_WIDGET_KEY
    assert calls["draft_editor"][0]["html"] == expected_html
    assert calls["draft_editor"][0]["revision"] == 0
    assert calls["draft_editor"][0]["on_html_change"] is writing_desk_ui._on_writing_desk_draft_change
    assert session[WRITING_DESK_KEY]["draft"]["content"] == (
        "Meglévő vázlat\nmásodik sor"
    )
    assert _widget_visible(session).replace("\n", "") == "Meglévő vázlatmásodik sor"


def test_notes_edit_updates_writing_desk_draft_and_survives_rerun(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY

    session: dict = {}
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == ""

    session[WRITING_DESK_DRAFT_WIDGET_KEY] = {
        "html": "<p>Gépelt jegyzet<br>új sor</p>"
    }
    writing_desk_ui.render_writing_desk_shell()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == (
        "<p>Gépelt jegyzet<br>új sor</p>"
    )

    revision_before = session.get(WRITING_DESK_DRAFT_REVISION_KEY, 0)
    writing_desk_ui.render_writing_desk_shell()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == (
        "<p>Gépelt jegyzet<br>új sor</p>"
    )
    assert session.get(WRITING_DESK_DRAFT_REVISION_KEY, 0) == revision_before
    assert "Gépelt jegyzet" in _widget_visible(session)


def test_notes_widget_shows_new_project_draft_after_switch(monkeypatch):
    import streamlit as st

    from writing_desk_data import (
        WRITING_DESK_KEY,
        normalize_writing_desk,
        set_writing_desk_draft,
    )

    session: dict = {}
    set_writing_desk_draft(session, "Projekt A jegyzet")
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell()
    assert "Projekt A jegyzet" in _widget_visible(session)
    revision_a = calls["draft_editor"][-1]["revision"]

    session[WRITING_DESK_KEY] = normalize_writing_desk(
        {"draft": {"content": "Projekt B jegyzet"}}
    )
    session[WRITING_DESK_DRAFT_RESYNC_FLAG] = True
    writing_desk_ui.render_writing_desk_shell()
    assert "Projekt B jegyzet" in _widget_visible(session)
    assert session[WRITING_DESK_KEY]["draft"]["content"] == "Projekt B jegyzet"
    assert WRITING_DESK_DRAFT_RESYNC_FLAG not in session
    assert calls["draft_editor"][-1]["revision"] == revision_a + 1


def test_on_change_commit_updates_durable_draft_before_unmount(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY, set_writing_desk_extract

    session: dict = {}
    set_writing_desk_extract(
        session,
        "history",
        content="Rövid kortörténeti kivonat.",
        source_fingerprint="abc",
    )
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell()

    session[WRITING_DESK_DRAFT_WIDGET_KEY] = "Íróasztal jegyzet\n\nmásodik bekezdés"
    writing_desk_ui.commit_writing_desk_draft_from_widget()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == (
        "Íróasztal jegyzet\n\nmásodik bekezdés"
    )
    assert (
        session[WRITING_DESK_KEY]["extracts"]["history"]["content"]
        == "Rövid kortörténeti kivonat."
    )

    session.pop(WRITING_DESK_DRAFT_WIDGET_KEY, None)
    assert WRITING_DESK_DRAFT_WIDGET_KEY not in session
    assert session[WRITING_DESK_KEY]["draft"]["content"] == (
        "Íróasztal jegyzet\n\nmásodik bekezdés"
    )

    writing_desk_ui.render_writing_desk_shell()
    assert "Íróasztal jegyzet" in _widget_visible(session)
    assert "második bekezdés" in _widget_visible(session)
    assert session[WRITING_DESK_KEY]["draft"]["content"] == (
        "Íróasztal jegyzet\n\nmásodik bekezdés"
    )
    assert (
        session[WRITING_DESK_KEY]["extracts"]["history"]["content"]
        == "Rövid kortörténeti kivonat."
    )


def test_commit_skips_stale_widget_during_project_resync(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY, set_writing_desk_draft

    session: dict = {
        WRITING_DESK_DRAFT_WIDGET_KEY: {"html": "<p>Projekt A stale widget</p>"},
        WRITING_DESK_DRAFT_RESYNC_FLAG: True,
        "_pending_project_widget_sync": {
            WRITING_DESK_DRAFT_WIDGET_KEY: "Projekt B jegyzet",
        },
    }
    set_writing_desk_draft(session, "Projekt B jegyzet")
    monkeypatch.setattr(st, "session_state", session)

    writing_desk_ui.commit_writing_desk_draft_from_widget()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == "Projekt B jegyzet"
    assert session[WRITING_DESK_DRAFT_WIDGET_KEY] == {
        "html": "<p>Projekt A stale widget</p>"
    }


def test_flush_is_noop_while_resync_flag_is_set(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY, set_writing_desk_draft

    session: dict = {
        WRITING_DESK_DRAFT_WIDGET_KEY: {"html": "<p>Stale CCv2 HTML</p>"},
        WRITING_DESK_DRAFT_RESYNC_FLAG: True,
    }
    set_writing_desk_draft(session, "")
    monkeypatch.setattr(st, "session_state", session)

    writing_desk_ui.flush_writing_desk_draft_from_widget()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == ""
    assert session.get(WRITING_DESK_DRAFT_RESYNC_FLAG) is True
    assert session[WRITING_DESK_DRAFT_WIDGET_KEY] == {"html": ""}


def test_flush_is_noop_while_pending_project_sync(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY, set_writing_desk_draft

    session: dict = {
        WRITING_DESK_DRAFT_WIDGET_KEY: {"html": "<p>Stale CCv2 HTML</p>"},
        "_pending_project_widget_sync": {
            WRITING_DESK_DRAFT_WIDGET_KEY: {"html": ""},
        },
    }
    set_writing_desk_draft(session, "")
    monkeypatch.setattr(st, "session_state", session)

    writing_desk_ui.flush_writing_desk_draft_from_widget()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == ""
    assert session["_pending_project_widget_sync"]


def test_callback_is_noop_while_resync_pending(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY, set_writing_desk_draft

    session: dict = {
        WRITING_DESK_DRAFT_WIDGET_KEY: {"html": "<p>Stale CCv2 HTML</p>"},
        WRITING_DESK_DRAFT_RESYNC_FLAG: True,
        "_pending_project_widget_sync": {
            WRITING_DESK_DRAFT_WIDGET_KEY: {"html": ""},
        },
    }
    set_writing_desk_draft(session, "")
    monkeypatch.setattr(st, "session_state", session)

    writing_desk_ui._on_writing_desk_draft_change()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == ""


def test_new_work_stale_ccv2_state_does_not_restore_draft(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY, set_writing_desk_draft

    session: dict = {}
    set_writing_desk_draft(session, "<p>Előző dokumentum</p>")
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell()
    revision_before = calls["draft_editor"][-1]["revision"]

    import app as app_mod

    monkeypatch.setattr(app_mod.st, "session_state", session)
    monkeypatch.setattr(app_mod, "_reset_language_grounding_warnings", lambda: None)
    app_mod._clear_workspace_content()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == ""
    assert session.get(WRITING_DESK_DRAFT_RESYNC_FLAG) is True

    session[WRITING_DESK_DRAFT_WIDGET_KEY] = {
        "html": "<p>Előző dokumentum</p>"
    }
    writing_desk_ui._on_writing_desk_draft_change()
    app_mod._apply_pending_project_widget_sync()
    writing_desk_ui.flush_writing_desk_draft_from_widget()
    writing_desk_ui.render_writing_desk_shell()

    assert session[WRITING_DESK_KEY]["draft"]["content"] == ""
    assert calls["draft_editor"][-1]["html"] == ""
    assert calls["draft_editor"][-1]["revision"] == revision_before + 1
    assert WRITING_DESK_DRAFT_RESYNC_FLAG not in session
    assert "Előző dokumentum" not in _widget_visible(session)


def test_project_switch_stale_widget_does_not_restore_previous_draft(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY, set_writing_desk_draft

    session: dict = {}
    set_writing_desk_draft(session, "Projekt A jegyzet")
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell()

    import app as app_mod

    monkeypatch.setattr(app_mod.st, "session_state", session)
    monkeypatch.setattr(app_mod, "_reset_language_grounding_warnings", lambda: None)
    app_mod._apply_project_data_to_session({"last_igehely": "Zsolt 23,1"})
    session[WRITING_DESK_DRAFT_WIDGET_KEY] = {
        "html": "<p>Projekt A jegyzet</p>"
    }
    writing_desk_ui._on_writing_desk_draft_change()
    app_mod._apply_pending_project_widget_sync()
    writing_desk_ui.flush_writing_desk_draft_from_widget()
    writing_desk_ui.render_writing_desk_shell()

    assert session[WRITING_DESK_KEY]["draft"]["content"] == ""
    assert calls["draft_editor"][-1]["html"] == ""
    assert "Projekt A jegyzet" not in _widget_visible(session)


def test_import_without_draft_stale_widget_does_not_restore(monkeypatch):
    import json

    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY, set_writing_desk_draft

    session: dict = {}
    set_writing_desk_draft(session, "Előző projekt jegyzete")
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell()

    import app as app_mod

    monkeypatch.setattr(app_mod.st, "session_state", session)
    monkeypatch.setattr(app_mod, "_reset_language_grounding_warnings", lambda: None)
    raw = json.dumps(
        {"_app": "Textus", "last_igehely": "Róm 8,1"},
        ensure_ascii=False,
    ).encode("utf-8")
    ok, _info = app_mod.deserialize_workspace(raw)
    assert ok is True
    session[WRITING_DESK_DRAFT_WIDGET_KEY] = {
        "html": "<p>Előző projekt jegyzete</p>"
    }
    writing_desk_ui._on_writing_desk_draft_change()
    app_mod._apply_pending_project_widget_sync()
    writing_desk_ui.flush_writing_desk_draft_from_widget()
    writing_desk_ui.render_writing_desk_shell()

    assert session[WRITING_DESK_KEY]["draft"]["content"] == ""
    assert calls["draft_editor"][-1]["html"] == ""


def test_normal_edit_still_commits_widget_to_durable(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY

    session: dict = {}
    monkeypatch.setattr(st, "session_state", session)
    session[WRITING_DESK_DRAFT_WIDGET_KEY] = {"html": "<p>Gépelt HTML</p>"}
    writing_desk_ui.commit_writing_desk_draft_from_widget()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == "<p>Gépelt HTML</p>"


def test_widget_dict_commits_sanitized_html_to_durable(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY, set_writing_desk_extract

    session: dict = {}
    set_writing_desk_extract(
        session,
        "theology",
        content="Rövid teológiai kivonat.",
        source_fingerprint="abc",
    )
    monkeypatch.setattr(st, "session_state", session)
    session[WRITING_DESK_DRAFT_WIDGET_KEY] = {
        "html": '<p style="color:red">Gépelt <strong>HTML</strong></p>'
    }
    writing_desk_ui.commit_writing_desk_draft_from_widget()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == (
        "<p>Gépelt <strong>HTML</strong></p>"
    )
    assert (
        session[WRITING_DESK_KEY]["extracts"]["theology"]["content"]
        == "Rövid teológiai kivonat."
    )


def test_legacy_string_widget_state_still_commits(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY

    session: dict = {}
    monkeypatch.setattr(st, "session_state", session)
    session[WRITING_DESK_DRAFT_WIDGET_KEY] = "4A string jegyzet"
    writing_desk_ui.commit_writing_desk_draft_from_widget()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == "4A string jegyzet"


def test_replace_writing_desk_draft_content_triggers_revision_resync(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY

    session: dict = {}
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell()
    revision_before = calls["draft_editor"][-1]["revision"]

    writing_desk_ui.replace_writing_desk_draft_content(
        "<p>Teljes kifejtett vázlat a 4C-hez.</p>"
    )
    writing_desk_ui.render_writing_desk_shell()
    assert session[WRITING_DESK_KEY]["draft"]["content"] == (
        "<p>Teljes kifejtett vázlat a 4C-hez.</p>"
    )
    assert calls["draft_editor"][-1]["html"] == (
        "<p>Teljes kifejtett vázlat a 4C-hez.</p>"
    )
    assert calls["draft_editor"][-1]["revision"] == revision_before + 1
    assert WRITING_DESK_DRAFT_RESYNC_FLAG not in session


def test_valid_extract_is_shown_and_does_not_call_llm(monkeypatch):
    import streamlit as st

    from writing_desk_extracts import current_extract_fingerprint
    from writing_desk_data import set_writing_desk_extract

    session = {
        "history": "TELJES kortörténeti forrásanyag a projekthez.",
        "last_igehely": "Jn 3,16",
        "passage_text": "Mert úgy szerette Isten a világot.",
    }
    set_writing_desk_extract(
        session,
        "history",
        content="Rövid, használható kortörténeti megállapítás.",
        source_fingerprint=current_extract_fingerprint(session, "history"),
    )
    llm_calls: list[str] = []
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell(
        generate_fn=lambda *args, **kwargs: llm_calls.append("called") or "új"
    )

    joined = _joined_markdown(calls)
    assert "Rövid, használható kortörténeti megállapítás." in joined
    assert "Kivonat készítése" not in [label for label, _key in calls["buttons"]]
    assert llm_calls == []
    assert calls["rerun"] == []


def test_missing_source_shows_cultural_empty_state_without_llm(monkeypatch):
    import streamlit as st

    llm_calls: list[str] = []
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st, {})
    writing_desk_ui.render_writing_desk_shell(
        generate_fn=lambda *args, **kwargs: llm_calls.append("called") or "új"
    )

    captions = "\n".join(calls["caption"])
    assert "Ehhez a projekthez még nincs elkészített eredeti szöveges elemzés." in captions
    assert "Ehhez a projekthez még nincs elkészített kortörténeti elemzés." in captions
    assert "Ehhez a projekthez még nincs elkészített teológiai elemzés." in captions
    assert calls["buttons"] == []
    assert llm_calls == []


def test_stale_extract_is_refreshable_and_not_shown_as_valid(monkeypatch):
    import streamlit as st

    from writing_desk_data import fingerprint_source_text, set_writing_desk_extract
    from writing_desk_extracts import STATUS_STALE, inspect_writing_desk_extract

    session = {"theology": "ÚJ teológiai forrásanyag."}
    set_writing_desk_extract(
        session,
        "theology",
        content="Régi teológiai kivonat, ne ezt mutasd érvényesként.",
        source_fingerprint=fingerprint_source_text("régi forrás"),
    )
    assert inspect_writing_desk_extract(session, "theology").status == STATUS_STALE

    llm_calls: list[str] = []
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell(
        generate_fn=lambda *args, **kwargs: llm_calls.append("called") or "új"
    )

    joined = _joined_markdown(calls)
    assert "Régi teológiai kivonat, ne ezt mutasd érvényesként." not in joined
    assert "A forrásanyag megváltozott" in calls["caption"]
    assert ("Kivonat frissítése", "writing_desk_extract_refresh_theology") in calls["buttons"]
    assert llm_calls == []


def test_leftover_lk15_theology_is_not_shown_on_jn316(monkeypatch):
    import streamlit as st

    from writing_desk_data import set_writing_desk_extract
    from writing_desk_extracts import current_extract_fingerprint

    lk = {
        "last_igehely": "Lk 15,11–24",
        "passage_text": "Egy embernek volt két fia.",
        "theology": (
            "Az elébesiető Atya ünneppel fogadja a hazatérő fiút: "
            "a halott él, az elveszett megtaláltatott."
        ),
    }
    set_writing_desk_extract(
        lk,
        "theology",
        content="Lk 15 teológiai kivonat, ne ezt mutasd Jn 3,16-ként.",
        source_fingerprint=current_extract_fingerprint(lk, "theology"),
    )
    session = dict(lk)
    session["last_igehely"] = "Jn 3,16"
    session["passage_text"] = "Mert úgy szerette Isten a világot."
    llm_calls: list[str] = []
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell(
        generate_fn=lambda *args, **kwargs: llm_calls.append("called") or "új"
    )
    joined = _joined_markdown(calls)
    assert "Lk 15 teológiai kivonat" not in joined
    assert "A forrásanyag megváltozott" in calls["caption"]
    assert llm_calls == []


def test_page_load_does_not_generate_extracts_automatically(monkeypatch):
    import streamlit as st

    session = {
        "original_text": "Van forrás, de még nincs kivonat.",
        "history": "Van kortörténet is.",
        "theology": "Van teológia is.",
    }
    llm_calls: list[str] = []
    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell(
        generate_fn=lambda *args, **kwargs: llm_calls.append("called") or "új"
    )

    labels = [label for label, _key in calls["buttons"]]
    assert labels == ["Kivonat készítése", "Kivonat készítése", "Kivonat készítése"]
    assert llm_calls == []
    assert calls["rerun"] == []


def test_generate_button_calls_llm_only_for_clicked_card(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY

    session = {
        "original_text": "Eredeti forrás mondatokkal.",
        "history": "Kortörténeti forrás mondatokkal.",
        "theology": "Teológiai forrás mondatokkal.",
    }
    llm_calls: list[str] = []

    def _generate(prompt, **kwargs):
        llm_calls.append(prompt)
        return "Egy rövid, használható kivonatmondat."

    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(
        monkeypatch,
        st,
        session,
        click_key="writing_desk_extract_generate_history",
    )
    writing_desk_ui.render_writing_desk_shell(generate_fn=_generate)

    assert len(llm_calls) == 1
    assert "Kortörténet" in llm_calls[0]
    assert session[WRITING_DESK_KEY]["extracts"]["history"]["content"] == (
        "Egy rövid, használható kivonatmondat."
    )
    assert session[WRITING_DESK_KEY]["extracts"]["original_text"]["content"] == ""
    assert session[WRITING_DESK_KEY]["extracts"]["theology"]["content"] == ""
    assert calls["rerun"] == [True]


def test_output_limit_ui_does_not_show_partial_as_valid_extract(monkeypatch):
    import streamlit as st

    from writing_desk_data import WRITING_DESK_KEY
    from writing_desk_extracts import (
        EXTRACT_INCOMPLETE_MESSAGE,
        extract_error_session_key,
    )

    partial = (
        "Az ἀσώτως (asótós) határozószó nem csupán a tékozló pénzszórásra utal, "
        "hanem egy olyan mértéktelen élet"
    )
    truncated = (
        f"{partial}\n\n---\n\n"
        "> ⚠️ **A válasz a modell kimeneti korlátjánál megszakadt.** "
        "Kérlek, próbáld újra vagy bontsd kisebb részekre a kérést; "
        "részletekért használd a **finomítás chatet**."
    )
    session = {
        "original_text": "Eredeti forrás mondatokkal.",
        "history": "Kortörténeti forrás mondatokkal.",
        "theology": "Teológiai forrás mondatokkal.",
    }

    monkeypatch.setattr(writing_desk_ui, "_render_scripture_block", lambda: None)
    calls = _patch_streamlit_shell(
        monkeypatch,
        st,
        session,
        click_key="writing_desk_extract_generate_history",
    )
    writing_desk_ui.render_writing_desk_shell(
        generate_fn=lambda *args, **kwargs: truncated
    )

    assert session[WRITING_DESK_KEY]["extracts"]["history"]["content"] == ""
    assert (
        session[extract_error_session_key("history")] == EXTRACT_INCOMPLETE_MESSAGE
    )
    assert partial not in _joined_markdown(calls)
    assert calls["rerun"] == [True]

    calls2 = _patch_streamlit_shell(monkeypatch, st, session)
    writing_desk_ui.render_writing_desk_shell(
        generate_fn=lambda *args, **kwargs: truncated
    )
    joined = _joined_markdown(calls2)
    assert partial not in joined
    assert "A kivonat most nem készült el" in joined
    assert EXTRACT_INCOMPLETE_MESSAGE in joined
    assert (
        "Kivonat készítése",
        "writing_desk_extract_generate_history",
    ) in calls2["buttons"]


def test_draft_editor_toolbar_has_exactly_the_requested_commands():
    html = (
        Path(__file__).resolve().parents[1]
        / "components"
        / "writing_desk_draft_editor"
        / "frontend"
        / "index.html"
    ).read_text(encoding="utf-8")
    js = (
        Path(__file__).resolve().parents[1]
        / "components"
        / "writing_desk_draft_editor"
        / "frontend"
        / "main.js"
    ).read_text(encoding="utf-8")
    commands = re.findall(r'data-cmd="([^"]+)"', html)
    aligns = re.findall(r'data-align="([^"]+)"', html)
    css = (
        Path(__file__).resolve().parents[1]
        / "components"
        / "writing_desk_draft_editor"
        / "frontend"
        / "style.css"
    ).read_text(encoding="utf-8")
    assert commands == [
        "bold",
        "italic",
        "underline",
        "insertUnorderedList",
        "insertOrderedList",
        "undo",
        "redo",
    ]
    assert aligns == ["left", "center", "right", "justify"]
    assert "<svg" in html
    assert ">Bold<" not in html
    assert ">Undo<" not in html
    assert "position: sticky" in css
    assert "heading" not in html.casefold()
    assert "font" not in html.casefold()
    assert "tiptap" not in js.casefold()
    assert "prosemirror" not in js.casefold()
    assert "quill" not in js.casefold()
    assert "tinymce" not in js.casefold()
    assert "lastRevision === null" in js or "revision !== lastRevision" in js
    assert "applyTextAlign" in js
    assert "text-align" in js


def test_draft_editor_ccv2_registers_frontend_payload(monkeypatch):
    import importlib

    import streamlit as st

    import components.writing_desk_draft_editor as editor_mod

    captured: dict[str, str] = {}
    real_factory = st.components.v2.component

    def spy_factory(name, **kwargs):
        if name == "writing_desk_draft_editor":
            captured["name"] = name
            captured["html"] = kwargs.get("html") or ""
            captured["css"] = kwargs.get("css") or ""
            captured["js"] = kwargs.get("js") or ""
        return real_factory(name, **kwargs)

    monkeypatch.setattr(st.components.v2, "component", spy_factory)
    reloaded = importlib.reload(editor_mod)
    reloaded._component()
    monkeypatch.setattr(
        writing_desk_ui, "writing_desk_draft_editor", reloaded.writing_desk_draft_editor
    )
    try:
        assert captured["name"] == "writing_desk_draft_editor"
        assert 'contenteditable="true"' in captured["html"]
        assert 'data-cmd="bold"' in captured["html"]
        assert 'data-align="justify"' in captured["html"]
        assert "<svg" in captured["html"]
        assert ".wd-draft-surface" in captured["css"]
        assert "min-height: 650px" in captured["css"]
        assert "min-height: 700px" in captured["css"]
        assert "position: sticky" in captured["css"]
        assert "setStateValue" in captured["js"]
        assert "revision" in captured["js"]
    finally:
        importlib.reload(editor_mod)


def _render_writing_desk_john_compact() -> None:
    import streamlit as st

    from bible_engine.greek_analysis_ui import load_john_3_16_tokens
    import bible_engine.greek_analysis_ui as greek_ui

    real_panel = greek_ui._render_analysis_panel
    real_loader = greek_ui.load_greek_passage_tokens
    real_tbesg = greek_ui.load_tbesg_lexicon_entry
    real_factory = st.components.v2.component

    def spy_panel(selected, lexicon_entries, tbesg_lexicon_loader, *, key_prefix, display_mode="full"):
        st.session_state["_writing_desk_analysis_display_mode"] = display_mode
        st.session_state["_writing_desk_analysis_key_prefix"] = key_prefix
        st.session_state["_writing_desk_analysis_form"] = selected.greek_form
        return real_panel(
            selected,
            lexicon_entries,
            tbesg_lexicon_loader,
            key_prefix=key_prefix,
            display_mode=display_mode,
        )

    def spy_factory(name, **kwargs):
        renderer = real_factory(name, **kwargs)

        def mounted(*args, **mount_kwargs):
            if name == "greek_token_selector":
                st.session_state["_writing_desk_token_selector_key"] = mount_kwargs.get("key")
            return renderer(*args, **mount_kwargs)

        return mounted

    greek_ui.load_greek_passage_tokens = lambda reference: load_john_3_16_tokens()
    greek_ui.load_tbesg_lexicon_entry = lambda _strong_id: None
    greek_ui._render_analysis_panel = spy_panel
    st.components.v2.component = spy_factory
    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["passage_text"] = "16. Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"
    import writing_desk_ui
    try:
        writing_desk_ui.render_writing_desk_shell()
    finally:
        greek_ui.load_greek_passage_tokens = real_loader
        greek_ui.load_tbesg_lexicon_entry = real_tbesg
        greek_ui._render_analysis_panel = real_panel
        st.components.v2.component = real_factory


def _render_writing_desk_ot_compact() -> None:
    import streamlit as st

    real_factory = st.components.v2.component

    def spy_factory(name, **kwargs):
        renderer = real_factory(name, **kwargs)

        def mounted(*args, **mount_kwargs):
            if name == "hebrew_token_selector":
                st.session_state["_writing_desk_hebrew_token_selector_key"] = mount_kwargs.get(
                    "key"
                )
            return renderer(*args, **mount_kwargs)

        return mounted

    st.components.v2.component = spy_factory
    st.session_state["last_igehely"] = "Zsolt 23,1"
    st.session_state["passage_text"] = "1. Az Úr az én pásztorom."
    import writing_desk_ui
    try:
        writing_desk_ui.render_writing_desk_shell()
    finally:
        st.components.v2.component = real_factory


def _page_text(app: AppTest) -> str:
    text = "\n".join(markdown.value for markdown in app.markdown)
    text += "\n".join(caption.value for caption in app.caption)
    return text


def test_writing_desk_compact_reaches_real_greek_analysis_panel() -> None:
    app = AppTest.from_function(_render_writing_desk_john_compact).run()

    assert not app.exception
    assert app.session_state["_writing_desk_analysis_display_mode"] == "compact"
    assert (
        app.session_state["_writing_desk_analysis_key_prefix"]
        == WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX
    )
    page_text = _page_text(app)
    assert "textus-greek-compact-card-marker" in page_text
    assert "Magyar lexikai jelentések" not in page_text
    assert "Ellenőrzési állapot" not in page_text
    assert "Konkordancia" not in page_text
    assert not any("Alternatív szóválasztás" in expander.label for expander in app.expander)


def test_writing_desk_token_selector_uses_isolated_stable_key() -> None:
    app = AppTest.from_function(_render_writing_desk_john_compact).run()

    assert not app.exception
    assert (
        app.session_state["_writing_desk_token_selector_key"]
        == f"{WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX}_inline_token_selector"
    )
    assert "bible_text_ui" not in app.session_state["_writing_desk_token_selector_key"]
    assert "textus_original_language" not in app.session_state["_writing_desk_token_selector_key"]


def test_writing_desk_token_selection_reaches_compact_analysis_panel() -> None:
    from bible_engine.greek_analysis_ui import load_john_3_16_tokens

    app = AppTest.from_function(_render_writing_desk_john_compact).run()
    assert not app.exception
    assert "οὕτως" in (app.session_state["_writing_desk_analysis_form"] or "")

    tokens = load_john_3_16_tokens()
    chosen = next(token for token in tokens if token.word_index == 3)
    app.session_state[f"{WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX}_selected_token_key"] = (
        f"{chosen.book}:{chosen.chapter}:{chosen.verse}:{chosen.word_index}"
    )
    app.run()

    assert not app.exception
    assert app.session_state["_writing_desk_analysis_form"] == chosen.greek_form
    assert app.session_state["_writing_desk_analysis_display_mode"] == "compact"
    page_text = _page_text(app)
    assert chosen.greek_form in page_text
    assert "Magyar lexikai jelentések" not in page_text
    assert not any("Alternatív szóválasztás" in expander.label for expander in app.expander)


def test_writing_desk_hebrew_compact_path_keeps_isolated_key() -> None:
    app = AppTest.from_function(_render_writing_desk_ot_compact).run()

    assert not app.exception
    assert (
        app.session_state["_writing_desk_hebrew_token_selector_key"]
        == f"{WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX}_inline_token_selector"
    )
    page_text = _page_text(app)
    assert "textus-hebrew-compact-card-marker" in page_text
    assert "Technikai morfológiai részletek" not in page_text
    assert "Forrás és licenc" not in page_text
    assert not any("Alternatív szóválasztás" in expander.label for expander in app.expander)


def _render_desk_with_main_view_switcher() -> None:
    """Íróasztal + valódi főnézet-váltó — a smoke útvonal AppTestje."""
    import streamlit as st

    import writing_desk_ui as wd
    from workshop_nav_ui import render_workspace_switcher

    original_scripture = wd._render_scripture_block
    wd._render_scripture_block = lambda: None
    try:
        st.session_state.setdefault("ui_mode", wd.WRITING_DESK_MODE)
        wd.flush_writing_desk_draft_from_widget()
        render_workspace_switcher(
            options=["workshop", "sermon_workshop", wd.WRITING_DESK_MODE],
            labels={
                "workshop": "Textusműhely",
                "sermon_workshop": "Igehirdetési műhely",
                wd.WRITING_DESK_MODE: wd.WRITING_DESK_LABEL,
            },
            key="ui_mode",
        )
        if st.session_state.get("ui_mode") == wd.WRITING_DESK_MODE:
            wd.render_writing_desk_shell()
            st.stop()
        st.markdown("Textusműhely")
    finally:
        wd._render_scripture_block = original_scripture


def test_draft_survives_textusmuhely_round_trip_via_switcher() -> None:
    from writing_desk_data import WRITING_DESK_KEY

    app = AppTest.from_function(_render_desk_with_main_view_switcher).run(timeout=60)
    assert not app.exception
    assert app.session_state["ui_mode"] == WRITING_DESK_MODE

    app.session_state[WRITING_DESK_DRAFT_WIDGET_KEY] = {
        "html": "<p>Íróasztal jegyzet</p><p>második bekezdés</p>"
    }
    app.run(timeout=60)
    assert not app.exception
    assert app.session_state[WRITING_DESK_KEY]["draft"]["content"] == (
        "<p>Íróasztal jegyzet</p><p>második bekezdés</p>"
    )

    app.button(key="tx_mainnav_workshop").click().run()
    assert not app.exception
    assert app.session_state["ui_mode"] == "workshop"
    assert app.session_state[WRITING_DESK_KEY]["draft"]["content"] == (
        "<p>Íróasztal jegyzet</p><p>második bekezdés</p>"
    )
    # Az élő app a nem renderelt CCv2 kulcsát eldobja; az AppTest
    # megtartja. A production unmountot így szimuláljuk a visszatérés előtt.
    del app.session_state[WRITING_DESK_DRAFT_WIDGET_KEY]

    app.button(key="tx_mainnav_writing_desk").click().run()
    assert not app.exception
    assert app.session_state["ui_mode"] == WRITING_DESK_MODE
    visible = draft_visible_text(
        writing_desk_draft_widget_html(
            app.session_state[WRITING_DESK_DRAFT_WIDGET_KEY]
        )
    )
    assert "Íróasztal jegyzet" in visible
    assert "második bekezdés" in visible
    assert app.session_state[WRITING_DESK_KEY]["draft"]["content"] == (
        "<p>Íróasztal jegyzet</p><p>második bekezdés</p>"
    )


def _render_desk_new_work_live_order() -> None:
    """Íróasztal → Új munka sorrend: pending apply, flush, editor, majd clear+rerun."""
    import streamlit as st

    import app as app_mod
    import writing_desk_ui as wd

    original_scripture = wd._render_scripture_block
    wd._render_scripture_block = lambda: None
    try:
        st.session_state.setdefault("ui_mode", wd.WRITING_DESK_MODE)
        if st.session_state.pop("_wd_smoke_do_new_work", False):
            app_mod._clear_workspace_content()
            st.session_state["_wd_smoke_inject_stale_widget"] = True
            st.rerun()
        if st.session_state.pop("_wd_smoke_inject_stale_widget", False):
            st.session_state[wd.WRITING_DESK_DRAFT_WIDGET_KEY] = {
                "html": "<p>Előző dokumentum a CCv2-ből</p>"
            }
            wd._on_writing_desk_draft_change()
        if st.session_state.get("_pending_project_widget_sync"):
            app_mod._apply_pending_project_widget_sync()
        wd.flush_writing_desk_draft_from_widget()
        if st.session_state.get("ui_mode") == wd.WRITING_DESK_MODE:
            wd.render_writing_desk_shell()
    finally:
        wd._render_scripture_block = original_scripture


def test_apptest_new_work_clears_editor_despite_stale_ccv2_state() -> None:
    from writing_desk_data import WRITING_DESK_KEY

    app = AppTest.from_function(_render_desk_new_work_live_order).run(timeout=60)
    assert not app.exception

    app.session_state[WRITING_DESK_DRAFT_WIDGET_KEY] = {
        "html": "<p>Előző dokumentum a CCv2-ből</p>"
    }
    app.run(timeout=60)
    assert not app.exception
    assert app.session_state[WRITING_DESK_KEY]["draft"]["content"] == (
        "<p>Előző dokumentum a CCv2-ből</p>"
    )
    revision_before = 0
    if WRITING_DESK_DRAFT_REVISION_KEY in app.session_state:
        revision_before = int(app.session_state[WRITING_DESK_DRAFT_REVISION_KEY] or 0)

    app.session_state["_wd_smoke_do_new_work"] = True
    app.run(timeout=60)
    assert not app.exception
    # st.rerun() a clear után: a stale inject a következő futáson érvényesül.
    app.run(timeout=60)
    assert not app.exception
    assert app.session_state[WRITING_DESK_KEY]["draft"]["content"] == ""
    widget = {"html": ""}
    if WRITING_DESK_DRAFT_WIDGET_KEY in app.session_state:
        widget = app.session_state[WRITING_DESK_DRAFT_WIDGET_KEY]
    visible = draft_visible_text(writing_desk_draft_widget_html(widget))
    assert "Előző dokumentum" not in visible
    assert WRITING_DESK_DRAFT_RESYNC_FLAG not in app.session_state
    revision_after = 0
    if WRITING_DESK_DRAFT_REVISION_KEY in app.session_state:
        revision_after = int(app.session_state[WRITING_DESK_DRAFT_REVISION_KEY] or 0)
    assert revision_after == revision_before + 1
